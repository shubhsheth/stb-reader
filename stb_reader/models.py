from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class Genre:
    id: str
    title: str
    alias: str
    censored: bool


@dataclass
class Channel:
    id: str
    number: str
    name: str
    cmd: str
    logo: str
    genre_id: str
    hd: bool
    censored: bool


@dataclass
class Category:
    id: str
    title: str
    alias: str
    censored: bool


@dataclass
class Content:
    id: str
    name: str
    cmd: str
    screenshot_uri: str
    genres: str
    year: str
    description: str
    rating: str
    duration: str
    is_series: bool
    fav: bool
    category_id: str = ""


@dataclass
class Season:
    id: str
    name: str
    video_id: str


@dataclass
class Episode:
    id: str
    name: str
    series_number: str
    cmd: str


@dataclass
class EpisodeFile:
    id: str
    name: str
    cmd: str


@dataclass
class PagedResult(Generic[T]):
    items: list[T]
    total: int
    page: int
    per_page: int
