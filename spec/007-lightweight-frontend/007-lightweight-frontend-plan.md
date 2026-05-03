# Plan: Lightweight Media Frontend (007)

## Components

### 1. FastAPI static file serving (`server/main.py`)
Mount `server/static/` so that `GET /` serves `index.html`. One change: add a `StaticFiles` mount after the existing routers. Must not break the existing `/health`, `/vod/*`, `/library/*` routes — those are registered first and take precedence.

### 2. Frontend HTML file (`server/static/index.html`)
Single self-contained file. Three logical sections:

| Section | Responsibility |
|---------|---------------|
| **State** | JS module-level variables: `libraryIds` (Set), `currentPage`, `currentQuery`, `currentFilter` |
| **API layer** | `fetchLibrary()`, `search(page)`, `addToLibrary(id)`, `removeFromLibrary(id)` — all `async`, all surface errors |
| **Render layer** | `renderResults(items, total, page, pageSize)`, `renderPagination(...)`, `updateItemButton(id, inLibrary)` |

### 3. Library state strategy
On page load, call `GET /library` and populate a `Set<content_id>`. Search results cross-reference this set to decide Add vs Remove. After each add/remove, update the set and re-render only the affected row's button (no full re-render). This avoids re-fetching after every action.

---

## Implementation Order

Steps must be sequential — each builds on the previous.

```
1. Server change    → add StaticFiles mount to main.py
2. HTML skeleton    → bare page loads at /
3. Search           → query + filter + results table (FR-1, FR-2, FR-5)
4. Library state    → load on startup, Add/Remove buttons (FR-3, FR-4)
5. Pagination       → prev/next controls (FR-6)
6. UX polish        → loading indicator, error display (FR-7, FR-8)
7. Docs update      → AGENTS.md
```

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `StaticFiles` mount at `/` intercepts API routes | Register all API routers before the static mount; FastAPI matches routes in registration order |
| `GET /library` returns large list on page load | Acceptable for a home-lab tool; library size is bounded |
| `search_vod_content` returns `in_library` already in the row | Confirmed — `vod_content` has `in_library` column included in `SELECT *`; we can use it directly instead of the cross-reference set if present |

---

## Verification Checkpoints

After step 1: `pytest` passes, `GET /` returns 200.  
After step 3: search returns results in browser, filter toggles work.  
After step 4: Add/Remove buttons reflect library state, clicking updates in-place.  
After step 5: Pagination controls appear and navigate correctly.  
After step 6: Loading spinner visible during slow fetches, error message shown on 503.  
After step 7: `pytest` still passes, AGENTS.md reflects new route.
