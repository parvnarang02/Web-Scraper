"""
Playwright browser session management (standalone, no AgentCore).
"""

import logging
import random
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from user_agents import get_random_user_agent

logger = logging.getLogger(__name__)


@asynccontextmanager
async def create_playwright_browser() -> AsyncGenerator[tuple[Page, BrowserContext], None]:
    """
    Create a standalone Playwright browser session.
    
    Yields:
        Tuple of (Page, BrowserContext) for browser automation
        
    Example:
        async with create_playwright_browser() as (page, context):
            await page.goto("https://example.com")
            content = await page.content()
    """
    browser: Browser | None = None
    playwright_instance = None
    
    try:
        logger.info("🎭 Starting Playwright browser with stealth mode...")
        playwright_instance = await async_playwright().start()
        
        # Random viewport sizes to avoid fingerprinting
        viewports = [
            {'width': 1920, 'height': 1080},
            {'width': 1366, 'height': 768},
            {'width': 1536, 'height': 864},
            {'width': 1440, 'height': 900},
            {'width': 2560, 'height': 1440},
        ]
        viewport = random.choice(viewports)
        
        browser = await playwright_instance.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-infobars',
                '--window-position=0,0',
                '--ignore-certificate-errors',
                '--ignore-certificate-errors-spki-list',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-site-isolation-trials',
                '--disable-features=BlockInsecurePrivateNetworkRequests',
                '--single-process',
                '--disable-gpu',
                '--no-zygote'
            ]
        )
        logger.info("✅ Playwright browser launched")
        
        context = await browser.new_context(
            user_agent=get_random_user_agent(),
            viewport=viewport,
            locale='en-US',
            timezone_id='America/New_York',
            extra_http_headers={
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1'
            }
        )
        
        # Comprehensive stealth script - removes all bot detection markers
        await context.add_init_script("""
            // Remove webdriver flag
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Mock plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // Mock languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            
            // Chrome runtime
            window.chrome = {
                runtime: {}
            };
            
            // Permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // Mock hardware concurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8
            });
            
            // Mock device memory
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8
            });
        """)
        
        # Block all heavy resources - only load HTML and scripts for content extraction
        await context.route("**/*", lambda route: (
            route.abort() if route.request.resource_type in ["image", "stylesheet", "font", "media"] 
            else route.continue_()
        ))
        
        page = await context.new_page()
        
        logger.info("⚡ Blocking images/CSS/fonts - content only mode")
        logger.info("📄 Browser page ready")
        
        yield page, context
        
        logger.info("🔒 Closing Playwright browser...")
        
    finally:
        # Close all pages in context first
        if 'context' in locals() and context:
            try:
                for page in context.pages:
                    try:
                        await page.close()
                    except:
                        pass
                await context.close()
                logger.info("✅ Context closed")
            except Exception as e:
                logger.warning(f"⚠️  Error closing context: {e}")
        
        # Then close browser
        if browser:
            try:
                await browser.close()
                logger.info("✅ Browser closed")
            except Exception as e:
                logger.warning(f"⚠️  Error closing browser: {e}")
                
        # Finally stop playwright
        if playwright_instance:
            try:
                await playwright_instance.stop()
                logger.info("✅ Playwright stopped")
            except Exception as e:
                logger.warning(f"⚠️  Error stopping Playwright: {e}")
