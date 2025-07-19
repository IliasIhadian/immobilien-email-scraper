"""
Browser Manager für 11880.com Email Scraper
Verwaltet Playwright Browser-Instanzen mit robusten Konfigurationen
"""

import asyncio
import random
import time
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
)
import yaml


class BrowserManager:
    """
    Verwaltet Browser-Instanzen für Web-Scraping mit Playwright
    Implementiert Best Practices für ethisches Scraping
    """

    def __init__(
        self, headless: Optional[bool] = None, config_path: str = "config/settings.yaml"
    ):
        self.config_path = config_path
        self.config = self._load_config()
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.headless_override = headless

        # Setup logging
        self.logger = logging.getLogger(__name__)
        self._setup_logging()

        # User agents für Rotation
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]

    def _load_config(self) -> Dict[str, Any]:
        """Lädt die Konfiguration aus der YAML-Datei"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as file:
                return yaml.safe_load(file)
        except FileNotFoundError:
            self.logger.warning(f"Config file not found: {self.config_path}")
            return self._default_config()
        except Exception as e:
            self.logger.error(f"Error loading config: {e}")
            return self._default_config()

    def _default_config(self) -> Dict[str, Any]:
        """Standard-Konfiguration falls keine Datei vorhanden ist"""
        return {
            "browser": {
                "headless": True,
                "timeout": 60000,  # Increased timeout to 60 seconds
                "viewport": {"width": 1920, "height": 1080},
            },
            "scraping": {
                "delay_between_requests": {"min": 2, "max": 5},
                "retry_attempts": 5,  # Increased retry attempts
                "retry_delay": 2,  # Base delay for exponential backoff
            },
        }

    def _setup_logging(self):
        """Konfiguriert das Logging für den BrowserManager"""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    async def start_browser(self) -> Page:
        """
        Startet den Browser und erstellt eine neue Seite

        Returns:
            Page: Playwright Page-Objekt
        """
        try:
            self.logger.info("Starting browser...")

            # Playwright starten
            self.playwright = await async_playwright().start()

            # Browser konfigurieren
            browser_config = self.config.get("browser", {})

            # Headless-Modus bestimmen (Override > Config > Default)
            is_headless = self.headless_override
            if is_headless is None:
                is_headless = browser_config.get("headless", True)

            self.browser = await self.playwright.chromium.launch(
                headless=is_headless,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-extensions",
                    "--disable-plugins",
                    "--disable-images",  # Für bessere Performance
                ],
            )

            # Browser Context mit zufälligem User-Agent
            user_agent = random.choice(self.user_agents)
            viewport = browser_config.get("viewport", {"width": 1920, "height": 1080})

            self.context = await self.browser.new_context(
                user_agent=user_agent,
                viewport=viewport,
                java_script_enabled=True,
                ignore_https_errors=True,
                extra_http_headers={
                    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                },
            )

            # Neue Seite erstellen
            self.page = await self.context.new_page()

            # Timeout konfigurieren
            timeout = browser_config.get("timeout", 30000)
            self.page.set_default_timeout(timeout)

            # Event-Handler für besseres Debugging
            self.page.on("response", self._on_response)
            self.page.on("requestfailed", self._on_request_failed)

            self.logger.info(
                f"Browser started successfully with User-Agent: {user_agent}"
            )
            return self.page

        except Exception as e:
            self.logger.error(f"Failed to start browser: {e}")
            await self.cleanup()
            raise

    async def _on_response(self, response):
        """Event-Handler für HTTP-Responses"""
        if response.status >= 400:
            self.logger.warning(f"HTTP {response.status}: {response.url}")

    async def _on_request_failed(self, request):
        """Event-Handler für fehlgeschlagene Requests"""
        # URLs die ignoriert werden sollen
        ignored_urls = [
            "fonts",  # Font-Loading Fehler
            "google-analytics",  # Google Analytics
            "googleads",  # Google Ads
            "doubleclick",  # DoubleClick
            "google.com/ads",  # Google Ads
            "google.com/pagead",  # Google Ads
            "google.de/pagead",  # Google Ads
            "google-analytics.com/collect",  # Analytics
            "static.11880.com/Portal/fonts",  # 11880 Fonts
            "googlesyndication.com",  # Google Syndication
            "pagead2.googlesyndication.com",  # Google Syndication spezifisch
            "amazon-adsystem.com",  # Amazon Ads
            "id5-sync.com",  # ID5 Tracking
            "jsdelivr.net/gh/prebid",  # Prebid Currency Files
            "adtrafficquality.google",  # Google Ad Traffic Quality
            "sodar",  # Google Sodar Tracking
            "google.com/ccm/collect",  # Google Consent Management
            "googletagmanager.com",  # Google Tag Manager
            "dnacdn.net",  # DNA CDN
        ]

        # Prüfen ob die URL ignoriert werden soll
        url = request.url.lower()
        if not any(ignored_url in url for ignored_url in ignored_urls):
            error_message = (
                str(request.failure) if hasattr(request, "failure") else "Unknown error"
            )
            # Ignore ERR_ABORTED errors as they are usually just navigation cancellations
            if "net::ERR_ABORTED" not in error_message:
                self.logger.error(f"Request failed: {request.url} - {error_message}")

    async def navigate_to(self, url: str, wait_for: Optional[str] = None) -> bool:
        """
        Navigiert zu einer URL mit robusten Wartezeiten

        Args:
            url: Ziel-URL
            wait_for: CSS-Selektor auf den gewartet werden soll

        Returns:
            bool: True wenn erfolgreich, False sonst
        """
        if not self.page:
            raise RuntimeError("Browser not started. Call start_browser() first.")

        try:
            self.logger.info(f"Navigating to: {url}")

            # Navigation mit Retry-Logik
            retry_attempts = self.config.get("scraping", {}).get("retry_attempts", 5)
            base_delay = self.config.get("scraping", {}).get("retry_delay", 2)

            for attempt in range(retry_attempts):
                try:
                    # Clear cache and cookies before navigation
                    if attempt > 0:  # Only clear on retry attempts
                        await self.context.clear_cookies()
                        await self.page.evaluate("() => window.localStorage.clear()")
                        await self.page.evaluate("() => window.sessionStorage.clear()")

                    # Navigate with longer timeout
                    response = await self.page.goto(
                        url,
                        wait_until="networkidle",  # Wait for network to be idle
                        timeout=60000,  # 60 second timeout
                    )

                    if response and response.status < 400:
                        self.logger.info(f"Successfully navigated to {url}")

                        # Wait for specific selector if provided
                        if wait_for:
                            await self.page.wait_for_selector(
                                wait_for,
                                timeout=30000,
                                state="visible",  # Ensure element is visible
                            )
                            self.logger.info(
                                f"Successfully waited for selector: {wait_for}"
                            )

                        # Additional wait for dynamic content
                        await asyncio.sleep(2)

                        return True
                    else:
                        error_msg = f"Navigation returned status {response.status if response else 'None'}"
                        self.logger.warning(error_msg)

                        if attempt == retry_attempts - 1:
                            # Save page content on last failed attempt
                            try:
                                html = await self.page.content()
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                with open(
                                    f"logs/failed_page_{timestamp}.html",
                                    "w",
                                    encoding="utf-8",
                                ) as f:
                                    f.write(html)
                                await self.take_screenshot(
                                    f"failed_page_{timestamp}.png"
                                )
                            except Exception as e:
                                self.logger.error(f"Failed to save debug info: {e}")

                except Exception as e:
                    self.logger.warning(f"Navigation attempt {attempt + 1} failed: {e}")

                    if attempt < retry_attempts - 1:
                        # Exponential backoff with jitter
                        delay = (base_delay ** (attempt + 1)) + random.uniform(0, 1)
                        self.logger.info(f"Retrying in {delay:.2f} seconds...")
                        await asyncio.sleep(delay)
                    else:
                        raise

            return False

        except Exception as e:
            self.logger.error(f"Failed to navigate to {url}: {e}")
            return False

    async def wait_human_like(self):
        """Wartet eine zufällige Zeit um menschliches Verhalten zu simulieren"""
        delay_config = self.config.get("scraping", {}).get("delay_between_requests", {})
        min_delay = delay_config.get("min", 2)
        max_delay = delay_config.get("max", 5)

        delay = random.uniform(min_delay, max_delay)
        self.logger.debug(f"Waiting {delay:.2f} seconds...")
        await asyncio.sleep(delay)

    async def take_screenshot(self, filename: Optional[str] = None) -> str:
        """
        Macht einen Screenshot der aktuellen Seite

        Args:
            filename: Optionaler Dateiname, sonst wird Timestamp verwendet

        Returns:
            str: Pfad zur Screenshot-Datei
        """
        if not self.page:
            raise RuntimeError("Browser not started. Call start_browser() first.")

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"

        screenshot_path = Path("logs") / filename
        screenshot_path.parent.mkdir(exist_ok=True)

        await self.page.screenshot(path=str(screenshot_path), full_page=True)
        self.logger.info(f"Screenshot saved: {screenshot_path}")
        return str(screenshot_path)

    async def get_page_content(self) -> str:
        """Gibt den HTML-Inhalt der aktuellen Seite zurück"""
        if not self.page:
            raise RuntimeError("Browser not started. Call start_browser() first.")

        return await self.page.content()

    async def get_or_create_page(self) -> Page:
        """
        Gibt die existierende Seite zurück oder startet den Browser und erstellt eine neue.

        Returns:
            Page: Das Playwright Page-Objekt.
        """
        if self.page and not self.page.is_closed():
            self.logger.info("Returning existing browser page.")
            return self.page

        self.logger.info("No active page found. Starting new browser session.")
        return await self.start_browser()

    async def scroll_to_bottom(self, pause_time: float = 1.0) -> bool:
        """
        Scrollt langsam zum Ende der Seite um dynamische Inhalte zu laden

        Args:
            pause_time: Pause zwischen Scroll-Aktionen

        Returns:
            bool: True wenn erfolgreich
        """
        if not self.page:
            return False

        try:
            # Aktuelle Höhe abrufen
            previous_height = await self.page.evaluate("document.body.scrollHeight")

            while True:
                # Zum Ende scrollen
                await self.page.evaluate(
                    "window.scrollTo(0, document.body.scrollHeight)"
                )
                await asyncio.sleep(pause_time)

                # Neue Höhe prüfen
                new_height = await self.page.evaluate("document.body.scrollHeight")

                if new_height == previous_height:
                    break

                previous_height = new_height

            self.logger.info("Finished scrolling to bottom")
            return True

        except Exception as e:
            self.logger.error(f"Error scrolling to bottom: {e}")
            return False

    async def cleanup(self):
        """Räumt alle Browser-Ressourcen auf"""
        try:
            if self.page:
                await self.page.close()
                self.page = None

            if self.context:
                await self.context.close()
                self.context = None

            if self.browser:
                await self.browser.close()
                self.browser = None

            if self.playwright:
                await self.playwright.stop()
                self.playwright = None

            self.logger.info("Browser cleanup completed")

        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")

    async def __aenter__(self):
        """Context Manager Entry"""
        return await self.start_browser()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context Manager Exit"""
        await self.cleanup()


# Beispiel für die Verwendung
async def example_usage():
    """Beispiel-Code für die Verwendung des BrowserManagers"""
    browser_manager = BrowserManager()

    try:
        page = await browser_manager.start_browser()

        # Navigation zu einer Website
        await browser_manager.navigate_to("https://www.11880.com")

        # Menschenähnliche Pause
        await browser_manager.wait_human_like()

        # Screenshot machen
        await browser_manager.take_screenshot()

    finally:
        await browser_manager.cleanup()


if __name__ == "__main__":
    # Für Testing
    asyncio.run(example_usage())
