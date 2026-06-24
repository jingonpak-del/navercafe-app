from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

try:
    import yaml
except Exception:  # pragma: no cover - only hit in minimal deployments
    yaml = None

from navercafe_app.cafe_urls import parse_cafe_url


@dataclass(slots=True)
class DelayRange:
    min: float = 2.0
    max: float = 5.0


@dataclass(slots=True)
class CrawlDefaults:
    max_pages_per_board: int = 3
    include_comments: bool = True
    include_images: bool = False
    since_mode: str = "last_seen_article_id"
    delay_seconds: DelayRange = field(default_factory=DelayRange)


@dataclass(slots=True)
class BoardTarget:
    name: str
    menu_id: str = ""
    board_url: str = ""
    max_pages: int | None = None
    include_comments: bool | None = None
    include_images: bool | None = None


@dataclass(slots=True)
class CafeTarget:
    name: str
    cafe_url: str
    cafe_slug: str = ""
    cafe_id: str = ""
    boards: list[BoardTarget] = field(default_factory=list)


@dataclass(slots=True)
class CrawlTargets:
    defaults: CrawlDefaults
    targets: list[CafeTarget]


def load_targets(path: str | Path) -> CrawlTargets:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Target config not found: {config_path}")
    data = _load_mapping(config_path)
    return parse_targets(data)


def parse_targets(data: dict[str, Any]) -> CrawlTargets:
    defaults = _parse_defaults(data.get("defaults") or {})
    cafes: list[CafeTarget] = []
    for item in data.get("targets") or []:
        if not isinstance(item, dict):
            raise ValueError("Each target must be a mapping.")
        cafe_url = str(item.get("cafe_url") or "").strip()
        cafe_slug = str(item.get("cafe_slug") or "").strip()
        parsed = parse_cafe_url(cafe_url) if cafe_url else None
        if not cafe_slug and parsed:
            cafe_slug = parsed.cafe_slug
        cafe_id = str(item.get("cafe_id") or (parsed.club_id if parsed else "") or "").strip()
        boards: list[BoardTarget] = []
        for board in item.get("boards") or []:
            if not isinstance(board, dict):
                raise ValueError("Each board must be a mapping.")
            board_url = str(board.get("board_url") or "").strip()
            menu_id = str(board.get("menu_id") or _menu_id_from_url(board_url) or "").strip()
            if not menu_id and not board_url:
                raise ValueError(f"Board target needs menu_id or board_url: {item.get('name')}")
            boards.append(
                BoardTarget(
                    name=str(board.get("name") or menu_id or board_url),
                    menu_id=menu_id,
                    board_url=board_url,
                    max_pages=_optional_int(board.get("max_pages")),
                    include_comments=_optional_bool(board.get("include_comments")),
                    include_images=_optional_bool(board.get("include_images")),
                )
            )
        if not cafe_url and not cafe_id:
            raise ValueError("Cafe target needs cafe_url or cafe_id.")
        if not boards:
            raise ValueError(f"Cafe target has no boards: {item.get('name') or cafe_url}")
        cafes.append(
            CafeTarget(
                name=str(item.get("name") or cafe_slug or cafe_id),
                cafe_url=cafe_url,
                cafe_slug=cafe_slug,
                cafe_id=cafe_id,
                boards=boards,
            )
        )
    return CrawlTargets(defaults=defaults, targets=cafes)


def _load_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        if yaml is None:
            raise RuntimeError("PyYAML is required for YAML target files. Use JSON or install pyyaml.")
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("Target config root must be a mapping.")
    return data


def _parse_defaults(data: dict[str, Any]) -> CrawlDefaults:
    delay = data.get("delay_seconds") or {}
    if not isinstance(delay, dict):
        delay = {}
    return CrawlDefaults(
        max_pages_per_board=int(data.get("max_pages_per_board") or 3),
        include_comments=bool(data.get("include_comments", True)),
        include_images=bool(data.get("include_images", False)),
        since_mode=str(data.get("since_mode") or "last_seen_article_id"),
        delay_seconds=DelayRange(min=float(delay.get("min", 2)), max=float(delay.get("max", 5))),
    )


def _menu_id_from_url(url: str) -> str:
    if not url:
        return ""
    query = parse_qs(urlparse(url).query)
    for key in ("search.menuid", "menuid", "menuId"):
        if query.get(key):
            return query[key][0]
    return ""


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}
