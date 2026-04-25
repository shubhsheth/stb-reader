from __future__ import annotations
from typing import TYPE_CHECKING
from .exceptions import AuthError

if TYPE_CHECKING:
    from ._http import STBSession


def handshake(session: "STBSession") -> str:
    data = session.get("stb", "handshake")
    token = data.get("token", "")
    if not token:
        raise AuthError("handshake returned no token")
    session.token = token
    return token


def get_profile(session: "STBSession") -> dict:
    return session.get("stb", "get_profile")
