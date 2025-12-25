"""
Playwright-only WebSearchTool implementation.
"""

import logging
import time
import asyncio
from typing import Optional

from browser_session import create_playwright_browser
from search_engine import search_brave_playwright, search_images_brave_playwright, search_startpage, search_yahoo, search_yandex
from content_scraper import scrape_parallel_playwright

# Check if src module exists
try:
    from src.data_models import SearchAndScrapeResult, ScrapedContent
    from src.exceptions import SearchError, WebSearchError
except ImportError:
    # Define minimal versions if src doesn't exist
    class SearchError(Exception):
        pass
    
    class WebSearchError(Exception):
        pass
    
    class ScrapedContent:
        def __init__(self, url, title, content, word_count, success, error, images):
            self.url = url
            self.title = title
            self.content = content
            self.word_count = word_count
            self.success = success
            self.error = error
            self.images = images
    
    class SearchAndScrapeResult:
        def __init__(self, query, engine, results, total_time):
            self.query = query
            self.engine = engine
            self.results = results
            self.total_time = total_time
        
        def to_dict(self):
            return {
                'query': self.query,
                'engine': self.engine,
                'results': [
                    {
                        'url': r.url,
                        'title': r.title,
                        'content': r.content,
                        'word_count': r.word_count,
                        'success': r.success,
                        'error': r.error,
                        'images': r.images
                    } for r in self.results
                ],
                'total_time': self.total_time
            }

logger = logging.getLogger(__name__)


def is_llm_readable(text: str) -> bool:
    """
    Check if text is readable by LLMs (English, Hindi, and other major languages).
    Accepts any text that's not just symbols/garbage.
    """
    if not text or len(text) < 10:
        return False
    
    # Count alphanumeric characters (letters from any language + numbers)
    alphanumeric_count = sum(1 for c in text if c.isalnum() or c.isspace())
    total_count = len(text)
    
    # At least 70% should be alphanumeric (letters/numbers from any language)
    # This accepts English, Hindi, Chinese, Arabic, etc.
    return (alphanumeric_count / total_count) >= 0.7


class WebSearchToolPlaywright:
    """
    Web search and scraping tool using only Playwright.
    
    Example:
        tool = WebSearchToolPlaywright()
        result = await tool.search_and_scrape("python tutorials", k=5)
        print(f"Found {len(result.results)} results in {result.total_time:.2f}s")
    """
    
    def __init__(self, resource_monitor: Optional['ResourceMonitor'] = None):
        """
        Initialize Playwright-only web search tool.
        
        Args:
            resource_monitor: Optional ResourceMonitor for Lambda environment
                             to enable adaptive parallelism and timeout handling
        """
        self.resource_monitor = resource_monitor
    
    async def search_and_scrape(
        self,
        query: str,
        k: int = 5,
        engine: str = "brave",
        include_images: bool = False,
        lambda_context: Optional[object] = None
    ) -> SearchAndScrapeResult:
        """
        Search for query and scrape top k results using only Playwright.
        
        Args:
            query: Search query string
            k: Number of results to scrape (default: 5)
            engine: Search engine to use (default: "brave")
            include_images: Whether to search for images only (default: False)
            lambda_context: Optional AWS Lambda context for timeout awareness
            
        Returns:
            SearchAndScrapeResult with scraped content from top k URLs
            
        Raises:
            SearchError: If search fails or URL extraction fails
            WebSearchError: If browser session cannot be created
            ValueError: If unsupported search engine is specified
        """
        # Log memory usage at start if resource monitor is available
        if self.resource_monitor:
            memory_usage = self.resource_monitor.get_memory_usage_mb()
            memory_available = self.resource_monitor.get_memory_available_mb()
            logger.info(f"Starting search - Memory: {memory_usage:.1f}MB used, {memory_available:.1f}MB available")
            if lambda_context:
                time_remaining = self.resource_monitor.get_time_remaining_seconds(lambda_context)
                logger.info(f"Starting search - Time remaining: {time_remaining:.1f}s")
        
        logger.info(f"Starting Playwright search_and_scrape: query='{query}', k={k}, engine={engine}")
        
        start_time = time.time()
        
        try:
            if engine not in ["brave"]:
                error_msg = f"Unsupported search engine: {engine}. Only 'brave' is supported."
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            async with create_playwright_browser() as (page, context):
                if include_images:
                    # Images only mode - just search for images
                    logger.info(f"Searching for images only...")
                    image_urls = await search_images_brave_playwright(page, query, k)
                    urls = []
                    scraped_contents = []
                    actual_engine = "bing"  # Images are from Bing
                    
                    # Create dummy results with just image URLs
                    for img_url in image_urls:
                        scraped_contents.append(ScrapedContent(
                            url=img_url,
                            title="",
                            content="",
                            word_count=0,
                            success=True,
                            error=None,
                            images=[img_url]
                        ))
                else:
                    # OPTIMIZATION: Dynamic timeout and buffer based on request size
                    timeout = 10000  # 10 seconds per page - ensures quality content from slow sites
                    
                    # Adaptive parallelism based on memory usage
                    if self.resource_monitor and self.resource_monitor.should_reduce_parallelism():
                        max_parallel = 5  # Reduce parallelism when memory is constrained
                        logger.warning(f"Memory usage high, reducing parallelism to {max_parallel} tabs")
                    else:
                        max_parallel = 11  # Default parallelism - optimized for 10GB memory
                    
                    if k <= 5:
                        search_k = k + 3  # Buffer for small requests (k<=5)
                    elif k <= 10:
                        search_k = k + 4  # Buffer for medium requests (6-10)
                    else:
                        search_k = k + 5  # Larger buffer for big requests (>10)
                    
                    # Aggressive duplicate filtering: normalize URLs
                    def normalize_url(url: str) -> str:
                        """Normalize URL for duplicate detection (remove trailing slashes, fragments, etc)"""
                        url = url.rstrip('/')
                        if '#' in url:
                            url = url.split('#')[0]
                        if '?' in url:
                            # Keep query params but normalize
                            url = url.lower()
                        return url
                    
                    # Block low-quality URLs (social media, forums, etc.)
                    def is_blocked_url(url: str) -> bool:
                        """Check if URL should be blocked (social media, forums, etc.)"""
                        blocked_domains = [
                            'reddit.com',
                            'facebook.com',
                            'twitter.com',
                            'x.com',
                            'instagram.com',
                            'tiktok.com',
                            'pinterest.com',
                            'youtube.com',
                            'mastodon.social/@',  # Block Mastodon profiles
                        ]
                        url_lower = url.lower()
                        return any(blocked in url_lower for blocked in blocked_domains)
                    
                    # OPTIMIZATION: Search and scrape in parallel (don't wait for search to finish)
                    logger.info(f"Searching Brave (need {k} URLs, searching for {search_k} with buffer)...")
                    
                    try:
                        brave_urls = await search_brave_playwright(page, query, search_k)
                    except Exception as e:
                        logger.error(f"Brave search failed: {e}")
                        brave_urls = []
                    
                    # Remove duplicates and blocked URLs from Brave results
                    seen_normalized = set()
                    unique_brave_urls = []
                    blocked_count = 0
                    for url in brave_urls:
                        if is_blocked_url(url):
                            blocked_count += 1
                            continue
                        normalized = normalize_url(url)
                        if normalized not in seen_normalized:
                            seen_normalized.add(normalized)
                            unique_brave_urls.append(url)
                    
                    if blocked_count > 0:
                        logger.info(f"Blocked {blocked_count} low-quality URLs (social media, forums, etc.)")
                    
                    logger.info(f"Brave: {len(unique_brave_urls)} unique URLs (filtered from {len(brave_urls)})")
                    
                    # OPTIMIZATION: Scrape URLs in batches (memory-efficient for Lambda)
                    # Early return once we have k successful results
                    valid_results = []
                    actual_engine = "brave"  # Track which engine provided results
                    
                    if unique_brave_urls:
                        # Check if approaching timeout before scraping
                        if self.resource_monitor and lambda_context:
                            if self.resource_monitor.should_return_partial_results(lambda_context):
                                logger.warning("Approaching timeout, skipping scraping and returning empty results")
                                valid_results = []
                            else:
                                logger.info(f"Scraping {len(unique_brave_urls)} URLs with {max_parallel} parallel tabs...")
                                all_scraped = await scrape_parallel_playwright(unique_brave_urls, context, max_parallel=max_parallel, timeout=timeout)
                                
                                # Filter valid results
                                for content in all_scraped:
                                    if content.success and content.word_count >= 50:
                                        if ('403' not in content.title and 
                                            'Forbidden' not in content.title and
                                            '404' not in content.title and
                                            'Not Found' not in content.title and
                                            is_llm_readable(content.content)):
                                            valid_results.append(content)
                                            if len(valid_results) >= k:
                                                break  # Stop once we have k valid results
                                    
                                    # Check timeout after each result
                                    if self.resource_monitor and lambda_context:
                                        if self.resource_monitor.should_return_partial_results(lambda_context):
                                            logger.warning(f"Approaching timeout, returning {len(valid_results)} partial results")
                                            break
                        else:
                            logger.info(f"Scraping {len(unique_brave_urls)} URLs with {max_parallel} parallel tabs...")
                            all_scraped = await scrape_parallel_playwright(unique_brave_urls, context, max_parallel=max_parallel, timeout=timeout)
                            
                            # Filter valid results
                            for content in all_scraped:
                                if content.success and content.word_count >= 50:
                                    if ('403' not in content.title and 
                                        'Forbidden' not in content.title and
                                        '404' not in content.title and
                                        'Not Found' not in content.title and
                                        is_llm_readable(content.content)):
                                        valid_results.append(content)
                                        if len(valid_results) >= k:
                                            break  # Stop once we have k valid results
                    
                    logger.info(f"Got {len(valid_results)}/{k} valid results from Brave")
                    
                    # Fallback chain: Brave -> Startpage -> Yahoo -> Yandex
                    engines_used = ["brave"] if len(valid_results) > 0 else []
                    
                    # Determine acceptable shortage based on k
                    if k <= 10:
                        acceptable_shortage = 2  # For k<=10, can be 2 short
                    else:
                        acceptable_shortage = 4  # For k>10, can be 4 short
                    
                    # Try Startpage if Brave failed completely OR shortage exceeds acceptable limit
                    needed = k - len(valid_results)
                    brave_failed = len(unique_brave_urls) == 0
                    
                    if needed > 0 and (brave_failed or needed > acceptable_shortage):
                        logger.info(f"Need {needed} more (have {len(valid_results)}/{k}), trying Startpage...")
                        
                        # Determine search buffer based on what's actually needed
                        if needed <= 5:
                            startpage_search_k = needed + 3
                        elif needed <= 10:
                            startpage_search_k = needed + 4
                        else:
                            startpage_search_k = needed + 5
                        
                        # If Brave completely failed, search for full k
                        if brave_failed:
                            startpage_search_k = search_k
                            logger.info(f"Brave failed completely, searching Startpage for all results (k={startpage_search_k})")
                        
                        try:
                            startpage_page = await context.new_page()
                            startpage_urls = await search_startpage(startpage_page, query, startpage_search_k)
                            await startpage_page.close()
                        except Exception as e:
                            logger.error(f"Failed to create Startpage page (context may be closed): {e}")
                            startpage_urls = []
                        
                        # Only scrape unique URLs not found by Brave
                        unique_startpage_urls = []
                        for url in startpage_urls:
                            if is_blocked_url(url):
                                continue
                            normalized = normalize_url(url)
                            if normalized not in seen_normalized:
                                seen_normalized.add(normalized)
                                unique_startpage_urls.append(url)
                        
                        logger.info(f"Startpage: {len(unique_startpage_urls)} unique URLs (filtered from {len(startpage_urls)})")
                        
                        if unique_startpage_urls:
                            # Check timeout before scraping
                            if self.resource_monitor and lambda_context and self.resource_monitor.should_return_partial_results(lambda_context):
                                logger.warning(f"Approaching timeout, returning {len(valid_results)} partial results")
                            else:
                                logger.info(f"Scraping {len(unique_startpage_urls)} unique Startpage URLs with {max_parallel} parallel tabs...")
                                startpage_scraped = await scrape_parallel_playwright(unique_startpage_urls, context, max_parallel=max_parallel, timeout=timeout)
                                
                                for content in startpage_scraped:
                                    if content.success and content.word_count >= 50:
                                        if ('403' not in content.title and 
                                            'Forbidden' not in content.title and
                                            '404' not in content.title and
                                            'Not Found' not in content.title and
                                            is_llm_readable(content.content)):
                                            valid_results.append(content)
                                            if len(valid_results) >= k:
                                                break
                                    
                                    # Check timeout after each result
                                    if self.resource_monitor and lambda_context:
                                        if self.resource_monitor.should_return_partial_results(lambda_context):
                                            logger.warning(f"Approaching timeout, returning {len(valid_results)} partial results")
                                            break
                                
                                if len(startpage_scraped) > 0:
                                    engines_used.append("startpage")
                                    logger.info(f"Got {len(valid_results)}/{k} valid results after Startpage")
                    
                    # Try Yahoo if still needed
                    needed = k - len(valid_results)
                    both_failed = brave_failed and len(valid_results) == 0
                    
                    if needed > 0 and (both_failed or needed > acceptable_shortage):
                        logger.info(f"Need {needed} more, trying Yahoo...")
                        
                        # Determine search buffer based on what's actually needed
                        if needed <= 5:
                            yahoo_search_k = needed + 3
                        elif needed <= 10:
                            yahoo_search_k = needed + 4
                        else:
                            yahoo_search_k = needed + 5
                        
                        # If both Brave and Startpage failed, search for full k
                        if both_failed:
                            yahoo_search_k = search_k
                            logger.info(f"Brave and Startpage failed, searching Yahoo for all results (k={yahoo_search_k})")
                        
                        try:
                            yahoo_page = await context.new_page()
                            yahoo_urls = await search_yahoo(yahoo_page, query, yahoo_search_k)
                            await yahoo_page.close()
                        except Exception as e:
                            logger.error(f"Failed to create Yahoo page (context may be closed): {e}")
                            yahoo_urls = []
                        
                        # Only scrape unique URLs not found by previous engines
                        unique_yahoo_urls = []
                        for url in yahoo_urls:
                            if is_blocked_url(url):
                                continue
                            normalized = normalize_url(url)
                            if normalized not in seen_normalized:
                                seen_normalized.add(normalized)
                                unique_yahoo_urls.append(url)
                        
                        logger.info(f"Yahoo: {len(unique_yahoo_urls)} unique URLs (filtered from {len(yahoo_urls)})")
                        
                        if unique_yahoo_urls:
                            # Check timeout before scraping
                            if self.resource_monitor and lambda_context and self.resource_monitor.should_return_partial_results(lambda_context):
                                logger.warning(f"Approaching timeout, returning {len(valid_results)} partial results")
                            else:
                                logger.info(f"Scraping {len(unique_yahoo_urls)} unique Yahoo URLs with {max_parallel} parallel tabs...")
                                yahoo_scraped = await scrape_parallel_playwright(unique_yahoo_urls, context, max_parallel=max_parallel, timeout=timeout)
                                
                                for content in yahoo_scraped:
                                    if content.success and content.word_count >= 50:
                                        if ('403' not in content.title and 
                                            'Forbidden' not in content.title and
                                            '404' not in content.title and
                                            'Not Found' not in content.title and
                                            is_llm_readable(content.content)):
                                            valid_results.append(content)
                                            if len(valid_results) >= k:
                                                break
                                    
                                    # Check timeout after each result
                                    if self.resource_monitor and lambda_context:
                                        if self.resource_monitor.should_return_partial_results(lambda_context):
                                            logger.warning(f"Approaching timeout, returning {len(valid_results)} partial results")
                                            break
                                
                                if len(yahoo_scraped) > 0:
                                    engines_used.append("yahoo")
                                    logger.info(f"Got {len(valid_results)}/{k} valid results after Yahoo")
                    
                    # Try Yandex if still needed
                    needed = k - len(valid_results)
                    all_failed = brave_failed and len(valid_results) == 0
                    
                    if needed > 0 and (all_failed or needed > acceptable_shortage):
                        logger.info(f"Need {needed} more, trying Yandex...")
                        
                        # Determine search buffer based on what's actually needed
                        if needed <= 5:
                            yandex_search_k = needed + 3
                        elif needed <= 10:
                            yandex_search_k = needed + 4
                        else:
                            yandex_search_k = needed + 5
                        
                        # If all previous engines failed, search for full k
                        if all_failed:
                            yandex_search_k = search_k
                            logger.info(f"All previous engines failed, searching Yandex for all results (k={yandex_search_k})")
                        
                        try:
                            yandex_page = await context.new_page()
                            yandex_urls = await search_yandex(yandex_page, query, yandex_search_k)
                            await yandex_page.close()
                        except Exception as e:
                            logger.error(f"Failed to create Yandex page (context may be closed): {e}")
                            yandex_urls = []
                        
                        # Only scrape unique URLs not found by previous engines
                        unique_yandex_urls = []
                        for url in yandex_urls:
                            if is_blocked_url(url):
                                continue
                            normalized = normalize_url(url)
                            if normalized not in seen_normalized:
                                seen_normalized.add(normalized)
                                unique_yandex_urls.append(url)
                        
                        logger.info(f"Yandex: {len(unique_yandex_urls)} unique URLs (filtered from {len(yandex_urls)})")
                        
                        if unique_yandex_urls:
                            # Check timeout before scraping
                            if self.resource_monitor and lambda_context and self.resource_monitor.should_return_partial_results(lambda_context):
                                logger.warning(f"Approaching timeout, returning {len(valid_results)} partial results")
                            else:
                                logger.info(f"Scraping {len(unique_yandex_urls)} unique Yandex URLs with {max_parallel} parallel tabs...")
                                yandex_scraped = await scrape_parallel_playwright(unique_yandex_urls, context, max_parallel=max_parallel, timeout=timeout)
                                
                                for content in yandex_scraped:
                                    if content.success and content.word_count >= 50:
                                        if ('403' not in content.title and 
                                            'Forbidden' not in content.title and
                                            '404' not in content.title and
                                            'Not Found' not in content.title and
                                            is_llm_readable(content.content)):
                                            valid_results.append(content)
                                            if len(valid_results) >= k:
                                                break
                                    
                                    # Check timeout after each result
                                    if self.resource_monitor and lambda_context:
                                        if self.resource_monitor.should_return_partial_results(lambda_context):
                                            logger.warning(f"Approaching timeout, returning {len(valid_results)} partial results")
                                            break
                                
                                if len(yandex_scraped) > 0:
                                    engines_used.append("yandex")
                                    logger.info(f"Got {len(valid_results)}/{k} valid results after Yandex")
                    
                    # Set actual engine name
                    if len(engines_used) == 0:
                        actual_engine = "none"
                    elif len(engines_used) == 1:
                        actual_engine = engines_used[0]
                    else:
                        actual_engine = "+".join(engines_used)
                    
                    logger.info(f"Got {len(valid_results)} valid results total from: {actual_engine}")
                    
                    scraped_contents = valid_results[:k]  # Take only k results
                
                # Use scraped_contents for both modes (already limited to k)
                if include_images:
                    scraped_contents = scraped_contents  # Already created above for images
            
            # Step 5: Calculate total time and create result
            total_time = time.time() - start_time
            
            # Log completion metrics including memory usage
            if self.resource_monitor:
                memory_usage = self.resource_monitor.get_memory_usage_mb()
                memory_available = self.resource_monitor.get_memory_available_mb()
                logger.info(f"search_and_scrape complete: {len(scraped_contents)} results returned, {total_time:.2f}s total")
                logger.info(f"Completion metrics - Memory: {memory_usage:.1f}MB used, {memory_available:.1f}MB available, Time: {total_time:.2f}s")
                if lambda_context:
                    time_remaining = self.resource_monitor.get_time_remaining_seconds(lambda_context)
                    logger.info(f"Completion metrics - Time remaining: {time_remaining:.1f}s")
            else:
                logger.info(f"search_and_scrape complete: {len(scraped_contents)} results returned, {total_time:.2f}s total")
            
            return SearchAndScrapeResult(
                query=query,
                engine=actual_engine,  # Use actual engine that provided results
                results=scraped_contents,
                total_time=total_time
            )
            
        except (SearchError, WebSearchError, ValueError):
            raise
        except Exception as e:
            error_msg = f"Unexpected error in search_and_scrape: {str(e)}"
            logger.error(error_msg)
            raise WebSearchError(error_msg)
