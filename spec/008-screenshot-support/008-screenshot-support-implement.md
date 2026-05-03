# Implementation: Screenshot Support (008)

## Tasks

- [x] Add `GET /vod/content/{content_id}/screenshot` endpoint to `server/routes/vod.py`
- [x] Add `TestScreenshot` tests to `tests/test_server.py`
- [x] Add poster thumbnail column to `server/static/index.html`
- [x] Update `AGENTS.md`

## Verification

```
pytest tests/test_server.py -k screenshot   # targeted
pytest tests/                               # full suite
```
