#!/usr/bin/env python3
"""
HKJC Race Card Scraper

Scrapes race card data for today's races (or a specific date).
Unlike historical scrapers, this is designed for daily use to
capture upcoming race cards.

Usage:
    python scrape_racecard.py                          # today's races
    python scrape_racecard.py --date 20240101           # specific date
    python scrape_racecard.py --workers 5 --db hkjc.db
"""
import argparse
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tqdm import tqdm

from config import (
    DEFAULT_WORKERS, PAGE_LOAD_TIMEOUT, MAX_RACES_PER_DAY, setup_logging,
)
from db import init_db, insert_racecard, log_scrape, get_completed_urls
from scraper_utils import get_driver, quit_driver, retry

logger = setup_logging("racecard")

RACECARD_URL = (
    "https://racing.hkjc.com/racing/information/English/Racing/"
    "RaceCard.aspx?RaceDate={date}&RaceNo={race_no}"
)

# Racecard columns (27 fields)
RACECARD_COLUMNS = [
    'horse_no', 'last_6_runs', 'colour', 'horse', 'brand_no', 'wt',
    'jockey', 'over_wt', 'draw', 'trainer', 'intl_rtg', 'rtg',
    'rtg_change', 'horse_wt_decl', 'wt_change_vs_decl', 'best_time',
    'age', 'wfa', 'sex', 'season_stakes', 'priority', 'gear',
    'owner', 'sire', 'dam', 'import_cat', 'date', 'match'
]


@retry()
def scrape_racecard(url: str) -> list:
    """
    Scrape a single race card page.

    Returns a list of rows, each row containing racecard fields + date + match.
    """
    driver = get_driver()
    driver.get(url)

    # Extract date and match from URL
    race_date = url.split("RaceDate=")[1].split("&")[0]
    match = url.split("RaceNo=")[1]

    # Check for empty page
    if "No information." in driver.page_source:
        return []

    # Wait for racecard table
    try:
        WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
            EC.presence_of_element_located(
                (By.XPATH, '//table[@class="starter f_tac f_fs13 draggable hiddenable"]')
            )
        )
    except Exception:
        return []

    soup = BeautifulSoup(driver.page_source, "html.parser")
    table = soup.find("table", class_="starter f_tac f_fs13 draggable hiddenable")

    if table is None:
        return []

    output_list = []
    tbody = table.find("tbody")
    if tbody is None:
        return []

    for tr in tbody.find_all("tr"):
        cols = [td.string for td in tr("td")]
        cols.append(race_date)
        cols.append(match)

        # Pad to 28 fields (26 racecard + date + match)
        while len(cols) < 28:
            cols.append("")
        output_list.append(cols[:28])

    return output_list


def worker(url: str, db_path: str) -> tuple:
    """Worker function: scrape one URL, insert results, log status."""
    try:
        rows = scrape_racecard(url)
        if rows:
            insert_racecard(rows, db_path)
            log_scrape("racecard", url, "success", db_path=db_path)
        else:
            log_scrape("racecard", url, "empty", db_path=db_path)
        return url, len(rows), None
    except Exception as e:
        log_scrape("racecard", url, "error", str(e), db_path=db_path)
        return url, 0, str(e)


def main():
    parser = argparse.ArgumentParser(description="HKJC Race Card Scraper")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Number of concurrent workers (default: {DEFAULT_WORKERS})")
    parser.add_argument("--db", type=str, default=None,
                        help="Path to SQLite database")
    parser.add_argument("--date", type=str, default=None,
                        help="Race date in YYYYMMDD format (default: today)")
    args = parser.parse_args()

    db_path = args.db
    if db_path is None:
        from config import DB_PATH
        db_path = DB_PATH

    # Initialize database
    init_db(db_path)

    # Determine date
    if args.date:
        race_date = args.date
    else:
        race_date = date.today().strftime("%Y%m%d")

    # Build URLs
    all_urls = [
        RACECARD_URL.format(date=race_date, race_no=r)
        for r in range(1, MAX_RACES_PER_DAY + 1)
    ]

    # Filter out already-scraped URLs
    completed = get_completed_urls("racecard", db_path)
    urls = [u for u in all_urls if u not in completed]

    logger.info(
        "Racecard: date=%s, %d URLs, %d already done, %d remaining",
        race_date, len(all_urls), len(completed), len(urls),
    )

    if not urls:
        logger.info("Nothing to scrape — all URLs already completed.")
        return

    total_rows = 0
    errors = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(worker, url, db_path): url for url in urls}

        with tqdm(total=len(urls), desc="Race Cards", unit="race") as pbar:
            for future in as_completed(futures):
                url, row_count, error = future.result()
                total_rows += row_count
                if error:
                    errors += 1
                pbar.update(1)
                pbar.set_postfix(rows=total_rows, errors=errors)

    quit_driver()

    logger.info(
        "✅ Racecard scraping complete: %d rows scraped, %d errors",
        total_rows, errors,
    )


if __name__ == "__main__":
    main()
