"""
Pagination Handler für 11880.com Email Scraper
Verwaltet das Durchlaufen aller Suchergebnisseiten
"""

import asyncio
import random
import re
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from ..utils.logging_config import get_logger


class PaginationHandler:
    """
    Verwaltet die Navigation durch mehrere Seiten von Suchergebnissen
    Implementiert robuste Paginierung für 11880.com
    """

    def __init__(self, page: Page, config: Dict[str, Any]):
        self.page = page
        self.config = config
        self.logger = get_logger(__name__)

        # Konfiguration
        self.max_pages = self.config.get("scraping", {}).get("max_pages", 50)
        self.delay_between_pages = self.config.get("scraping", {}).get(
            "delay_between_requests", {}
        )
        self.base_url = self.config.get("target", {}).get(
            "base_url", "https://www.11880.com"
        )

        # State tracking
        self.current_page = 1
        self.total_pages = None
        self.visited_urls = set()

    async def get_all_pages(self) -> List[str]:
        """
        Durchläuft alle verfügbaren Seiten und gibt URLs zurück

        Returns:
            List[str]: Liste aller Seiten-URLs
        """
        try:
            self.logger.info("Starting pagination crawl")

            page_urls = []
            current_url = self.page.url

            # Erste Seite hinzufügen
            page_urls.append(current_url)
            self.visited_urls.add(current_url)

            page_count = 1

            while page_count < self.max_pages:
                # Versuche zur nächsten Seite zu navigieren
                next_url = await self._get_next_page_url()

                if not next_url or next_url in self.visited_urls:
                    self.logger.info(
                        f"No more pages found. Total pages processed: {page_count}"
                    )
                    break

                # Zur nächsten Seite navigieren
                success = await self._navigate_to_next_page(next_url)

                if not success:
                    self.logger.warning(f"Failed to navigate to page {page_count + 1}")
                    break

                page_count += 1
                current_url = self.page.url
                page_urls.append(current_url)
                self.visited_urls.add(current_url)

                self.logger.info(
                    f"Successfully navigated to page {page_count}: {current_url}"
                )

                # Menschenähnliche Pause zwischen Seiten
                await self._wait_between_pages()

                # Sicherheitscheck: Sind wir noch auf einer Suchergebnisseite?
                if not await self._is_search_results_page():
                    self.logger.warning(
                        "Not on search results page anymore, stopping pagination"
                    )
                    break

            self.logger.info(f"Pagination completed. Found {len(page_urls)} pages")
            return page_urls

        except Exception as e:
            self.logger.error(f"Error during pagination: {e}")
            return page_urls if "page_urls" in locals() else []

    async def _get_next_page_url(self) -> Optional[str]:
        """Findet die URL der nächsten Seite"""

        try:
            html_content = await self.page.content()
            soup = BeautifulSoup(html_content, "html.parser")

            # Verschiedene Selektoren für "Nächste Seite" Links
            next_selectors = [
                'a[rel="next"]',
                'a:contains("Weiter")',
                'a:contains("Nächste")',
                'a:contains("Next")',
                'a:contains(">")',
                '.pagination a:contains(">")',
                '.pager a:contains(">")',
                '[class*="next"] a',
                '[class*="weiter"] a',
            ]

            for selector in next_selectors:
                try:
                    next_link = soup.select_one(selector)
                    if next_link:
                        href = next_link.get("href")
                        if href:
                            # Relative URLs zu absoluten konvertieren
                            if href.startswith("/"):
                                next_url = urljoin(self.base_url, href)
                            else:
                                next_url = href

                            self.logger.debug(f"Found next page URL: {next_url}")
                            return next_url
                except Exception as e:
                    self.logger.debug(f"Selector {selector} failed: {e}")
                    continue

            # Fallback: Suche nach Pagination-Pattern in Links
            all_links = soup.select("a[href]")

            for link in all_links:
                href = link.get("href", "")
                text = link.get_text(strip=True)

                # Pattern für Seitennummer (page+1)
                if self._is_next_page_link(href, text):
                    if href.startswith("/"):
                        next_url = urljoin(self.base_url, href)
                    else:
                        next_url = href

                    self.logger.debug(f"Found next page via pattern: {next_url}")
                    return next_url

            self.logger.debug("No next page URL found")
            return None

        except Exception as e:
            self.logger.error(f"Error finding next page URL: {e}")
            return None

    def _is_next_page_link(self, href: str, text: str) -> bool:
        """Prüft ob ein Link zur nächsten Seite führt"""

        # Text-basierte Prüfung
        next_keywords = ["weiter", "nächste", "next", ">", "▶", "→"]
        if any(keyword in text.lower() for keyword in next_keywords):
            return True

        # URL-basierte Prüfung für Seitennummer
        try:
            parsed = urlparse(href)
            query_params = parse_qs(parsed.query)

            # Häufige Parameter für Seitennummer
            page_params = ["page", "seite", "p", "offset"]

            for param in page_params:
                if param in query_params:
                    try:
                        page_num = int(query_params[param][0])
                        if page_num == self.current_page + 1:
                            return True
                    except (ValueError, IndexError):
                        continue
        except:
            pass

        return False

    async def _navigate_to_next_page(self, next_url: str) -> bool:
        """Navigiert zur nächsten Seite"""

        try:
            self.logger.debug(f"Navigating to next page: {next_url}")

            response = await self.page.goto(next_url, wait_until="domcontentloaded")

            if response and response.status < 400:
                # Warten bis Inhalte geladen sind
                await self._wait_for_page_load()

                self.current_page += 1
                self.logger.info(f"Successfully navigated to page {self.current_page}")
                return True
            else:
                self.logger.warning(
                    f"Navigation returned status {response.status if response else 'None'}"
                )
                return False

        except Exception as e:
            self.logger.error(f"Error navigating to next page: {e}")
            return False

    async def _wait_for_page_load(self) -> bool:
        """Wartet bis die Seite vollständig geladen ist"""

        try:
            # Warten auf Suchergebnisse
            result_selectors = [
                ".search-results",
                ".result-list",
                '[class*="result"]',
                '[class*="listing"]',
                "article",
            ]

            for selector in result_selectors:
                try:
                    await self.page.wait_for_selector(selector, timeout=10000)
                    self.logger.debug(f"Page loaded, found results: {selector}")
                    return True
                except PlaywrightTimeoutError:
                    continue

            # Fallback: Kurz warten
            await asyncio.sleep(3)
            return True

        except Exception as e:
            self.logger.warning(f"Error waiting for page load: {e}")
            return False

    async def _is_search_results_page(self) -> bool:
        """Prüft ob wir uns noch auf einer Suchergebnisseite befinden"""

        try:
            current_url = self.page.url.lower()
            title = (await self.page.title()).lower()

            # URL-basierte Prüfung
            url_indicators = ["suche", "search", "hausverwaltung", "düsseldorf"]
            if any(indicator in current_url for indicator in url_indicators):
                return True

            # Titel-basierte Prüfung
            title_indicators = ["hausverwaltung", "düsseldorf", "suche", "ergebnis"]
            if any(indicator in title for indicator in title_indicators):
                return True

            # Element-basierte Prüfung
            html_content = await self.page.content()
            soup = BeautifulSoup(html_content, "html.parser")

            result_elements = soup.select(
                '[class*="result"], [class*="listing"], article'
            )
            if len(result_elements) > 0:
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error checking if search results page: {e}")
            return False

    async def _wait_between_pages(self):
        """Wartet zwischen Seitenaufrufen (ethisches Scraping)"""

        min_delay = self.delay_between_pages.get("min", 2)
        max_delay = self.delay_between_pages.get("max", 5)

        delay = random.uniform(min_delay, max_delay)
        self.logger.debug(f"Waiting {delay:.2f} seconds before next page...")
        await asyncio.sleep(delay)

    async def get_pagination_info(self) -> Dict[str, Any]:
        """
        Gibt Informationen über die aktuelle Paginierung zurück

        Returns:
            Dict mit Paginierungs-Informationen
        """
        try:
            html_content = await self.page.content()
            soup = BeautifulSoup(html_content, "html.parser")

            pagination_info = {
                "current_page": self.current_page,
                "total_pages": None,
                "has_next": False,
                "has_previous": False,
                "total_results": None,
            }

            # Suche nach Paginierungs-Elementen
            pagination_selectors = [
                ".pagination",
                ".pager",
                ".page-nav",
                '[class*="pagination"]',
                '[class*="pager"]',
            ]

            for selector in pagination_selectors:
                try:
                    pagination = soup.select_one(selector)
                    if pagination:
                        # Aktuelle Seite
                        current = pagination.select_one(
                            '.current, .active, [class*="current"]'
                        )
                        if current:
                            try:
                                pagination_info["current_page"] = int(
                                    current.get_text(strip=True)
                                )
                            except:
                                pass

                        # Nächste/Vorherige Seite
                        next_link = pagination.select_one(
                            'a[rel="next"], a:contains("Weiter")'
                        )
                        prev_link = pagination.select_one(
                            'a[rel="prev"], a:contains("Zurück")'
                        )

                        pagination_info["has_next"] = next_link is not None
                        pagination_info["has_previous"] = prev_link is not None

                        break
                except:
                    continue

            # Suche nach Gesamtergebnis-Anzahl
            try:
                result_count_pattern = r"(\d+)\s*(Ergebnisse|Treffer|Einträge|results)"
                text_content = soup.get_text()
                match = re.search(result_count_pattern, text_content, re.IGNORECASE)
                if match:
                    pagination_info["total_results"] = int(match.group(1))
            except:
                pass

            return pagination_info

        except Exception as e:
            self.logger.error(f"Error getting pagination info: {e}")
            return {
                "current_page": self.current_page,
                "total_pages": None,
                "has_next": False,
                "has_previous": False,
                "total_results": None,
            }

    async def navigate_to_page(self, page_number: int) -> bool:
        """
        Navigiert direkt zu einer bestimmten Seitennummer

        Args:
            page_number: Zielseitennummer

        Returns:
            bool: True wenn erfolgreich
        """
        try:
            current_url = self.page.url

            # Versuche URL-Parameter zu modifizieren
            parsed = urlparse(current_url)
            query_params = parse_qs(parsed.query)

            # Häufige Parameter für Seitennummer
            page_params = ["page", "seite", "p"]

            for param in page_params:
                if param in query_params:
                    query_params[param] = [str(page_number)]

                    # URL rekonstruieren
                    from urllib.parse import urlencode

                    new_query = urlencode(query_params, doseq=True)
                    new_url = (
                        f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{new_query}"
                    )

                    # Zur neuen URL navigieren
                    response = await self.page.goto(
                        new_url, wait_until="domcontentloaded"
                    )

                    if response and response.status < 400:
                        await self._wait_for_page_load()
                        self.current_page = page_number
                        return True

            self.logger.warning(f"Could not navigate to page {page_number}")
            return False

        except Exception as e:
            self.logger.error(f"Error navigating to page {page_number}: {e}")
            return False
