import json
from pathlib import Path
import click
from stb_reader import STBClient

CONFIG_PATH = Path.home() / ".stb" / "config"
TOKEN_PATH = Path.home() / ".stb" / "token"


def save_config(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise click.ClickException("No config found. Run `stb init` first.")
    return json.loads(CONFIG_PATH.read_text())


def save_token(session) -> None:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps({
        "token": session.token,
        "extra_headers": session.extra_headers,
    }))


def load_token() -> dict | None:
    if not TOKEN_PATH.exists():
        return None
    try:
        return json.loads(TOKEN_PATH.read_text())
    except (json.JSONDecodeError, KeyError):
        return None


def get_client() -> STBClient:
    cfg = load_config()
    base_url = cfg["url"]
    if cfg.get("port"):
        base_url = f"{base_url}:{cfg['port']}"
    kwargs: dict = {"base_url": base_url, "mac": cfg["mac"]}
    for key in ("serial", "lang", "timezone", "portal_path"):
        if key in cfg:
            kwargs[key] = cfg[key]
    client = STBClient(**kwargs)

    def _auth_and_save() -> None:
        client.authenticate()
        save_token(client._session)

    client._session.reauth_fn = _auth_and_save

    cached = load_token()
    if cached:
        client._session.token = cached["token"]
        client._session.extra_headers.update(cached.get("extra_headers", {}))
    else:
        _auth_and_save()

    return client
