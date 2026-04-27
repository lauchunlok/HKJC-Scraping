#!/usr/bin/env python3
"""
HKJC Sectional Time Scraper

Scrapes sectional time and position data for all races found in the
race_results database table.

Usage:
    python scrape_sectional_time.py [--workers 5] [--db hkjc.db]
"""
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tqdm import tqdm

from config import (
    SECTIONAL_TIME_URL, DEFAULT_WORKERS, PAGE_LOAD_TIMEOUT, setup_logging,
)
from db import (
    init_db, insert_sectional_times, log_scrape, get_completed_urls,
    get_unique_race_dates_and_matches,
)
from scraper_utils import get_driver, quit_driver, retry

logger = setup_logging("sectional_time")


def convert_date_format(date_str: str) -> str:
    """
    Convert date from YYYY/MM/DD to DD/MM/YYYY format
    (as used by the sectional time page).
    """
    try:
        dt = datetime.strptime(date_str, "%Y/%m/%d")
        return dt.strftime("%d/%m/%Y")
    except ValueError:
        return date_str


@retry()
def scrape_sectional_time(url: str) -> list:
    """
    Scrape a single sectional time page.

    Returns a list of rows, each row is a list of 18 fields:
    [finishing_order, horse_no, horse, time,
     section_time_1..6, margin_behind_1..6,
     date, match]
    """
    driver = get_driver()
    driver.get(url)

    date = url.split("RaceDate=")[1][:10]
    match = url.split("RaceNo=")[1]

    # Wait for the sectional time table
    try:
        WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
            EC.presence_of_element_located(
                (By.XPATH, '//table[@class="table_bd f_tac race_table"]')
            )
        )
    except Exception:
        # No sectional time data for this race
        return []

    soup = BeautifulSoup(driver.page_source, "html.parser")

    table = soup.find("table", class_="table_bd f_tac race_table")
    if table is None:
        return []

    tbody = table.find("tbody")
    if tbody is None:
        return []

    output_list = []
    for tr in tbody.find_all("tr"):
        # Extract different data types from the row
        position = [td.string for td in tr("td")]
        section_time = [p.string for p in tr("p")]
        margin_behind = [i.string for i in tr("i")]

        # Remove None values
        position = list(filter(None, position))
        section_time = list(filter(None, section_time))
        margin_behind = list(filter(None, margin_behind))

        # Pad to consistent length of 6
        section_time = section_time + [""] * (6 - len(section_time))
        margin_behind = margin_behind + [""] * (6 - len(margin_behind))

        cols = []
        cols.extend(position)
        cols.extend(section_time[:6])
        cols.extend(margin_behind[:6])
        cols.append(date)
        cols.append(match)

        # Ensure exactly 18 columns
        while len(cols) < 18:
            cols.append("")
        output_list.append(cols[:18])

    return output_list


def worker(url: str, db_path: str) -> tuple:
    """Worker function: scrape one URL, insert results, log status."""
    try:
        rows = scrape_sectional_time(url)
        if rows:
            insert_sectional_times(rows, db_path)
            log_scrape("sectional_time", url, "success", db_path=db_path)
        else:
            log_scrape("sectional_time", url, "empty", db_path=db_path)
        return url, len(rows), None
    except Exception as e:
        log_scrape("sectional_time", url, "error", str(e), db_path=db_path)
        return url, 0, str(e)


def main():
    parser = argparse.ArgumentParser(description="HKJC Sectional Time Scraper")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Number of concurrent workers (default: {DEFAULT_WORKERS})")
    parser.add_argument("--db", type=str, default=None,
                        help="Path to SQLite database")
    args = parser.parse_args()

    db_path = args.db
    if db_path is None:
        from config import DB_PATH
        db_path = DB_PATH

    # Initialize database
    init_db(db_path)

    # Get unique (date, match) pairs from race_results
    date_matches = get_unique_race_dates_and_matches(db_path)
    if not date_matches:
        logger.error(
            "No race data found in database. "
            "Run scrape_race_result.py first."
        )
        return

    # Build URLs — sectional time page uses DD/MM/YYYY format
    all_urls = []
    for date, match_no in date_matches:
        converted_date = convert_date_format(date)
        url = SECTIONAL_TIME_URL.format(date=converted_date, race_no=match_no)
        all_urls.append(url)

    # Filter out already-scraped URLs (resume capability)
    completed = get_completed_urls("sectional_time", db_path)
    urls = [u for u in all_urls if u not in completed]

    logger.info(
        "Sectional Times: %d races total, %d already done, %d remaining",
        len(all_urls), len(completed), len(urls),
    )

    if not urls:
        logger.info("Nothing to scrape — all races already completed.")
        return

    # Scrape with thread pool
    total_rows = 0
    errors = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(worker, url, db_path): url for url in urls}

        with tqdm(total=len(urls), desc="Sectional Times", unit="race") as pbar:
            for future in as_completed(futures):
                url, row_count, error = future.result()
                total_rows += row_count
                if error:
                    errors += 1
                pbar.update(1)
                pbar.set_postfix(rows=total_rows, errors=errors)

    # Clean up
    quit_driver()

    logger.info(
        "✅ Sectional Time scraping complete: %d rows scraped, %d errors",
        total_rows, errors,
    )


if __name__ == "__main__":
    main()
