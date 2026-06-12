from naver_cafe_strategy.naver.search_content_crawler import (
    content_type_from_url,
    extract_blog_cafe_results_from_html,
    normalize_naver_url,
    parse_blog_identity,
    parse_cafe_identity,
    parse_detail_html,
)


def test_parse_and_normalize_blog_url():
    url = "https://blog.naver.com/PostView.naver?blogId=testblog&logNo=123456&redirect=Dlog"

    assert parse_blog_identity(url) == ("testblog", "123456")
    assert content_type_from_url(url) == "blog"
    assert normalize_naver_url(url) == "https://blog.naver.com/testblog/123456"


def test_parse_and_normalize_cafe_url_with_tracking_query():
    url = "https://cafe.naver.com/mycafe/98765?art=tracking-token"

    assert parse_cafe_identity(url) == ("mycafe", "98765")
    assert content_type_from_url(url) == "cafe"
    assert normalize_naver_url(url) == "https://cafe.naver.com/mycafe/98765"


def test_extract_blog_cafe_results_excludes_ads_place_and_websites():
    html = """
    <html><body>
      <section class="sc_new ad_section"><h2>관련 광고</h2>
        <a href="https://blog.naver.com/adblog/111">광고 블로그</a>
      </section>
      <section class="sc_new"><h2>플레이스</h2>
        <a href="https://cafe.naver.com/placecafe/222">플레이스 카페</a>
      </section>
      <section class="sc_new"><h2>웹사이트</h2>
        <a href="https://blog.naver.com/siteblog/333">웹사이트 블로그</a>
      </section>
      <section class="sc_new"><h2>블로그</h2>
        <ul>
          <li>
            <a href="https://blog.naver.com/goodblog/444">창원흥신소 블로그 후기</a>
            <a href="https://blog.naver.com/goodblog/444">중복 링크</a>
            <p>블로그 본문 일부입니다.</p>
          </li>
          <li>
            <a href="https://cafe.naver.com/goodcafe/555?art=tracking">창원흥신소 카페 후기</a>
            <p>카페 본문 일부입니다.</p>
          </li>
        </ul>
      </section>
    </body></html>
    """

    results = extract_blog_cafe_results_from_html(html)

    assert [(r.content_type, r.url, r.title) for r in results] == [
        ("blog", "https://blog.naver.com/goodblog/444", "창원흥신소 블로그 후기"),
        ("cafe", "https://cafe.naver.com/goodcafe/555", "창원흥신소 카페 후기"),
    ]
    assert results[0].rank == 1
    assert results[1].rank == 2


def test_parse_blog_detail_html_smart_editor():
    html = """
    <html><body>
      <div class="se-title-text"><span>블로그 상세 제목</span></div>
      <div class="se-main-container">
        <p>첫 번째 문장</p>
        <p>두 번째 문장</p>
      </div>
    </body></html>
    """

    title, body = parse_detail_html(html, "blog")

    assert title == "블로그 상세 제목"
    assert body == "첫 번째 문장\n두 번째 문장"


def test_parse_cafe_detail_html():
    html = """
    <html><body>
      <h3 class="title_text">카페 상세 제목</h3>
      <div class="article_viewer">
        <p>카페 본문 1</p>
        <p>카페 본문 2</p>
      </div>
    </body></html>
    """

    title, body = parse_detail_html(html, "cafe")

    assert title == "카페 상세 제목"
    assert body == "카페 본문 1\n카페 본문 2"
