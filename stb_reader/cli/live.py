import click
from .config import get_client
from .formatting import print_table
from stb_reader.exceptions import STBError


@click.group()
def live() -> None:
    """Live TV commands."""


@live.command("genres")
def genres_cmd() -> None:
    """List live TV genres."""
    try:
        client = get_client()
        genres = client.live_tv.get_genres()
        print_table(["ID", "Title"], [[g.id, g.title] for g in genres])
    except STBError as e:
        raise click.ClickException(str(e))


@live.command("channels")
@click.option("--genre", "genre_id", default="*", help="Genre ID to filter by.")
@click.option("--hd", is_flag=True, default=False, help="HD channels only.")
@click.option("--page", default=1, show_default=True, help="Page number.")
def channels_cmd(genre_id: str, hd: bool, page: int) -> None:
    """List live TV channels."""
    try:
        client = get_client()
        result = client.live_tv.get_channels(genre_id=genre_id, page=page, hd=hd)
        rows = [[c.number, c.name, c.genre_id, "yes" if c.hd else "", c.cmd] for c in result.items]
        total_pages = -(-result.total // result.per_page) if result.per_page else 1
        footer = f"Page {result.page} of {total_pages} ({result.total} total)"
        print_table(["#", "Name", "Genre ID", "HD", "CMD"], rows, footer=footer)
    except STBError as e:
        raise click.ClickException(str(e))
