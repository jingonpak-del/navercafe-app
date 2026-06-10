from datetime import date

from navercafe_app.crawlers.attendance import evaluate_activity, parse_korean_date


def test_parse_korean_date_with_year_and_without_year():
    assert parse_korean_date("2026.06.09") == date(2026, 6, 9)
    assert parse_korean_date("06.09", default_year=2026) == date(2026, 6, 9)


def test_evaluate_activity_filters_range():
    result = evaluate_activity(
        "member1",
        ["2026.06.01", "2026.06.05", "2026.07.01", "not a date"],
        date(2026, 6, 1),
        date(2026, 6, 30),
    )
    assert result.member_id == "member1"
    assert result.to_sorted_strings() == ["2026-06-01", "2026-06-05"]
