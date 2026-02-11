from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import re
import logging
import aiohttp

# Basic logger for visibility in console/Streamlit logs
logger = logging.getLogger("cmsautomatex.crawler")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _formatter = logging.Formatter("%(asctime)s %(levelname)s [crawler] %(message)s")
    _handler.setFormatter(_formatter)
    logger.addHandler(_handler)
logger.setLevel(logging.INFO)


def _normalize_pattern(url: str, base_netloc: str) -> str:
    """
    Normalize URL path to derive a page-type pattern by replacing dynamic
    segments like numeric ids, UUIDs, dates, and slugs with placeholders.
    Preserves actual category names to distinguish different page types.
    Different categories = different groups, same depth subcategories = same group only if under same parent.
    """
    uuid_re = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
    parsed = urlparse(url)

    if parsed.netloc != base_netloc:
        return ""

    path = parsed.path.strip("/")
    segments = [s for s in path.split("/") if s]

    if not segments:
        return "/"

    norm = []
    for i, s in enumerate(segments):
        is_last = (i == len(segments) - 1)
        
        # Pure numeric ID
        if s.isdigit():
            norm.append(":id")
        # UUID format
        elif uuid_re.match(s):
            norm.append(":uuid")
        # Year (4 digits)
        elif re.match(r"^\d{4}$", s):
            norm.append(":year")
        # Date formats: YYYY-MM-DD, YYYY-MM
        elif re.match(r"^\d{4}-\d{2}(-\d{2})?$", s):
            norm.append(":date")
        # Month/day (01-12 or 01-31)
        elif re.match(r"^\d{2}$", s):
            try:
                num = int(s)
                if 1 <= num <= 12:
                    norm.append(":month")
                elif 13 <= num <= 31:
                    norm.append(":day")
                else:
                    norm.append(":id")
            except:
                norm.append(":id")
        # Alphanumeric IDs (e.g., abc123, p12345) - 8+ chars with mixed alpha/digit
        elif re.match(r"^[a-zA-Z0-9]{8,}$", s) and any(c.isdigit() for c in s) and any(c.isalpha() for c in s):
            norm.append(":alphaid")
        # Hyphens/underscores: distinguish between category names and content slugs
        elif "-" in s or "_" in s:
            # If last segment or very long (>30 chars), it's likely a content slug
            if is_last and len(s) > 15:
                norm.append(":slug")
            # Short hyphenated segments not at end could be category names - keep them
            elif not is_last and len(s) <= 25:
                norm.append(s.lower())
            # Last segment, medium length - could be slug or short identifier
            elif is_last:
                norm.append(":slug")
            else:
                norm.append(s.lower())
        # Very long segments - likely slugs
        elif len(s) > 30:
            norm.append(":slug")
        # Short alphanumeric segments not at end - preserve as category names
        elif not is_last and len(s) <= 20 and s.isalnum():
            norm.append(s.lower())
        # Last segment that's short alphanumeric
        elif is_last and len(s) <= 20 and s.isalnum():
            # Known static pages - keep as-is
            static_pages = {"about", "contact", "services", "products", "blog", "news", 
                          "team", "pricing", "faq", "help", "support", "careers", "index",
                          "home", "portfolio", "gallery", "events"}
            if s.lower() in static_pages:
                norm.append(s.lower())
            # Otherwise treat as dynamic slug
            else:
                norm.append(":slug")
        # Default: preserve segment
        else:
            norm.append(s.lower())

    pattern = "/" + "/".join(norm)
    
    # Optional debug logging
    logger.debug("URL: %s -> Pattern: %s", url, pattern)
    
    return pattern


def _looks_like_spa(html: str, text_len: int) -> bool:
    """
    Heuristics to detect client-rendered pages that likely need JS execution:
    - Very low text content
    - Presence of common SPA markers
    - Script-heavy markup with minimal visible text
    """
    if text_len < 300:
        markers = [
            'id="root"', 'id="app"', 'data-reactroot', '__NEXT_DATA__',
            'window.__INITIAL', 'ng-app', 'id="__nuxt"', 'data-v-app'
        ]
        if any(m in html for m in markers):
            return True
        # count scripts
        script_count = html.count('<script')
        if script_count >= 8:
            return True
    return False


async def _discover_sitemap_urls(page, base_url: str) -> list[str]:
    """
    Discover sitemap URLs via robots.txt and common locations.
    """
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    candidates = [
        urljoin(root, "/robots.txt"),
        urljoin(root, "/sitemap.xml"),
        urljoin(root, "/sitemap_index.xml"),
    ]

    sitemap_urls = set()

    # robots.txt
    try:
        resp = await page.goto(candidates[0], timeout=30000)
        if resp and resp.ok:
            content = await page.content()
            text = BeautifulSoup(content, "html.parser").get_text("\n")
            for line in text.splitlines():
                if line.lower().startswith("sitemap:"):
                    sm = line.split(":", 1)[1].strip()
                    if sm.startswith("http"):
                        sitemap_urls.add(sm)
    except Exception:
        pass

    # Common paths
    sitemap_urls.add(candidates[1])
    sitemap_urls.add(candidates[2])

    return list(sitemap_urls)


async def _extract_urls_from_sitemap(page, sitemap_url: str) -> list[str]:
    """
    Extract <loc> URLs from a sitemap or sitemap index.
    """
    urls: list[str] = []
    try:
        resp = await page.goto(sitemap_url, timeout=30000)
        if not resp or not resp.ok:
            return urls
        xml = await page.content()
        soup = BeautifulSoup(xml, "xml")

        index = soup.find_all("sitemap")
        if index:
            for sm in index:
                loc = sm.find("loc")
                if loc and loc.text:
                    urls.extend(await _extract_urls_from_sitemap(page, loc.text.strip()))
            return urls

        for u in soup.find_all("url"):
            loc = u.find("loc")
            if loc and loc.text:
                urls.append(loc.text.strip())

        if not urls:
            for loc in soup.find_all("loc"):
                if loc and loc.text:
                    urls.append(loc.text.strip())
    except Exception:
        return urls

    return urls


async def _representative_urls_from_sitemaps(page, base_url: str, max_types: int = 100) -> list[str]:
    """
    Build representative URLs for unique page types from discovered sitemaps.
    """
    parsed = urlparse(base_url)
    netloc = parsed.netloc
    patterns_to_url: dict[str, str] = {}

    for sm_url in await _discover_sitemap_urls(page, base_url):
        for u in await _extract_urls_from_sitemap(page, sm_url):
            if urlparse(u).netloc != netloc:
                continue
            pattern = _normalize_pattern(u, netloc)
            if not pattern:
                continue
            if pattern not in patterns_to_url:
                patterns_to_url[pattern] = u
                if len(patterns_to_url) >= max_types:
                    break
        if len(patterns_to_url) >= max_types:
            break

    return list(patterns_to_url.values())

async def _representative_urls_from_given_sitemap(page, sitemap_url: str, max_types: int = 30) -> list[str]:
    """
    Build representative URLs for unique page types from a provided sitemap URL.
    """
    urls = await _extract_urls_from_sitemap(page, sitemap_url)
    netloc = urlparse(sitemap_url).netloc
    if not netloc and urls:
        netloc = urlparse(urls[0]).netloc

    patterns_to_url: dict[str, str] = {}
    for u in urls:
        parsed = urlparse(u)
        if netloc and parsed.netloc != netloc:
            continue
        pattern = _normalize_pattern(u, netloc or parsed.netloc)
        if not pattern:
            continue
        if pattern not in patterns_to_url:
            patterns_to_url[pattern] = u
            if len(patterns_to_url) >= max_types:
                break

    return list(patterns_to_url.values())


async def crawl_website(url: str, max_pages: int = 300, concurrency: int = 8, render_js: bool = False) -> tuple[str, list[str]]:
    """
    Crawls a website and returns extracted text content.
    Groups page types via sitemap.xml and crawls one representative URL per type.
    Safe for Streamlit + Windows.
    """
    collected_text: list[str] = []
    crawled_urls: list[str] = []
    visited = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True,args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page()

        await page.goto(url, timeout=60000)

        # Prefer sitemap-driven representative URLs
        if url.lower().endswith(".xml") or "sitemap" in url.lower():
            representative_links = await _representative_urls_from_given_sitemap(page, url, max_types=max_pages)
        else:
            representative_links = await _representative_urls_from_sitemaps(page, url, max_types=max_pages)

        if representative_links:
            logger.info("Representative URLs discovered (%d):\n%s", len(representative_links), "\n".join(representative_links))

        links_to_crawl: list[str] = []

        if representative_links:
            links_to_crawl = representative_links[:max_pages]
            logger.info("Selected URLs to crawl (%d):\n%s", len(links_to_crawl), "\n".join(links_to_crawl))
        else:
            # Fallback: original anchor-based approach
            links = await page.eval_on_selector_all(
                "a[href]",
                "els => els.map(e => e.href)"
            )
            base_netloc = urlparse(url).netloc
            links_to_crawl = [
                l for l in links if urlparse(l).netloc == base_netloc and l.startswith(url)
            ][:max_pages]
            if links_to_crawl:
                logger.info("Fallback to anchor-based selection. URLs to crawl (%d):\n%s", len(links_to_crawl), "\n".join(links_to_crawl))

        # Fetch pages with limited concurrency to speed up crawling
        import asyncio
        from time import perf_counter

        sem = asyncio.Semaphore(concurrency)  # configurable concurrency limit

        # Optional aiohttp session if not rendering JS
        aio_sess: aiohttp.ClientSession | None = None
        if not render_js:
            aio_sess = aiohttp.ClientSession(headers={
                "User-Agent": "CMSAutomateXCrawler/1.0",
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"
            })

        async def fetch(url_to_fetch: str) -> str | None:
            async with sem:
                if url_to_fetch in visited:
                    return None
                visited.add(url_to_fetch)

                start = perf_counter()
                try:
                    if render_js:
                        # Playwright-rendered fetch with heavy resource blocking
                        ctx = await browser.new_context()
                        pg = await ctx.new_page()

                        async def _route(route):
                            if route.request.resource_type in ("image", "font", "stylesheet"):
                                await route.abort()
                            else:
                                await route.continue_()

                        try:
                            await pg.route("**/*", _route)
                        except Exception:
                            pass

                        await pg.goto(url_to_fetch, timeout=30000, wait_until="domcontentloaded")
                        html = await pg.content()
                        elapsed = perf_counter() - start
                        logger.info("Fetched (JS) %s in %.2fs", url_to_fetch, elapsed)
                        soup = BeautifulSoup(html, "html.parser")
                        text = soup.get_text(" ", strip=True)
                        await ctx.close()
                        return text[:6000]
                    else:
                        # Fast static fetch via aiohttp
                        assert aio_sess is not None
                        async with aio_sess.get(url_to_fetch, timeout=20) as resp:
                            if resp.status != 200:
                                logger.debug("HTTP %s for %s", resp.status, url_to_fetch)
                                return None
                            html = await resp.text(errors="ignore")
                            elapsed = perf_counter() - start
                            logger.info("Fetched (static) %s in %.2fs", url_to_fetch, elapsed)
                            soup = BeautifulSoup(html, "html.parser")
                            text = soup.get_text(" ", strip=True)
                            # Auto-switch to JS rendering if SPA indicators detected or very little text
                            if _looks_like_spa(html, len(text)):
                                logger.info("Static fetch looked empty/SPA for %s; re-fetching with JS", url_to_fetch)
                                ctx = await browser.new_context()
                                pg = await ctx.new_page()

                                async def _route(route):
                                    if route.request.resource_type in ("image", "font", "stylesheet"):
                                        await route.abort()
                                    else:
                                        await route.continue_()

                                try:
                                    await pg.route("**/*", _route)
                                except Exception:
                                    pass

                                await pg.goto(url_to_fetch, timeout=30000, wait_until="domcontentloaded")
                                html_js = await pg.content()
                                soup_js = BeautifulSoup(html_js, "html.parser")
                                text_js = soup_js.get_text(" ", strip=True)
                                await ctx.close()
                                return text_js[:6000]
                            return text[:6000]
                except Exception as e:
                    elapsed = perf_counter() - start
                    logger.warning("Failed %s after %.2fs: %s", url_to_fetch, elapsed, e)
                    return None

        tasks = [fetch(l) for l in links_to_crawl]
        results = await asyncio.gather(*tasks)
        for url_idx, r in enumerate(results):
            if r:
                collected_text.append(r)
                # preserve the URL order mapping from links_to_crawl
                try:
                    crawled_urls.append(links_to_crawl[url_idx])
                except Exception:
                    pass

        await browser.close()

    # Close aiohttp session if used
    try:
        if 'aio_sess' in locals() and aio_sess:
            await aio_sess.close()
    except Exception:
        pass

    return "\n".join(collected_text)[:20000], crawled_urls
