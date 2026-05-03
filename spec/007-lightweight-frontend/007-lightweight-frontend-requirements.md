# Spec: Lightweight Media Frontend (007)

## Objective

Build a minimal single-page web UI served by the existing FastAPI server that lets a user search the VOD catalogue, see which items are already in their library, and add or remove items — without leaving the browser. No build tools, no JS framework, no bundler.

The user is a developer or home-lab operator running this locally or over LAN. Success means they can stop using `curl` to manage their library.

---

## User Stories

- As a user, I want to type a query and see matching VOD titles so I can find content quickly.
- As a user, I want to see whether a result is already in my library so I don't add duplicates.
- As a user, I want to add a search result to my library with one click.
- As a user, I want to remove an item from my library with one click.
- As a user, I want to filter search results to movies only or series only.

---

## Functional Requirements

- **FR-1** A search input accepts free-text and submits to `GET /vod/search?query=…`.
- **FR-2** Results list shows: title, year, genres, rating, duration, is_series flag (movie vs series), and in-library status.
- **FR-3** Each result has an **Add** button (disabled / hidden when already in library) that calls `POST /library/add/{content_id}` and updates the UI.
- **FR-4** Each result has a **Remove** button (shown only when in library) that calls `DELETE /library/{content_id}` and updates the UI.
- **FR-5** A filter control (All / Movies / Series) narrows results via the `is_series` query param.
- **FR-6** The page shows a loading indicator while a fetch is in progress.
- **FR-7** Errors from the API (4xx / 5xx) are surfaced inline in the UI (not just console).
- **FR-8** The frontend is served at `GET /` by the FastAPI app (static file or inline template).

---

## Non-Functional Requirements

- **NFR-1** Zero build step — plain `.html` + optional inline `<style>` and `<script>`.
- **NFR-2** No external JS or CSS CDN dependencies (works offline / air-gapped).
- **NFR-3** The full UI fits in a single HTML file.
- **NFR-4** The file is served via FastAPI's `StaticFiles` mount or a dedicated route — no new server process.

---

## Out of Scope

- Browsing library contents (separate from search results)
- Pagination controls (first page of results is sufficient for MVP)
- Authentication / login UI
- Mobile-responsive design optimisation
- Thumbnail / poster images
- Live TV tab

---

## Assumptions

- The API runs on the same origin as the frontend (no CORS needed).
- `in_library` status for search results is derived by cross-referencing `GET /library` once on page load and after each add/remove.
- The server's `GET /vod/search` returns a `{"items": [...], "total": N}` envelope; each item has `content_id`, `name`, `year`, `genres`, `rating`, `duration`, `is_series`, `in_library` fields.

---

## Tech Stack

- **HTML5** — single file: `server/static/index.html`
- **Vanilla JS (ES2020)** — `fetch` API, no transpilation
- **Inline CSS** — no external stylesheet

---

## Commands

```
Start server:  uvicorn server.main:app --reload
Open UI:       http://localhost:8000/
Run tests:     pytest
```

---

## Project Structure

```
server/
  static/
    index.html     ← entire frontend (HTML + CSS + JS)
  main.py          ← mounts StaticFiles("/", directory="server/static")
```

---

## Code Style

Single HTML file. JS is written as a plain script block at the bottom of `<body>`. No classes for UI state — use simple functions and direct DOM manipulation. Async/await for all `fetch` calls.

```js
async function search() {
  const q = document.getElementById('query').value.trim();
  if (!q) return;
  const res = await fetch(`/vod/search?query=${encodeURIComponent(q)}&page_size=50`);
  if (!res.ok) { showError(await res.text()); return; }
  const { items } = await res.json();
  renderResults(items);
}
```

---

## Testing Strategy

No automated tests for the frontend (it's a single static file; the existing pytest suite covers the API). Manual acceptance testing against a running server is sufficient for this scope.

---

## Boundaries

- **Always:** Keep the file self-contained (no external network requests); run `pytest` after changing `main.py`.
- **Ask first:** Adding a second HTML page, introducing a JS module system, adding any npm dependency.
- **Never:** Embed credentials or portal URLs in the HTML; add a separate frontend dev server.

---

## Success Criteria

1. Navigating to `http://localhost:8000/` in a browser loads the search page without errors.
2. Typing a query and pressing Enter (or a Search button) renders a list of matching results.
3. Each result correctly shows an **Add** or **Remove** button based on current library state.
4. Clicking **Add** calls the library API and the button switches to **Remove** without a page reload.
5. Clicking **Remove** calls the library API and the button switches to **Add** without a page reload.
6. Selecting "Movies" or "Series" filter re-runs the search with the appropriate `is_series` param.
7. An API error (e.g. 503 "not yet synced") displays a readable message in the UI.
8. `pytest` continues to pass after `main.py` is modified to serve the static file.

---

## Open Questions

_None — requirements are clear enough to proceed to planning._
