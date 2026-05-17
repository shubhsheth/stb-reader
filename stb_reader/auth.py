from __future__ import annotations
from typing import TYPE_CHECKING
from .exceptions import AuthError

if TYPE_CHECKING:
    from ._http import STBSession


def handshake(session: "STBSession") -> None:
    data = session.get("stb", "handshake")
    token = data.get("token", "")
    if not token:
        raise AuthError("handshake returned no token")
    session.token = token
    random_token = data.get("random")
    if random_token:
        session.extra_headers["X-Random"] = random_token
        session.extra_headers["Random"] = random_token


def get_profile(session: "STBSession") -> None:
    data = session.get("stb", "get_profile")
    token = data.get("token", "")
    if token:
        session.token = token
