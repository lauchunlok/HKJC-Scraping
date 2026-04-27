#!/usr/bin/env python3
"""
HKJC Data Validation & Merge Tool

Validates data completeness across all scraped tables and builds
the merged dataset for feature engineering.

Usage:
    python validate_and_merge.py                    # validate only
    python validate_and_merge.py --merge            # validate + build merged dataset
    python validate_and_merge.py --export           # validate + export merged CSV
    python validate_and_merge.py --re-scrape        # validate + re-scrape missing data
"""
import argparse
import sys

from config import setup_logging
from db import (
    init_db, validate_completeness, build_merged_dataset,
    export_table_to_csv, get_missing_horse_ids, get_missing_sectional_dates,
)

logger = setup_logging("validate")


def print_validation(results: dict):
    """Pretty-print validation results."""
    print("\n" + "=" * 60)
    print("  HKJC Data Validation Report")
    print("=" * 60)

    # Row counts
    print("\n📊 Table Row Counts:")
    for table in ['race_results', 'form_records', 'sectional_times', 'racecard']:
        count = results.get(f"{table}_count", 0)
        print(f"   {table:20s} : {count:>10,} rows")

    # Data quality
    print("\n🔍 Data Quality:")
    void = results.get("void_races", 0)
    bad_dates = results.get("malformed_dates", 0)
    status = "✅" if void == 0 else "⚠️ "
    print(f"   {status} VOID races         : {void}")
    status = "✅" if bad_dates == 0 else "⚠️ "
    print(f"   {status} Malformed dates    : {bad_dates}")

    # Completeness
    print("\n📋 Cross-Table Completeness:")
    missing_fr = results.get("missing_form_record_horses", 0)
    missing_st = results.get("missing_sectional_time_races", 0)

    status = "✅" if missing_fr == 0 else "❌"
    print(f"   {status} Horses missing form records  : {missing_fr}")
    if missing_fr > 0:
        ids = results.get("missing_form_record_horse_ids", [])
        print(f"      First {len(ids)}: {ids}")

    status = "✅" if missing_st == 0 else "❌"
    print(f"   {status} Races missing sectional times: {missing_st}")
    if missing_st > 0:
        dates = results.get("missing_sectional_time_dates", [])
        print(f"      First {len(dates)}: {dates}")

    print("\n" + "=" * 60)

    all_good = missing_fr == 0 and missing_st == 0 and void == 0 and bad_dates == 0
    if all_good:
        print("  ✅ All checks passed — data is complete!")
    else:
        print("  ⚠️  Some issues found — see above")
        if missing_fr > 0:
            print(f"      → Run: python scrape_form_record.py  (to fill {missing_fr} missing horses)")
        if missing_st > 0:
            print(f"      → Run: python scrape_sectional_time.py  (to fill {missing_st} missing races)")
    print("=" * 60 + "\n")

    return all_good


def main():
    parser = argparse.ArgumentParser(description="HKJC Data Validation & Merge")
    parser.add_argument("--db", type=str, default=None,
                        help="Path to SQLite database")
    parser.add_argument("--merge", action="store_true",
                        help="Build merged dataset after validation")
    parser.add_argument("--export", action="store_true",
                        help="Export merged dataset to CSV")
    parser.add_argument("--re-scrape", action="store_true",
                        help="Re-scrape missing form records and sectional times")
    args = parser.parse_args()

    db_path = args.db
    if db_path is None:
        from config import DB_PATH
        db_path = DB_PATH

    init_db(db_path)

    # --- Validation ---
    print("\n🔄 Running data validation...")
    results = validate_completeness(db_path)
    all_good = print_validation(results)

    # --- Re-scrape missing data ---
    if args.re_scrape:
        missing_horses = get_missing_horse_ids(db_path)
        missing_st = get_missing_sectional_dates(db_path)

        if missing_horses:
            print(f"\n🔄 Re-scraping form records for {len(missing_horses)} missing horses...")
            from scrape_form_record import worker as fr_worker
            from concurrent.futures import ThreadPoolExecutor, as_completed
            from config import FORM_RECORD_URL, DEFAULT_WORKERS
            from tqdm import tqdm

            urls = [FORM_RECORD_URL.format(horse_id=hid) for hid in missing_horses]
            with ThreadPoolExecutor(max_workers=DEFAULT_WORKERS) as executor:
                futures = {executor.submit(fr_worker, url, db_path): url for url in urls}
                with tqdm(total=len(urls), desc="Form Records (missing)", unit="horse") as pbar:
                    for future in as_completed(futures):
                        pbar.update(1)
            print(f"   ✅ Re-scraped {len(missing_horses)} horses")

        if missing_st:
            print(f"\n🔄 Re-scraping sectional times for {len(missing_st)} missing races...")
            from scrape_sectional_time import worker as st_worker, convert_date_format
            from concurrent.futures import ThreadPoolExecutor, as_completed
            from config import SECTIONAL_TIME_URL, DEFAULT_WORKERS
            from tqdm import tqdm

            urls = [
                SECTIONAL_TIME_URL.format(
                    date=convert_date_format(d), race_no=m
                )
                for d, m in missing_st
            ]
            with ThreadPoolExecutor(max_workers=DEFAULT_WORKERS) as executor:
                futures = {executor.submit(st_worker, url, db_path): url for url in urls}
                with tqdm(total=len(urls), desc="Sectional Times (missing)", unit="race") as pbar:
                    for future in as_completed(futures):
                        pbar.update(1)
            print(f"   ✅ Re-scraped {len(missing_st)} races")

        # Re-validate
        print("\n🔄 Re-validating after re-scrape...")
        results = validate_completeness(db_path)
        print_validation(results)

    # --- Merge ---
    if args.merge or args.export:
        print("\n🔄 Building merged dataset...")
        merged = build_merged_dataset(db_path)

        if merged.empty:
            print("❌ Merged dataset is empty — check your data")
            sys.exit(1)

        print(f"   ✅ Merged dataset: {merged.shape[0]:,} rows × {merged.shape[1]} columns")

        if args.export:
            import os
            from config import CSV_DIR
            os.makedirs(CSV_DIR, exist_ok=True)
            filepath = os.path.join(CSV_DIR, "form_record_clean.csv")
            merged.to_csv(filepath, index=False)
            print(f"   📁 Exported to: {filepath}")


if __name__ == "__main__":
    main()
