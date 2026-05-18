import logging
import click
from .config import load_config, save_config, CONFIG_PATH
from .live import live
from .vod import vod


@click.group()
@click.option("--debug", is_flag=True, default=False, help="Print raw portal responses to stderr.")
@click.pass_context
def main(ctx: click.Context, debug: bool) -> None:
    """STB portal CLI."""
    if debug:
        logging.basicConfig(level=logging.DEBUG, format="%(message)s")


@main.command("init")
def init_cmd() -> None:
    """Save portal connection settings to ~/.stb/config."""
    url = click.prompt("Portal URL (no port)")
    port = click.prompt("Port", default="")
    mac = click.prompt("MAC address")
    serial = click.prompt("Serial", default="000000000000")
    lang = click.prompt("Language", default="en")
    timezone = click.prompt("Timezone", default="Europe/London")
    portal_path = click.prompt("Portal path", default="stalker_portal/c/portal.php")
    device_id = click.prompt("Device ID", default="")
    device_id2 = click.prompt("Device ID 2", default="")
    cfg: dict = {"url": url.rstrip("/"), "mac": mac, "serial": serial,
                 "lang": lang, "timezone": timezone, "portal_path": portal_path}
    if device_id:
        cfg["device_id"] = device_id
    if device_id2:
        cfg["device_id2"] = device_id2
    if port:
        cfg["port"] = port
    save_config(cfg)
    click.echo(f"Config saved to {CONFIG_PATH}")


@main.command("stream")
@click.option("--type", "stream_type", required=True, type=click.Choice(["live", "vod"]), help="Stream type.")
@click.argument("cmd")
def stream_cmd(stream_type: str, cmd: str) -> None:
    """Resolve and print a stream URL."""
    from .config import get_client
    from stb_reader.exceptions import STBError
    try:
        client = get_client()
        if stream_type == "live":
            url = client.live_tv.get_stream_url(cmd)
        else:
            url = client.vod.get_stream_url(cmd)
        click.echo(url)
    except STBError as e:
        raise click.ClickException(str(e))


main.add_command(live)
main.add_command(vod)
