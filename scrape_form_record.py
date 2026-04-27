#!/usr/bin/env python3
"""
HKJC Horse Form Record Scraper

Scrapes individual horse form records for all horses found in the
race_results database table.

Usage:
    python scrape_form_record.py [--workers 5] [--db hkjc.db]
"""
import argparse
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup, NavigableString
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tqdm import tqdm

from config import (
    FORM_RECORD_URL, DEFAULT_WORKERS, PAGE_LOAD_TIMEOUT, setup_logging,
)
from db import (
    init_db, insert_form_records, log_scrape, get_completed_urls,
    get_unique_horse_ids,
)
from scraper_utils import get_driver, quit_driver, retry

logger = setup_logging("form_record")


def get_sibling(tag, previous=False):
    """Navigate to the next/previous non-whitespace sibling tag."""
    if previous:
        sibling = tag.previous_sibling
        while isinstance(sibling, NavigableString):
            sibling = sibling.previous_sibling
    else:
        sibling = tag.next_sibling
        while isinstance(sibling, NavigableString):
            sibling = sibling.next_sibling
    return sibling


@retry()
def scrape_form_record(url: str) -> list:
    """
    Scrape a single horse's form record page.

    Returns a list of rows, each row is a list of 20 fields:
    [RaceIndex, Pla, Date, RC/Track/Course, Dist, Ground,
     RaceClass, Draw, Rating, Trainer, Jockey, LBW, WinOdds,
     ActWt, RunPo, FinishTime, Declare_Horse_Wt, Gear,
     VideoReplay, horseid]
    """
    driver = get_driver()
    driver.get(url)

    # Extract horse ID from URL
    horse_id = re.split(r"HorseId=", url, flags=re.IGNORECASE)[1].split("&")[0]

    # Check for empty page
    if "No information." in driver.page_source:
        return []

    # Wait for form record table
    try:
        WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
            EC.presence_of_element_located((By.CLASS_NAME, "htable_eng_text"))
        )
    except Exception:
        logger.warning("Timeout loading form record for %s", horse_id)
        return []

    soup = BeautifulSoup(driver.page_source, "html.parser")

    # Find all race date links (each represents one race record)
    horses = soup.find_all(href=re.compile("racedate", re.IGNORECASE))

    form_record_list = []
    for horse in horses:
        output = [horse.text.strip()]

        # Walk through sibling cells to get remaining fields
        a = get_sibling(horse.parent)
        while a is not None:
            text = (
                a.text.strip()
                .replace("\n", "")
                .replace(" " * 20, " ")
            )
            output.append(text)
            a = get_sibling(a)

        # Append horse ID
        output.append(horse_id)

        # Ensure exactly 20 columns
        while len(output) < 20:
            output.append("")
        form_record_list.append(output[:20])

    return form_record_list


def worker(url: str, db_path: str) -> tuple:
    """Worker function: scrape one URL, insert results, log status."""
    try:
        rows = scrape_form_record(url)
        if rows:
            insert_form_records(rows, db_path)
            log_scrape("form_record", url, "success", db_path=db_path)
        else:
            log_scrape("form_record", url, "empty", db_path=db_path)
        return url, len(rows), None
    except Exception as e:
        log_scrape("form_record", url, "error", str(e), db_path=db_path)
        return url, 0, str(e)


def main():
    parser = argparse.ArgumentParser(description="HKJC Form Record Scraper")
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

    # Get unique horse IDs from race_results table
    horse_ids = get_unique_horse_ids(db_path)
    if not horse_ids:
        logger.error(
            "No horse IDs found in database. "
            "Run scrape_race_result.py first."
        )
        return

    # Build URLs
    all_urls = [
        FORM_RECORD_URL.format(horse_id=hid)
        for hid in horse_ids
    ]

    # Filter out already-scraped URLs (resume capability)
    completed = get_completed_urls("form_record", db_path)
    urls = [u for u in all_urls if u not in completed]

    logger.info(
        "Form Records: %d horses total, %d already done, %d remaining",
        len(all_urls), len(completed), len(urls),
    )

    if not urls:
        logger.info("Nothing to scrape — all horses already completed.")
        return

    # Scrape with thread pool
    total_rows = 0
    errors = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(worker, url, db_path): url for url in urls}

        with tqdm(total=len(urls), desc="Form Records", unit="horse") as pbar:
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
        "✅ Form Record scraping complete: %d rows scraped, %d errors",
        total_rows, errors,
    )


if __name__ == "__main__":
    main()
