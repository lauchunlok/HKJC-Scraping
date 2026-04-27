#!/usr/bin/env python3
"""
HKJC Race Result Scraper

Scrapes race results from the HKJC website for a configurable date range.
Generates race dates dynamically based on YEAR_START / YEAR_END in config.

Usage:
    python scrape_race_result.py [--workers 5] [--db hkjc.db] [--year-start 2007] [--year-end 2024]
"""
import argparse
import re
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tqdm import tqdm

from config import (
    RACE_RESULT_URL, DEFAULT_WORKERS, PAGE_LOAD_TIMEOUT,
    MAX_RACES_PER_DAY, YEAR_START, YEAR_END, setup_logging,
)
from db import init_db, insert_race_results, log_scrape, get_completed_urls
from scraper_utils import get_driver, quit_driver, retry

logger = setup_logging("race_result")


def generate_race_dates(year_start: int, year_end: int) -> list:
    """
    Generate all potential HKJC race dates between year_start and year_end.

    HKJC races are typically held on Wed, Sat, Sun — but also on
    public holidays (Chinese New Year, Easter, National Day, Boxing Day,
    etc.) which can fall on any weekday. Rather than maintaining a
    fragile holiday calendar, we generate EVERY date in the range and
    let the scraper skip non-race days gracefully (returns empty).
    The overhead is minimal since non-race URLs fail fast on timeout.
    """
    dates = []
    start = datetime(year_start, 1, 1)
    end = datetime(year_end, 12, 31)

    current = start
    while current <= end:
        dates.append(current.strftime("%Y/%m/%d"))
        current += timedelta(days=1)

    logger.info(
        "Generated %d potential race dates from %d to %d",
        len(dates), year_start, year_end,
    )
    return dates


def build_urls(dates: list, max_races: int = MAX_RACES_PER_DAY) -> list:
    """Build all race result URLs from dates × race numbers."""
    urls = []
    for date in dates:
        for race_no in range(1, max_races + 1):
            urls.append(RACE_RESULT_URL.format(date=date, race_no=race_no))
    return urls


@retry()
def scrape_race_result(url: str) -> list:
    """
    Scrape a single race result page.

    Returns a list of rows, each row is a list of 17 fields:
    [Plc, HorseNo, Horse, Jockey, Trainer, ActualWt, Declar_HorseWt,
     Draw, LBW, RunningPosition, FinishTime, Win_Odds,
     date, match, cdr, prize_money, horseid]
    """
    driver = get_driver()
    driver.get(url)

    date = url.split("RaceDate=")[1][:10]
    match = url.split("RaceNo=")[1]

    # Wait for the main results table
    try:
        WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
            EC.presence_of_element_located(
                (By.XPATH, '//table[@class="f_tac table_bd draggable"]')
            )
        )
    except Exception:
        # No race for this date/number — not an error
        return []

    soup = BeautifulSoup(driver.page_source, "html.parser")

    # Main results table
    table = soup.find("table", class_="f_tac table_bd draggable")
    if table is None:
        return []

    # Class/Distance/Rating + Prize money table
    cdr_table = soup.find("tbody", class_="f_fs13")
    cdr_list = []
    if cdr_table:
        for cdr_row in cdr_table.find_all("tr")[1:4:2]:
            cdr_cols = cdr_row.find_all("td")
            cdr_cols = [ele.text.strip() for ele in cdr_cols]
            if cdr_cols:
                cdr_list.append(cdr_cols[0])

    # Horse IDs
    horse_id_list = []
    for horse_link in soup.find_all(href=re.compile("horseid")):
        hid = horse_link["href"].split("horseid=")[1]
        horse_id_list.append(hid)

    # Parse main table rows
    output_list = []
    rows = table.find("tbody").find_all("tr")
    for row in rows:
        cols = row.find_all("td")
        cols = [
            ele.text.strip()
            .replace("\n", "")
            .replace(" " * 20, " ")
            .replace("-", " ")
            for ele in cols
        ]
        cols.append(date)
        cols.append(match)
        cols.extend(cdr_list)
        output_list.append(cols)

    # Merge horse IDs with rows
    result = []
    for i, row in enumerate(output_list):
        horseid = horse_id_list[i] if i < len(horse_id_list) else ""
        row.append(horseid)
        # Ensure exactly 17 columns
        while len(row) < 17:
            row.append("")
        result.append(row[:17])

    return result


def worker(url: str, db_path: str) -> tuple:
    """Worker function: scrape one URL, insert results, log status."""
    try:
        rows = scrape_race_result(url)
        if rows:
            insert_race_results(rows, db_path)
            log_scrape("race_result", url, "success", db_path=db_path)
        else:
            log_scrape("race_result", url, "empty", db_path=db_path)
        return url, len(rows), None
    except Exception as e:
        log_scrape("race_result", url, "error", str(e), db_path=db_path)
        return url, 0, str(e)


def main():
    parser = argparse.ArgumentParser(description="HKJC Race Result Scraper")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Number of concurrent workers (default: {DEFAULT_WORKERS})")
    parser.add_argument("--db", type=str, default=None,
                        help="Path to SQLite database")
    parser.add_argument("--year-start", type=int, default=YEAR_START,
                        help=f"Start year (default: {YEAR_START})")
    parser.add_argument("--year-end", type=int, default=YEAR_END,
                        help=f"End year (default: {YEAR_END})")
    args = parser.parse_args()

    db_path = args.db
    if db_path is None:
        from config import DB_PATH
        db_path = DB_PATH

    # Initialize database
    init_db(db_path)

    # Generate URLs
    dates = generate_race_dates(args.year_start, args.year_end)
    all_urls = build_urls(dates)

    # Filter out already-scraped URLs (resume capability)
    completed = get_completed_urls("race_result", db_path)
    urls = [u for u in all_urls if u not in completed]

    logger.info(
        "Race Result: %d total URLs, %d already done, %d remaining",
        len(all_urls), len(completed), len(urls),
    )

    if not urls:
        logger.info("Nothing to scrape — all URLs already completed.")
        return

    # Scrape with thread pool
    total_rows = 0
    errors = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(worker, url, db_path): url for url in urls}

        with tqdm(total=len(urls), desc="Race Results", unit="page") as pbar:
            for future in as_completed(futures):
                url, row_count, error = future.result()
                total_rows += row_count
                if error:
                    errors += 1
                pbar.update(1)
                pbar.set_postfix(rows=total_rows, errors=errors)

    # Clean up all thread-local drivers
    quit_driver()

    logger.info(
        "✅ Race Result scraping complete: %d rows scraped, %d errors",
        total_rows, errors,
    )


if __name__ == "__main__":
    main()
