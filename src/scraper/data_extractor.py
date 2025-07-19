"""Data Extractor für 11880.com Email Scraper"""

import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from bs4 import BeautifulSoup
from playwright.async_api import Page
from ..utils.logging_config import get_logger


@dataclass
class CompanyData:
    """Datenklasse für Firmeninformationen"""

    name: str
    address: str
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class DataExtractor:
    """Extrahiert Firmendaten aus 11880.com Detailseiten"""

    def __init__(self, page: Page, config: Dict[str, Any]):
        self.page = page
        self.config = config
        self.logger = get_logger(__name__)  # Add logger initialization

    async def extract_all_listings_from_page(self) -> List[CompanyData]:
        """Extrahiert Firmendaten von der aktuellen Detailseite"""
        try:
            current_url = self.page.url
            self.logger.info(
                f"Checking if current page is a detail page: {current_url}"
            )

            # Get HTML content first
            html = await self.page.content()
            soup = BeautifulSoup(html, "html.parser")

            # Check if we're on a detail page using both URL and content indicators
            is_detail = self._is_detail_page(soup)
            if not is_detail:
                self.logger.warning("Current page does not appear to be a detail page")
                return []

            self.logger.info("Extracting data from detail page")

            # Wait for any of the detail page indicators with increased timeout
            detail_selectors = [
                ".detail-card",
                ".company-detail",
                ".business-detail",
                ".profile-detail",
                ".company-profile",
                "h1.detail-card-title",
                "h1.company-name",
                "h1[itemprop='name']",
                ".company-title h1",
                "h1.title",  # hinzugefügt für 11880
            ]

            try:
                for selector in detail_selectors:
                    try:
                        await self.page.wait_for_selector(
                            selector, timeout=15000
                        )  # Increased timeout
                        self.logger.info(f"Found detail page indicator: {selector}")
                        break
                    except Exception:
                        continue
            except Exception:
                self.logger.info(
                    "Detail selectors not found, continuing with extraction attempt"
                )

            # Name extrahieren
            name = ""
            name_selectors = [
                "h1.title",  # 11880
                "h1.detail-card-title",
                "h1.company-name",
                "h1[itemprop='name']",
                ".company-title h1",
            ]
            for selector in name_selectors:
                name_element = soup.select_one(selector)
                if name_element:
                    name = name_element.text.strip()
                    break

            # Adresse extrahieren
            address = ""
            # Suche nach dem Location-Icon und dann das nächste Label
            location_icon = soup.select_one(".entry-detail-list__icon--location")
            if location_icon:
                label = location_icon.find_next(
                    "div", class_="entry-detail-list__label"
                )
                if label:
                    address = " ".join(label.stripped_strings)
            if not address:
                # Fallback: alte Selektoren
                address_selectors = [
                    ".detail-card-address",
                    "address",
                    "[itemprop='address']",
                    ".company-address",
                ]
                for selector in address_selectors:
                    address_element = soup.select_one(selector)
                    if address_element:
                        address = address_element.text.strip()
                        break

            # Telefonnummer extrahieren
            phone = None
            phone_element = soup.select_one('a[href^="tel:"]')
            if phone_element:
                phone = phone_element.get("href", "").replace("tel:", "").strip()

            # Website extrahieren
            website = None
            website_element = soup.select_one("a.tracking--entry-detail-website-link")
            if website_element:
                website = website_element.get("href")
            if not website:
                # Fallback: alte Selektoren
                website_selectors = [
                    "a.detail-card-website",
                    'a[itemprop="url"]',
                    ".company-website a",
                    'a[href*="http"]:not([href*="11880.com"])',
                ]
                for selector in website_selectors:
                    website_element = soup.select_one(selector)
                    if website_element:
                        website = website_element.get("href")
                        break

            # Email extrahieren
            email = None
            # 1. Versuche meta[itemprop="email"]
            email_element = soup.select_one('meta[itemprop="email"]')
            if email_element:
                email = email_element.get("content", "").strip()
            else:
                # 2. Versuche Cloudflare-verschleierte E-Mail
                cf_email = soup.select_one("a.__cf_email__")
                if cf_email and cf_email.has_attr("data-cfemail"):
                    email = self._decode_cfemail(cf_email["data-cfemail"])
                else:
                    # 3. Fallback: alte Selektoren
                    email_selectors = [
                        'a[href^="mailto:"]',
                        '[itemprop="email"]',
                        ".company-email",
                    ]
                    for selector in email_selectors:
                        email_element = soup.select_one(selector)
                        if email_element:
                            email = (
                                email_element.get("href", "")
                                .replace("mailto:", "")
                                .strip()
                                or email_element.text.strip()
                            )
                            break

            print("detail page data", name, address, website, phone, email)
            if name or address:  # Mindestens eines muss vorhanden sein
                self.logger.info(f"Found company: {name}")
                company = CompanyData(
                    name=name,
                    address=address,
                    website=website,
                    phone=phone,
                    email=email,
                )
                return [company]

            self.logger.warning("No company data found on detail page")
            return []

        except Exception as e:
            self.logger.error(f"Error extracting data from detail page: {e}")
            return []

    def _is_detail_page(self, soup: BeautifulSoup) -> bool:
        """Prüft ob die aktuelle Seite eine Detailseite ist"""
        # Typische Elemente einer Detailseite
        detail_indicators = [
            'div[class*="company-detail"]',
            'div[class*="business-detail"]',
            'div[class*="profile-detail"]',
            'section[class*="detail"]',
            ".company-profile",
            "#opening-hours",  # Öffnungszeiten Tab
            'a[href*="Karte & Route"]',  # Karte & Route Tab
        ]

        for indicator in detail_indicators:
            if soup.select_one(indicator):
                return True
        return False

    async def _extract_from_detail_page(
        self, soup: BeautifulSoup
    ) -> Optional[CompanyData]:
        """Extrahiert Firmendaten von der Detailseite"""
        try:
            # Name aus dem Titel oder h1 Element
            name_element = soup.select_one(
                'h1, .company-name, [class*="company-title"]'
            )
            name = name_element.get_text(strip=True) if name_element else None

            # Adresse aus der Detailseite
            address = None
            address_elements = [
                soup.select_one('.address, [class*="address"], [class*="location"]'),
                soup.select_one("address"),
                soup.select_one('[class*="postal-code"], [class*="street-address"]'),
            ]
            for elem in address_elements:
                if elem:
                    address = elem.get_text(strip=True)
                    break

            if not name or not address:
                return None

            # Website Link
            website = None
            website_element = soup.select_one(
                'a[href*="http"]:not([href*="11880.com"]), '
                'a[class*="website"], a[data-type="website"], '
                '[class*="website-link"], [class*="homepage"]'
            )
            if website_element:
                website = website_element.get("href")

            # Telefonnummer
            phone = None
            phone_element = soup.select_one(
                '[class*="phone-number"], [class*="tel"], '
                'a[href^="tel:"], [data-phone], '
                '[class*="phone"]'
            )
            if phone_element:
                phone = (
                    phone_element.get("data-phone")
                    or phone_element.get("href", "").replace("tel:", "")
                    or phone_element.get_text(strip=True)
                )
            else:
                # Fallback: Suche nach Telefonnummer im Text
                text = soup.get_text()
                phone_patterns = [
                    r"\+49[\s-]*\d+[\s\d-]+",
                    r"0\d+[\s\d-]+",
                    r"\d{3,5}[\s/-]*\d{4,8}",
                ]
                for pattern in phone_patterns:
                    match = re.search(pattern, text)
                    if match and len(match.group()) > 8:
                        phone = match.group().strip()
                        break

            # Email direkt von der Detailseite
            email = None
            email_element = soup.select_one(
                'a[href^="mailto:"], [class*="email"], [data-email], [class*="mail"]'
            )
            if email_element:
                email = (
                    email_element.get("href", "").replace("mailto:", "")
                    or email_element.get("data-email")
                    or email_element.get_text(strip=True)
                )

            return CompanyData(
                name=name, address=address, website=website, phone=phone, email=email
            )

        except Exception as e:
            print(f"Error extracting from detail page: {e}")
            return None

    def _find_listings(self, soup: BeautifulSoup):
        """Findet Firmeneinträge auf der Seite"""
        # Aktualisierte Selektoren für 11880.com Listings
        selectors = [
            "div.result-list-entry__container",
            'div[class*="result-list-entry"]',
            "article[data-entry-id]",
            'div[class*="entry"]',
            'div[class*="listing"]',
        ]

        for selector in selectors:
            listings = soup.select(selector)
            if listings:
                return listings

        return []

    def _extract_company_data(self, listing) -> Optional[CompanyData]:
        """Extrahiert Firmendaten aus einem Listing"""
        try:
            # Name aus dem h2 Element extrahieren
            name_element = listing.select_one(
                "h2.result-list-entry-title__headline, h2"
            )
            name = name_element.get_text(strip=True) if name_element else None

            # Adresse extrahieren
            address = None
            address_element = listing.select_one("address, .result-list-entry-address")
            if address_element:
                address = address_element.get_text(strip=True)
            else:
                # Fallback: Suche nach Adresse im Text
                text_elements = listing.select(
                    'div[class*="address"], span[class*="address"]'
                )
                for elem in text_elements:
                    text = elem.get_text(strip=True)
                    if text and any(char.isdigit() for char in text):
                        address = text
                        break

            if not name or not address:
                return None

            # Website Link extrahieren
            website = None
            website_element = listing.select_one(
                'a[href*="http"]:not([href*="11880.com"]), a[class*="website"], a[data-type="website"]'
            )
            if website_element:
                website = website_element.get("href")

            # Telefonnummer extrahieren
            phone = None
            phone_element = listing.select_one(
                '[data-phone], [class*="phone"], span[class*="tel"], a[href^="tel:"]'
            )
            if phone_element:
                phone = phone_element.get("data-phone") or phone_element.get(
                    "href", ""
                ).replace("tel:", "")
            else:
                # Fallback: Suche nach Telefonnummer im Text
                text = listing.get_text()
                phone_patterns = [
                    r"\+49[\s-]*\d+[\s\d-]+",
                    r"0\d+[\s\d-]+",
                    r"\d{3,5}[\s/-]*\d{4,8}",
                ]
                for pattern in phone_patterns:
                    match = re.search(pattern, text)
                    if match and len(match.group()) > 8:
                        phone = match.group().strip()
                        break

            return CompanyData(name=name, address=address, website=website, phone=phone)
        except Exception as e:
            print(f"Error extracting company data: {e}")  # Debug line
            return None

    def _decode_cfemail(self, cfemail: str) -> str:
        """Decodes Cloudflare's email obfuscation."""
        r = int(cfemail[:2], 16)
        email = "".join(
            [chr(int(cfemail[i : i + 2], 16) ^ r) for i in range(2, len(cfemail), 2)]
        )
        return email
