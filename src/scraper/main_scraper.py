"""
Main Scraper Orchestrator für 11880.com Email Scraper
Koordiniert alle Scraping-Komponenten für den kompletten Workflow
"""

import asyncio
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
import random

import yaml

from ..utils.browser_manager import BrowserManager
from ..utils.logging_config import ScraperLogger, get_logger
from .navigator import Navigator, NavigationError
from .data_extractor import DataExtractor, CompanyData
from .email_extractor import EmailExtractor
from .pagination_handler import PaginationHandler
from ..export.csv_exporter import CSVExporter


class MainScraper:
    """
    Haupt-Orchestrator für den 11880.com Email Scraper
    Koordiniert alle Scraping-Komponenten und den gesamten Workflow
    """

    def __init__(
        self,
        browser_manager: BrowserManager,
        csv_exporter: CSVExporter,
        config_path: str = "config/settings.yaml",
    ):
        self.config_path = config_path
        self.config = self._load_config()

        # Logging initialisieren
        self.scraper_logger = ScraperLogger()
        self.logger = get_logger(__name__)

        # Komponenten
        self.browser_manager = browser_manager
        self.csv_exporter = csv_exporter
        self.navigator: Optional[Navigator] = None
        self.data_extractor: Optional[DataExtractor] = None
        self.email_extractor: Optional[EmailExtractor] = None
        self.pagination_handler: Optional[PaginationHandler] = None

        # Statistiken
        self.stats = {
            "start_time": None,
            "end_time": None,
            "pages_processed": 0,
            "companies_found": 0,
            "emails_extracted": 0,
            "errors_encountered": 0,
        }

    def _load_config(self) -> Dict[str, Any]:
        """Lädt die Konfiguration aus der YAML-Datei"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as file:
                return yaml.safe_load(file)
        except Exception as e:
            print(f"Warning: Could not load config from {self.config_path}: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Gibt eine Standard-Konfiguration zurück"""
        return {
            "target": {
                "base_url": "https://www.11880.com",
                "search_term": "Hausverwaltungen",
                "location": "Düsseldorf",
            },
            "browser": {"headless": True, "timeout": 30000},
            "scraping": {
                "delay_between_requests": {"min": 2, "max": 5},
                "max_pages": 50,
            },
            "email": {
                "extract_from_detail_page": True,
                "extract_from_website": True,
                "extract_from_impressum": True,
            },
            "export": {
                "format": "csv",
                "filename": "hausverwaltungen_duesseldorf_{timestamp}.csv",
            },
        }

    async def initialize(self):
        """Initialisiert alle Scraper-Komponenten"""
        try:
            self.logger.info("Initializing scraper components...")

            # Browser Manager ist bereits initialisiert, wir holen nur die Page
            page = await self.browser_manager.get_or_create_page()

            # Komponenten mit der Page initialisieren
            self.navigator = Navigator(page, self.config)
            self.data_extractor = DataExtractor(page, self.config)
            self.email_extractor = EmailExtractor(page, self.config)
            self.pagination_handler = PaginationHandler(page, self.config)

            self.logger.info("All scraper components initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize scraper components: {e}")
            raise

    async def scrape_companies(
        self,
        search_term: str,
        location: str,
        max_pages: int,
        extract_emails: bool = True,
        delay_override: Optional[float] = None,
        test_mode: bool = False,
    ) -> Dict[str, Any]:
        """
        Führt den kompletten Scraping-Prozess aus

        Returns:
            Dict: Zusammenfassung der Ergebnisse
        """
        try:
            self.stats["start_time"] = datetime.now()

            # Target-Konfiguration überschreiben
            self.config["target"]["search_term"] = search_term
            self.config["target"]["location"] = location
            self.config["scraping"]["max_pages"] = max_pages

            if delay_override is not None:
                self.config["scraping"]["delay_between_requests"]["min"] = (
                    delay_override
                )
                self.config["scraping"]["delay_between_requests"]["max"] = (
                    delay_override
                )

            self.logger.info("Starting complete scraping process")

            # Initialisieren
            await self.initialize()

            # 1. Zu Suchergebnisseite navigieren
            search_url = await self._navigate_to_search_results()
            if not search_url:
                raise Exception("Failed to navigate to search results")

            # 2. Alle Seiten durchlaufen und Firmendaten sammeln
            all_companies = await self._scrape_all_pages(test_mode)

            if not all_companies:
                self.logger.warning("No companies found during scraping")
                return self.get_statistics()

            self.stats["companies_found"] = len(all_companies)
            self.logger.info(f"Found {len(all_companies)} companies total")

            # 3. E-Mail-Adressen extrahieren (falls gewünscht)
            if extract_emails:
                companies_with_emails = await self._extract_all_emails(all_companies)
                emails_found = sum(
                    1 for company in companies_with_emails if company.email
                )
                self.stats["emails_extracted"] = emails_found
                self.logger.info(f"Extracted {emails_found} email addresses")
                final_companies = companies_with_emails
            else:
                final_companies = all_companies

            # 4. Daten als CSV exportieren
            output_file = await self._export_results(final_companies)

            self.stats["end_time"] = datetime.now()
            await self._log_final_statistics()

            final_stats = self.get_statistics()
            final_stats["output_file"] = output_file
            return final_stats

        except Exception as e:
            self.logger.error(f"Error during complete scraping process: {e}")
            self.stats["errors_encountered"] += 1
            raise
        finally:
            await self.cleanup()

    async def _navigate_to_search_results(self) -> bool:
        """Navigiert zur Suchergebnisseite."""
        try:
            # Direkt zur Suchergebnisseite navigieren
            if not await self.navigator.start_scraping():
                raise NavigationError(
                    "Navigation zur Suchergebnisseite fehlgeschlagen."
                )

            self.logger.info("Navigation zur Suchergebnisseite erfolgreich.")
            return True

        except Exception as e:
            self.logger.error(f"Error navigating to search results: {e}")
            self.stats["errors_encountered"] += 1
            return False

    async def _scrape_all_pages(self, test_mode: bool = False) -> List[CompanyData]:
        """Scrapet alle Seiten bis zum Maximum oder bis keine weiteren Seiten verfügbar sind."""
        all_companies = []
        current_page = 1
        max_pages = self.config["scraping"]["max_pages"]

        try:
            while current_page <= max_pages:
                self.logger.info(f"Processing page {current_page}")

                # Auf das erste Suchergebnis klicken
                if not await self.navigator.click_first_result():
                    self.logger.error("Failed to click on first result")
                    break

                # Warten, bis die Detailseite geladen ist
                try:
                    await self.navigator.page.wait_for_load_state(
                        "networkidle", timeout=30000
                    )
                    self.logger.info(
                        "Detail page loaded, waiting for content to stabilize"
                    )
                    await asyncio.sleep(5)  # Wait for any dynamic content
                except Exception as e:
                    self.logger.warning(f"Error waiting for page load: {e}")

                # Daten von der Detailseite extrahieren
                companies = await self.data_extractor.extract_all_listings_from_page()

                if companies:
                    self.logger.info(f"Successfully extracted data from detail page")
                    all_companies.extend(companies)

                    # Direkt in CSV speichern
                    await self._export_results(companies)
                else:
                    self.logger.warning("No data could be extracted from detail page")

                # Zurück zur Suchergebnisseite
                if not await self.navigator.return_to_search_results():
                    self.logger.error("Failed to return to search results")
                    break

                # Warten bis die Suchergebnisseite wieder geladen ist
                try:
                    await self.navigator.page.wait_for_load_state(
                        "networkidle", timeout=30000
                    )
                    self.logger.info("Search results page loaded")
                    await asyncio.sleep(5)  # Wait for any dynamic content
                except Exception as e:
                    self.logger.warning(
                        f"Error waiting for search results page load: {e}"
                    )

                if test_mode and len(all_companies) >= 5:
                    self.logger.info("Test mode: Stopping after 5 companies")
                    break

                # Zur nächsten Seite navigieren
                has_next = await self.pagination_handler.go_to_next_page()
                if not has_next:
                    self.logger.info("No more pages available")
                    break

                current_page += 1
                self.stats["pages_processed"] = current_page

                # Zufällige Verzögerung zwischen Requests
                delay = random.uniform(
                    self.config["scraping"]["delay_between_requests"]["min"],
                    self.config["scraping"]["delay_between_requests"]["max"],
                )
                await asyncio.sleep(delay)

            return all_companies

        except Exception as e:
            self.logger.error(f"Error while scraping pages: {e}")
            self.stats["errors_encountered"] += 1
            return all_companies  # Return what we have so far

    async def _extract_all_emails(
        self, companies: List[CompanyData]
    ) -> List[CompanyData]:
        """Extrahiert E-Mail-Adressen für alle Firmen"""
        try:
            self.logger.info(
                f"Starting email extraction for {len(companies)} companies..."
            )

            companies_with_emails = await self.email_extractor.extract_emails_bulk(
                companies
            )

            emails_found = sum(1 for company in companies_with_emails if company.email)
            success_rate = (emails_found / len(companies)) * 100 if companies else 0

            self.logger.info(
                f"Email extraction completed: {emails_found}/{len(companies)} emails found ({success_rate:.1f}%)"
            )

            return companies_with_emails

        except Exception as e:
            self.logger.error(f"Error during email extraction: {e}")
            self.stats["errors_encountered"] += 1
            return companies

    async def _export_results(self, companies: List[CompanyData]) -> str:
        """Exportiert die Ergebnisse als CSV"""
        try:
            self.logger.info("Exporting results to CSV...")

            # Wenn noch keine Datei existiert, erstelle eine neue
            if not hasattr(self, "output_file"):
                self.output_file = await self.csv_exporter.export_companies(companies)
            else:
                # Füge die neuen Daten zur bestehenden Datei hinzu
                await self.csv_exporter.append_companies(companies, self.output_file)

            self.logger.info(f"Results exported to: {self.output_file}")
            return self.output_file

        except Exception as e:
            self.logger.error(f"Error exporting results: {e}")
            self.stats["errors_encountered"] += 1
            return ""

    async def _log_final_statistics(self):
        """Loggt finale Statistiken"""
        try:
            duration = self.stats["end_time"] - self.stats["start_time"]

            self.logger.info("=" * 60)
            self.logger.info("SCRAPING COMPLETED - FINAL STATISTICS")
            self.logger.info("=" * 60)
            self.logger.info(f"Duration: {duration}")
            self.logger.info(f"Pages processed: {self.stats['pages_processed']}")
            self.logger.info(f"Companies found: {self.stats['companies_found']}")
            self.logger.info(f"Emails extracted: {self.stats['emails_extracted']}")
            self.logger.info(
                f"Success rate: {(self.stats['emails_extracted'] / self.stats['companies_found'] * 100) if self.stats['companies_found'] > 0 else 0:.1f}%"
            )
            self.logger.info(f"Errors encountered: {self.stats['errors_encountered']}")
            self.logger.info("=" * 60)

        except Exception as e:
            self.logger.error(f"Error logging final statistics: {e}")

    async def cleanup(self):
        """Räumt Ressourcen auf"""
        try:
            self.logger.info("Cleaning up resources...")

            if self.browser_manager:
                await self.browser_manager.cleanup()

            self.logger.info("Cleanup completed")

        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")

    # Utility Methods

    async def test_navigation(self) -> bool:
        """Testet die Navigation zur Suchergebnisseite"""
        try:
            await self.initialize()
            search_url = await self._navigate_to_search_results()
            await self.cleanup()
            return search_url is not None
        except Exception as e:
            self.logger.error(f"Navigation test failed: {e}")
            return False

    async def test_data_extraction(self, max_companies: int = 5) -> List[CompanyData]:
        """Testet die Datenextraktion von der ersten Seite"""
        try:
            await self.initialize()
            await self._navigate_to_search_results()

            companies = await self.data_extractor.extract_all_listings_from_page()
            limited_companies = companies[:max_companies] if companies else []

            await self.cleanup()
            return limited_companies
        except Exception as e:
            self.logger.error(f"Data extraction test failed: {e}")
            return []

    async def test_email_extraction(self, company_data: CompanyData) -> CompanyData:
        """Testet die E-Mail-Extraktion für eine einzelne Firma"""
        try:
            await self.initialize()

            updated_company = await self.email_extractor.extract_emails_for_company(
                company_data
            )

            await self.cleanup()
            return updated_company
        except Exception as e:
            self.logger.error(f"Email extraction test failed: {e}")
            return company_data

    def get_statistics(self) -> Dict[str, Any]:
        """Gibt aktuelle Statistiken zurück"""
        return self.stats.copy()


# Convenience Functions


async def run_scraper(config_path: str = "config/settings.yaml") -> str:
    """
    Convenience-Funktion zum Ausführen des kompletten Scrapers

    Args:
        config_path: Pfad zur Konfigurationsdatei

    Returns:
        str: Pfad zur exportierten CSV-Datei
    """
    scraper = MainScraper(config_path)
    try:
        await scraper.initialize()
        return await scraper.run_complete_scraping()
    except Exception as e:
        print(f"Error running scraper: {e}")
        return ""
    finally:
        await scraper.cleanup()


async def test_scraper_components(config_path: str = "config/settings.yaml"):
    """
    Testet alle Scraper-Komponenten

    Args:
        config_path: Pfad zur Konfigurationsdatei
    """
    scraper = MainScraper(config_path)

    try:
        print("Testing scraper components...")

        # Test Navigation
        print("1. Testing navigation...")
        navigation_ok = await scraper.test_navigation()
        print(f"   Navigation: {'✓' if navigation_ok else '✗'}")

        if navigation_ok:
            # Test Data Extraction
            print("2. Testing data extraction...")
            test_companies = await scraper.test_data_extraction(3)
            print(f"   Data extraction: {'✓' if test_companies else '✗'}")
            print(f"   Found {len(test_companies)} test companies")

            if test_companies:
                # Test Email Extraction
                print("3. Testing email extraction...")
                test_company = test_companies[0]
                print(f"   Testing with: {test_company.name}")

                updated_company = await scraper.test_email_extraction(test_company)
                email_found = updated_company.email is not None
                print(f"   Email extraction: {'✓' if email_found else '✗'}")
                if email_found:
                    print(f"   Found email: {updated_company.email}")

        print("Component testing completed.")

    except Exception as e:
        print(f"Error during component testing: {e}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Test-Modus
        asyncio.run(test_scraper_components())
    else:
        # Vollständiger Scraping-Lauf
        output_file = asyncio.run(run_scraper())
        if output_file:
            print(f"Scraping completed successfully. Results saved to: {output_file}")
        else:
            print("Scraping failed or no results found.")
