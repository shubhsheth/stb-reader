from __future__ import annotations
import hashlib
import os
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
    random_token = data.get("random")
    if random_token:
        signature = hashlib.sha256(random_token.encode()).hexdigest().upper()
        session.extra_headers["X-Random"] = random_token
        session.extra_headers["Random"] = random_token
    else:
        signature = hashlib.sha256(os.urandom(32)).hexdigest().upper()
    session.signature = signature
    return token


def get_profile(session: "STBSession") -> dict:
    return session.get("stb", "get_profile")
