from bs4 import BeautifulSoup

from navercafe_app.cafe_urls import parse_cafe_url
from navercafe_app.parsers import extract_image_assets, extract_title, extract_view_count, parse_comments


def test_parse_cafe_url_slug_article():
    parts = parse_cafe_url("https://cafe.naver.com/mycafe/123456?clubid=999&menuid=12")
    assert parts.cafe_slug == "mycafe"
    assert parts.article_id == "123456"
    assert parts.club_id == "999"
    assert parts.menu_id == "12"


def test_extract_title_and_view_count():
    html = '<h3 class="title"><span>샘플 글</span></h3><div>조회 1,234</div>'
    assert extract_title(BeautifulSoup(html, "html.parser")) == "샘플 글"
    assert extract_view_count(html) == 1234


def test_extract_images_and_comments():
    html = '''
    <img src="https://example.com/a.jpg"><img data-src="https://example.com/b.png">
    <li class="CommentItem"><span class="nickname">작성자</span><p class="text_comment">댓글</p><span class="date">2026.06.09</span></li>
    '''
    assert [x.filename for x in extract_image_assets(html)] == ["a.jpg", "b.png"]
    comments = parse_comments(html)
    assert comments[0].author == "작성자"
    assert comments[0].text == "댓글"
