"""PhantomAPI — Browser automation engine.

Launches a persistent headless Chrome instance via Playwright
and interacts with chatgpt.com to generate responses.

Also exposes search_web() and fetch_url() for the agentic search feature.
"""

import asyncio
import threading
import urllib.parse
from urllib.parse import urlparse, parse_qs

from app.config import settings


class BrowserEngine(threading.Thread):
    """A dedicated thread that runs an async Playwright browser.

    This avoids blocking the FastAPI event loop while still giving
    us a persistent browser instance that can handle sequential requests.
    """

    _STEALTH_UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        self.browser = None
        self.playwright = None

    # ------------------------------------------------------------------
    # Thread lifecycle
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Thread entry point — start browser and run the event loop forever."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._launch())
        self.ready.set()
        print("[PhantomAPI] ⚡ Browser engine ready.")
        self.loop.run_forever()

    async def _launch(self) -> None:
        """Launch a stealth Chromium browser."""
        from playwright.async_api import async_playwright

        print("[PhantomAPI] 🚀 Launching browser...")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=settings.HEADLESS,
            channel="chrome",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
            ],
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_ready(self) -> None:
        if not self.ready.wait(timeout=30) or self.browser is None:
            raise RuntimeError("Browser engine is not ready. Is Chrome installed?")

    async def _new_context(self, viewport_w: int = 1280, viewport_h: int = 800):
        return await self.browser.new_context(
            user_agent=self._STEALTH_UA,
            viewport={"width": viewport_w, "height": viewport_h},
        )

    # ------------------------------------------------------------------
    # Public API — ChatGPT chat
    # ------------------------------------------------------------------

    def chat(self, prompt: str) -> str:
        """Send a prompt to ChatGPT and return the response text.

        This is a blocking call that schedules work on the browser
        thread's event loop and waits for the result.
        """
        self._require_ready()
        future = asyncio.run_coroutine_threadsafe(
            self._interact(prompt), self.loop
        )
        return future.result(timeout=settings.BROWSER_TIMEOUT // 1000 + 30)

    # ------------------------------------------------------------------
    # Public API — web search & page fetch
    # ------------------------------------------------------------------

    def search_web(self, query: str) -> list[dict]:
        """Search the web for *query* and return up to 8 result dicts.

        Tries DuckDuckGo HTML (no JS) first, falls back to Google.
        Each result has keys: title, url, snippet.
        """
        self._require_ready()
        future = asyncio.run_coroutine_threadsafe(
            self._search_web_async(query), self.loop
        )
        return future.result(timeout=60)

    def fetch_url(self, url: str) -> dict:
        """Fetch readable content from *url* using Playwright.

        Returns a dict with keys: title, url, tables (markdown), content (text).
        """
        self._require_ready()
        future = asyncio.run_coroutine_threadsafe(
            self._fetch_url_async(url), self.loop
        )
        return future.result(timeout=60)

    # ------------------------------------------------------------------
    # Private — ChatGPT interaction
    # ------------------------------------------------------------------

    async def _interact(self, prompt: str) -> str:
        """Open a new ChatGPT session, send the prompt, and scrape the reply."""
        context = await self.browser.new_context(
            user_agent=self._STEALTH_UA,
            viewport={"width": 1920, "height": 1080},
        )

        # Hide the webdriver flag so ChatGPT thinks we're a real user
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = await context.new_page()

        try:
            page.set_default_timeout(settings.BROWSER_TIMEOUT)

            # Navigate to ChatGPT
            await page.goto("https://chatgpt.com/", wait_until="domcontentloaded")

            # Type the prompt
            await page.wait_for_selector("#prompt-textarea", timeout=60000)
            await page.fill("#prompt-textarea", prompt)
            await asyncio.sleep(0.5)
            await page.press("#prompt-textarea", "Enter")

            # Wait for the assistant to start responding
            await page.wait_for_selector(
                '[data-message-author-role="assistant"]',
                timeout=settings.BROWSER_TIMEOUT,
            )

            # Poll until the response stabilises (no new text for ~2 seconds)
            last_text = ""
            unchanged_count = 0
            while unchanged_count < 4:
                elements = await page.query_selector_all(
                    '[data-message-author-role="assistant"]'
                )
                if elements:
                    current_text = await elements[-1].inner_text()
                    if current_text == last_text and current_text.strip():
                        unchanged_count += 1
                    else:
                        last_text = current_text
                        unchanged_count = 0
                await asyncio.sleep(0.5)

            return last_text.strip()

        except Exception as exc:
            print(f"[PhantomAPI] ❌ Browser error: {exc}")
            raise
        finally:
            await page.close()
            await context.close()

    # ------------------------------------------------------------------
    # Private — web search (DDG → Google fallback)
    # ------------------------------------------------------------------

    async def _search_web_async(self, query: str) -> list[dict]:
        """Try DuckDuckGo HTML, fall back to Google if no results."""
        ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        print(f"[PhantomAPI] 🔍 Searching DDG: {query}")

        context = await self._new_context()
        page = await context.new_page()
        results = []
        try:
            page.set_default_timeout(30000)
            await page.goto(ddg_url, wait_until="domcontentloaded")

            try:
                await page.wait_for_selector(".result", timeout=10000)
            except Exception:
                print("[PhantomAPI] No .result elements on DDG page.")

            elements = await page.query_selector_all(".result")
            for element in elements[:8]:
                title_el = await element.query_selector(".result__title")
                snippet_el = await element.query_selector(".result__snippet")

                title = (await title_el.inner_text()).strip() if title_el else ""
                snippet = (await snippet_el.inner_text()).strip() if snippet_el else ""

                link_el = await title_el.query_selector("a") if title_el else None
                raw_href = (await link_el.get_attribute("href") or "").strip() if link_el else ""
                link = self._resolve_ddg_url(raw_href)

                if title and link:
                    results.append({"title": title, "url": link, "snippet": snippet})

        except Exception as exc:
            print(f"[PhantomAPI] DDG search error: {exc}")
        finally:
            await page.close()
            await context.close()

        if results:
            return results

        # Fallback to Google
        print("[PhantomAPI] ↩ Falling back to Google search.")
        return await self._search_google_async(query)

    def _resolve_ddg_url(self, href: str) -> str:
        """Unwrap a DDG redirect URL to the real target URL."""
        if not href:
            return ""
        if href.startswith("//"):
            href = "https:" + href
        if "uddg=" in href:
            qs = parse_qs(urlparse(href).query)
            if "uddg" in qs:
                return qs["uddg"][0]
        return href

    async def _search_google_async(self, query: str) -> list[dict]:
        """Scrape Google search results as a fallback."""
        google_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        context = await self._new_context(1280, 900)
        page = await context.new_page()
        results = []
        try:
            page.set_default_timeout(30000)
            await page.goto(google_url, wait_until="domcontentloaded")

            try:
                await page.wait_for_selector("div.g", timeout=10000)
            except Exception:
                pass

            elements = await page.query_selector_all("div.g")
            for element in elements[:8]:
                title_el = await element.query_selector("h3")
                link_el = await element.query_selector("a")
                # Try two common Google snippet selectors
                snippet_el = await element.query_selector("div.VwiC3b")
                if not snippet_el:
                    snippet_el = await element.query_selector("[data-sncf]")

                title = (await title_el.inner_text()).strip() if title_el else ""
                link = (await link_el.get_attribute("href") or "").strip() if link_el else ""
                snippet = (await snippet_el.inner_text()).strip() if snippet_el else ""

                if title and link and link.startswith("http"):
                    results.append({"title": title, "url": link, "snippet": snippet})

        except Exception as exc:
            print(f"[PhantomAPI] Google search error: {exc}")
        finally:
            await page.close()
            await context.close()

        return results

    # ------------------------------------------------------------------
    # Private — webpage content fetching
    # ------------------------------------------------------------------

    async def _fetch_url_async(self, url: str) -> dict:
        """Load a URL with Playwright and extract readable text + tables."""
        print(f"[PhantomAPI] 📄 Fetching: {url}")
        context = await self._new_context(1280, 900)
        page = await context.new_page()
        try:
            page.set_default_timeout(30000)
            await page.goto(url, wait_until="load")
            await asyncio.sleep(2)  # Allow JS-rendered content to settle

            extract_script = """
            () => {
                // Collect table data as markdown-style text
                const tables = [];
                document.querySelectorAll('table').forEach((table, idx) => {
                    let text = `\\n[Table ${idx + 1}]\\n`;
                    table.querySelectorAll('tr').forEach(row => {
                        const cells = Array.from(row.querySelectorAll('th, td'))
                            .map(c => c.innerText.trim().replace(/\\s+/g, ' '));
                        if (cells.length > 0) {
                            text += '| ' + cells.join(' | ') + ' |\\n';
                        }
                    });
                    tables.push(text);
                });

                // Remove noise elements
                document.querySelectorAll(
                    'script, style, nav, footer, iframe, noscript, svg, header, form, aside'
                ).forEach(el => el.remove());

                // Extract readable text nodes
                const parts = [];
                document.querySelectorAll('h1, h2, h3, h4, h5, p, li, pre, td, th').forEach(el => {
                    const text = el.innerText.trim().replace(/\\s+/g, ' ');
                    if (text.length > 10 && text.length < 2000) {
                        parts.push(text);
                    }
                });

                return {
                    title: document.title,
                    url: window.location.href,
                    tables: tables.join('\\n'),
                    content: parts.slice(0, 200).join('\\n')
                };
            }
            """
            return await page.evaluate(extract_script)

        except Exception as exc:
            print(f"[PhantomAPI] ❌ Error fetching {url}: {exc}")
            return {
                "title": "",
                "url": url,
                "tables": "",
                "content": f"Failed to fetch page: {exc}",
            }
        finally:
            await page.close()
            await context.close()


# ---------------------------------------------------------------------------
# Singleton — created once at import time, started in app lifespan
# ---------------------------------------------------------------------------
engine = BrowserEngine()
