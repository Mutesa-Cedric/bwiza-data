#!/bin/bash
set -euo pipefail

# Overnight full pipeline: crawl → index → dedup → enrich → split → export
# Usage: nohup bash scripts/run_overnight.sh > logs/overnight.log 2>&1 &
#
# Strategy:
#   CC Index is the primary crawler — queries Common Crawl's CDX across 50+
#   crawls (2013–present) for all .rw domains + Rwandan news sites, then
#   fetches WARC records via byte-range from S3 (no rate limiting).
#   Wayback is capped at 5K records as a supplement for URLs not in CC.

cd "$(dirname "$0")/.."
VENV=".venv/bin/python"
LOG_DIR="logs/overnight_$(date +%Y%m%dT%H%M%S)"
mkdir -p "$LOG_DIR"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_DIR/pipeline.log"; }

log "=== OVERNIGHT PIPELINE START ==="
log "Logs → $LOG_DIR"

# ─────────────────────────────────────────────
# STAGE 1: DATA COLLECTION
# ─────────────────────────────────────────────
log "STAGE 1: Starting data collection..."

# 1a. CC Index — primary heavy lifter (50 crawls × .rw + news domains, WARC byte-range)
log "  Starting CC index miner (primary)..."
$VENV scripts/run_cc_index.py > "$LOG_DIR/cc_index.log" 2>&1 &
PID_CCI=$!

# 1b. Targeted crawler (105 .rw domains, live web)
log "  Starting targeted crawler..."
$VENV scripts/run_targeted_crawler.py > "$LOG_DIR/targeted.log" 2>&1 &
PID_TC=$!

# 1c. Wayback Machine (supplement only, capped at 5K records)
log "  Starting Wayback miner (supplement, max 5K records)..."
$VENV scripts/run_wayback_miner.py > "$LOG_DIR/wayback.log" 2>&1 &
PID_WB=$!

# 1d. CC Miner (random WET files — low Kinyarwanda yield but free)
log "  Starting CC miner..."
$VENV scripts/run_cc_miner.py > "$LOG_DIR/cc_miner.log" 2>&1 &
PID_CC=$!

# 1e. Books corpus (high-quality direct PDF/HTML sources)
log "  Starting books corpus pipeline..."
$VENV scripts/run_books_corpus.py > "$LOG_DIR/books.log" 2>&1 &
PID_BK=$!

# Wait for all crawlers
log "  Waiting for crawlers to finish..."
FAIL=0
for PID_NAME in "$PID_CCI:cc_index" "$PID_TC:targeted" "$PID_WB:wayback" "$PID_CC:cc_miner" "$PID_BK:books"; do
    PID="${PID_NAME%%:*}"
    NAME="${PID_NAME##*:}"
    if wait "$PID"; then
        log "  ✓ $NAME finished successfully"
    else
        log "  ✗ $NAME failed (exit $?), check $LOG_DIR/${NAME}.log"
        FAIL=1
    fi
done

if [ "$FAIL" -eq 1 ]; then
    log "WARNING: Some crawlers failed, continuing with available data..."
fi

# ─────────────────────────────────────────────
# STAGE 2: BUILD INDEX from manifests
# ─────────────────────────────────────────────
log "STAGE 2: Building dataset index..."
$VENV scripts/build_index.py \
    --dataset pretrain \
    --bucket bwiza-test-bucket \
    --version v1 \
    --manifest-dir manifests/shards \
    --output-dir outputs/datasets \
    > "$LOG_DIR/build_index.log" 2>&1
log "  Index built: $(wc -l < outputs/datasets/pretrain/v1/index.jsonl) entries"

# ─────────────────────────────────────────────
# STAGE 3: GLOBAL DEDUP
# ─────────────────────────────────────────────
log "STAGE 3: Running global dedup pass..."
$VENV scripts/run_dedup_pass.py \
    --index outputs/datasets/pretrain/v1/index.jsonl \
    --shard-dir outputs/shards \
    --output-dir outputs/packaging \
    > "$LOG_DIR/dedup.log" 2>&1
log "  Dedup complete"

# ─────────────────────────────────────────────
# STAGE 4: ENRICH METADATA
# ─────────────────────────────────────────────
log "STAGE 4: Enriching metadata (tokenizing all docs)..."
$VENV scripts/enrich_metadata.py \
    --index outputs/datasets/pretrain/v1/index.jsonl \
    --shard-dir outputs/shards \
    --output outputs/packaging/enrichment.jsonl \
    --tokenizer Qwen/Qwen3-8B \
    > "$LOG_DIR/enrich.log" 2>&1
log "  Enrichment complete: $(wc -l < outputs/packaging/enrichment.jsonl) docs"

# ─────────────────────────────────────────────
# STAGE 5: SPLITS + PARQUET EXPORT
# ─────────────────────────────────────────────
log "STAGE 5a: Building splits..."
$VENV scripts/build_splits.py \
    --index outputs/datasets/pretrain/v1/index.jsonl \
    --output-dir outputs/packaging/splits \
    --enrichment outputs/packaging/enrichment.jsonl \
    > "$LOG_DIR/splits.log" 2>&1
log "  Splits: train=$(wc -l < outputs/packaging/splits/train.txt) val=$(wc -l < outputs/packaging/splits/val.txt) test=$(wc -l < outputs/packaging/splits/test.txt)"

log "STAGE 5b: Exporting pre-tokenized Parquet..."
$VENV scripts/export_pretokenized.py \
    --splits-dir outputs/packaging/splits \
    --shard-dir outputs/shards \
    --output-dir outputs/packaging/parquet \
    --tokenizer Qwen/Qwen3-8B \
    --max-length 4096 \
    > "$LOG_DIR/export.log" 2>&1
log "  Parquet export complete"

# ─────────────────────────────────────────────
# STAGE 6: VALIDATION REPORTS
# ─────────────────────────────────────────────
log "STAGE 6: Running validation..."
$VENV scripts/tokenizer_validation.py \
    --shard-dir outputs/shards \
    --tokenizer Qwen/Qwen3-8B \
    --max-docs-per-source 500 \
    > "$LOG_DIR/tokenizer_validation.log" 2>&1
log "  Tokenizer validation complete"

# ─────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────
log "=== OVERNIGHT PIPELINE COMPLETE ==="
log "Shards:     $(find outputs/shards -name '*.jsonl.zst' | wc -l) files"
log "Index:      $(wc -l < outputs/datasets/pretrain/v1/index.jsonl) entries"
log "Enrichment: $(wc -l < outputs/packaging/enrichment.jsonl) docs"
log "Parquet:    $(du -sh outputs/packaging/parquet/ 2>/dev/null | cut -f1)"
log "Logs:       $LOG_DIR/"
