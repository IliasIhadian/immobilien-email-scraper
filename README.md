# immobilien-email-scraper

## 📧 11880.com E-Mail-Scraper für Hausverwaltungen

Ein Python-basierter Web-Scraper, der automatisiert E-Mail-Adressen von Hausverwaltungen in Düsseldorf von der Website 11880.com sammelt.

## 🚀 Features

- **Automatische Navigation** auf 11880.com
- **Intelligente E-Mail-Extraktion** mit mehreren Fallback-Strategien
- **Robuste Fehlerbehandlung** und Retry-Mechanismen  
- **CSV-Export** mit Zeitstempel und Duplikatsvermeidung
- **Ethisches Scraping** mit angemessenen Delays
- **Modulare Architektur** für einfache Erweiterungen

## 🛠️ Installation

### 1. Repository klonen
```bash
git clone <repository-url>
cd immobilien-email-scraper
```

### 2. Virtual Environment erstellen
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# oder
venv\Scripts\activate     # Windows
```

### 3. Dependencies installieren
```bash
pip install -r requirements.txt
```

### 4. Playwright Browser installieren
```bash
playwright install chromium
```

## ⚙️ Konfiguration

Die Konfiguration erfolgt über `config/settings.yaml`:

```yaml
target:
  search_term: "Hausverwaltungen"
  location: "Düsseldorf"
  
scraping:
  delay_between_requests:
    min: 2
    max: 5
  max_pages: 50
```

## 🎯 Verwendung

### Basis-Scraping
```bash
python main.py
```

### Mit benutzerdefinierten Parametern
```bash
python main.py --location "Köln" --search-term "Immobilienmakler"
```

## 📊 Output

Der Scraper erstellt CSV-Dateien mit folgenden Spalten:
- **Firma**: Name der Hausverwaltung
- **Adresse**: Vollständige Adresse  
- **Website**: URL der Firmen-Website (falls verfügbar)
- **E-Mail**: Extrahierte E-Mail-Adresse

Beispiel: `data/hausverwaltungen_duesseldorf_2024-01-15_14-30-25.csv`

## 🔧 Projektstruktur

```
immobilien-email-scraper/
├── src/
│   ├── scraper/          # Hauptkomponenten des Scrapers
│   ├── utils/            # Hilfsfunktionen
│   └── export/           # Datenexport-Module
├── config/               # Konfigurationsdateien
├── logs/                 # Log-Dateien
├── data/                 # Ausgabe-Dateien
├── tests/                # Unit Tests
└── requirements.txt      # Python Dependencies
```

## 🤖 Technologie-Stack

- **Python 3.8+**
- **Playwright** - Browser-Automatisierung
- **Pandas** - Datenverarbeitung
- **BeautifulSoup4** - HTML-Parsing
- **PyYAML** - Konfiguration
- **Asyncio** - Asynchrone Verarbeitung

## 🛡️ Ethisches Scraping

Dieser Scraper befolgt Best Practices:
- ✅ Respektiert `robots.txt`
- ✅ Verwendet angemessene Delays zwischen Requests
- ✅ Implementiert Retry-Mechanismen mit Exponential Backoff
- ✅ Sammelt nur öffentlich verfügbare Daten
- ✅ Vermeidet Überlastung der Ziel-Website

## 📝 Logging

Alle Aktivitäten werden geloggt:
- Erfolgreiche Extraktionen
- Fehlgeschlagene Requests
- Performance-Metriken
- Fehlerdetails für Debugging

## 🧪 Testing

```bash
pytest tests/
```

## 📄 Lizenz

Dieses Projekt steht unter der MIT-Lizenz. Siehe [LICENSE](LICENSE) für Details.

## ⚠️ Rechtlicher Hinweis

Dieses Tool dient ausschließlich zu Bildungszwecken. Stellen Sie sicher, dass Sie alle geltenden Gesetze und Nutzungsbedingungen einhalten, bevor Sie es verwenden.

## 🤝 Beitragen

Contributions sind willkommen! Bitte erstellen Sie einen Pull Request oder öffnen Sie ein Issue.

---

**Erstellt mit ❤️ für die Immobilienbranche**
