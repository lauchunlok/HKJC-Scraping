#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# HKJC Scraping Pipeline — run_scraper.sh
#
# Runs all scrapers in the correct order:
#   1. Race Results      (independent — generates the date/horse data)
#   2. Form Records      (depends on race_results for horse IDs)
#   3. Sectional Times   (depends on race_results for date/match pairs)
#
# Usage:
#   ./run_scraper.sh                           # defaults
#   ./run_scraper.sh --workers 8               # custom thread count
#   ./run_scraper.sh --year-start 2020         # scrape only recent years
#   ./run_scraper.sh --skip-race-result        # skip step 1
#   ./run_scraper.sh --export-csv              # export DB → CSV after scraping
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Defaults ──────────────────────────────────────────────────
WORKERS=5
YEAR_START=2007
YEAR_END=$(date +%Y)
DB_PATH="hkjc.db"
SKIP_RACE_RESULT=false
SKIP_FORM_RECORD=false
SKIP_SECTIONAL_TIME=false
SKIP_RACECARD=false
EXPORT_CSV=false

# ── Parse arguments ───────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --workers)          WORKERS="$2"; shift 2 ;;
        --year-start)       YEAR_START="$2"; shift 2 ;;
        --year-end)         YEAR_END="$2"; shift 2 ;;
        --db)               DB_PATH="$2"; shift 2 ;;
        --skip-race-result) SKIP_RACE_RESULT=true; shift ;;
        --skip-form-record) SKIP_FORM_RECORD=true; shift ;;
        --skip-sectional)   SKIP_SECTIONAL_TIME=true; shift ;;
        --skip-racecard)    SKIP_RACECARD=true; shift ;;
        --export-csv)       EXPORT_CSV=true; shift ;;
        -h|--help)
            head -20 "$0" | grep -E "^#" | sed 's/^# *//'
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# ── Colors ────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ── Pre-flight checks ────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  HKJC Scraping Pipeline"
echo "═══════════════════════════════════════════════════════"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    log_error "Python 3 is not installed. Please install Python 3.8+."
    exit 1
fi
PYTHON_VERSION=$(python3 --version 2>&1)
log_ok "Found $PYTHON_VERSION"

# ── Virtual environment setup ─────────────────────────────────
VENV_DIR="$SCRIPT_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    log_info "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    log_ok "Virtual environment created at $VENV_DIR"
fi

# Activate venv
source "$VENV_DIR/bin/activate"
log_ok "Virtual environment activated"

# Check/install dependencies
log_info "Checking Python dependencies..."
if ! python3 -c "import selenium, bs4, pandas, tqdm" 2>/dev/null; then
    log_warn "Missing dependencies. Installing from requirements.txt..."
    pip install -r requirements.txt
fi
log_ok "All dependencies installed"

# Create directories
mkdir -p logs clean

# Initialize database
log_info "Initializing database at $DB_PATH..."
python3 -c "from db import init_db; init_db('$DB_PATH')"
log_ok "Database ready"

echo ""
echo "Configuration:"
echo "  Workers:    $WORKERS"
echo "  Years:      $YEAR_START → $YEAR_END"
echo "  Database:   $DB_PATH"
echo ""

# ── Step 1: Race Results ──────────────────────────────────────
if [ "$SKIP_RACE_RESULT" = false ]; then
    echo "───────────────────────────────────────────────────"
    log_info "Step 1/4: Scraping Race Results..."
    echo "───────────────────────────────────────────────────"

    python3 scrape_race_result.py \
        --workers "$WORKERS" \
        --db "$DB_PATH" \
        --year-start "$YEAR_START" \
        --year-end "$YEAR_END" \
        2>&1 | tee logs/race_result_$(date +%Y%m%d_%H%M%S).log

    log_ok "Race Results complete"
    echo ""
else
    log_warn "Skipping Race Results (--skip-race-result)"
fi

# ── Step 2: Form Records ─────────────────────────────────────
if [ "$SKIP_FORM_RECORD" = false ]; then
    echo "───────────────────────────────────────────────────"
    log_info "Step 2/4: Scraping Form Records..."
    echo "───────────────────────────────────────────────────"

    python3 scrape_form_record.py \
        --workers "$WORKERS" \
        --db "$DB_PATH" \
        2>&1 | tee logs/form_record_$(date +%Y%m%d_%H%M%S).log

    log_ok "Form Records complete"
    echo ""
else
    log_warn "Skipping Form Records (--skip-form-record)"
fi

# ── Step 3: Sectional Times ──────────────────────────────────
if [ "$SKIP_SECTIONAL_TIME" = false ]; then
    echo "───────────────────────────────────────────────────"
    log_info "Step 3/4: Scraping Sectional Times..."
    echo "───────────────────────────────────────────────────"

    python3 scrape_sectional_time.py \
        --workers "$WORKERS" \
        --db "$DB_PATH" \
        2>&1 | tee logs/sectional_time_$(date +%Y%m%d_%H%M%S).log

    log_ok "Sectional Times complete"
    echo ""
else
    log_warn "Skipping Sectional Times (--skip-sectional)"
fi

# ── Step 4: Race Card ─────────────────────────────────────────
if [ "$SKIP_RACECARD" = false ]; then
    echo "───────────────────────────────────────────────────"
    log_info "Step 4/4: Scraping Race Card (today)..."
    echo "───────────────────────────────────────────────────"

    python3 scrape_racecard.py \
        --workers "$WORKERS" \
        --db "$DB_PATH" \
        2>&1 | tee logs/racecard_$(date +%Y%m%d_%H%M%S).log

    log_ok "Race Card complete"
    echo ""
else
    log_warn "Skipping Race Card (--skip-racecard)"
fi

# ── Step 5: Validation & Re-scrape ────────────────────────────
echo "───────────────────────────────────────────────────"
log_info "Step 5: Validating data completeness..."
echo "───────────────────────────────────────────────────"

python3 validate_and_merge.py --db "$DB_PATH" --re-scrape \
    2>&1 | tee logs/validate_$(date +%Y%m%d_%H%M%S).log

log_ok "Validation complete"
echo ""

# ── Optional: Export to CSV ───────────────────────────────────
if [ "$EXPORT_CSV" = true ]; then
    echo "───────────────────────────────────────────────────"
    log_info "Exporting database to CSV..."
    echo "───────────────────────────────────────────────────"

    python3 validate_and_merge.py --db "$DB_PATH" --export

    python3 -c "
from db import export_table_to_csv
export_table_to_csv('race_results', 'race_result.csv', '$DB_PATH')
export_table_to_csv('form_records', 'form_record.csv', '$DB_PATH')
export_table_to_csv('sectional_times', 'sectional_time.csv', '$DB_PATH')
export_table_to_csv('racecard', 'racecard.csv', '$DB_PATH')
print('CSV export complete → clean/ directory')
"
    log_ok "CSV export complete"
fi

# ── Summary ───────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✅ HKJC Scraping Pipeline Complete!"
echo ""

python3 -c "
import sqlite3
conn = sqlite3.connect('$DB_PATH')
tables = ['race_results', 'form_records', 'sectional_times', 'racecard']
for t in tables:
    try:
        count = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
        print(f'  {t:20s} : {count:>8,} rows')
    except:
        print(f'  {t:20s} : 0 rows')
conn.close()
"

echo ""
echo "  Database: $DB_PATH"
echo "  Logs:     logs/"
echo "═══════════════════════════════════════════════════════"
echo ""

