"""
Navigator für 11880.com Email Scraper
Verwaltet die Navigation und Suche auf der 11880.com Website
"""

import asyncio
import random
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urljoin, urlparse, quote

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from ..utils.logging_config import get_logger


class NavigationError(Exception):
    """Custom Exception für Navigation-Fehler"""

    pass


class Navigator:
    """
    Verwaltet die Navigation auf 11880.com
    Implementiert robuste Suchfunktionalität für Hausverwaltungen
    """

    def __init__(self, page: Page, config: Dict[str, Any]):
        self.page = page
        self.config = config
        self.logger = get_logger(__name__)
        self.last_search_url = None  # Speichert die letzte Suchergebnisseite

        # 11880.com spezifische URLs und Parameter
        self.base_url = "https://www.11880.com/suche/hausverwaltung/duesseldorf"
        self.search_term = self.config.get("target", {}).get(
            "search_term", "Hausverwaltungen"
        )
        self.location = self.config.get("target", {}).get("location", "Düsseldorf")

        # Retry-Konfiguration
        self.max_retries = self.config.get("scraping", {}).get("retry_attempts", 3)
        self.retry_delay = self.config.get("scraping", {}).get("retry_delay", 10)

    async def start_scraping(self) -> bool:
        """
        Startet den Scraping-Prozess direkt mit der Suchergebnisseite

        Returns:
            bool: True wenn erfolgreich, False sonst
        """
        self.logger.info(
            f"Starting scraping directly at search results: {self.base_url}"
        )

        return await self.navigate_to_search_url(self.base_url)

    async def navigate_to_search_url(self, search_url: str) -> bool:
        """Navigiert zu einer gegebenen Such-URL und wartet auf die Ergebnisse"""
        for attempt in range(self.max_retries):
            try:
                # Use domcontentloaded instead of networkidle for faster loading
                # This allows us to start working with the page before all resources are loaded
                response = await self.page.goto(
                    search_url, wait_until="domcontentloaded", timeout=15000
                )

                if not response or response.status >= 400:
                    raise NavigationError(
                        f"Page returned status {response.status if response else 'None'}"
                    )

                # Wait a bit for critical content to render, but don't wait for everything
                await asyncio.sleep(3)

                await self.handle_cookie_consent()

                # Try to find search results with a reasonable timeout
                # Don't wait too long - the page might be usable even if not fully loaded
                success = await self._wait_for_search_results()
                if not success:
                    # Try a second time with a shorter wait - sometimes content loads progressively
                    await asyncio.sleep(2)
                    success = await self._wait_for_search_results()
                    if not success:
                        raise NavigationError("Search results did not load")

                self.logger.info(f"Successfully navigated to search URL: {search_url}")
                return True

            except Exception as e:
                self.logger.warning(
                    f"Direct navigation attempt {attempt + 1} to {search_url} failed: {e}"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))

                    # Save debug info on last attempt
                    if attempt == self.max_retries - 2:
                        try:
                            html = await self.page.content()
                            with open(
                                "page_on_timeout.html", "w", encoding="utf-8"
                            ) as f:
                                f.write(html)
                            self.logger.info(
                                "Saved page content to page_on_timeout.html"
                            )

                            await self.page.screenshot(path="page_on_timeout.png")
                            self.logger.info("Saved screenshot to page_on_timeout.png")
                        except Exception as debug_e:
                            self.logger.error(f"Failed to save debug info: {debug_e}")

        self.logger.error(
            f"Failed to navigate to search URL {search_url} after all attempts"
        )
        return False

    async def handle_cookie_consent(self) -> None:
        """Akzeptiert den Cookie-Banner, falls vorhanden"""
        try:
            # Warte kurz, damit der Cookie-Banner erscheinen kann
            await asyncio.sleep(2)

            # Versuche verschiedene Cookie-Banner-Selektoren
            cookie_selectors = [
                "#cmpwelcomebtnyes",
                ".cmpboxbtnyes",
                "[aria-label='Alle akzeptieren']",
                "#onetrust-accept-btn-handler",
            ]

            for selector in cookie_selectors:
                try:
                    await self.page.click(selector, timeout=5000)
                    self.logger.info("Accepted cookie consent")
                    await asyncio.sleep(5)  # Warte nach dem Klicken
                    return
                except PlaywrightTimeoutError:
                    continue

        except Exception as e:
            self.logger.warning(f"Could not handle cookie consent: {str(e)}")

    async def _wait_for_search_results(self) -> bool:
        """Wartet, bis die Suchergebnisliste geladen ist und klickt auf das erste Ergebnis."""
        self.logger.info("Waiting for search results to load...")
        try:
            # Updated selectors for search results based on the new HTML structure
            result_selectors = [
                "div.result-list-entry__container",  # New primary selector
                "div.result-list-entry-wrapper",  # Alternative wrapper
                "article[data-entry-id]",  # Legacy selector
                ".search-entry",  # Backup selector
                ".business-entry",  # Another backup
            ]

            # Try each selector with a reasonable timeout - don't wait too long
            found_selector = None
            for selector in result_selectors:
                try:
                    await self.page.wait_for_selector(selector, timeout=10000)
                    found_selector = selector
                    break
                except PlaywrightTimeoutError:
                    continue

            if not found_selector:
                self.logger.warning("No search results found with any selector")
                return False

            # Get all entries with the working selector
            entries = await self.page.query_selector_all(found_selector)
            if not entries:
                self.logger.warning("No search results found on the page.")
                return False

            self.logger.info(f"Found {len(entries)} search results.")

            # Try to click the first result's title link
            first_result = entries[0]
            click_successful = False

            # Try clicking the title link first (new selector chain)
            try:
                title_selectors = [
                    "a.result-list-entry-title",  # New primary selector
                    "a.entry-detail-link",  # Alternative link class
                    "h2 a",  # Generic heading link
                    'a[title*="in"]',  # Link with location in title
                ]

                for selector in title_selectors:
                    title_link = await first_result.query_selector(selector)
                    if title_link:
                        await title_link.click()
                        click_successful = True
                        self.logger.info(
                            f"Clicked on the first result's title link using selector: {selector}"
                        )
                        break

            except Exception as e:
                self.logger.warning(f"Failed to click title link: {e}")

            # If title click failed, try clicking the entire container
            if not click_successful:
                try:
                    # Try to find a clickable parent element
                    clickable_selectors = [
                        "div.result-list-entry__container",
                        "div.result-list-entry-wrapper",
                        '[class*="result-list-entry"]',
                    ]

                    for selector in clickable_selectors:
                        clickable = await first_result.query_selector(selector)
                        if clickable:
                            await clickable.click()
                            click_successful = True
                            self.logger.info(
                                f"Clicked on the container using selector: {selector}"
                            )
                            break

                except Exception as e:
                    self.logger.error(f"Failed to click container: {e}")

            if not click_successful:
                self.logger.error("Could not click on any element of the first result")
                return False

            # Wait for navigation after click, but with reasonable timeout
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=15000)
                self.logger.info("Successfully navigated to detail page")
                # Give the page a moment to render critical content
                await asyncio.sleep(2)
                return True
            except PlaywrightTimeoutError:
                # Even if we hit timeout, check if we're on a detail page
                if "/branchenbuch/" in self.page.url and ".html" in self.page.url:
                    self.logger.info(
                        "Navigation successful despite timeout - already on detail page"
                    )
                    return True
                self.logger.error("Timeout waiting for detail page to load")
                return False

        except Exception as e:
            self.logger.error(f"Error in _wait_for_search_results: {e}")
            return False

    async def get_current_page_info(self) -> Dict[str, Any]:
        """Sammelt Informationen über die aktuelle Seite"""
        try:
            # Try multiple selectors to find entries
            selectors = [
                "article[data-entry-id]",
                ".search-entry",
                ".business-entry",
                '[data-testid="search-result-item"]',
                ".entry-card",
            ]

            total_entries = 0
            for selector in selectors:
                entries = await self.page.query_selector_all(selector)
                if entries:
                    total_entries = len(entries)
                    break

            return {
                "is_search_results_page": total_entries > 0,
                "num_results": total_entries,
            }
        except Exception as e:
            self.logger.error(f"Error getting page info: {e}")
            return {"is_search_results_page": False, "num_results": 0}

    async def navigate_to_url(self, url: str) -> None:
        """Navigiert zu einer bestimmten URL"""
        try:
            await self.page.goto(url, timeout=120000)  # 120 Sekunden Timeout
            self.logger.info(f"Successfully navigated to {url}")
            await asyncio.sleep(5)  # Warte nach der Navigation
        except PlaywrightTimeoutError:
            self.logger.error(f"Timeout while navigating to {url}")
            raise NavigationError(f"Could not navigate to {url}")

    async def click_nth_result(self, index: int) -> bool:
        """Klickt auf das n-te Suchergebnis (1-basiert)"""
        try:
            # Speichere die aktuelle URL als Suchergebnisseite
            self.last_search_url = self.page.url
            self.logger.info(f"Saved search results URL: {self.last_search_url}")

            # Wenn wir bereits auf einer Detailseite sind, war die Navigation erfolgreich
            if (
                "/branchenbuch/" in self.last_search_url
                and ".html" in self.last_search_url
            ):
                self.logger.info("Already on detail page")
                return True

            # Warte auf die Suchergebnisse
            try:
                await self.page.wait_for_selector(
                    ".result-list-entry__container", timeout=30000
                )
            except PlaywrightTimeoutError:
                # Wenn wir auf einer Detailseite sind, ist das kein Fehler
                if "/branchenbuch/" in self.page.url and ".html" in self.page.url:
                    self.logger.info("Successfully navigated to detail page")
                    return True
                self.logger.error("Timeout while waiting for search results")
                return False

            # Versuche alle Titel-Links zu finden
            link_selector = "a.result-list-entry-title.entry-detail-link"
            await self.page.wait_for_selector(link_selector, timeout=10000)

            # Hole alle Links
            links = await self.page.evaluate(
                f"""Array.from(document.querySelectorAll('{link_selector}')).map(link => link.getAttribute('href'))"""
            )

            if not links:
                self.logger.error("No search result links found")
                return False

            # Prüfe ob der gewünschte Index existiert
            if index < 1 or index > len(links):
                self.logger.warning(f"Result index {index} out of range (1-{len(links)})")
                return False

            # Hole den href-Wert des gewünschten Links (index-1 wegen 0-basiertem Array)
            href = links[index - 1]
            if href:
                # Konstruiere die vollständige URL
                base_url = "https://www.11880.com"
                full_url = urljoin(base_url, href)

                # Navigiere zur Detail-Seite
                await self.navigate_to_url(full_url)
                self.logger.info(f"Successfully navigated to detail page for result {index}")
                return True

            self.logger.error(f"Could not find detail page link for result {index}")
            return False

        except PlaywrightTimeoutError:
            # Wenn wir auf einer Detailseite sind, ist das kein Fehler
            if "/branchenbuch/" in self.page.url and ".html" in self.page.url:
                self.logger.info("Successfully navigated to detail page")
                return True
            self.logger.error("Timeout while waiting for search results")
            return False
        except Exception as e:
            self.logger.error(f"Error clicking on result {index}: {str(e)}")
            return False

    async def click_first_result(self) -> bool:
        """Klickt auf das erste Suchergebnis - Wrapper für click_nth_result"""
        return await self.click_nth_result(1)

    async def return_to_search_results(self) -> bool:
        """Kehrt zur letzten Suchergebnisseite zurück mit dem Browser-Zurück-Button"""
        try:
            self.logger.info("Going back to search results using browser back button")

            # Verwende den Browser-Zurück-Button
            await self.page.go_back(wait_until="domcontentloaded", timeout=15000)

            # Kurz warten, damit sich die Seite stabilisiert
            await asyncio.sleep(2)

            # Prüfe ob wir wieder auf der Suchergebnisseite sind
            # page_info = await self.get_current_page_info()
            # if page_info["is_search_results_page"]:
            #     self.logger.info("Successfully returned to search results page")
            #     return True
            # else:
            #     self.logger.warning("Back navigation successful but not on search results page")
            #     # Fallback: Verwende die gespeicherte URL
            #     if self.last_search_url:
            #         self.logger.info(f"Fallback: Navigating to saved URL: {self.last_search_url}")
            #         await self.navigate_to_url(self.last_search_url)
            #         return True
            #     return False

        except Exception as e:
            self.logger.error(f"Error going back to search results: {str(e)}")
            # Fallback: Verwende die gespeicherte URL
            try:
                if self.last_search_url:
                    self.logger.info(
                        f"Fallback: Navigating to saved URL: {self.last_search_url}"
                    )
                    await self.navigate_to_url(self.last_search_url)
                    return True
            except Exception as fallback_error:
                self.logger.error(f"Fallback navigation also failed: {fallback_error}")
            return False

    async def search_for_term(self, search_term: str, location: str = "") -> bool:
        """
        Führt eine Suche auf 11880.com durch

        Args:
            search_term: Der Suchbegriff
            location: Optional - der Ort für die Suche
        """
        try:
            # Baue die Such-URL
            encoded_term = quote(search_term)
            encoded_location = quote(location) if location else ""

            if location:
                search_url = (
                    f"https://www.11880.com/suche/{encoded_term}/{encoded_location}"
                )
            else:
                search_url = f"https://www.11880.com/suche/{encoded_term}"

            # Navigiere zur Suchseite
            await self.navigate_to_url(search_url)
            self.last_search_url = search_url  # Speichere die Such-URL

            # Warte auf die Suchergebnisse
            await self.page.wait_for_selector(
                ".result-list-entry__container", timeout=30000
            )

            # Prüfe ob Ergebnisse gefunden wurden
            results = await self.page.query_selector_all(
                ".result-list-entry__container"
            )
            if not results:
                self.logger.warning("No search results found")
                return False

            self.logger.info(f"Found {len(results)} search results")
            return True

        except Exception as e:
            self.logger.error(f"Error during search: {str(e)}")
            return False
