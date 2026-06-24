from __future__ import annotations

import csv
import json

from navercafe_app.cli.popular_detail_crawl import _read_source_rows, _status_from_body


def test_read_source_rows_json(tmp_path) -> None:
    path = tmp_path / "rows.json"
    path.write_text(json.dumps([{"cafe_id": 14793916, "title": "테스트"}], ensure_ascii=False), encoding="utf-8")
    rows = _read_source_rows(path)
    assert rows == [{"cafe_id": "14793916", "title": "테스트"}]


def test_read_source_rows_csv_utf8_sig(tmp_path) -> None:
    path = tmp_path / "rows.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["cafe_id", "title"])
        writer.writeheader()
        writer.writerow({"cafe_id": "14793916", "title": "한글 제목"})
    rows = _read_source_rows(path)
    assert rows[0]["title"] == "한글 제목"


def test_status_from_body() -> None:
    assert _status_from_body("제목", "본문이 충분히 길어서 공개글로 판단할 수 있습니다.") == "public_detail_ok"
    assert _status_from_body("네이버 카페", "") == "detail_unavailable"
    assert _status_from_body("제목", "멤버만 볼 수 있습니다") == "login_or_member_required"
