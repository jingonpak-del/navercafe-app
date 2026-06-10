from navercafe_app.browser import build_driver
from navercafe_app.crawlers.article import ArticleCrawler

URL = "https://cafe.naver.com/your-cafe-slug/123456"

if __name__ == "__main__":
    driver = build_driver(headless=False)
    try:
        article = ArticleCrawler(driver).crawl(URL)
        print(article)
    finally:
        driver.quit()
