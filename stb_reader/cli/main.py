import click
from .config import load_config, save_config, CONFIG_PATH
from .live import live
from .vod import vod


@click.group()
def main() -> None:
    """STB portal CLI."""


@main.command("init")
def init_cmd() -> None:
    """Save portal URL and MAC address to ~/.stb/config."""
    url = click.prompt("Portal URL")
    mac = click.prompt("MAC address")
    save_config({"url": url.rstrip("/"), "mac": mac})
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
