from collections.abc import Callable
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from stb_reader.exceptions import NotFoundError, STBError, StreamError


def stream_redirect(url_fn: Callable, *args, **kwargs) -> RedirectResponse:
    try:
        url = url_fn(*args, **kwargs)
    except StreamError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except STBError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return RedirectResponse(url=url, status_code=302)


def paged_response(result) -> dict:
    return {
        "data": result.items,
        "page": result.page,
        "total": result.total,
        "per_page": result.per_page,
    }
