import hashlib
import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from stb_reader.exceptions import AuthError, STBError

from .db import (
    count_vod_content,
    delete_vod_content_rows,
    get_content_hashes,
    get_sync_state,
    get_vod_content,
    remove_from_library,
    set_sync_state,
    upsert_vod_category,
    upsert_vod_content,
    upsert_vod_content_category,
)

log = logging.getLogger(__name__)


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _content_changed(old: dict, new_name: str, new_year: str) -> bool:
    return (
        _similar(old["name"], new_name) < 0.75
        or _similar(old["year"], new_year) < 0.75
    )


def _content_hash(row: dict) -> str:
    key = f"{row['name']}|{row['year']}|{row['cmd']}|{row['genres']}|{row['rating']}|{row['is_series']}"
    return hashlib.md5(key.encode()).hexdigest()


def _delete_strm_files(paths: list[str]) -> None:
    for p in paths:
        path = Path(p)
        path.unlink(missing_ok=True)
        for parent in [path.parent, path.parent.parent]:
            try:
                parent.rmdir()
            except OSError:
                break


def _build_content_row(item: dict) -> dict:
    genres = item.get("genres_str", item.get("genres", ""))
    if isinstance(genres, list):
        genres = json.dumps(genres)
    row = {
        "content_id": str(item["id"]),
        "name": item.get("name", ""),
        "cmd": item.get("cmd", ""),
        "screenshot_uri": item.get("screenshot_uri", ""),
        "genres": genres,
        "year": str(item.get("year", "")),
        "description": item.get("description", ""),
        "rating": str(item.get("rating_imdb", "")),
        "duration": item.get("time"),
        "is_series": 1 if int(item.get("is_series") or 0) else 0,
        "fav": int(bool(item.get("fav", False))),
        "for_rent": int(bool(item.get("for_rent", False))),
        "lock": int(bool(item.get("lock", False))),
        "portal_raw": json.dumps(item),
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }
    row["content_hash"] = _content_hash(row)
    return row


def run_portal_sync(
    db: sqlite3.Connection,
    lock: threading.Lock,
    vod,
    output_dir: str,
    delay_ms: int,
    max_pages: int,
    early_stop_pages: int = 3,
    full_sync_days: int = 7,
) -> None:
    """Walk the portal and populate vod_content. Blocking — run via asyncio.to_thread."""
    t0 = time.monotonic()
    log.info("vod_sync.started", extra={"max_pages": max_pages, "delay_ms": delay_ms})

    with lock:
        prev_state = get_sync_state(db)
        set_sync_state(
            db,
            last_sync_status="running",
            last_sync_started_at=datetime.now(timezone.utc).isoformat(),
            last_sync_finished_at=None,
            error_message=None,
        )

    try:
        _run_sync(db, lock, vod, output_dir, delay_ms, max_pages, t0, early_stop_pages, full_sync_days, prev_state)
    except AuthError as exc:
        log.error("vod_sync.auth_failed", extra={"error": str(exc)})
        with lock:
            set_sync_state(db, last_sync_status="failed", error_message=str(exc))
        raise
    except Exception as exc:
        log.error("vod_sync.failed", extra={"error": str(exc)})
        with lock:
            set_sync_state(db, last_sync_status="failed", error_message=str(exc))
        raise


def _run_sync(
    db: sqlite3.Connection,
    lock: threading.Lock,
    vod,
    output_dir: str,
    delay_ms: int,
    max_pages: int,
    t0: float,
    early_stop_pages: int,
    full_sync_days: int,
    prev_state: dict,
) -> None:
    delay_s = delay_ms / 1000.0
    seen_ids: set[str] = set()

    # --- Determine effective early-stop threshold ---
    # Force a full sync periodically to catch deleted content.
    effective_early_stop = early_stop_pages
    if full_sync_days > 0:
        last_full = prev_state.get("last_full_sync_at")
        if last_full is None:
            effective_early_stop = 0
            log.info("vod_sync.full_sync_forced", extra={"reason": "no_previous_full_sync"})
        else:
            last_full_dt = datetime.fromisoformat(last_full)
            age_days = (datetime.now(timezone.utc) - last_full_dt).days
            if age_days >= full_sync_days:
                effective_early_stop = 0
                log.info("vod_sync.full_sync_forced", extra={"reason": "scheduled", "age_days": age_days})

    # --- Determine resume page ---
    prev_status = prev_state.get("last_sync_status", "idle")
    prev_page = prev_state.get("last_synced_page", 0) or 0
    if prev_status in ("running", "failed") and prev_page > 0:
        start_page = prev_page + 1
        log.info("vod_sync.resuming", extra={"from_page": start_page})
    else:
        start_page = 1
        with lock:
            set_sync_state(db, last_synced_page=0)

    # --- Phase 1: fetch categories ---
    categories = vod.get_categories()
    with lock:
        for cat in categories:
            upsert_vod_category(db, cat.id, cat.title, cat.alias)
        db.commit()
    log.info("vod_sync.categories_fetched", extra={"count": len(categories)})

    # --- Phase 2: fetch all content via category="*" ---
    page = start_page
    total_pages = None
    consecutive_stable_pages = 0
    early_stopped = False

    while True:
        if delay_s > 0:
            time.sleep(delay_s)
        try:
            result = vod.get_content(category_id="*", page=page)
        except AuthError:
            raise
        except STBError as exc:
            log.warning("vod_sync.page_error", extra={"page": page, "error": str(exc)})
            page += 1
            if total_pages is not None and page > total_pages:
                break
            if max_pages > 0 and page > max_pages:
                break
            continue

        if total_pages is None:
            per_page = result.per_page or 1
            total_pages = max(1, -(-result.total // per_page))  # ceiling division

        page_ids: list[str] = []
        rows_to_upsert: list[tuple[dict, str, str]] = []

        for item in result.items:
            row = _build_content_row(vars(item) if hasattr(item, "__dict__") else item)
            rows_to_upsert.append((row, row["name"], row["year"]))

        incoming_ids = [row["content_id"] for row, _, _ in rows_to_upsert]
        incoming_hashes = {row["content_id"]: row["content_hash"] for row, _, _ in rows_to_upsert}

        with lock:
            # Snapshot stored hashes before upserting so early-stop compares old vs new
            pre_upsert_hashes = get_content_hashes(db, incoming_ids)
            for row, new_name, new_year in rows_to_upsert:
                existing = get_vod_content(db, row["content_id"])
                if existing and existing["in_library"] and _content_changed(existing, new_name, new_year):
                    log.warning(
                        "vod_sync.content_changed",
                        extra={
                            "content_id": row["content_id"],
                            "old_name": existing["name"],
                            "new_name": new_name,
                        },
                    )
                    paths = remove_from_library(db, row["content_id"])
                    _delete_strm_files(paths)
                upsert_vod_content(db, row)
                page_ids.append(row["content_id"])
            set_sync_state(db, last_synced_page=page)
            db.commit()

        seen_ids.update(page_ids)
        log.info("vod_sync.page", extra={"page": page, "page_count": len(page_ids), "cumulative": len(seen_ids)})

        # --- Early-stop check ---
        if effective_early_stop > 0 and page_ids:
            page_stable = all(
                pre_upsert_hashes.get(cid) == incoming_hashes[cid]
                for cid in page_ids
            )
            if page_stable:
                consecutive_stable_pages += 1
                if consecutive_stable_pages >= effective_early_stop:
                    early_stopped = True
                    log.info(
                        "vod_sync.early_stop",
                        extra={"page": page, "stable_pages": consecutive_stable_pages},
                    )
                    break
            else:
                consecutive_stable_pages = 0

        if max_pages > 0 and page >= max_pages:
            break
        if page >= total_pages:
            break
        page += 1

    # --- Phase 3: category associations (full sync only) ---
    if max_pages == 0 and not early_stopped:
        for cat in categories:
            cat_page = 1
            cat_total_pages = None
            while True:
                if delay_s > 0:
                    time.sleep(delay_s)
                try:
                    result = vod.get_content(category_id=cat.id, page=cat_page)
                except AuthError:
                    raise
                except STBError as exc:
                    log.warning(
                        "vod_sync.category_page_error",
                        extra={"category_id": cat.id, "page": cat_page, "error": str(exc)},
                    )
                    break

                if cat_total_pages is None:
                    per_page = result.per_page or 1
                    cat_total_pages = max(1, -(-result.total // per_page))

                with lock:
                    for item in result.items:
                        content_id = str(item.id)
                        if content_id in seen_ids:
                            upsert_vod_content_category(db, content_id, cat.id)
                    db.commit()

                if cat_page >= cat_total_pages:
                    break
                cat_page += 1

        # --- Phase 4: stale content cleanup ---
        stale_ids = [
            r[0]
            for r in db.execute(
                "SELECT content_id FROM vod_content WHERE content_id NOT IN ({})".format(
                    ",".join("?" * len(seen_ids))
                ),
                list(seen_ids),
            ).fetchall()
        ] if seen_ids else []

        if stale_ids:
            log.info("vod_sync.stale_cleanup", extra={"count": len(stale_ids)})
            with lock:
                paths = delete_vod_content_rows(db, stale_ids)
            _delete_strm_files(paths)

    elapsed = time.monotonic() - t0
    content_count = len(seen_ids)

    finish_kwargs: dict = {
        "last_sync_status": "success",
        "last_sync_finished_at": datetime.now(timezone.utc).isoformat(),
        "content_count": content_count,
        "error_message": None,
        "last_synced_page": 0,
    }
    if max_pages == 0 and not early_stopped:
        finish_kwargs["last_full_sync_at"] = datetime.now(timezone.utc).isoformat()

    with lock:
        set_sync_state(db, **finish_kwargs)
    log.info("vod_sync.finished", extra={"count": content_count, "duration_s": round(elapsed, 2)})
