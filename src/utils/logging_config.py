"""
Logging Configuration für 11880.com Email Scraper
Zentralisierte Logging-Konfiguration mit verschiedenen Levels und Ausgabeformaten
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

import yaml


class ScraperLogger:
    """
    Zentraler Logger für den Email-Scraper
    Konfiguriert verschiedene Handler für Konsole und Datei-Ausgabe
    """

    def __init__(self, config_path: str = "config/settings.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        self.loggers: Dict[str, logging.Logger] = {}
        self._setup_base_logging()

    def _load_config(self) -> Dict[str, Any]:
        """Lädt die Logging-Konfiguration aus der YAML-Datei"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as file:
                config = yaml.safe_load(file)
                return config.get("logging", {})
        except FileNotFoundError:
            return self._default_logging_config()
        except Exception:
            return self._default_logging_config()

    def _default_logging_config(self) -> Dict[str, Any]:
        """Standard-Logging-Konfiguration"""
        return {
            "level": "INFO",
            "log_to_file": True,
            "log_file": "logs/scraper_{date}.log",
            "max_log_files": 10,
        }

    def _setup_base_logging(self):
        """Konfiguriert das Basis-Logging-System"""
        # Log-Verzeichnis erstellen
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        # Root Logger konfigurieren
        root_logger = logging.getLogger()
        root_logger.setLevel(self._get_log_level())

        # Handler entfernen falls vorhanden
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(logging.INFO)
        root_logger.addHandler(console_handler)

        # File Handler (falls aktiviert)
        if self.config.get("log_to_file", True):
            file_handler = self._create_file_handler()
            if file_handler:
                root_logger.addHandler(file_handler)

    def _get_log_level(self) -> int:
        """Konvertiert Log-Level String zu logging Konstante"""
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        return level_map.get(self.config.get("level", "INFO").upper(), logging.INFO)

    def _create_file_handler(self) -> Optional[logging.Handler]:
        """Erstellt einen File Handler mit Rotation"""
        try:
            # Log-Datei-Pfad generieren
            log_file_template = self.config.get("log_file", "logs/scraper_{date}.log")
            current_date = datetime.now().strftime("%Y-%m-%d")
            log_file = log_file_template.format(date=current_date)

            # Verzeichnis erstellen falls nicht vorhanden
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            # Rotating File Handler erstellen
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=self.config.get("max_log_files", 10),
                encoding="utf-8",
            )

            # File Formatter
            file_formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(self._get_log_level())

            return file_handler

        except Exception as e:
            print(f"Failed to create file handler: {e}")
            return None

    def get_logger(self, name: str) -> logging.Logger:
        """
        Gibt einen konfigurierten Logger für das angegebene Modul zurück

        Args:
            name: Name des Loggers (normalerweise __name__)

        Returns:
            logging.Logger: Konfigurierter Logger
        """
        if name not in self.loggers:
            logger = logging.getLogger(name)

            # Performance-Logger für spezielle Metriken
            if name.endswith(".performance"):
                logger.setLevel(logging.DEBUG)

            self.loggers[name] = logger

        return self.loggers[name]

    def log_scraping_start(self, target_url: str, search_params: Dict[str, Any]):
        """Loggt den Start eines Scraping-Vorgangs"""
        logger = self.get_logger("scraper.main")
        logger.info("=" * 50)
        logger.info("SCRAPING SESSION STARTED")
        logger.info(f"Target URL: {target_url}")
        logger.info(f"Search Parameters: {search_params}")
        logger.info("=" * 50)

    def log_scraping_end(self, total_extracted: int, duration: float):
        """Loggt das Ende eines Scraping-Vorgangs"""
        logger = self.get_logger("scraper.main")
        logger.info("=" * 50)
        logger.info("SCRAPING SESSION COMPLETED")
        logger.info(f"Total extracted entries: {total_extracted}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info("=" * 50)

    def log_page_extraction(self, page_num: int, extracted_count: int, page_url: str):
        """Loggt die Extraktion einer einzelnen Seite"""
        logger = self.get_logger("scraper.extraction")
        logger.info(
            f"Page {page_num}: Extracted {extracted_count} entries from {page_url}"
        )

    def log_email_extraction(self, company_name: str, email: str, source: str):
        """Loggt eine erfolgreiche E-Mail-Extraktion"""
        logger = self.get_logger("scraper.email")
        logger.info(
            f"Email found - Company: {company_name}, Email: {email}, Source: {source}"
        )

    def log_error_with_screenshot(
        self, error_msg: str, screenshot_path: Optional[str] = None
    ):
        """Loggt einen Fehler mit optionalem Screenshot-Pfad"""
        logger = self.get_logger("scraper.error")
        logger.error(f"Error occurred: {error_msg}")
        if screenshot_path:
            logger.error(f"Screenshot saved: {screenshot_path}")

    def log_performance_metric(self, metric_name: str, value: float, unit: str = ""):
        """Loggt Performance-Metriken"""
        logger = self.get_logger("scraper.performance")
        logger.debug(f"METRIC - {metric_name}: {value} {unit}")

    def log_retry_attempt(
        self, operation: str, attempt: int, max_attempts: int, error: str
    ):
        """Loggt Retry-Versuche"""
        logger = self.get_logger("scraper.retry")
        logger.warning(f"Retry {attempt}/{max_attempts} for {operation}: {error}")


# Globale Logger-Instanz
_scraper_logger = None


def get_scraper_logger() -> ScraperLogger:
    """
    Gibt die globale ScraperLogger-Instanz zurück (Singleton)

    Returns:
        ScraperLogger: Konfigurierte Logger-Instanz
    """
    global _scraper_logger
    if _scraper_logger is None:
        _scraper_logger = ScraperLogger()
    return _scraper_logger


def setup_logging(level: Optional[str] = None, config_path: Optional[str] = None):
    """
    Initialisiert das Logging-System

    Args:
        level: Optionaler Log-Level (überschreibt Konfiguration)
        config_path: Optionaler Pfad zur Konfigurationsdatei
    """
    global _scraper_logger

    # Logger-Instanz erstellen
    if config_path:
        _scraper_logger = ScraperLogger(config_path)
    else:
        _scraper_logger = ScraperLogger()

    # Log-Level überschreiben falls angegeben
    if level and _scraper_logger:
        level = level.upper()
        log_level = _scraper_logger._get_log_level()  # get default

        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }

        new_level = level_map.get(level, log_level)

        # Level für alle Handler des Root-Loggers setzen
        root_logger = logging.getLogger()
        root_logger.setLevel(new_level)
        for handler in root_logger.handlers:
            handler.setLevel(new_level)

        _scraper_logger.get_logger("main").info(f"Log level set to {level}")


# Convenience-Funktionen für schnellen Zugriff
def get_logger(name: str) -> logging.Logger:
    """Convenience-Funktion für get_scraper_logger().get_logger()"""
    return get_scraper_logger().get_logger(name)


def log_scraping_start(target_url: str, search_params: Dict[str, Any]):
    """Convenience-Funktion für Scraping-Start-Log"""
    get_scraper_logger().log_scraping_start(target_url, search_params)


def log_scraping_end(total_extracted: int, duration: float):
    """Convenience-Funktion für Scraping-End-Log"""
    get_scraper_logger().log_scraping_end(total_extracted, duration)


def log_email_extraction(company_name: str, email: str, source: str):
    """Convenience-Funktion für E-Mail-Extraktion-Log"""
    get_scraper_logger().log_email_extraction(company_name, email, source)


# Initialisierung beim Import
setup_logging()
