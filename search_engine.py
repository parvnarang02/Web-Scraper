"""
Search engine implementations using Playwright.
Supports Brave (primary) and Google (fallback).
"""

import logging
from typing import List
from playwright.async_api import Page
from urllib.parse import quote_plus


class SearchError(Exception):
    pass

logger = logging.getLogger(__name__)


async def search_brave_playwright(page: Page, query: str, k: int = 5) -> List[str]:
    """
    Search Brave using Playwright and extract top k URLs.
    Brave Search is privacy-focused and more bot-friendly.
    
    Args:
        page: Playwright Page object
        query: Search query string
        k: Number of URLs to extract (default: 5)
        
    Returns:
        List of URLs (up to k results)
        
    Raises:
        SearchError: If search fails or URL extraction fails
    """
    try:
        logger.info(f"🔍 Searching Brave with Playwright: '{query}' (k={k})")
        
        # Perform search with English language filter
        search_url = f"https://search.brave.com/search?q={quote_plus(query)}&lang=en"
        logger.info(f"   Navigating to: {search_url}")
        # Fast search - minimal waiting
        await page.goto(search_url, wait_until='domcontentloaded', timeout=3000)
        # Wait for results to render
        await page.wait_for_timeout(800)
        
        # Extract URLs from search results with diversity
        urls = await page.evaluate('''(k) => {
            const results = [];
            const seenDomains = new Set();
            
            // Brave search result selectors
            const selectors = [
                'div.snippet a[href^="http"]',
                'div#results a.result-header[href^="http"]',
                'div.snippet-url-path',
                'a.snippet-url[href^="http"]',
                'div#results a[href^="http"]:not([href*="brave.com"])'
            ];
            
            for (const selector of selectors) {
                const links = document.querySelectorAll(selector);
                if (links.length > 0) {
                    console.log(`Found ${links.length} links with selector: ${selector}`);
                    for (let i = 0; i < links.length; i++) {
                        const href = links[i].href;
                        
                        // Extract domain for diversity check
                        let domain = '';
                        try {
                            domain = new URL(href).hostname.replace('www.', '');
                        } catch(e) {
                            continue;
                        }
                        
                        // STRICT: Only 1 URL per domain for maximum diversity
                        if (seenDomains.has(domain)) continue;
                        
                        // Filter out Brave's own links, social media, YouTube, non-English sites, and duplicates
                        if (href && 
                            !href.includes('brave.com') &&
                            !href.includes('search.brave') &&
                            !href.includes('youtube.com') &&
                            !href.includes('youtu.be') &&
                            !href.includes('instagram.com') &&
                            !href.includes('facebook.com') &&
                            !href.includes('twitter.com') &&
                            !href.includes('x.com') &&
                            !href.includes('tiktok.com') &&
                            !href.includes('.cn') &&
                            !href.includes('.jp') &&
                            !href.includes('.kr') &&
                            !href.includes('zhihu.com') &&
                            !href.includes('baidu.com') &&
                            !href.includes('weibo.com') &&
                            !results.includes(href) &&
                            href.startsWith('http')) {
                            
                            results.push(href);
                            seenDomains.add(domain);
                            
                            if (results.length >= k) break;
                        }
                    }
                    if (results.length >= k) break;
                }
            }
            
            console.log(`Found ${results.length} URLs from ${seenDomains.size} unique domains`);
            return results;
        }''', k)
        
        if not urls or len(urls) == 0:
            # Debug: save screenshot and HTML
            logger.error("❌ No URLs found, saving debug info...")
            await page.screenshot(path='debug_search.png')
            html = await page.content()
            with open('debug_search.html', 'w', encoding='utf-8') as f:
                f.write(html)
            raise SearchError(f"No search results found for query: {query}. Debug files saved: debug_search.png, debug_search.html")
        
        logger.info(f"✅ Extracted {len(urls)} URLs from Brave")
        return urls[:k]
        
    except SearchError:
        raise
    except Exception as e:
        error_msg = f"Brave search failed: {str(e)}"
        logger.error(error_msg)
        raise SearchError(error_msg)


async def search_bing(page: Page, query: str, k: int = 5) -> List[str]:
    """
    Search Bing (more bot-friendly than Google).
    
    Args:
        page: Playwright Page object
        query: Search query string
        k: Number of URLs to extract (default: 5)
        
    Returns:
        List of URLs (up to k results)
    """
    try:
        logger.info(f"🔍 Searching Bing: '{query}' (k={k})")
        
        search_url = f"https://www.bing.com/search?q={quote_plus(query)}&setlang=en"
        logger.info(f"   Navigating to: {search_url}")
        
        await page.goto(search_url, wait_until='domcontentloaded', timeout=5000)
        await page.wait_for_timeout(1000)
        
        urls = await page.evaluate('''(k) => {
            const results = [];
            const seenDomains = new Set();
            
            // Bing result selectors
            const selectors = [
                'li.b_algo h2 a[href^="http"]',
                'li.b_algo a[href^="http"]',
                'a[href^="http"]'
            ];
            
            for (const selector of selectors) {
                const links = document.querySelectorAll(selector);
                console.log(`Selector ${selector}: found ${links.length} links`);
                
                for (let link of links) {
                    const href = link.href;
                    
                    // Extract domain
                    let domain = '';
                    try {
                        domain = new URL(href).hostname.replace('www.', '');
                    } catch(e) {
                        continue;
                    }
                    
                    // Filter out Bing's own links and social media
                    if (href && 
                        !href.includes('bing.com') &&
                        !href.includes('microsoft.com') &&
                        !href.includes('youtube.com') &&
                        !href.includes('youtu.be') &&
                        !href.includes('instagram.com') &&
                        !href.includes('facebook.com') &&
                        !href.includes('twitter.com') &&
                        !href.includes('x.com') &&
                        !href.includes('tiktok.com') &&
                        !seenDomains.has(domain) &&
                        !results.includes(href) &&
                        href.startsWith('http')) {
                        
                        results.push(href);
                        seenDomains.add(domain);
                        
                        if (results.length >= k) break;
                    }
                }
                if (results.length >= k) break;
            }
            
            console.log(`Found ${results.length} URLs from ${seenDomains.size} unique domains`);
            return results;
        }''', k)
        
        if urls and len(urls) > 0:
            logger.info(f"✅ Extracted {len(urls)} URLs from Bing")
            return urls[:k]
        
        return []
        
    except Exception as e:
        logger.warning(f"Bing search failed: {str(e)}")
        return []


async def search_images_brave_playwright(page: Page, query: str, k: int = 5) -> List[str]:
    """
    Search for images using Bing Images.
    Returns direct URLs to original images (not thumbnails).
    
    Args:
        page: Playwright Page object
        query: Search query string
        k: Number of image URLs to extract (default: 5)
        
    Returns:
        List of image URLs (up to k results) - direct links to source images
    """
    try:
        logger.info(f"🖼️  Searching Bing Images: '{query}' (k={k})")
        
        # Navigate to Bing Images
        search_url = f"https://www.bing.com/images/search?q={quote_plus(query)}"
        logger.info(f"   Navigating to: {search_url}")
        await page.goto(search_url, wait_until='domcontentloaded', timeout=6500)
        
        # Wait for images to load
        await page.wait_for_timeout(2000)
        
        # Extract image URLs from Bing
        image_urls = await page.evaluate('''(k) => {
            const results = [];
            
            // Bing stores image data in m attribute
            const imageLinks = document.querySelectorAll('a.iusc');
            
            console.log(`Found ${imageLinks.length} image links`);
            
            for (let link of imageLinks) {
                try {
                    const m = link.getAttribute('m');
                    if (m) {
                        const data = JSON.parse(m);
                        const imageUrl = data.murl || data.turl;
                        
                        if (imageUrl && !results.includes(imageUrl)) {
                            results.push(imageUrl);
                            console.log(`Added: ${imageUrl.substring(0, 80)}`);
                            
                            if (results.length >= k) break;
                        }
                    }
                } catch (e) {
                    // Skip invalid entries
                }
            }
            
            // Fallback: get img src if JSON parsing failed
            if (results.length < k) {
                console.log(`Only found ${results.length} from JSON, trying img tags...`);
                const images = document.querySelectorAll('img.mimg');
                
                for (let img of images) {
                    const src = img.src;
                    if (src && 
                        src.startsWith('http') &&
                        !src.includes('bing.com/th') &&
                        !results.includes(src)) {
                        results.push(src);
                        if (results.length >= k) break;
                    }
                }
            }
            
            console.log(`Extracted ${results.length} image URLs`);
            return results;
        }''', k)
        
        if not image_urls or len(image_urls) == 0:
            logger.warning(f"⚠️  No images found for query: {query}")
            return []
        
        logger.info(f"✅ Extracted {len(image_urls)} image URLs from Bing Images")
        return image_urls[:k]
        
    except Exception as e:
        error_msg = f"Bing Images search failed: {str(e)}"
        logger.warning(error_msg)
        return []


async def search_duckduckgo(page: Page, query: str, k: int = 5) -> List[str]:
    """
    Search DuckDuckGo as backup.
    
    Args:
        page: Playwright Page object
        query: Search query string
        k: Number of URLs to extract (default: 5)
        
    Returns:
        List of URLs (up to k results)
    """
    try:
        logger.info(f"🔍 Searching DuckDuckGo (backup): '{query}' (k={k})")
        
        # DuckDuckGo search with English filter
        search_url = f"https://duckduckgo.com/?q={quote_plus(query)}&kl=us-en"
        logger.info(f"   Navigating to: {search_url}")
        
        await page.goto(search_url, wait_until='networkidle', timeout=5000)
        await page.wait_for_timeout(2000)  # Wait for JS to render
        
        # Extract URLs - try all possible selectors
        urls = await page.evaluate('''(k) => {
            const results = [];
            const seenDomains = new Set();
            
            // Try to find any links that look like search results
            const allLinks = document.querySelectorAll('a[href^="http"]');
            console.log(`Total links found: ${allLinks.length}`);
            
            for (let link of allLinks) {
                const href = link.href;
                
                // Extract domain
                let domain = '';
                try {
                    domain = new URL(href).hostname.replace('www.', '');
                } catch(e) {
                    continue;
                }
                
                // Filter out DuckDuckGo's own links and social media
                if (href && 
                    !href.includes('duckduckgo.com') &&
                    !href.includes('youtube.com') &&
                    !href.includes('youtu.be') &&
                    !href.includes('instagram.com') &&
                    !href.includes('facebook.com') &&
                    !href.includes('twitter.com') &&
                    !href.includes('x.com') &&
                    !href.includes('tiktok.com') &&
                    !href.includes('.cn') &&
                    !href.includes('.jp') &&
                    !href.includes('.kr') &&
                    !seenDomains.has(domain) &&
                    !results.includes(href) &&
                    href.startsWith('http')) {
                    
                    results.push(href);
                    seenDomains.add(domain);
                    
                    if (results.length >= k) break;
                }
            }
            
            console.log(`Found ${results.length} URLs from ${seenDomains.size} unique domains`);
            return results;
        }''', k)
        
        if urls and len(urls) > 0:
            logger.info(f"✅ Extracted {len(urls)} URLs from DuckDuckGo")
            return urls[:k]
        
        return []
        
    except Exception as e:
        logger.warning(f"DuckDuckGo search failed: {str(e)}")
        return []


async def search_startpage(page: Page, query: str, k: int = 5) -> List[str]:
    """
    Search Startpage (privacy-focused, works well with Playwright).
    
    Args:
        page: Playwright Page object
        query: Search query string
        k: Number of URLs to extract (default: 5)
        
    Returns:
        List of URLs (up to k results)
    """
    try:
        logger.info(f"🔍 Searching Startpage: '{query}' (k={k})")
        
        search_url = f"https://www.startpage.com/do/search?q={quote_plus(query)}"
        logger.info(f"   Navigating to: {search_url}")
        
        await page.goto(search_url, wait_until='domcontentloaded', timeout=5000)
        await page.wait_for_timeout(1500)
        
        urls = await page.evaluate('''(k) => {
            const results = [];
            const seen = new Set();
            
            // Startpage result selectors
            const selectors = [
                'a.w-gl__result-url[href^="http"]',
                'a[href^="http"]'
            ];
            
            for (const selector of selectors) {
                const links = document.querySelectorAll(selector);
                
                for (let link of links) {
                    const url = link.href;
                    
                    // Extract domain
                    let domain = '';
                    try {
                        domain = new URL(url).hostname.replace('www.', '');
                    } catch(e) {
                        continue;
                    }
                    
                    // Filter out Startpage's own links and social media
                    if (!url.includes('startpage.com') && 
                        !url.includes('youtube.com') &&
                        !url.includes('youtu.be') &&
                        !url.includes('instagram.com') &&
                        !url.includes('facebook.com') &&
                        !url.includes('twitter.com') &&
                        !url.includes('x.com') &&
                        !url.includes('tiktok.com') &&
                        !seen.has(url)) {
                        results.push(url);
                        seen.add(url);
                        if (results.length >= k) break;
                    }
                }
                if (results.length >= k) break;
            }
            
            return results;
        }''', k)
        
        if urls and len(urls) > 0:
            logger.info(f"✅ Extracted {len(urls)} URLs from Startpage")
            return urls[:k]
        
        return []
        
    except Exception as e:
        logger.warning(f"Startpage search failed: {str(e)}")
        return []


async def search_google_lite(page: Page, query: str, k: int = 5) -> List[str]:
    """
    Search Google using lite version (less bot detection).
    NOTE: Google has aggressive bot detection and may show CAPTCHAs.
    
    Args:
        page: Playwright Page object
        query: Search query string
        k: Number of URLs to extract (default: 5)
        
    Returns:
        List of URLs (up to k results)
    """
    try:
        logger.info(f"🔍 Searching Google Lite: '{query}' (k={k})")
        
        # Use Google with English language filter
        search_url = f"https://www.google.com/search?q={quote_plus(query)}&num={k+10}&hl=en&lr=lang_en"
        logger.info(f"   Navigating to: {search_url}")
        
        # Set mobile user agent
        await page.set_extra_http_headers({
            'Accept-Language': 'en-US,en;q=0.9'
        })
        
        await page.goto(search_url, wait_until='domcontentloaded', timeout=5000)
        await page.wait_for_timeout(1000)  # Increased wait for Google
        
        # Check for CAPTCHA or bot detection
        page_content = await page.content()
        if 'captcha' in page_content.lower() or 'unusual traffic' in page_content.lower():
            logger.warning("⚠️  Google detected bot - CAPTCHA or unusual traffic warning")
            return []
        
        # Extract URLs with strict diversity
        urls = await page.evaluate('''(k) => {
            const results = [];
            const seenDomains = new Set();
            
            // Find all links
            const allLinks = document.querySelectorAll('a[href]');
            
            for (let link of allLinks) {
                const href = link.href;
                
                // Skip if not http or is google/youtube/social media/non-English link
                if (!href.startsWith('http') || 
                    href.includes('google.com') ||
                    href.includes('youtube.com') ||
                    href.includes('youtu.be') ||
                    href.includes('instagram.com') ||
                    href.includes('facebook.com') ||
                    href.includes('twitter.com') ||
                    href.includes('x.com') ||
                    href.includes('tiktok.com') ||
                    href.includes('gstatic.com') ||
                    href.includes('webcache') ||
                    href.includes('.cn') ||
                    href.includes('.jp') ||
                    href.includes('.kr') ||
                    href.includes('zhihu.com') ||
                    href.includes('baidu.com') ||
                    href.includes('weibo.com')) {
                    continue;
                }
                
                // Extract domain
                let domain = '';
                try {
                    domain = new URL(href).hostname.replace('www.', '');
                } catch(e) {
                    continue;
                }
                
                // STRICT: Only 1 URL per domain for maximum diversity
                if (seenDomains.has(domain)) continue;
                
                if (!results.includes(href)) {
                    results.push(href);
                    seenDomains.add(domain);
                    
                    if (results.length >= k) break;
                }
            }
            
            console.log(`Found ${results.length} URLs from ${seenDomains.size} unique domains`);
            return results;
        }''', k)
        
        if urls and len(urls) > 0:
            logger.info(f"✅ Extracted {len(urls)} URLs from Google")
            return urls[:k]
        
        return []
        
    except Exception as e:
        logger.warning(f"Google search failed: {str(e)}")
        return []





async def search_yahoo(page: Page, query: str, k: int = 5) -> List[str]:
    """
    Search Yahoo as fallback.
    
    Args:
        page: Playwright Page object
        query: Search query string
        k: Number of URLs to extract (default: 5)
        
    Returns:
        List of URLs (up to k results)
    """
    try:
        logger.info(f"🔍 Searching Yahoo: '{query}' (k={k})")
        
        search_url = f"https://search.yahoo.com/search?p={quote_plus(query)}"
        logger.info(f"   Navigating to: {search_url}")
        
        await page.goto(search_url, wait_until='domcontentloaded', timeout=5000)
        await page.wait_for_timeout(1500)
        
        urls = await page.evaluate('''(k) => {
            const results = [];
            const seenDomains = new Set();
            
            const selectors = [
                'div.dd.algo a[href^="http"]',
                'h3.title a[href^="http"]',
                'div.compTitle a[href^="http"]',
                'a[href^="http"]'
            ];
            
            for (const selector of selectors) {
                const links = document.querySelectorAll(selector);
                console.log(`Selector ${selector}: found ${links.length} links`);
                
                for (let link of links) {
                    const href = link.href;
                    
                    let domain = '';
                    try {
                        domain = new URL(href).hostname.replace('www.', '');
                    } catch(e) {
                        continue;
                    }
                    
                    if (href && 
                        !href.includes('yahoo.com') &&
                        !href.includes('search.yahoo') &&
                        !href.includes('youtube.com') &&
                        !href.includes('youtu.be') &&
                        !href.includes('instagram.com') &&
                        !href.includes('facebook.com') &&
                        !href.includes('twitter.com') &&
                        !href.includes('x.com') &&
                        !href.includes('tiktok.com') &&
                        !seenDomains.has(domain) &&
                        !results.includes(href)) {
                        results.push(href);
                        seenDomains.add(domain);
                        if (results.length >= k) break;
                    }
                }
                if (results.length >= k) break;
            }
            
            console.log(`Found ${results.length} URLs from ${seenDomains.size} unique domains`);
            return results;
        }''', k)
        
        if urls and len(urls) > 0:
            logger.info(f"✅ Extracted {len(urls)} URLs from Yahoo")
            return urls[:k]
        
        return []
        
    except Exception as e:
        logger.warning(f"Yahoo search failed: {str(e)}")
        return []


async def search_yandex(page: Page, query: str, k: int = 5) -> List[str]:
    """
    Search Yandex as fallback (good international results).
    
    Args:
        page: Playwright Page object
        query: Search query string
        k: Number of URLs to extract (default: 5)
        
    Returns:
        List of URLs (up to k results)
    """
    try:
        logger.info(f"🔍 Searching Yandex: '{query}' (k={k})")
        
        search_url = f"https://yandex.com/search/?text={quote_plus(query)}&lang=en"
        logger.info(f"   Navigating to: {search_url}")
        
        await page.goto(search_url, wait_until='domcontentloaded', timeout=15000)
        await page.wait_for_timeout(4000)
        
        urls = await page.evaluate('''(k) => {
            const results = [];
            const seenDomains = new Set();
            
            const selectors = [
                'li.serp-item a.Link[href^="http"]',
                'div.OrganicTitle a[href^="http"]',
                'a[href^="http"]'
            ];
            
            for (const selector of selectors) {
                const links = document.querySelectorAll(selector);
                console.log(`Selector ${selector}: found ${links.length} links`);
                
                for (let link of links) {
                    const href = link.href;
                    
                    let domain = '';
                    try {
                        domain = new URL(href).hostname.replace('www.', '');
                    } catch(e) {
                        continue;
                    }
                    
                    if (href && 
                        !href.includes('yandex.') &&
                        !href.includes('ya.ru') &&
                        !href.includes('youtube.com') &&
                        !href.includes('youtu.be') &&
                        !href.includes('instagram.com') &&
                        !href.includes('facebook.com') &&
                        !href.includes('twitter.com') &&
                        !href.includes('x.com') &&
                        !href.includes('tiktok.com') &&
                        !seenDomains.has(domain) &&
                        !results.includes(href)) {
                        results.push(href);
                        seenDomains.add(domain);
                        if (results.length >= k) break;
                    }
                }
                if (results.length >= k) break;
            }
            
            console.log(`Found ${results.length} URLs from ${seenDomains.size} unique domains`);
            return results;
        }''', k)
        
        if urls and len(urls) > 0:
            logger.info(f"✅ Extracted {len(urls)} URLs from Yandex")
            return urls[:k]
        
        return []
        
    except Exception as e:
        logger.warning(f"Yandex search failed: {str(e)}")
        return []
