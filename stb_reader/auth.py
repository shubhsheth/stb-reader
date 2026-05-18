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
    params: dict = {}
    if session.device_id is not None:
        params["device_id"] = session.device_id
    if session.device_id2 is not None:
        params["device_id2"] = session.device_id2
    data = session.get("stb", "get_profile", **params)
    token = data.get("token", "")
    if token:
        session.token = token
