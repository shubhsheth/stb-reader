import json
from pathlib import Path
import click
from stb_reader import STBClient

CONFIG_PATH = Path.home() / ".stb" / "config"


def save_config(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise click.ClickException("No config found. Run `stb init` first.")
    return json.loads(CONFIG_PATH.read_text())


def get_client() -> STBClient:
    cfg = load_config()
    kwargs = {"base_url": cfg["url"], "mac": cfg["mac"]}
    if "portal_path" in cfg:
        kwargs["portal_path"] = cfg["portal_path"]
    client = STBClient(**kwargs)
    client.authenticate()
    return client
