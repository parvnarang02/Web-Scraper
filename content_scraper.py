"""
Playwright-only content scraping.
Uses Playwright for all scraping operations (no requests/BeautifulSoup).
"""

import asyncio
import logging
from typing import List, Optional
from playwright.async_api import Page, Browser, BrowserContext
try:
    from src.data_models import ScrapedContent
except ImportError:
    # Define minimal version if src doesn't exist
    class ScrapedContent:
        def __init__(self, url, title, content, word_count, success, error, images):
            self.url = url
            self.title = title
            self.content = content
            self.word_count = word_count
            self.success = success
            self.error = error
            self.images = images

logger = logging.getLogger(__name__)


async def scrape_url_playwright(url: str, page: Page, timeout: int = 4000) -> ScrapedContent:
    """
    Scrape a URL using Playwright.
    
    Args:
        url: URL to scrape
        page: Playwright Page object
        timeout: Timeout in milliseconds (default: 4000ms = 4s)
        
    Returns:
        ScrapedContent with extracted text, title, images, and word count.
    """
    try:
        logger.info(f"📥 Scraping with Playwright: {url}")
        
        # Load page and wait for DOM to be ready
        # domcontentloaded = HTML parsed, scripts loaded (needed for dynamic content)
        await page.goto(url, wait_until='domcontentloaded', timeout=timeout)
        result = await page.evaluate('''() => {
            const main = document.querySelector('main') || 
                        document.querySelector('article') || 
                        document.body;
            
            return {
                title: document.title || '',
                content: main ? main.innerText : ''
            };
        }''')
        
        # Fast text processing
        content = ' '.join(result['content'].split())
        word_count = len(content.split())
        
        logger.info(f"✅ Successfully scraped {url}: {word_count} words")
        return ScrapedContent(
            url=url,
            title=result['title'],
            content=content,
            word_count=word_count,
            success=True,
            error=None,
            images=[]
        )
        
    except Exception as e:
        error_msg = f"Playwright scraping error: {str(e)}"
        logger.warning(f"❌ Error scraping {url}: {error_msg}")
        return ScrapedContent(
            url=url,
            title="",
            content="",
            word_count=0,
            success=False,
            error=error_msg,
            images=[]
        )


async def scrape_parallel_playwright(urls: List[str], context: BrowserContext, max_parallel: int = 15, timeout: int = 10000) -> List[ScrapedContent]:
    """
    Scrape multiple URLs using Playwright with parallel tabs.
    Uses batching to limit memory usage (important for Lambda/serverless).
    
    Args:
        urls: List of URLs to scrape
        context: Playwright BrowserContext to create new pages
        max_parallel: Maximum number of parallel tabs (default: 15 for Lambda compatibility)
        timeout: Timeout per URL in milliseconds (default: 10000ms = 10s)
        
    Returns:
        List of ScrapedContent objects (one per URL, in same order)
    """
    if not urls:
        logger.warning("⚠️  scrape_parallel_playwright called with empty URL list")
        return []
    
    logger.info(f"🚀 Starting Playwright scrape of {len(urls)} URLs (up to {max_parallel} tabs in parallel)")
    
    async def scrape_in_new_tab(url: str, index: int) -> tuple:
        """Scrape URL in a new browser tab"""
        new_page = None
        try:
            new_page = await context.new_page()
            result = await scrape_url_playwright(url, new_page, timeout)
            return index, result
        except Exception as e:
            # If page creation or scraping fails, return error result
            logger.error(f"Failed to scrape {url}: {e}")
            return index, ScrapedContent(
                url=url,
                title="",
                content="",
                word_count=0,
                success=False,
                error=f"Scraping failed: {str(e)}",
                images=[]
            )
        finally:
            if new_page:
                try:
                    await new_page.close()
                except Exception as e:
                    logger.warning(f"Failed to close page for {url}: {e}")
    
    # Process URLs in batches to limit memory usage
    results = [None] * len(urls)
    
    # Process in batches of max_parallel
    for batch_start in range(0, len(urls), max_parallel):
        batch_end = min(batch_start + max_parallel, len(urls))
        batch_urls = urls[batch_start:batch_end]
        
        # Create tasks for this batch
        tasks = [scrape_in_new_tab(url, batch_start + i) for i, url in enumerate(batch_urls)]
        
        # Run batch in parallel
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Store results
        for item in batch_results:
            if isinstance(item, tuple):
                index, result = item
                results[index] = result
            else:
                # Handle exceptions
                logger.error(f"Task failed with exception: {item}")
    
    successful = sum(1 for r in results if r and r.success)
    failed = len(results) - successful
    logger.info(f"✅ Playwright scrape complete: {successful} successful, {failed} failed")
    
    return results
