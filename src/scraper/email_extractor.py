"""
Email Extractor für 11880.com Email Scraper
Extrahiert E-Mail-Adressen von Firmendetailseiten und externen Websites
"""

import re
import asyncio
import random
from typing import Optional, Dict, Any, List, Set
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
import validators

from ..utils.logging_config import get_logger
from .data_extractor import CompanyData


class EmailExtractor:
    """
    Extrahiert E-Mail-Adressen von verschiedenen Quellen:
    - 11880.com Detailseiten
    - Externe Firmenwebsites
    - Impressum-Seiten
    """

    def __init__(self, page: Page, config: Dict[str, Any]):
        self.page = page
        self.config = config
        self.logger = get_logger(__name__)

        # Konfiguration für E-Mail-Extraktion
        self.email_config = self.config.get("email", {})
        self.extract_from_detail_page = self.email_config.get(
            "extract_from_detail_page", True
        )
        self.extract_from_website = self.email_config.get("extract_from_website", True)
        self.extract_from_impressum = self.email_config.get(
            "extract_from_impressum", True
        )
        self.timeout_per_website = self.email_config.get("timeout_per_website", 15)

        # Delay-Konfiguration
        self.delay_config = self.config.get("scraping", {}).get(
            "delay_between_requests", {}
        )

        # E-Mail-Pattern für Regex-Suche
        self.email_pattern = re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", re.IGNORECASE
        )

        # Bereits besuchte URLs cachen
        self.visited_urls: Set[str] = set()

    async def extract_emails_for_company(
        self, company_data: CompanyData
    ) -> CompanyData:
        """
        Extrahiert E-Mail-Adressen für eine Firma aus verschiedenen Quellen

        Args:
            company_data: CompanyData-Objekt mit Firmeninformationen

        Returns:
            CompanyData: Aktualisiertes Objekt mit E-Mail-Adresse
        """
        try:
            self.logger.info(f"Extracting emails for: {company_data.name}")

            email = None

            # 1. Versuche E-Mail von 11880.com Detailseite
            if self.extract_from_detail_page and company_data.detail_url:
                email = await self._extract_from_11880_detail_page(
                    company_data.detail_url
                )
                if email:
                    self.logger.info(f"Found email on 11880 detail page: {email}")
                    company_data.email = email
                    return company_data

            # 2. Versuche E-Mail von externer Website
            if self.extract_from_website and company_data.website:
                email = await self._extract_from_external_website(company_data.website)
                if email:
                    self.logger.info(f"Found email on company website: {email}")
                    company_data.email = email
                    return company_data

            # 3. Versuche E-Mail vom Impressum der externen Website
            if self.extract_from_impressum and company_data.website:
                email = await self._extract_from_impressum(company_data.website)
                if email:
                    self.logger.info(f"Found email on impressum page: {email}")
                    company_data.email = email
                    return company_data

            if not email:
                self.logger.debug(f"No email found for: {company_data.name}")

            return company_data

        except Exception as e:
            self.logger.error(f"Error extracting emails for {company_data.name}: {e}")
            return company_data

    async def _extract_from_11880_detail_page(self, detail_url: str) -> Optional[str]:
        """Extrahiert E-Mail von 11880.com Detailseite mit spezifischer Logik"""

        if detail_url in self.visited_urls:
            self.logger.debug(f"Already visited: {detail_url}")
            return None

        try:
            self.logger.debug(f"Extracting from 11880 detail page: {detail_url}")

            # Zur Detailseite navigieren
            response = await self.page.goto(detail_url, wait_until="domcontentloaded")

            if not response or response.status >= 400:
                self.logger.warning(
                    f"Failed to load detail page: {response.status if response else 'None'}"
                )
                return None

            self.visited_urls.add(detail_url)

            # Warten auf spezifische 11880.com Elemente
            await self._wait_for_11880_content()

            # HTML-Inhalt abrufen
            html_content = await self.page.content()
            soup = BeautifulSoup(html_content, "html.parser")

            # Spezielle 11880.com E-Mail-Extraktion
            email = self._extract_11880_specific_email(soup)

            if not email:
                # Fallback zur allgemeinen Extraktion
                email = self._extract_email_from_html(soup)

            # Kurze Pause zwischen Anfragen
            await self._wait_between_requests()

            return email

        except Exception as e:
            self.logger.error(f"Error extracting from 11880 detail page: {e}")
            return None

    async def _extract_from_external_website(self, website_url: str) -> Optional[str]:
        """Extrahiert E-Mail von externer Firmenwebsite"""

        if not self._is_valid_external_url(website_url):
            return None

        if website_url in self.visited_urls:
            self.logger.debug(f"Already visited: {website_url}")
            return None

        try:
            self.logger.debug(f"Extracting from external website: {website_url}")

            # Zur externen Website navigieren
            response = await self.page.goto(
                website_url,
                wait_until="domcontentloaded",
                timeout=self.timeout_per_website * 1000,
            )

            if not response or response.status >= 400:
                self.logger.warning(
                    f"Failed to load website: {response.status if response else 'None'}"
                )
                return None

            self.visited_urls.add(website_url)

            # Warten auf Inhalte
            await self._wait_for_content_load()

            # HTML-Inhalt abrufen
            html_content = await self.page.content()
            soup = BeautifulSoup(html_content, "html.parser")

            # E-Mail extrahieren
            email = self._extract_email_from_html(soup)

            # Pause zwischen Anfragen
            await self._wait_between_requests()

            return email

        except Exception as e:
            self.logger.error(f"Error extracting from external website: {e}")
            return None

    async def _extract_from_impressum(self, website_url: str) -> Optional[str]:
        """Extrahiert E-Mail von Impressum-Seite der externen Website"""

        if not self._is_valid_external_url(website_url):
            return None

        try:
            self.logger.debug(f"Looking for impressum on: {website_url}")

            # Zuerst zur Homepage navigieren (falls nicht schon da)
            if website_url not in self.visited_urls:
                response = await self.page.goto(
                    website_url,
                    wait_until="domcontentloaded",
                    timeout=self.timeout_per_website * 1000,
                )

                if not response or response.status >= 400:
                    return None

                self.visited_urls.add(website_url)
                await self._wait_for_content_load()

            # Impressum-Link finden
            impressum_url = await self._find_impressum_link(website_url)

            if not impressum_url or impressum_url in self.visited_urls:
                return None

            # Zur Impressum-Seite navigieren
            response = await self.page.goto(
                impressum_url,
                wait_until="domcontentloaded",
                timeout=self.timeout_per_website * 1000,
            )

            if not response or response.status >= 400:
                return None

            self.visited_urls.add(impressum_url)
            await self._wait_for_content_load()

            # HTML-Inhalt abrufen
            html_content = await self.page.content()
            soup = BeautifulSoup(html_content, "html.parser")

            # E-Mail extrahieren
            email = self._extract_email_from_html(soup)

            await self._wait_between_requests()

            return email

        except Exception as e:
            self.logger.error(f"Error extracting from impressum: {e}")
            return None

    async def _find_impressum_link(self, base_url: str) -> Optional[str]:
        """Findet Impressum-Link auf der aktuellen Seite"""

        try:
            html_content = await self.page.content()
            soup = BeautifulSoup(html_content, "html.parser")

            # Verschiedene Impressum-Keywords
            impressum_keywords = [
                "impressum",
                "imprint",
                "kontakt",
                "contact",
                "datenschutz",
                "privacy",
                "rechtliches",
                "legal",
            ]

            # Links durchsuchen
            all_links = soup.find_all("a", href=True)

            for link in all_links:
                href = link.get("href", "").lower()
                text = link.get_text(strip=True).lower()

                # Prüfung auf Impressum-Keywords
                for keyword in impressum_keywords:
                    if keyword in href or keyword in text:
                        # Relative URLs zu absoluten konvertieren
                        if href.startswith("/"):
                            impressum_url = urljoin(base_url, link.get("href"))
                        else:
                            impressum_url = link.get("href")

                        if self._is_valid_external_url(impressum_url):
                            self.logger.debug(f"Found impressum link: {impressum_url}")
                            return impressum_url

            return None

        except Exception as e:
            self.logger.error(f"Error finding impressum link: {e}")
            return None

    def _extract_email_from_html(self, soup: BeautifulSoup) -> Optional[str]:
        """Extrahiert E-Mail-Adresse aus HTML-Inhalt"""

        try:
            # 1. 🎯 11880.com spezifische E-Mail-Extraktion (höchste Priorität)
            # Suche nach dem spezifischen 11880.com E-Mail-Format
            email_selectors_11880 = [
                "a[href^='mailto:']",  # Direkte mailto-Links
                ".entry-detail-list__item a[href^='mailto:']",  # E-Mail in entry-detail-list
                "#box-email-link",  # Spezifische E-Mail-Box ID
                ".tracking-mail-to",  # Tracking E-Mail-Links
                "a[title*='@']",  # Links mit E-Mail im title
            ]

            for selector in email_selectors_11880:
                email_links = soup.select(selector)
                for link in email_links:
                    # Aus href extrahieren
                    href = link.get("href", "")
                    if href.startswith("mailto:"):
                        email = href.replace("mailto:", "").split("?")[0].strip()
                        if self._is_valid_email(email):
                            self.logger.debug(
                                f"Found email via 11880 selector '{selector}': {email}"
                            )
                            return email

                    # Aus title extrahieren
                    title = link.get("title", "")
                    if "@" in title:
                        emails = self.email_pattern.findall(title)
                        for email in emails:
                            if self._is_valid_email(email):
                                self.logger.debug(
                                    f"Found email via title '{selector}': {email}"
                                )
                                return email

                    # Aus Text-Inhalt extrahieren
                    text = link.get_text(strip=True)
                    emails = self.email_pattern.findall(text)
                    for email in emails:
                        if self._is_valid_email(email):
                            self.logger.debug(
                                f"Found email via text '{selector}': {email}"
                            )
                            return email

            # 2. 🔍 Spezifische 11880.com E-Mail-Bereiche
            email_containers = soup.select(
                [
                    ".entry-detail-list__item",  # E-Mail-Container
                    ".entry-detail-list__wrapper",  # E-Mail-Wrapper
                    '[class*="email"]',  # Klassen mit "email"
                    '[id*="email"]',  # IDs mit "email"
                ]
            )

            for container in email_containers:
                # Suche nach E-Mail-Icons und deren Labels
                email_icons = container.select(".entry-detail-list__icon--email")
                if email_icons:
                    # Finde das zugehörige Label
                    label = container.select_one(".entry-detail-list__label")
                    if label:
                        text = label.get_text(strip=True)
                        emails = self.email_pattern.findall(text)
                        for email in emails:
                            if self._is_valid_email(email):
                                self.logger.debug(
                                    f"Found email via email icon container: {email}"
                                )
                                return email

                # Direkte Text-Suche im Container
                text = container.get_text()
                emails = self.email_pattern.findall(text)
                for email in emails:
                    if self._is_valid_email(email):
                        self.logger.debug(f"Found email via container text: {email}")
                        return email

            # 3. 📧 Allgemeine mailto-Link-Suche (Fallback)
            mailto_links = soup.find_all("a", href=re.compile(r"^mailto:"))
            if mailto_links:
                for link in mailto_links:
                    href = link.get("href", "")
                    email = href.replace("mailto:", "").split("?")[0].strip()
                    if self._is_valid_email(email):
                        self.logger.debug(f"Found email via general mailto: {email}")
                        return email

            # 4. 🏢 Suche in spezifischen Bereichen
            contact_areas = soup.select(
                [
                    ".contact",
                    ".kontakt",
                    ".contact-info",
                    ".impressum",
                    ".imprint",
                    ".footer",
                    '[class*="contact"]',
                    '[class*="kontakt"]',
                    '[id*="contact"]',
                    '[id*="kontakt"]',
                ]
            )

            for area in contact_areas:
                text = area.get_text()
                emails = self.email_pattern.findall(text)
                for email in emails:
                    if self._is_valid_email(email):
                        self.logger.debug(f"Found email via contact area: {email}")
                        return email

            # 5. 🔍 Volltext-Suche als letzter Fallback
            full_text = soup.get_text()
            emails = self.email_pattern.findall(full_text)

            for email in emails:
                if self._is_valid_email(email) and self._is_business_email(email):
                    self.logger.debug(f"Found email via full text search: {email}")
                    return email

            return None

        except Exception as e:
            self.logger.error(f"Error extracting email from HTML: {e}")
            return None

    def _extract_11880_specific_email(self, soup: BeautifulSoup) -> Optional[str]:
        """Spezielle E-Mail-Extraktion für 11880.com Format"""

        try:
            # 1. Direkte Suche nach der E-Mail-Box
            email_box = soup.select_one("#box-email-link")
            if email_box:
                href = email_box.get("href", "")
                if href.startswith("mailto:"):
                    email = href.replace("mailto:", "").split("?")[0].strip()
                    if self._is_valid_email(email):
                        self.logger.debug(f"Found email via #box-email-link: {email}")
                        return email

            # 2. Suche nach E-Mail-Icons und deren Labels
            email_items = soup.select(".entry-detail-list__item")
            for item in email_items:
                # Prüfe ob es ein E-Mail-Icon hat
                email_icon = item.select_one(".entry-detail-list__icon--email")
                if email_icon:
                    # Finde das zugehörige Label
                    label = item.select_one(".entry-detail-list__label")
                    if label:
                        text = label.get_text(strip=True)
                        emails = self.email_pattern.findall(text)
                        for email in emails:
                            if self._is_valid_email(email):
                                self.logger.debug(
                                    f"Found email via email icon: {email}"
                                )
                                return email

            # 3. Suche nach tracking-mail-to Links
            tracking_links = soup.select(".tracking-mail-to")
            for link in tracking_links:
                href = link.get("href", "")
                if href.startswith("mailto:"):
                    email = href.replace("mailto:", "").split("?")[0].strip()
                    if self._is_valid_email(email):
                        self.logger.debug(f"Found email via tracking-mail-to: {email}")
                        return email

            return None

        except Exception as e:
            self.logger.error(f"Error in 11880-specific email extraction: {e}")
            return None

    async def _wait_for_11880_content(self):
        """Wartet auf spezifische 11880.com Inhalte"""

        try:
            # Warten auf 11880.com spezifische Elemente
            selectors_to_wait = [
                ".entry-detail-list",
                ".entry-detail-list__item",
                "#box-email-link",
                ".tracking-mail-to",
            ]

            for selector in selectors_to_wait:
                try:
                    await self.page.wait_for_selector(selector, timeout=10000)
                    self.logger.debug(f"Found 11880 element: {selector}")
                    break
                except PlaywrightTimeoutError:
                    continue

            # Zusätzliche Wartezeit für dynamisches Laden
            await asyncio.sleep(random.uniform(2, 3))

        except Exception as e:
            self.logger.debug(f"Error waiting for 11880 content: {e}")

    def _is_valid_email(self, email: str) -> bool:
        """Validiert E-Mail-Adresse"""

        if not email or len(email) < 5:
            return False

        # Basis-Validierung
        if not validators.email(email):
            return False

        # Ausschließen von häufigen Dummy-E-Mails
        dummy_patterns = [
            "example.com",
            "test.com",
            "dummy.com",
            "noreply",
            "no-reply",
            "donotreply",
            "webmaster",
            "admin@",
            "info@website",
        ]

        email_lower = email.lower()
        for pattern in dummy_patterns:
            if pattern in email_lower:
                return False

        return True

    def _is_business_email(self, email: str) -> bool:
        """Prüft ob E-Mail wahrscheinlich geschäftlich ist"""

        email_lower = email.lower()

        # Geschäftliche Domains bevorzugen
        business_indicators = [
            ".de",
            ".com",
            ".org",
            ".net",
            ".eu",
            "info@",
            "kontakt@",
            "office@",
            "mail@",
        ]

        # Private/Consumer-Domains vermeiden
        personal_domains = [
            "gmail.com",
            "yahoo.com",
            "hotmail.com",
            "web.de",
            "gmx.de",
            "t-online.de",
            "outlook.com",
            "aol.com",
        ]

        # Wenn private Domain, dann ablehnen
        for domain in personal_domains:
            if domain in email_lower:
                return False

        # Wenn geschäftliche Indikatoren, dann bevorzugen
        for indicator in business_indicators:
            if indicator in email_lower:
                return True

        # Standard-Annahme: geschäftlich
        return True

    def _is_valid_external_url(self, url: str) -> bool:
        """Validiert externe URL"""

        if not url or not validators.url(url):
            return False

        parsed = urlparse(url)

        # Ausschließen von 11880.com (das ist unsere Quellseite)
        if "11880.com" in parsed.netloc:
            return False

        # Ausschließen von Social Media und anderen irrelevanten Domains
        excluded_domains = [
            "facebook.com",
            "instagram.com",
            "twitter.com",
            "linkedin.com",
            "xing.com",
            "youtube.com",
        ]

        for domain in excluded_domains:
            if domain in parsed.netloc:
                return False

        return True

    async def _wait_for_content_load(self):
        """Wartet bis Seiteninhalte geladen sind"""

        try:
            # Warten auf häufige Elemente
            selectors_to_wait = [
                "body",
                "main",
                ".content",
                "#content",
                "p",
                "div",
                "span",
            ]

            for selector in selectors_to_wait:
                try:
                    await self.page.wait_for_selector(selector, timeout=5000)
                    break
                except PlaywrightTimeoutError:
                    continue

            # Zusätzliche kurze Wartezeit für dynamisches Laden
            await asyncio.sleep(random.uniform(1, 2))

        except Exception as e:
            self.logger.debug(f"Error waiting for content load: {e}")

    async def _wait_between_requests(self):
        """Wartet zwischen Anfragen (ethisches Scraping)"""

        min_delay = self.delay_config.get("min", 2)
        max_delay = self.delay_config.get("max", 5)

        delay = random.uniform(min_delay, max_delay)
        self.logger.debug(f"Waiting {delay:.2f} seconds...")
        await asyncio.sleep(delay)

    async def extract_emails_bulk(
        self, companies: List[CompanyData]
    ) -> List[CompanyData]:
        """
        Extrahiert E-Mails für eine Liste von Firmen

        Args:
            companies: Liste von CompanyData-Objekten

        Returns:
            List[CompanyData]: Liste mit aktualisierten E-Mail-Adressen
        """
        try:
            self.logger.info(
                f"Starting bulk email extraction for {len(companies)} companies"
            )

            updated_companies = []

            for i, company in enumerate(companies):
                try:
                    self.logger.info(
                        f"Processing company {i + 1}/{len(companies)}: {company.name}"
                    )

                    updated_company = await self.extract_emails_for_company(company)
                    updated_companies.append(updated_company)

                    # Fortschritt loggen
                    if (i + 1) % 10 == 0:
                        emails_found = sum(1 for c in updated_companies if c.email)
                        self.logger.info(
                            f"Progress: {i + 1}/{len(companies)} companies processed, {emails_found} emails found"
                        )

                except Exception as e:
                    self.logger.error(f"Error processing company {company.name}: {e}")
                    updated_companies.append(company)  # Ohne E-Mail hinzufügen
                    continue

            emails_found = sum(1 for c in updated_companies if c.email)
            self.logger.info(
                f"Bulk extraction completed: {emails_found}/{len(companies)} emails found"
            )

            return updated_companies

        except Exception as e:
            self.logger.error(f"Error in bulk email extraction: {e}")
            return companies
