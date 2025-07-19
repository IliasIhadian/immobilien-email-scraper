#!/usr/bin/env python3
"""
11880.com E-Mail-Scraper für Hausverwaltungen
Hauptausführungsdatei mit CLI-Interface
"""

import asyncio
import argparse
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.append(str(Path(__file__).parent / "src"))

from src.scraper.main_scraper import MainScraper
from src.utils.logging_config import setup_logging, get_logger
from src.utils.browser_manager import BrowserManager
from src.export.csv_exporter import CSVExporter

logger = get_logger(__name__)


async def main():
    """Hauptfunktion für den Scraper"""

    # Argument parsing
    parser = argparse.ArgumentParser(
        description="11880.com E-Mail-Scraper für Hausverwaltungen",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python main.py                                      # Standard-Scraping für Hausverwaltungen in Düsseldorf
  python main.py --location "Köln"                   # Scraping in Köln
  python main.py --search-term "Immobilienmakler"    # Andere Branche
  python main.py --max-pages 10                      # Nur 10 Seiten scrapen
  python main.py --test                              # Test-Modus mit wenigen Einträgen
        """,
    )

    parser.add_argument(
        "--location",
        default="Düsseldorf",
        help="Zielstadt für die Suche (default: Düsseldorf)",
    )

    parser.add_argument(
        "--search-term",
        default="Hausverwaltungen",
        help="Suchbegriff für Unternehmen (default: Hausverwaltungen)",
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=50,
        help="Maximale Anzahl der zu scrapenden Seiten (default: 50)",
    )

    parser.add_argument(
        "--output-dir",
        default="data",
        help="Ausgabe-Verzeichnis für CSV-Dateien (default: data)",
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Log-Level (default: INFO)",
    )

    parser.add_argument(
        "--headless", action="store_true", help="Browser im Headless-Modus ausführen"
    )

    parser.add_argument(
        "--test", action="store_true", help="Test-Modus: Scrapt nur wenige Einträge"
    )

    parser.add_argument(
        "--no-emails",
        action="store_true",
        help="Keine E-Mail-Extraktion durchführen (nur Firmendaten)",
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help="Basis-Delay zwischen Requests in Sekunden",
    )

    args = parser.parse_args()

    # Logging Setup
    setup_logging(level=args.log_level)

    logger.info("=" * 60)
    logger.info("🚀 11880.com E-Mail-Scraper gestartet")
    logger.info("=" * 60)
    logger.info(f"📍 Location: {args.location}")
    logger.info(f"🔍 Search Term: {args.search_term}")
    logger.info(f"📄 Max Pages: {args.max_pages}")
    logger.info(f"💾 Output Dir: {args.output_dir}")
    logger.info(f"🖥️ Headless: {args.headless}")
    logger.info(f"🧪 Test Mode: {args.test}")
    logger.info(f"📧 Extract Emails: {not args.no_emails}")

    if args.test:
        logger.info("⚠️ Test-Modus aktiviert - Nur wenige Einträge werden extrahiert")
        args.max_pages = 2  # Begrenzt auf 2 Seiten im Test-Modus

    # Browser Manager initialisieren
    browser_manager = BrowserManager(headless=args.headless)

    # CSV Exporter initialisieren
    csv_exporter = CSVExporter(output_directory=args.output_dir)

    # Main Scraper initialisieren
    scraper = MainScraper(browser_manager=browser_manager, csv_exporter=csv_exporter)

    try:
        start_time = datetime.now()

        # Scraping durchführen
        results = await scraper.scrape_companies(
            search_term=args.search_term,
            location=args.location,
            max_pages=args.max_pages,
            extract_emails=not args.no_emails,
            delay_override=args.delay,
            test_mode=args.test,
        )

        end_time = datetime.now()
        duration = end_time - start_time

        # Ergebnisse anzeigen
        logger.info("=" * 60)
        logger.info("✅ SCRAPING ABGESCHLOSSEN")
        logger.info("=" * 60)
        logger.info(f"⏱️ Dauer: {duration}")
        logger.info(f"📊 Gefundene Unternehmen: {results.get('total_companies', 0)}")
        logger.info(f"📧 Extrahierte E-Mails: {results.get('emails_found', 0)}")
        logger.info(f"💾 CSV-Datei: {results.get('output_file', 'N/A')}")

        if results.get("errors", 0) > 0:
            logger.warning(f"⚠️ Aufgetretene Fehler: {results['errors']}")

        # Performance-Statistiken
        if duration.total_seconds() > 0:
            companies_per_minute = (
                results.get("total_companies", 0) / duration.total_seconds()
            ) * 60
            logger.info(
                f"⚡ Performance: {companies_per_minute:.1f} Unternehmen/Minute"
            )

        logger.info("=" * 60)

        return 0

    except KeyboardInterrupt:
        logger.info("\n🛑 Scraping durch Benutzer unterbrochen")
        return 1

    except Exception as e:
        logger.error(f"❌ Unerwarteter Fehler: {e}")
        logger.exception("Stacktrace:")
        return 1

    finally:
        # Cleanup
        await scraper.cleanup()
        logger.info("🧹 Cleanup abgeschlossen")


def print_banner():
    """Zeigt ein schönes Banner"""
    banner = """
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║                🏢 11880.com E-Mail-Scraper 🏢               ║
    ║                                                              ║
    ║              Sammelt E-Mail-Adressen von                    ║
    ║              Hausverwaltungen automatisch                   ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """
    print(banner)


if __name__ == "__main__":
    # Banner anzeigen
    print_banner()

    # Event Loop Policy für Windows setzen
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    # Asyncio ausführen
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n🛑 Programm unterbrochen")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Kritischer Fehler: {e}")
        sys.exit(1)
