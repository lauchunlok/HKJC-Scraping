"""
SQLite database manager for HKJC Scraping project.

Tables:
  - race_results      : race result data
  - form_records      : horse form record data
  - sectional_times   : sectional time & position data
  - racecard          : race card data (upcoming/today's races)
  - scrape_log        : tracks completed URLs for resume capability
  - merged_dataset    : view joining form_records + race_results + sectional_times
"""
import os
import sqlite3
from contextlib import contextmanager
from typing import List, Optional

import pandas as pd

from config import DB_PATH, CSV_DIR, setup_logging

logger = setup_logging("db")

# ──────────────────────────────────────────────
# Schema definitions
# ──────────────────────────────────────────────

RACE_RESULTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS race_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    plc             TEXT,
    horse_no        TEXT,
    horse           TEXT,
    jockey          TEXT,
    trainer         TEXT,
    actual_wt       TEXT,
    declar_horse_wt TEXT,
    draw            TEXT,
    lbw             TEXT,
    running_position TEXT,
    finish_time     TEXT,
    win_odds        TEXT,
    date            TEXT,
    match           TEXT,
    cdr             TEXT,
    prize_money     TEXT,
    horseid         TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, match, horse)
);
"""

FORM_RECORDS_SCHEMA = """
CREATE TABLE IF NOT EXISTS form_records (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    race_index        TEXT,
    pla               TEXT,
    date              TEXT,
    rc_track_course   TEXT,
    dist              TEXT,
    ground            TEXT,
    race_class        TEXT,
    draw              TEXT,
    rating            TEXT,
    trainer           TEXT,
    jockey            TEXT,
    lbw               TEXT,
    win_odds          TEXT,
    act_wt            TEXT,
    run_po            TEXT,
    finish_time       TEXT,
    declare_horse_wt  TEXT,
    gear              TEXT,
    video_replay      TEXT,
    horseid           TEXT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, horseid, race_index)
);
"""

SECTIONAL_TIMES_SCHEMA = """
CREATE TABLE IF NOT EXISTS sectional_times (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    finishing_order   TEXT,
    horse_no          TEXT,
    horse             TEXT,
    time              TEXT,
    section_time_1    TEXT,
    section_time_2    TEXT,
    section_time_3    TEXT,
    section_time_4    TEXT,
    section_time_5    TEXT,
    section_time_6    TEXT,
    margin_behind_1   TEXT,
    margin_behind_2   TEXT,
    margin_behind_3   TEXT,
    margin_behind_4   TEXT,
    margin_behind_5   TEXT,
    margin_behind_6   TEXT,
    date              TEXT,
    match             TEXT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, match, horse)
);
"""

RACECARD_SCHEMA = """
CREATE TABLE IF NOT EXISTS racecard (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    horse_no            TEXT,
    last_6_runs         TEXT,
    colour              TEXT,
    horse               TEXT,
    brand_no            TEXT,
    wt                  TEXT,
    jockey              TEXT,
    over_wt             TEXT,
    draw                TEXT,
    trainer             TEXT,
    intl_rtg            TEXT,
    rtg                 TEXT,
    rtg_change          TEXT,
    horse_wt_decl       TEXT,
    wt_change_vs_decl   TEXT,
    best_time           TEXT,
    age                 TEXT,
    wfa                 TEXT,
    sex                 TEXT,
    season_stakes       TEXT,
    priority            TEXT,
    gear                TEXT,
    owner               TEXT,
    sire                TEXT,
    dam                 TEXT,
    import_cat          TEXT,
    date                TEXT,
    match               TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, match, horse)
);
"""

SCRAPE_LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS scrape_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scraper     TEXT NOT NULL,
    url         TEXT NOT NULL,
    status      TEXT DEFAULT 'success',
    error_msg   TEXT,
    scraped_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(scraper, url)
);
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_race_results_date ON race_results(date);",
    "CREATE INDEX IF NOT EXISTS idx_race_results_horseid ON race_results(horseid);",
    "CREATE INDEX IF NOT EXISTS idx_form_records_horseid ON form_records(horseid);",
    "CREATE INDEX IF NOT EXISTS idx_sectional_times_date ON sectional_times(date);",
    "CREATE INDEX IF NOT EXISTS idx_racecard_date ON racecard(date);",
    "CREATE INDEX IF NOT EXISTS idx_scrape_log_scraper ON scrape_log(scraper);",
]


# ──────────────────────────────────────────────
# Database connection
# ──────────────────────────────────────────────

@contextmanager
def get_connection(db_path: str = DB_PATH):
    """Context manager for SQLite connections with WAL mode."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ──────────────────────────────────────────────
# Initialization
# ──────────────────────────────────────────────

def init_db(db_path: str = DB_PATH):
    """Create all tables and indexes if they don't exist."""
    with get_connection(db_path) as conn:
        conn.execute(RACE_RESULTS_SCHEMA)
        conn.execute(FORM_RECORDS_SCHEMA)
        conn.execute(SECTIONAL_TIMES_SCHEMA)
        conn.execute(RACECARD_SCHEMA)
        conn.execute(SCRAPE_LOG_SCHEMA)
        for idx_sql in CREATE_INDEXES:
            conn.execute(idx_sql)
    logger.info("Database initialized at %s", db_path)


# ──────────────────────────────────────────────
# Insert helpers
# ──────────────────────────────────────────────

def insert_race_results(rows: List[list], db_path: str = DB_PATH):
    """Bulk insert race results, skipping duplicates."""
    if not rows:
        return
    sql = """
        INSERT OR IGNORE INTO race_results
        (plc, horse_no, horse, jockey, trainer, actual_wt,
         declar_horse_wt, draw, lbw, running_position, finish_time,
         win_odds, date, match, cdr, prize_money, horseid)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    with get_connection(db_path) as conn:
        conn.executemany(sql, rows)
    logger.info("Inserted %d race result rows (duplicates ignored)", len(rows))


def insert_form_records(rows: List[list], db_path: str = DB_PATH):
    """Bulk insert form records, skipping duplicates."""
    if not rows:
        return
    sql = """
        INSERT OR IGNORE INTO form_records
        (race_index, pla, date, rc_track_course, dist, ground,
         race_class, draw, rating, trainer, jockey, lbw, win_odds,
         act_wt, run_po, finish_time, declare_horse_wt, gear,
         video_replay, horseid)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    with get_connection(db_path) as conn:
        conn.executemany(sql, rows)
    logger.info("Inserted %d form record rows (duplicates ignored)", len(rows))


def insert_sectional_times(rows: List[list], db_path: str = DB_PATH):
    """Bulk insert sectional times, skipping duplicates."""
    if not rows:
        return
    sql = """
        INSERT OR IGNORE INTO sectional_times
        (finishing_order, horse_no, horse, time,
         section_time_1, section_time_2, section_time_3,
         section_time_4, section_time_5, section_time_6,
         margin_behind_1, margin_behind_2, margin_behind_3,
         margin_behind_4, margin_behind_5, margin_behind_6,
         date, match)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    with get_connection(db_path) as conn:
        conn.executemany(sql, rows)
    logger.info("Inserted %d sectional time rows (duplicates ignored)", len(rows))


def insert_racecard(rows: List[list], db_path: str = DB_PATH):
    """Bulk insert racecard data, skipping duplicates."""
    if not rows:
        return
    sql = """
        INSERT OR IGNORE INTO racecard
        (horse_no, last_6_runs, colour, horse, brand_no, wt,
         jockey, over_wt, draw, trainer, intl_rtg, rtg,
         rtg_change, horse_wt_decl, wt_change_vs_decl, best_time,
         age, wfa, sex, season_stakes, priority, gear,
         owner, sire, dam, import_cat, date, match)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    with get_connection(db_path) as conn:
        conn.executemany(sql, rows)
    logger.info("Inserted %d racecard rows (duplicates ignored)", len(rows))


# ──────────────────────────────────────────────
# Scrape log helpers (resume capability)
# ──────────────────────────────────────────────

def log_scrape(scraper: str, url: str, status: str = "success",
               error_msg: str = None, db_path: str = DB_PATH):
    """Record a completed scrape in the log."""
    sql = """
        INSERT OR REPLACE INTO scrape_log (scraper, url, status, error_msg)
        VALUES (?, ?, ?, ?)
    """
    with get_connection(db_path) as conn:
        conn.execute(sql, (scraper, url, status, error_msg))


def get_completed_urls(scraper: str, db_path: str = DB_PATH) -> set:
    """Get the set of URLs already successfully scraped (or confirmed empty)."""
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "SELECT url FROM scrape_log WHERE scraper = ? AND status IN ('success', 'empty')",
            (scraper,),
        )
        return {row[0] for row in cursor.fetchall()}


# ──────────────────────────────────────────────
# Query helpers
# ──────────────────────────────────────────────

def get_unique_horse_ids(db_path: str = DB_PATH) -> List[str]:
    """Get unique horse IDs from race_results table."""
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "SELECT DISTINCT horseid FROM race_results WHERE horseid IS NOT NULL AND horseid != ''"
        )
        return [row[0] for row in cursor.fetchall()]


def get_unique_race_dates_and_matches(db_path: str = DB_PATH) -> List[tuple]:
    """Get unique (date, match) pairs from race_results table."""
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "SELECT DISTINCT date, match FROM race_results ORDER BY date, match"
        )
        return cursor.fetchall()


def get_missing_horse_ids(db_path: str = DB_PATH) -> List[str]:
    """
    Find horse IDs in race_results that are NOT in form_records.
    These horses need their form records scraped.
    """
    with get_connection(db_path) as conn:
        cursor = conn.execute("""
            SELECT DISTINCT r.horseid
            FROM race_results r
            LEFT JOIN (
                SELECT DISTINCT horseid FROM form_records
            ) f ON r.horseid = f.horseid
            WHERE r.horseid IS NOT NULL
              AND r.horseid != ''
              AND f.horseid IS NULL
        """)
        return [row[0] for row in cursor.fetchall()]


def get_missing_sectional_dates(db_path: str = DB_PATH) -> List[tuple]:
    """
    Find (date, match) pairs in race_results that are NOT in sectional_times.
    These races need their sectional times scraped.
    """
    with get_connection(db_path) as conn:
        cursor = conn.execute("""
            SELECT DISTINCT r.date, r.match
            FROM race_results r
            LEFT JOIN (
                SELECT DISTINCT date, match FROM sectional_times
            ) s ON r.date = s.date AND r.match = s.match
            WHERE s.date IS NULL
            ORDER BY r.date, r.match
        """)
        return cursor.fetchall()


def validate_completeness(db_path: str = DB_PATH) -> dict:
    """
    Cross-check all tables for data completeness.
    Returns a dict with validation results.

    Inspired by merge.ipynb validation steps:
    - Check for VOID races in race_results
    - Check for malformed dates
    - Find horse IDs missing from form_records
    - Find (date, match) pairs missing from sectional_times
    - Count rows per table
    """
    results = {}

    with get_connection(db_path) as conn:
        # Row counts
        for table in ['race_results', 'form_records', 'sectional_times', 'racecard']:
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                results[f"{table}_count"] = count
            except Exception:
                results[f"{table}_count"] = 0

        # VOID races
        void_count = conn.execute(
            "SELECT COUNT(*) FROM race_results WHERE plc = 'VOID'"
        ).fetchone()[0]
        results["void_races"] = void_count

        # Malformed dates (should be YYYY/MM/DD, 10 chars)
        bad_dates = conn.execute(
            "SELECT COUNT(*) FROM race_results WHERE LENGTH(date) != 10"
        ).fetchone()[0]
        results["malformed_dates"] = bad_dates

    # Missing form records
    missing_horses = get_missing_horse_ids(db_path)
    results["missing_form_record_horses"] = len(missing_horses)
    results["missing_form_record_horse_ids"] = missing_horses[:20]  # First 20

    # Missing sectional times
    missing_st = get_missing_sectional_dates(db_path)
    results["missing_sectional_time_races"] = len(missing_st)
    results["missing_sectional_time_dates"] = missing_st[:20]  # First 20

    return results


def build_merged_dataset(db_path: str = DB_PATH) -> pd.DataFrame:
    """
    Build the merged dataset joining form_records + race_results + sectional_times.

    Replicates the merge.ipynb logic:
    1. Join form_records with race_results on (horseid, date) to get
       participating_horse count and prize_money
    2. Join with sectional_times on (date, match, horse) for section times
    3. Export as a single DataFrame for feature engineering
    """
    with get_connection(db_path) as conn:
        # Load tables
        form_record = pd.read_sql_query(
            "SELECT * FROM form_records WHERE horseid IS NOT NULL AND horseid != ''",
            conn
        )
        race_result = pd.read_sql_query(
            "SELECT * FROM race_results WHERE plc != 'VOID' AND LENGTH(date) = 10",
            conn
        )
        sectional_time = pd.read_sql_query(
            "SELECT * FROM sectional_times",
            conn
        )

    if form_record.empty or race_result.empty:
        logger.warning("Cannot build merged dataset — tables are empty")
        return pd.DataFrame()

    # Drop internal columns
    for df in [form_record, race_result, sectional_time]:
        for col in ['id', 'created_at']:
            if col in df.columns:
                df.drop(columns=[col], inplace=True)

    # --- Step 1: Compute participating_horse count per race ---
    race_result['participating_horse'] = race_result.groupby(
        ['date', 'match']
    )['plc'].transform('size')

    # --- Step 2: Create merge keys ---
    # form_record date is YYYY-MM-DD, race_result date is YYYY/MM/DD
    form_record['formatted_date'] = pd.to_datetime(form_record['date'], errors='coerce')
    race_result['formatted_date'] = pd.to_datetime(race_result['date'], format='%Y/%m/%d', errors='coerce')

    form_record['merge_key'] = (
        form_record['horseid'] + '_' + form_record['formatted_date'].astype(str)
    )
    race_result['merge_key'] = (
        race_result['horseid'] + '_' + race_result['formatted_date'].astype(str)
    )

    # --- Step 3: Select columns from race_result for merge ---
    rr_cols = ['merge_key', 'prize_money', 'participating_horse',
               'date', 'match']
    rr_dedup = race_result[rr_cols].drop_duplicates(subset=['merge_key'])

    # --- Step 4: Merge form_records ← race_results ---
    merged = form_record.merge(
        rr_dedup, on='merge_key', how='left', suffixes=('', '_rr')
    )

    # --- Step 5: Merge sectional_times ---
    if not sectional_time.empty:
        # Create short_key for sectional_time matching via horse code
        # sectional_time.horse contains e.g. "HORSE NAME(CODE)"
        # We need to match on date + match + horse_code
        st_cols = [
            'date', 'match',
            'section_time_1', 'section_time_2', 'section_time_3',
            'section_time_4', 'section_time_5', 'section_time_6',
            'margin_behind_1', 'margin_behind_2', 'margin_behind_3',
            'margin_behind_4', 'margin_behind_5', 'margin_behind_6',
            'horse_no', 'horse'
        ]
        # Use date_rr and match from the merged dataset
        # Match using date_rr (YYYY/MM/DD format) and match
        st_for_merge = sectional_time[st_cols].copy()
        # Convert sectional_time date dd/mm/yyyy → yyyy/mm/dd
        try:
            st_for_merge['date_converted'] = pd.to_datetime(
                st_for_merge['date'], format='%d/%m/%Y', errors='coerce'
            ).dt.strftime('%Y/%m/%d')
        except Exception:
            st_for_merge['date_converted'] = st_for_merge['date']

        st_for_merge['st_key'] = (
            st_for_merge['date_converted'] + '_' + st_for_merge['match']
            + '_' + st_for_merge['horse_no']
        )

        merged['st_key'] = (
            merged['date_rr'].fillna('') + '_' + merged['match'].fillna('')
            + '_' + merged.get('horse_no', pd.Series([''] * len(merged))).fillna('')
        )

        st_dedup = st_for_merge.drop(
            columns=['date', 'match', 'horse_no', 'horse', 'date_converted']
        ).drop_duplicates(subset=['st_key'])

        merged = merged.merge(st_dedup, on='st_key', how='left')

    # Clean up temp columns
    drop_cols = [c for c in merged.columns if c.endswith('_rr') or c in
                 ['merge_key', 'st_key', 'formatted_date']]
    merged.drop(columns=[c for c in drop_cols if c in merged.columns],
                inplace=True, errors='ignore')

    logger.info("Built merged dataset: %d rows × %d columns", *merged.shape)
    return merged


# ──────────────────────────────────────────────
# CSV export (backward compatibility)
# ──────────────────────────────────────────────

def export_table_to_csv(table_name: str, filename: Optional[str] = None,
                        db_path: str = DB_PATH):
    """Export a database table to CSV."""
    os.makedirs(CSV_DIR, exist_ok=True)
    if filename is None:
        filename = f"{table_name}.csv"
    filepath = os.path.join(CSV_DIR, filename)

    with get_connection(db_path) as conn:
        df = pd.read_sql_query(
            f"SELECT * FROM {table_name} WHERE 1=1",  # noqa: S608
            conn,
        )
    # Drop internal columns
    drop_cols = [c for c in ("id", "created_at") if c in df.columns]
    df.drop(columns=drop_cols, inplace=True)
    df.to_csv(filepath, index=False)
    logger.info("Exported %s → %s (%d rows)", table_name, filepath, len(df))
    return filepath


# ──────────────────────────────────────────────
# Main — run standalone to init DB
# ──────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    print(f"✅ Database ready at {DB_PATH}")
