from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import asdict, dataclass, field
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from navercafe_app.auth.naver_session import NaverSessionManager

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
)
LIST_API = "https://apis.naver.com/cafe-web/cafe-boardlist-api/v1/cafes/{cafe_id}/menus/{menu_id}/articles"
DETAIL_API = "https://article.cafe.naver.com/gw/v4/cafes/{cafe_id}/articles/{article_id}"


@dataclass(slots=True)
class BoardTarget:
    cafe_id: str
    menu_id: str
    view_type: str = "L"

    @property
    def board_url(self) -> str:
        return f"https://cafe.naver.com/f-e/cafes/{self.cafe_id}/menus/{self.menu_id}?viewType={self.view_type}"


@dataclass(slots=True)
class BoardArticleItem:
    cafe_id: str
    menu_id: str
    article_id: str
    title: str
    article_url: str
    writer_nickname: str = ""
    writer_member_key: str = ""
    write_timestamp: int | None = None
    read_count: int | None = None
    comment_count: int | None = None
    represent_image: str = ""
    has_image: bool = False
    has_file: bool = False
    has_link: bool = False
    read_level: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ImageDownloadResult:
    index: int
    url: str
    saved_as: str = ""
    status: str = "pending"
    bytes: int = 0
    error: str = ""


@dataclass(slots=True)
class ArticleArchiveResult:
    article_id: str
    title: str
    folder: str
    status: str
    images_total: int = 0
    images_downloaded: int = 0
    error: str = ""


class _ImageSrcParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "img":
            return
        attrs_dict = {k.lower(): v for k, v in attrs if v}
        for key in ("src", "data-src", "data-lazy-src", "data-original"):
            value = attrs_dict.get(key)
            if value:
                self.urls.append(unescape(value))
                break


def parse_board_url(url: str) -> BoardTarget:
    """Parse a modern Naver Cafe f-e/ca-fe board URL into cafe/menu IDs."""
    parsed = urlparse(url)
    match = re.search(r"/(?:f-e|ca-fe)/cafes/(\d+)/menus/(\d+)", parsed.path)
    if not match:
        raise ValueError(f"지원하지 않는 게시판 URL입니다: {url}")
    query = parse_qs(parsed.query)
    return BoardTarget(cafe_id=match.group(1), menu_id=match.group(2), view_type=query.get("viewType", ["L"])[0] or "L")


def sanitize_filename(value: str, max_length: int = 90) -> str:
    value = unescape(value or "").strip()
    value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", value)
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"_+", "_", value).strip("._ ")
    return (value or "untitled")[:max_length].rstrip("._ ") or "untitled"


def article_url(cafe_id: str, menu_id: str, article_id: str) -> str:
    return f"https://cafe.naver.com/f-e/cafes/{cafe_id}/articles/{article_id}?menuid={menu_id}"


def _list_headers(target: BoardTarget) -> dict[str, str]:
    return {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": target.board_url,
        "Origin": "https://cafe.naver.com",
    }


def _detail_headers(target: BoardTarget, article_id: str) -> dict[str, str]:
    return {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": (
            f"https://cafe.naver.com/ca-fe/cafes/{target.cafe_id}/articles/{article_id}"
            f"?menuid={target.menu_id}&referrerAllArticles=false&fromNext=true"
        ),
        "Origin": "https://cafe.naver.com",
    }


class FeBoardListClient:
    def __init__(self, session: requests.Session | None = None, timeout: int = 20):
        self.session = session or requests.Session()
        self.timeout = timeout

    def fetch_page(self, target: BoardTarget, page: int = 1, size: int = 15) -> dict[str, Any]:
        url = LIST_API.format(cafe_id=target.cafe_id, menu_id=target.menu_id)
        response = self.session.get(
            url,
            params={"page": page, "size": size, "viewType": target.view_type},
            headers=_list_headers(target),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def iter_articles(
        self,
        target: BoardTarget,
        start_page: int = 1,
        end_page: int | None = None,
        limit: int | None = None,
        delay: float = 0.0,
    ) -> Iterable[BoardArticleItem]:
        seen: set[str] = set()
        page = start_page
        yielded = 0
        while True:
            payload = self.fetch_page(target, page=page)
            result = payload.get("result") or payload.get("message", {}).get("result") or {}
            rows = result.get("articleList") or []
            for row in rows:
                item_payload = row.get("item") if isinstance(row, dict) else None
                if not isinstance(item_payload, dict):
                    continue
                item = normalize_list_item(target, item_payload)
                if item.article_id in seen:
                    continue
                seen.add(item.article_id)
                yield item
                yielded += 1
                if limit and yielded >= limit:
                    return
            page_info = result.get("pageInfo") or {}
            last_page = int(page_info.get("lastNavigationPageNumber") or page)
            visible_next = bool(page_info.get("visibleNextButton"))
            if end_page and page >= end_page:
                return
            if page >= last_page and not visible_next:
                return
            if not rows:
                return
            page += 1
            if delay:
                time.sleep(delay)


def normalize_list_item(target: BoardTarget, item: dict[str, Any]) -> BoardArticleItem:
    writer = item.get("writerInfo") or {}
    article_id = str(item.get("articleId") or item.get("id") or "")
    title = str(item.get("subject") or item.get("title") or "")
    represent_image = item.get("representImage") or item.get("representImageUrl") or ""
    return BoardArticleItem(
        cafe_id=target.cafe_id,
        menu_id=str(item.get("menuId") or target.menu_id),
        article_id=article_id,
        title=title,
        article_url=article_url(target.cafe_id, target.menu_id, article_id),
        writer_nickname=str(
            writer.get("nickname") or writer.get("nickName") or writer.get("nick") or item.get("writerNickname") or ""
        ),
        writer_member_key=str(writer.get("memberKey") or item.get("memberKey") or ""),
        write_timestamp=_optional_int(item.get("writeDateTimestamp") or item.get("writeDate")),
        read_count=_optional_int(item.get("readCount")),
        comment_count=_optional_int(item.get("commentCount")),
        represent_image=str(represent_image or ""),
        has_image=bool(item.get("hasImage")),
        has_file=bool(item.get("hasFile")),
        has_link=bool(item.get("hasLink")),
        read_level=_optional_int(item.get("readLevel")),
        raw=item,
    )


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class FeArticleDetailClient:
    def __init__(self, session: requests.Session, timeout: int = 20):
        self.session = session
        self.timeout = timeout

    def fetch_detail(self, target: BoardTarget, article_id: str) -> dict[str, Any]:
        url = DETAIL_API.format(cafe_id=target.cafe_id, article_id=article_id)
        response = self.session.get(
            url,
            params={"useCafeId": "true", "requestFrom": "A"},
            headers=_detail_headers(target, article_id),
            timeout=self.timeout,
        )
        try:
            payload = response.json()
        except ValueError:
            response.raise_for_status()
            raise
        if response.status_code >= 400:
            result = payload.get("result") if isinstance(payload, dict) else {}
            code = result.get("errorCode") if isinstance(result, dict) else ""
            reason = result.get("reason") if isinstance(result, dict) else ""
            raise RuntimeError(f"상세 API 접근 실패(status={response.status_code}, code={code}, reason={reason})")
        return payload


def extract_detail_result(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result") or payload.get("message", {}).get("result") or {}
    if not isinstance(result, dict):
        return {}
    if "article" in result:
        return result
    return {"article": result}


def extract_body_html(detail_result: dict[str, Any]) -> str:
    article = detail_result.get("article") or {}
    return str(article.get("contentHtml") or article.get("contentHTML") or "")


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    return soup.get_text("\n", strip=True)


def extract_image_urls(detail_result: dict[str, Any], fallback: BoardArticleItem | None = None) -> list[str]:
    urls: list[str] = []
    article = detail_result.get("article") or {}
    html = extract_body_html(detail_result)
    parser = _ImageSrcParser()
    parser.feed(html or "")
    urls.extend(parser.urls)
    _collect_urls_from_obj(article.get("contentElements"), urls)
    _collect_urls_from_obj(article.get("customElements"), urls)
    _collect_urls_from_obj(detail_result.get("attaches"), urls)
    for key in ("representImageUrl", "representImage"):
        if article.get(key):
            urls.append(str(article[key]))
    if fallback and fallback.represent_image:
        urls.append(fallback.represent_image)
    return dedupe_urls([normalize_image_url(u) for u in urls if u])


def _collect_urls_from_obj(obj: Any, urls: list[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_l = str(key).lower()
            if isinstance(value, str) and (key_l in {"url", "imageurl", "src", "originurl", "thumbnailurl"} or _looks_like_image_url(value)):
                urls.append(value)
            else:
                _collect_urls_from_obj(value, urls)
    elif isinstance(obj, list):
        for item in obj:
            _collect_urls_from_obj(item, urls)


def _looks_like_image_url(value: str) -> bool:
    return value.startswith("http") and any(host in value for host in ("pstatic.net", "naver.net", "naver.com"))


def normalize_image_url(url: str) -> str:
    url = unescape(str(url)).strip()
    if url.startswith("//"):
        url = "https:" + url
    return url


def dedupe_urls(urls: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def _image_extension(url: str, content_type: str = "") -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
        return suffix
    if "png" in content_type:
        return ".png"
    if "gif" in content_type:
        return ".gif"
    if "webp" in content_type:
        return ".webp"
    return ".jpg"


class BoardArchiveWriter:
    def __init__(self, output_dir: str | Path, session: requests.Session | None = None, timeout: int = 30):
        self.output_dir = Path(output_dir)
        self.session = session or requests.Session()
        self.timeout = timeout

    def board_dir(self, target: BoardTarget, board_name: str = "board") -> Path:
        return self.output_dir / f"{sanitize_filename(board_name)}_{target.cafe_id}_{target.menu_id}"

    def article_dir(self, board_dir: Path, item: BoardArticleItem) -> Path:
        return board_dir / f"{item.article_id}_{sanitize_filename(item.title)}"

    def write_list_manifest(self, board_dir: Path, target: BoardTarget, items: list[BoardArticleItem], board_name: str = "") -> None:
        board_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            board_dir / "board_manifest.json",
            {
                "cafe_id": target.cafe_id,
                "menu_id": target.menu_id,
                "view_type": target.view_type,
                "board_url": target.board_url,
                "board_name": board_name,
                "article_count": len(items),
                "created_at": int(time.time()),
            },
        )
        with (board_dir / "board_articles.jsonl").open("w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")

    def write_article(
        self,
        board_dir: Path,
        target: BoardTarget,
        item: BoardArticleItem,
        detail_payload: dict[str, Any],
        download_images: bool = True,
        skip_existing: bool = True,
    ) -> ArticleArchiveResult:
        folder = self.article_dir(board_dir, item)
        if skip_existing and (folder / "metadata.json").exists():
            return ArticleArchiveResult(item.article_id, item.title, str(folder), "skipped")
        folder.mkdir(parents=True, exist_ok=True)
        detail_result = extract_detail_result(detail_payload)
        article = detail_result.get("article") or {}
        body_html = extract_body_html(detail_result)
        body_text = html_to_text(body_html)
        image_urls = extract_image_urls(detail_result, fallback=item)
        metadata = {
            **asdict(item),
            "detail_subject": article.get("subject"),
            "detail_write_date": article.get("writeDate"),
            "body_text_length": len(body_text),
            "body_html_length": len(body_html),
            "image_count": len(image_urls),
            "source": "naver_cafe_fe_board_archive",
        }
        write_json(folder / "metadata.json", metadata)
        (folder / "body.html").write_text(body_html, encoding="utf-8")
        (folder / "body.txt").write_text(body_text, encoding="utf-8")
        image_results = self.download_images(image_urls, folder / "images", target, item) if download_images else [
            ImageDownloadResult(index=i + 1, url=url, status="not_downloaded") for i, url in enumerate(image_urls)
        ]
        write_json(folder / "images_manifest.json", [asdict(result) for result in image_results])
        return ArticleArchiveResult(
            item.article_id,
            item.title,
            str(folder),
            "ok",
            images_total=len(image_results),
            images_downloaded=sum(1 for r in image_results if r.status == "ok"),
        )

    def download_images(self, urls: list[str], images_dir: Path, target: BoardTarget, item: BoardArticleItem) -> list[ImageDownloadResult]:
        images_dir.mkdir(parents=True, exist_ok=True)
        results: list[ImageDownloadResult] = []
        for idx, url in enumerate(urls, start=1):
            result = ImageDownloadResult(index=idx, url=url)
            try:
                response = self.session.get(
                    url,
                    headers={"User-Agent": DEFAULT_USER_AGENT, "Referer": item.article_url},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                ext = _image_extension(url, response.headers.get("Content-Type", ""))
                name_hint = sanitize_filename(Path(urlparse(url).path).stem, max_length=50)
                filename = f"{idx:03d}_{name_hint}{ext}" if name_hint != "untitled" else f"{idx:03d}{ext}"
                target_path = images_dir / filename
                target_path.write_bytes(response.content)
                result.saved_as = str(target_path.relative_to(images_dir.parent))
                result.status = "ok"
                result.bytes = len(response.content)
            except Exception as exc:  # pragma: no cover - network failures vary
                result.status = "error"
                result.error = str(exc)
            results.append(result)
        return results


def archive_board(
    target: BoardTarget,
    output_dir: str | Path,
    session: requests.Session | None = None,
    board_name: str = "board",
    start_page: int = 1,
    end_page: int | None = None,
    limit: int | None = None,
    delay: float = 1.0,
    download_images: bool = True,
    details: bool = True,
    skip_existing: bool = True,
) -> list[ArticleArchiveResult]:
    session = session or requests.Session()
    list_client = FeBoardListClient(session=session)
    items = list(list_client.iter_articles(target, start_page=start_page, end_page=end_page, limit=limit, delay=delay))
    writer = BoardArchiveWriter(output_dir, session=session)
    board_dir = writer.board_dir(target, board_name=board_name)
    writer.write_list_manifest(board_dir, target, items, board_name=board_name)
    if not details:
        return [
            ArticleArchiveResult(item.article_id, item.title, str(writer.article_dir(board_dir, item)), "list_only")
            for item in items
        ]
    detail_client = FeArticleDetailClient(session=session)
    results: list[ArticleArchiveResult] = []
    failed_path = board_dir / "failed_articles.jsonl"
    for item in items:
        try:
            detail_payload = detail_client.fetch_detail(target, item.article_id)
            result = writer.write_article(
                board_dir,
                target,
                item,
                detail_payload,
                download_images=download_images,
                skip_existing=skip_existing,
            )
        except Exception as exc:
            result = ArticleArchiveResult(item.article_id, item.title, str(writer.article_dir(board_dir, item)), "error", error=str(exc))
            append_jsonl(failed_path, asdict(result))
        results.append(result)
        if delay:
            time.sleep(delay)
    return results


def _build_session(args: argparse.Namespace) -> requests.Session:
    if args.no_login or args.list_only:
        session = requests.Session()
        session.headers.update({"User-Agent": DEFAULT_USER_AGENT})
        return session
    manager = NaverSessionManager(env_path=args.env_path, session_store=None)
    return manager.get_requests_session(force_login=args.force_login, headless=args.headless)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Naver Cafe f-e 게시판 본문/사진 폴더별 아카이브")
    parser.add_argument("--url", help="게시판 URL. 예: https://cafe.naver.com/f-e/cafes/14793916/menus/1556?viewType=L")
    parser.add_argument("--cafe-id")
    parser.add_argument("--menu-id")
    parser.add_argument("--board-name", default="board")
    parser.add_argument("--output", default="output/naver_cafe_archive")
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--end-page", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--list-only", action="store_true", help="목록만 저장하고 본문 상세 API는 호출하지 않습니다.")
    parser.add_argument("--no-login", action="store_true", help="로그인 세션 없이 실행합니다. 상세 본문은 대부분 실패합니다.")
    parser.add_argument("--force-login", action="store_true", help="저장 쿠키 대신 Selenium 로그인을 강제합니다.")
    parser.add_argument("--headless", action="store_true", help="Selenium 로그인 시 headless 모드 사용")
    parser.add_argument("--env-path", default=".env")
    parser.add_argument("--no-images", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    if args.url:
        target = parse_board_url(args.url)
    elif args.cafe_id and args.menu_id:
        target = BoardTarget(str(args.cafe_id), str(args.menu_id))
    else:
        parser.error("--url 또는 --cafe-id/--menu-id가 필요합니다.")

    session = _build_session(args)
    results = archive_board(
        target=target,
        output_dir=args.output,
        session=session,
        board_name=args.board_name,
        start_page=args.start_page,
        end_page=args.end_page,
        limit=args.limit,
        delay=args.delay,
        download_images=not args.no_images,
        details=not args.list_only,
        skip_existing=not args.overwrite,
    )
    list_only = sum(1 for r in results if r.status == "list_only")
    ok = sum(1 for r in results if r.status == "ok")
    skipped = sum(1 for r in results if r.status == "skipped")
    errors = [r for r in results if r.status == "error"]
    print(f"완료: list_only={list_only}, ok={ok}, skipped={skipped}, error={len(errors)}")
    if errors:
        print("상세 수집 실패가 있습니다. 로그인/카페 읽기 권한을 확인하세요.")
        for err in errors[:5]:
            print(f"- {err.article_id} {err.title}: {err.error}")
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
