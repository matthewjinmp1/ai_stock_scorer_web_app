# 13F Tools

Scripts for fetching institutional investors (13F filers) and their portfolio histories from SEC EDGAR and WhaleWisdom.

## Contents

- `fetch_filers_sec.py`: (Recommended) Fetches 13F filers directly from SEC master index files. Very fast and accurate.
- `fetch_portfolio_history.py`: Fetches complete 13F holdings history for a specific fund (defaults to Tiger Global).
- `fetch_filers_whalewisdom.py`: Fetches filers from WhaleWisdom.com (API or scraping).
- `data/`: Contains results from the above scripts.

## Requirements

- Python 3.7+
- `requests` library: `pip install requests`
- `beautifulsoup4` (optional, for scraping WhaleWisdom): `pip install beautifulsoup4`

## Setup

The SEC requires automated clients to identify themselves with a `User-Agent` that includes contact information.

1. Copy the example environment file:
   ```bash
   cp env.example .env
   ```
2. Edit `.env` and set your contact email:
   ```text
   SEC_USER_AGENT="Your Name (your.email@example.com)"
   ```

## Usage

### Fetch 13F Filers (SEC)

This script scans EDGAR's quarterly master index files backward in time until it finds the requested number of unique 13F filers.

```bash
python scripts/13f/fetch_filers_sec.py
```

### Fetch Portfolio History

Fetches historical 13F holdings for Tiger Global Management (CIK 0001167483).

```bash
python scripts/13f/fetch_portfolio_history.py
```

### Fetch Filers (WhaleWisdom)

```bash
python scripts/13f/fetch_filers_whalewisdom.py
```

## Data Output

Outputs are saved to `scripts/13f/data/filers.db` (SQLite database).
- Contains all 13F filers with CIK, name, total filings count, and most recent filing date.
- Used by the web app for fund search functionality.

