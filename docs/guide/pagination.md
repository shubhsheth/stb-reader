# Pagination

Methods that return lists of channels or VOD content return a `PagedResult` rather
than the full list. The portal delivers results one page at a time, so fetching
everything requires multiple calls.

---

## PagedResult fields

| Field | Type | Description |
|-------|------|-------------|
| `items` | `list[T]` | The items on this page |
| `total` | `int` | Total number of items across all pages |
| `page` | `int` | The current page number (1-indexed) |
| `per_page` | `int` | Number of items per page (set by the portal) |

```python
result = client.live_tv.get_channels(page=1)

print(result.total)    # e.g. 850  — total channels
print(result.page)     # 1         — current page
print(result.per_page) # 14        — items per page (portal-defined)
print(len(result.items))           # up to 14
```

---

## Checking if there are more pages

```python
result = client.vod.get_content(page=1)

has_more = len(result.items) > 0 and result.page * result.per_page < result.total
```

Or equivalently: you have fetched everything when the number of items collected
equals `result.total`.

---

## Fetch-all-pages pattern

Use this pattern whenever you need every item, not just the first page:

```python
def fetch_all_channels(client):
    items = []
    page = 1
    while True:
        result = client.live_tv.get_channels(genre_id="*", page=page)
        items.extend(result.items)
        if len(items) >= result.total:
            break
        page += 1
    return items

all_channels = fetch_all_channels(client)
print(f"Fetched {len(all_channels)} channels")
```

The same pattern works for VOD content:

```python
def fetch_all_content(client, category_id="*"):
    items = []
    page = 1
    while True:
        result = client.vod.get_content(category_id=category_id, page=page)
        items.extend(result.items)
        if len(items) >= result.total:
            break
        page += 1
    return items
```

---

## Lazy iteration (process page by page)

If you don't need everything in memory at once, process each page as you go:

```python
page = 1
while True:
    result = client.vod.get_content(category_id="*", page=page)
    for item in result.items:
        process(item)          # handle each item immediately
    if len(result.items) == 0 or page * result.per_page >= result.total:
        break
    page += 1
```

---

## Request pacing

Portals can be sensitive to rapid sequential requests. If you are fetching many
pages (e.g. a full VOD catalogue of thousands of items), consider adding a small
delay between requests:

```python
import time

page = 1
while True:
    result = client.vod.get_content(page=page)
    process(result.items)
    if len(result.items) == 0 or page * result.per_page >= result.total:
        break
    page += 1
    time.sleep(0.25)   # 250 ms between pages
```

The `get_episodes()` method has a built-in `delay_s` parameter for this purpose.
For channels and VOD content you manage pacing yourself.

---

## Which methods return PagedResult?

| Method | Returns |
|--------|---------|
| `client.live_tv.get_channels(...)` | `PagedResult[Channel]` |
| `client.vod.get_content(...)` | `PagedResult[Content]` |

All other methods (`get_genres`, `get_categories`, `get_seasons`, `get_episodes`,
`get_episode_files`) return plain lists and fetch all results automatically.

---

## Related

- [Live TV guide](./live-tv.md) — `get_channels()` parameters
- [VOD guide](./vod.md) — `get_content()` parameters
- [API reference](./api-reference.md) — `PagedResult` type definition
