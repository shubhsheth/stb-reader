# VOD — Movies

All VOD methods are on `client.vod`. This guide covers movies. For series
(content with `is_series=True`), see the [Series guide](./series.md).

---

## Categories

### `get_categories()`

Returns all VOD categories.

```python
categories = client.vod.get_categories()
for cat in categories:
    print(f"{cat.id}: {cat.title}")
```

**Returns:** `list[Category]`

> **Note:** Categories with adult-related titles are automatically filtered out by
> the library and will not appear in the returned list.

#### Category fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Category identifier — pass this as `category_id` to `get_content()` |
| `title` | `str` | Display name (e.g. `"Action"`, `"Drama"`) |
| `alias` | `str` | Lowercase slug (e.g. `"action"`, `"drama"`) |
| `censored` | `bool` | `True` if the category requires parental unlock on the portal |

---

## Content listing

### `get_content(category_id, page, sort, fav)`

Returns a paginated list of movies and series.

```python
result = client.vod.get_content(category_id="*", page=1)
print(f"{result.total} items total")
for item in result.items:
    print(f"  {item.name} ({item.year})")
```

**Returns:** `PagedResult[Content]`

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `category_id` | `str` | `"*"` | Category ID from `get_categories()`. Use `"*"` for all content. |
| `page` | `int` | `1` | Page number, 1-indexed |
| `sort` | `str` | `"added"` | Sort order: `"added"`, `"popular"`, `"rating"`, or `"name"` |
| `fav` | `bool` | `False` | If `True`, return only favourited items |

#### Content fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Content identifier |
| `name` | `str` | Title |
| `cmd` | `str` | Streaming command — for movies, pass to `get_stream_url()` |
| `screenshot_uri` | `str` | URL to the poster or thumbnail image |
| `genres` | `str` | Comma-separated genre names (e.g. `"Action, Thriller"`) |
| `year` | `str` | Release year (e.g. `"2010"`) |
| `description` | `str` | Synopsis text |
| `rating` | `str` | Rating value (format varies by portal, e.g. `"8.8"`) |
| `duration` | `str` | Duration in seconds (e.g. `"8880"` for 148 minutes); may be `"0"` for series |
| `is_series` | `bool` | `True` if this item has seasons/episodes; `False` for standalone movies |
| `fav` | `bool` | `True` if the item is in the user's favourites |

---

## Filtering movies vs series

`get_content()` returns both movies and series mixed together. Use `is_series` to
separate them:

```python
result = client.vod.get_content(page=1)

movies = [item for item in result.items if not item.is_series]
series = [item for item in result.items if item.is_series]

print(f"Movies: {len(movies)}, Series: {len(series)}")
```

---

## Stream URLs for movies

### `get_stream_url_by_content_id(content_id)`

The simplest way to get a playable URL for a movie when you have its ID:

```python
url = client.vod.get_stream_url_by_content_id("101")
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `content_id` | `str` | The `id` from a `Content` object |

**Returns:** `str` — a playable URL.

**Raises:** `StreamError` if the portal rejects the request.

---

### `get_stream_url(cmd)`

Lower-level method: resolves a `cmd` string directly. Use this when you already
have the `cmd` value from a `Content` object.

```python
item = result.items[0]
url = client.vod.get_stream_url(item.cmd)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `cmd` | `str` | The `cmd` value from a `Content` object |

**Returns:** `str` — a playable URL.

**Raises:** `StreamError` if the portal rejects the request.

> **Tip:** `get_stream_url_by_content_id(id)` is equivalent to calling
> `get_stream_url(f"/media/{id}.mpg")` — use whichever is more convenient.

---

## End-to-end example

```python
from stb_reader import STBClient, StreamError

client = STBClient(base_url="http://portal.example.com", mac="00:1A:79:XX:XX:XX")
client.authenticate()

# 1. Find a category
categories = client.vod.get_categories()
action = next((c for c in categories if "action" in c.title.lower()), None)
category_id = action.id if action else "*"

# 2. Fetch movies (filter out series)
result = client.vod.get_content(category_id=category_id, sort="rating", page=1)
movies = [item for item in result.items if not item.is_series]

print(f"Found {len(movies)} movies on this page (of {result.total} total items)")
for movie in movies:
    print(f"  {movie.name} ({movie.year}) — Rating: {movie.rating}")

# 3. Stream the first movie
if movies:
    try:
        url = client.vod.get_stream_url_by_content_id(movies[0].id)
        print(f"\nStream URL: {url}")
    except StreamError as e:
        print(f"Could not stream: {e}")
```

---

## Related

- [Series guide](./series.md) — seasons, episodes, quality selection
- [Pagination](./pagination.md) — fetching all pages
- [Error handling](./error-handling.md) — `StreamError`
- [API reference](./api-reference.md) — complete `VODService` reference
