from __future__ import annotations

from navercafe_app.crawlers.comment_api import comments_from_api_payload, extract_cafe_and_article_ids


def test_extract_cafe_and_article_ids_from_fe_url() -> None:
    cafe_id, article_id = extract_cafe_and_article_ids(
        "https://cafe.naver.com/f-e/cafes/14793916/articles/123456?boardType=L"
    )
    assert cafe_id == "14793916"
    assert article_id == "123456"


def test_comments_from_api_payload_nested_shapes() -> None:
    payload = {
        "result": {
            "comments": {
                "items": [
                    {
                        "commentId": 1,
                        "content": "첫 댓글입니다",
                        "writer": {"nickName": "작성자1"},
                        "createdAt": "2026.06.24. 10:00",
                    },
                    {
                        "commentId": 2,
                        "text": "대댓글입니다",
                        "member": {"nickname": "작성자2"},
                        "parentCommentId": 1,
                    },
                ]
            }
        }
    }

    comments = comments_from_api_payload(payload)

    assert len(comments) == 2
    assert comments[0].author == "작성자1"
    assert comments[0].text == "첫 댓글입니다"
    assert comments[1].author == "작성자2"
    assert comments[1].is_reply is True
