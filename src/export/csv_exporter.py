"""
CSV Exporter für 11880.com Email Scraper
Exportiert gesammelte Firmendaten in CSV-Format
"""

import csv
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

from ..scraper.data_extractor import CompanyData
from ..utils.logging_config import get_logger


class CSVExporter:
    """
    Exportiert Firmendaten in CSV-Format
    Verwaltet Duplikate und erstellt formatierte Ausgabedateien
    """

    def __init__(
        self,
        output_directory: str = "output/companies",
        config: Optional[Dict[str, Any]] = None,
    ):
        self.config = config or {}
        self.logger = get_logger(__name__)

        # Export-Konfiguration
        self.export_config = self.config.get("export", {})
        self.output_format = self.export_config.get("format", "csv")
        self.filename_template = self.export_config.get(
            "filename", "hausverwaltungen_{timestamp}.csv"
        )

        # Absoluten Pfad für das Ausgabeverzeichnis erstellen
        self.output_directory = os.path.abspath(output_directory)
        self.logger.info(f"CSV files will be saved to: {self.output_directory}")

        # CSV-Spalten definieren
        self.csv_columns = [
            "Firma",
            "Adresse",
            "Website",
            "Telefon",
            "E-Mail",
            "Datenquelle",
            "Erfassungsdatum",
        ]

        # Ausgabeverzeichnis erstellen
        self._ensure_output_directory()

    def _ensure_output_directory(self):
        """Stellt sicher, dass das Ausgabeverzeichnis existiert"""
        try:
            output_path = Path(self.output_directory)
            output_path.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Output directory ensured: {output_path}")
        except Exception as e:
            self.logger.error(f"Failed to create output directory: {e}")
            # Fallback auf aktuelles Verzeichnis
            self.output_directory = "."

    async def export_companies(self, companies: List[CompanyData]) -> str:
        """
        Exportiert Firmendaten als CSV-Datei

        Args:
            companies: Liste von CompanyData-Objekten

        Returns:
            str: Pfad zur erstellten CSV-Datei
        """
        try:
            self.logger.info(f"Exporting {len(companies)} companies to CSV...")

            # Duplikate entfernen
            unique_companies = self._remove_duplicates(companies)
            self.logger.info(
                f"After deduplication: {len(unique_companies)} unique companies"
            )

            # Ausgabedatei erstellen
            output_file = self._generate_output_filename()

            # CSV schreiben
            rows_written = await self._write_csv_file(output_file, unique_companies)

            if rows_written > 0:
                self.logger.info(
                    f"Successfully exported {rows_written} companies to: {output_file}"
                )

                # Zusätzliche Statistiken loggen
                await self._log_export_statistics(unique_companies, output_file)

                return output_file
            else:
                self.logger.warning("No data was written to CSV file")
                return ""

        except Exception as e:
            self.logger.error(f"Error exporting companies to CSV: {e}")
            return ""

    def _remove_duplicates(self, companies: List[CompanyData]) -> List[CompanyData]:
        """Entfernt Duplikate basierend auf Firmenname und Adresse"""
        try:
            seen = set()
            unique_companies = []

            for company in companies:
                # Eindeutigen Schlüssel erstellen (Name + Adresse)
                key = self._create_duplicate_key(company)

                if key not in seen:
                    seen.add(key)
                    unique_companies.append(company)
                else:
                    self.logger.debug(f"Duplicate found and removed: {company.name}")

            duplicates_removed = len(companies) - len(unique_companies)
            if duplicates_removed > 0:
                self.logger.info(f"Removed {duplicates_removed} duplicate entries")

            return unique_companies

        except Exception as e:
            self.logger.error(f"Error removing duplicates: {e}")
            return companies

    def _create_duplicate_key(self, company: CompanyData) -> str:
        """Erstellt einen eindeutigen Schlüssel für Duplikatserkennung"""
        name = (company.name or "").strip().lower()
        address = (company.address or "").strip().lower()

        # Normalisierung für bessere Duplikatserkennung
        name = name.replace("&", "und").replace("  ", " ")
        address = address.replace("  ", " ")

        return f"{name}|{address}"

    def _generate_output_filename(self) -> str:
        """Generiert den Ausgabedateinamen mit Zeitstempel"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self.filename_template.format(timestamp=timestamp)

            output_path = Path(self.output_directory) / filename
            return str(output_path)

        except Exception as e:
            self.logger.error(f"Error generating output filename: {e}")
            # Fallback-Dateiname
            fallback_filename = (
                f"scraping_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )
            return str(Path(self.output_directory) / fallback_filename)

    async def _write_csv_file(
        self, output_file: str, companies: List[CompanyData]
    ) -> int:
        """Schreibt Firmendaten in CSV-Datei"""
        try:
            rows_written = 0
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=self.csv_columns)

                # Header schreiben
                writer.writeheader()

                # Firmendaten schreiben
                for company in companies:
                    try:
                        row_data = self._company_to_csv_row(company, current_time)
                        writer.writerow(row_data)
                        rows_written += 1

                    except Exception as e:
                        self.logger.warning(
                            f"Error writing company {company.name}: {e}"
                        )
                        continue

            return rows_written

        except Exception as e:
            self.logger.error(f"Error writing CSV file: {e}")
            return 0

    def _company_to_csv_row(
        self, company: CompanyData, timestamp: str
    ) -> Dict[str, str]:
        """Konvertiert CompanyData zu CSV-Zeile"""
        return {
            "Firma": company.name or "",
            "Adresse": company.address or "",
            "Website": company.website or "",
            "Telefon": company.phone or "",
            "E-Mail": company.email or "",
            "Datenquelle": "11880.com",
            "Erfassungsdatum": timestamp,
        }

    async def append_companies(
        self, companies: List[CompanyData], output_file: str
    ) -> None:
        """
        Fügt neue Firmendaten an eine bestehende CSV-Datei an

        Args:
            companies: Liste von CompanyData-Objekten
            output_file: Pfad zur bestehenden CSV-Datei
        """
        try:
            self.logger.info(f"Appending {len(companies)} companies to {output_file}")
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            with open(output_file, "a", newline="", encoding="utf-8") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=self.csv_columns)

                # Firmendaten anhängen
                for company in companies:
                    try:
                        row_data = self._company_to_csv_row(company, current_time)
                        writer.writerow(row_data)

                    except Exception as e:
                        self.logger.warning(
                            f"Error appending company {company.name}: {e}"
                        )
                        continue

            self.logger.info(f"Successfully appended data to {output_file}")

        except Exception as e:
            self.logger.error(f"Error appending to CSV file: {e}")

    async def _log_export_statistics(
        self, companies: List[CompanyData], output_file: str
    ):
        """Loggt Exportstatistiken"""
        try:
            total_companies = len(companies)
            companies_with_email = sum(1 for c in companies if c.email)
            companies_with_website = sum(1 for c in companies if c.website)
            companies_with_phone = sum(1 for c in companies if c.phone)

            file_size = (
                os.path.getsize(output_file) if os.path.exists(output_file) else 0
            )
            file_size_kb = file_size / 1024

            self.logger.info("=" * 50)
            self.logger.info("CSV EXPORT STATISTICS")
            self.logger.info("=" * 50)
            self.logger.info(f"Output file: {output_file}")
            self.logger.info(f"File size: {file_size_kb:.1f} KB")
            self.logger.info(f"Total companies: {total_companies}")
            self.logger.info(
                f"Companies with email: {companies_with_email} ({(companies_with_email / total_companies * 100) if total_companies > 0 else 0:.1f}%)"
            )
            self.logger.info(
                f"Companies with website: {companies_with_website} ({(companies_with_website / total_companies * 100) if total_companies > 0 else 0:.1f}%)"
            )
            self.logger.info(
                f"Companies with phone: {companies_with_phone} ({(companies_with_phone / total_companies * 100) if total_companies > 0 else 0:.1f}%)"
            )
            self.logger.info("=" * 50)

        except Exception as e:
            self.logger.error(f"Error logging export statistics: {e}")

    async def export_sample_csv(
        self, companies: List[CompanyData], max_entries: int = 10
    ) -> str:
        """
        Exportiert eine Stichprobe der Daten für Tests

        Args:
            companies: Liste von CompanyData-Objekten
            max_entries: Maximale Anzahl von Einträgen in der Stichprobe

        Returns:
            str: Pfad zur erstellten Sample-CSV-Datei
        """
        try:
            self.logger.info(f"Creating sample CSV with max {max_entries} entries...")

            # Stichprobe erstellen
            sample_companies = companies[:max_entries] if companies else []

            # Sample-Dateiname generieren
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            sample_filename = f"sample_hausverwaltungen_{timestamp}.csv"
            sample_file = str(Path(self.output_directory) / sample_filename)

            # CSV schreiben
            rows_written = await self._write_csv_file(sample_file, sample_companies)

            if rows_written > 0:
                self.logger.info(
                    f"Sample CSV created: {sample_file} ({rows_written} entries)"
                )
                return sample_file
            else:
                self.logger.warning("No data was written to sample CSV")
                return ""

        except Exception as e:
            self.logger.error(f"Error creating sample CSV: {e}")
            return ""

    async def validate_csv_file(self, csv_file: str) -> bool:
        """
        Validiert eine CSV-Datei

        Args:
            csv_file: Pfad zur CSV-Datei

        Returns:
            bool: True wenn gültig, False andernfalls
        """
        try:
            if not os.path.exists(csv_file):
                self.logger.error(f"CSV file does not exist: {csv_file}")
                return False

            row_count = 0
            with open(csv_file, "r", encoding="utf-8") as file:
                reader = csv.DictReader(file)

                # Header validieren
                if reader.fieldnames != self.csv_columns:
                    self.logger.error(f"Invalid CSV headers in {csv_file}")
                    return False

                # Zeilen zählen und Basis-Validierung
                for row in reader:
                    row_count += 1

                    # Prüfe ob mindestens Name und Adresse vorhanden
                    if not row.get("Firma") or not row.get("Adresse"):
                        self.logger.warning(f"Row {row_count} missing required fields")

            self.logger.info(
                f"CSV validation successful: {csv_file} ({row_count} rows)"
            )
            return True

        except Exception as e:
            self.logger.error(f"Error validating CSV file: {e}")
            return False

    def get_output_directory(self) -> str:
        """Gibt das Ausgabeverzeichnis zurück"""
        return self.output_directory

    def set_output_directory(self, directory: str):
        """Setzt ein neues Ausgabeverzeichnis"""
        self.output_directory = directory
        self._ensure_output_directory()


# Utility Functions


def create_sample_data() -> List[CompanyData]:
    """Erstellt Beispieldaten für Tests"""
    return [
        CompanyData(
            name="Muster Hausverwaltung GmbH",
            address="40210 Düsseldorf, Musterstraße 123",
            website="https://www.muster-hv.de",
            phone="0211 123456",
            email="info@muster-hv.de",
        ),
        CompanyData(
            name="Düsseldorf Immobilien Service",
            address="40211 Düsseldorf, Beispielweg 45",
            website="https://www.dus-immo.de",
            phone="0211 654321",
            email="kontakt@dus-immo.de",
        ),
        CompanyData(
            name="Rhein Verwaltungs AG",
            address="40212 Düsseldorf, Rheinufer 67",
            website=None,
            phone="0211 789012",
            email=None,
        ),
    ]


async def test_csv_export():
    """Testet den CSV-Export mit Beispieldaten"""
    config = {
        "export": {
            "format": "csv",
            "filename": "test_export_{timestamp}.csv",
            "output_directory": "test_data",
        }
    }

    exporter = CSVExporter(config)
    sample_companies = create_sample_data()

    print("Testing CSV export...")

    # Sample-Export testen
    sample_file = await exporter.export_sample_csv(sample_companies, max_entries=2)
    if sample_file:
        print(f"✓ Sample CSV created: {sample_file}")

        # Validierung testen
        is_valid = await exporter.validate_csv_file(sample_file)
        print(f"✓ CSV validation: {'passed' if is_valid else 'failed'}")
    else:
        print("✗ Sample CSV creation failed")

    # Vollständigen Export testen
    full_file = await exporter.export_companies(sample_companies)
    if full_file:
        print(f"✓ Full CSV created: {full_file}")
    else:
        print("✗ Full CSV creation failed")


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_csv_export())
