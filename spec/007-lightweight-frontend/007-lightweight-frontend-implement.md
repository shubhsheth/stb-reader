# Tasks: Lightweight Media Frontend (007)

- [ ] **Task 1: Mount static files in FastAPI**
  - Acceptance: `GET /` returns 200 with HTML; all existing API routes still respond correctly
  - Verify: `pytest` passes; `curl http://localhost:8000/` returns HTML
  - Files: `server/main.py`, `server/static/index.html` (placeholder)

- [ ] **Task 2: Search UI (FR-1, FR-2, FR-5)**
  - Acceptance: Typing a query and submitting renders a results table with title, year, genres, rating, duration, and movie/series badge; filter buttons (All / Movies / Series) re-run the search with the correct `is_series` param
  - Verify: Manual test in browser with a real query; filter toggles change results
  - Files: `server/static/index.html`

- [ ] **Task 3: Library state + Add/Remove buttons (FR-3, FR-4)**
  - Acceptance: On search render, each row shows Add or Remove based on `in_library` from the search result; clicking Add calls `POST /library/add/{id}` and switches the button to Remove in-place; clicking Remove calls `DELETE /library/{id}` and switches to Add in-place; no full page reload on either action
  - Verify: Manual test — add an item, button flips; remove it, button flips back
  - Files: `server/static/index.html`

- [ ] **Task 4: Pagination controls (FR-6)**
  - Acceptance: Previous/Next buttons appear when `total > page_size`; current page and total count displayed; navigating fetches the correct `page` param and re-renders results; buttons are disabled at boundaries (page 1 / last page)
  - Verify: Manual test with a query that returns >50 results
  - Files: `server/static/index.html`

- [ ] **Task 5: Loading indicator + error display (FR-7, FR-8)**
  - Acceptance: A visible loading state appears during any in-flight fetch and clears on completion; API errors (4xx/5xx) render an inline message in the UI (not just console)
  - Verify: Temporarily point at a bad endpoint or disconnect server; error message appears
  - Files: `server/static/index.html`

- [ ] **Task 6: Update AGENTS.md**
  - Acceptance: AGENTS.md documents the new `GET /` route and `server/static/` directory
  - Verify: Review file for accuracy
  - Files: `AGENTS.md`
