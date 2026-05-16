import click
from .config import get_client
from .formatting import print_table
from stb_reader.exceptions import STBError


@click.group()
def vod() -> None:
    """VOD commands."""


@vod.command("categories")
def categories_cmd() -> None:
    """List VOD categories."""
    try:
        client = get_client()
        cats = client.vod.get_categories()
        print_table(["ID", "Title"], [[c.id, c.title] for c in cats])
    except STBError as e:
        raise click.ClickException(str(e))


@vod.command("list")
@click.option("--category", "category_id", default="*", help="Category ID to filter by.")
@click.option("--page", default=1, show_default=True, help="Page number.")
def list_cmd(category_id: str, page: int) -> None:
    """List VOD content."""
    try:
        client = get_client()
        result = client.vod.get_content(category_id=category_id, page=page)
        rows = [
            [c.id, c.name, c.year, c.genres, "yes" if c.is_series else "", "" if c.is_series else c.cmd]
            for c in result.items
        ]
        total_pages = -(-result.total // result.per_page) if result.per_page else 1
        footer = f"Page {result.page} of {total_pages} ({result.total} total)"
        print_table(["ID", "Name", "Year", "Genres", "Series", "CMD"], rows, footer=footer)
    except STBError as e:
        raise click.ClickException(str(e))


@vod.command("seasons")
@click.argument("series_id")
def seasons_cmd(series_id: str) -> None:
    """List seasons for a series."""
    try:
        client = get_client()
        seasons = client.vod.get_seasons(series_id)
        print_table(["ID", "Name"], [[s.id, s.name] for s in seasons])
    except STBError as e:
        raise click.ClickException(str(e))


@vod.command("episodes")
@click.argument("series_id")
@click.argument("season_id")
@click.option("--page", default=1, show_default=True, help="Page number.")
def episodes_cmd(series_id: str, season_id: str, page: int) -> None:
    """List episodes for a season."""
    try:
        client = get_client()
        result = client.vod.get_episodes(series_id, season_id, page=page)
        rows = [[e.id, e.name, e.series_number, e.cmd] for e in result.items]
        total_pages = -(-result.total // result.per_page) if result.per_page else 1
        footer = f"Page {result.page} of {total_pages} ({result.total} total)"
        print_table(["ID", "Name", "#", "CMD"], rows, footer=footer)
    except STBError as e:
        raise click.ClickException(str(e))
