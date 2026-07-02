import asyncio
import re
from typing import Optional
from urllib.parse import urlparse, urljoin
from loguru import logger
from new.agents.base import BaseAgent, LLMClient, EventCallback
from new.rate_limiter import DomainRateLimiter
from new.config import settings


class ScraperAgent(BaseAgent):
    def __init__(
        self,
        llm_client: LLMClient = None,
        on_event: EventCallback = None,
        rate_limiter: DomainRateLimiter = None,
    ):
        super().__init__("scraper", llm_client, on_event)
        self.rate_limiter = rate_limiter or DomainRateLimiter(
            settings.rate_limit_per_domain
        )
        self._browser = None
        self._context = None

    async def _ensure_browser(self):
        if self._browser is None:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=settings.playwright_headless
            )
            self._context = await self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )

    async def _extract_links(self, html: str, base_url: str) -> list[str]:
        links = set()
        for m in re.finditer(r'href=["\'](.*?)["\']', html, re.IGNORECASE):
            href = m.group(1)
            full = urljoin(base_url, href)
            if full.startswith(("http://", "https://")):
                links.add(full)
        return list(links)

    async def _scrape_page(self, url: str) -> tuple[Optional[str], Optional[str]]:
        """Scrape a single page.

        Returns ``(content, final_url)`` on success. On any failure
        (Playwright timeout, network error, etc.) logs URL + error and
        returns ``(None, None)`` without raising so the agent pipeline
        can degrade gracefully.
        """
        await self.rate_limiter.wait(url)
        await self._ensure_browser()
        page = await self._context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(1)
            content = await page.content()
            return content, page.url
        except Exception as e:
            logger.error(
                "[AGENT:ScraperAgent] _scrape_page failed for url={}: {}: {}",
                url,
                type(e).__name__,
                e,
            )
            return None, None
        finally:
            await page.close()

    async def _find_pagination_urls(self, html: str, base_url: str) -> list[str]:
        parsed = urlparse(base_url)
        page_urls = set()
        for m in re.finditer(
            r'href=["\']([^"\']*?)["\']', html, re.IGNORECASE
        ):
            href = m.group(1)
            full = urljoin(base_url, href)
            if (
                full.startswith((f"{parsed.scheme}://{parsed.netloc}",))
                and parsed.netloc
            ):
                if re.search(r"[?&]page=\d+|/page/\d+|/jobs\b", full, re.I):
                    page_urls.add(full)
        return sorted(page_urls)

    async def run(self, context: dict) -> dict:
        run_id = context.get("run_id", "?")
        url = context.get("url", "")
        max_pages = context.get("max_pages", 3)
        logger.info("[AGENT:ScraperAgent] run() ENTERED for run_id={}", run_id)
        if not url:
            logger.warning("ScraperAgent: no URL provided")
            await self.emit("failed", "No URL provided")
            return {"pages": [], "error": "No URL provided"}

        await self.emit("started", f"Starting scraper for {url}")
        pages = []
        errors = []

        try:
            content, final_url = await self._scrape_page(url)
            if content is None or final_url is None:
                error_msg = f"Failed to scrape {url}"
                logger.error("[AGENT:ScraperAgent] {}", error_msg)
                await self.emit("failed", error_msg[:100])
                return {"pages": pages, "error": error_msg}
            title_match = re.search(r"<title>(.*?)</title>", content, re.DOTALL | re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else final_url
            pages.append({"url": final_url, "html": content, "page_num": 1, "title": title})
            await self.emit(
                "progress",
                f"Scraped page 1: {title[:80]}",
            )

            if max_pages > 1:
                pagination_urls = await self._find_pagination_urls(content, url)
                seen = {final_url}
                # ``max_pages - 1`` caps the slice so pagination can never
                # loop infinitely even if ``_find_pagination_urls`` returns
                # many URLs or duplicates.
                for i, page_url in enumerate(pagination_urls[: max_pages - 1], start=2):
                    if page_url in seen:
                        continue
                    seen.add(page_url)
                    p_content, p_final = await self._scrape_page(page_url)
                    if p_content is None or p_final is None:
                        errors.append(f"Page {i}: scrape failed")
                        await self.emit(
                            "progress",
                            f"Failed page {i}: scrape failed",
                        )
                        continue
                    p_title_match = re.search(
                        r"<title>(.*?)</title>", p_content, re.DOTALL | re.IGNORECASE
                    )
                    p_title = p_title_match.group(1).strip() if p_title_match else p_final
                    pages.append(
                        {
                            "url": p_final,
                            "html": p_content,
                            "page_num": i,
                            "title": p_title,
                        }
                    )
                    await self.emit(
                        "progress",
                        f"Scraped page {i}: {p_title[:80]}",
                    )

            await self.emit(
                "completed",
                f"Scraped {len(pages)} page(s), {len(errors)} error(s)",
            )
            return {"pages": pages, "errors": errors, "domain": urlparse(url).hostname or url}

        except Exception as e:
            logger.exception(
                "[AGENT:ScraperAgent] unexpected error in run() for url={}: {}",
                url,
                e,
            )
            await self.emit("failed", f"Scraper error: {str(e)[:100]}")
            return {"pages": pages, "error": str(e)}

    async def cleanup(self):
        if self._browser:
            await self._browser.close()
        if hasattr(self, "_playwright"):
            await self._playwright.stop()
