from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup


def crawl_website(url: str, max_pages: int = 5) -> str:
    """
    Crawls a website and returns extracted text content.
    """
    collected_text = []
    visited = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=60000)

        links = page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => e.href)"
        )

        for link in links[:max_pages]:
            if link in visited or not link.startswith(url):
                continue

            visited.add(link)
            page.goto(link)

            soup = BeautifulSoup(page.content(), "html.parser")
            text = soup.get_text(" ", strip=True)
            collected_text.append(text[:4000])

        browser.close()

    return "\n".join(collected_text)[:12000]
