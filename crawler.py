from playwright.async_api import async_playwright
from bs4 import BeautifulSoup


async def crawl_website(url: str, max_pages: int = 5) -> str:
    """
    Crawls a website and returns extracted text content.
    Safe for Streamlit + Windows.
    """
    collected_text = []
    visited = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(url, timeout=60000)

        links = await page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => e.href)"
        )

        for link in links[:max_pages]:
            if link in visited or not link.startswith(url):
                continue

            visited.add(link)
            await page.goto(link, timeout=60000)

            soup = BeautifulSoup(await page.content(), "html.parser")
            text = soup.get_text(" ", strip=True)

            collected_text.append(text[:4000])

        await browser.close()

    return "\n".join(collected_text)[:12000]
