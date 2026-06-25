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


def test_extract_blog_cafe_results_keeps_only_top_representative_per_result_card():
    html = """
    <html><body>
      <section class="sc_new"><h2>인기글</h2>
        <div class="sds-comps-vertical-layout _fe_view_po">
          <a href="https://cafe.naver.com/1sejongcity">세종시닷컴</a>
          <a href="https://cafe.naver.com/1sejongcity/1958813?art=tracking">부산흥신소 비용 기준</a>
          <a href="https://cafe.naver.com/1sejongcity/1958813?art=tracking">부산흥신소 비용 기준 본문 미리보기</a>
          <a href="https://cafe.naver.com/1sejongcity/1952590?art=tracking">부산흥신소 비용 이해는</a>
          <a href="https://cafe.naver.com/1sejongcity/1951533?art=tracking">부산 흥신소 의뢰결정은</a>
          <a href="https://cafe.naver.com/1sejongcity/1958813?art=tracking">RE댓글 링크는 제외</a>
        </div>
        <div class="sds-comps-vertical-layout _fe_view_po">
          <a href="https://cafe.naver.com/kig">피터팬의 좋은방 구하기</a>
          <a href="https://cafe.naver.com/kig/19525501?art=tracking">부산 흥신소 의뢰 비용</a>
          <a href="https://cafe.naver.com/kig/19525502?art=tracking">같은 카드 추가글</a>
        </div>
        <div class="sds-comps-vertical-layout _fe_view_po">
          <a href="https://blog.naver.com/0557418">고탐정사무소</a>
          <a href="https://blog.naver.com/0557418/224312791497">부산흥신소 탐정의뢰 처음이라 망설였던 내 이야기</a>
          <a href="https://blog.naver.com/0557418/224312791498">같은 카드 블로그 추가글</a>
        </div>
      </section>
    </body></html>
    """

    results = extract_blog_cafe_results_from_html(html)

    assert [(r.content_type, r.url, r.title) for r in results] == [
        ("cafe", "https://cafe.naver.com/1sejongcity/1958813", "부산흥신소 비용 기준"),
        ("cafe", "https://cafe.naver.com/kig/19525501", "부산 흥신소 의뢰 비용"),
        ("blog", "https://blog.naver.com/0557418/224312791497", "부산흥신소 탐정의뢰 처음이라 망설였던 내 이야기"),
    ]
    assert all("1952590" not in result.url and "1951533" not in result.url for result in results)


def test_extract_blog_cafe_results_falls_back_to_non_card_view_results_when_power_cards_are_ads():
    html = """
    <html><body>
      <section class="sc_new"><h2>파워컨텐츠</h2>
        <div class="_fe_view_power_content">
          <a href="https://example.com/ad">광고성 병원 페이지</a>
        </div>
      </section>
      <section class="sc_new"><h2>블로그</h2>
        <ul>
          <li>
            <a href="https://blog.naver.com/goodblog/111">요실금수술 블로그 대표글</a>
            <a href="https://blog.naver.com/goodblog/111">본문 미리보기 중복 링크</a>
          </li>
          <li>
            <a href="https://cafe.naver.com/goodcafe/222?art=tracking">요실금수술 카페 대표글</a>
          </li>
        </ul>
      </section>
    </body></html>
    """

    results = extract_blog_cafe_results_from_html(html)

    assert [(r.content_type, r.url, r.title) for r in results] == [
        ("blog", "https://blog.naver.com/goodblog/111", "요실금수술 블로그 대표글"),
        ("cafe", "https://cafe.naver.com/goodcafe/222", "요실금수술 카페 대표글"),
    ]


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
