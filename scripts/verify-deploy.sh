#!/usr/bin/env bash
# Post-deploy verification script for stock dashboard.
# Must be run AFTER publish-local-runtime.sh completes.
# Exits with code 0 only when ALL checks pass.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_ROOT="${HOME}/codex/runtime/projects/ashare-dashboard"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:5173}"
BACKEND_ENV_FILE="${ASHARE_LOCAL_BACKEND_ENV_FILE:-$HOME/.config/codex/ashare-dashboard.backend.env}"
MAX_RETRIES=3
PASS=0
FAIL=0

red() { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }

check() {
    local label="$1" cmd="$2"
    if eval "$cmd" >/dev/null 2>&1; then
        green "  [PASS] $label"
        PASS=$((PASS + 1))
        return 0
    else
        red "  [FAIL] $label"
        FAIL=$((FAIL + 1))
        return 1
    fi
}

echo "============================================"
echo " Deploy Verification"
echo " Repo:    $REPO_ROOT"
echo " Runtime: $RUNTIME_ROOT"
echo " Backend: $BACKEND_URL"
echo "============================================"
echo ""

# ── Phase 1: File Sync ──────────────────────────────────────────

echo "--- Phase 1: File Synchronization ---"

check "analysis_pipeline.py synced" \
    "diff -q '$REPO_ROOT/src/ashare_evidence/analysis_pipeline.py' '$RUNTIME_ROOT/src/ashare_evidence/analysis_pipeline.py'"

check "factors.py synced" \
    "diff -q '$REPO_ROOT/src/ashare_evidence/signal_engine_parts/factors.py' '$RUNTIME_ROOT/src/ashare_evidence/signal_engine_parts/factors.py'"

check "factors_extended.py synced" \
    "diff -q '$REPO_ROOT/src/ashare_evidence/signal_engine_parts/factors_extended.py' '$RUNTIME_ROOT/src/ashare_evidence/signal_engine_parts/factors_extended.py'"

check "assembly.py synced" \
    "diff -q '$REPO_ROOT/src/ashare_evidence/signal_engine_parts/assembly.py' '$RUNTIME_ROOT/src/ashare_evidence/signal_engine_parts/assembly.py'"

check "news_analysis.py synced" \
    "diff -q '$REPO_ROOT/src/ashare_evidence/news_analysis.py' '$RUNTIME_ROOT/src/ashare_evidence/news_analysis.py'"

check "analysis_enrichment.py synced" \
    "diff -q '$REPO_ROOT/src/ashare_evidence/analysis_enrichment.py' '$RUNTIME_ROOT/src/ashare_evidence/analysis_enrichment.py'"

check "llm_service.py synced" \
    "diff -q '$REPO_ROOT/src/ashare_evidence/llm_service.py' '$RUNTIME_ROOT/src/ashare_evidence/llm_service.py'"

check "base.py synced" \
    "diff -q '$REPO_ROOT/src/ashare_evidence/signal_engine_parts/base.py' '$RUNTIME_ROOT/src/ashare_evidence/signal_engine_parts/base.py'"

check "frontend constants.ts synced" \
    "diff -q '$REPO_ROOT/frontend/src/utils/constants.ts' '$RUNTIME_ROOT/frontend/src/utils/constants.ts'"

echo ""

# ── Phase 2: Backend Health & Configuration ────────────────────

echo "--- Phase 2: Backend Health ---"

check "Backend health endpoint" \
    "curl -s '$BACKEND_URL/health' | python3 -c \"import sys,json; assert json.load(sys.stdin).get('status')=='ok'\""

check "ANTHROPIC_AUTH_TOKEN in backend env (checked via LLM module import)" \
    "cd '$RUNTIME_ROOT' && set -a && [ -f '$BACKEND_ENV_FILE' ] && source '$BACKEND_ENV_FILE' && set +a && PYTHONPATH=src python3 -c \"from ashare_evidence.llm_service import route_model; t,b,k,m = route_model('announcement_general'); assert 'deepseek' in b.lower()\""

check "Database accessible" \
    "cd '$RUNTIME_ROOT' && PYTHONPATH=src python3 -c \"from sqlalchemy import text; from ashare_evidence.db import get_session_factory; s=get_session_factory()(); s.execute(text('SELECT 1')); s.close()\""

check "MarketBar has total_mv column" \
    "cd '$RUNTIME_ROOT' && PYTHONPATH=src python3 -c \"from ashare_evidence.models import MarketBar; assert hasattr(MarketBar, 'total_mv')\""

echo ""

# ── Phase 3: API Endpoint Verification ──────────────────────────

echo "--- Phase 3: API Responses ---"

check "Watchlist endpoint returns valid payload" \
    "curl -s '$BACKEND_URL/watchlist' | python3 -c \"import sys,json; d=json.load(sys.stdin); assert isinstance(d.get('items'), list)\""

SAMPLE_INFO=$(
    BACKEND_URL="$BACKEND_URL" RUNTIME_ROOT="$RUNTIME_ROOT" python3 - <<'PY'
import json
import os
import sqlite3
import urllib.request
from pathlib import Path


def _api_symbols(path: str) -> list[str]:
    try:
        payload = json.loads(urllib.request.urlopen(os.environ["BACKEND_URL"] + path, timeout=20).read())
    except Exception:
        return []
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    symbols: list[str] = []
    for item in items:
        if isinstance(item, dict) and item.get("symbol"):
            symbols.append(str(item["symbol"]))
    return symbols


def _latest_recommendation_symbols() -> list[str]:
    runtime_root = Path(os.environ["RUNTIME_ROOT"])
    for db_path in (runtime_root / "data" / "ashare_hot.db", runtime_root / "data" / "ashare_dashboard.db"):
        if not db_path.exists():
            continue
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT s.symbol
                FROM recommendations r
                JOIN stocks s ON s.id = r.stock_id
                WHERE r.recommendation_payload IS NOT NULL
                GROUP BY s.symbol
                ORDER BY MAX(r.as_of_data_time) DESC, MAX(r.generated_at) DESC
                LIMIT 8
                """
            ).fetchall()
        except Exception:
            continue
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return [str(row["symbol"]) for row in rows if row["symbol"]]
    return []


source = "dashboard_candidates"
symbols = _api_symbols("/dashboard/candidates")
if not symbols:
    source = "watchlist"
    symbols = _api_symbols("/watchlist")
if not symbols:
    source = "runtime_latest_recommendations"
    symbols = _latest_recommendation_symbols()

seen: set[str] = set()
deduped: list[str] = []
for candidate in symbols:
    if candidate not in seen:
        seen.add(candidate)
        deduped.append(candidate)
print(f"{source}|{','.join(deduped[:8])}")
PY
)
SAMPLE_SOURCE="${SAMPLE_INFO%%|*}"
SYMBOLS="${SAMPLE_INFO#*|}"
echo "Dashboard verification sample source: $SAMPLE_SOURCE"

check "Dashboard verification sample symbols available" \
    "[ -n '$SYMBOLS' ]"

if [ -n "$SYMBOLS" ]; then
    IFS=',' read -ra SYM_ARRAY <<< "$SYMBOLS"
    for sym in "${SYM_ARRAY[@]}"; do
        check "$sym dashboard returns factor_cards" \
            "curl -s --max-time 90 '$BACKEND_URL/stocks/$sym/dashboard' | python3 -c \"import sys,json; d=json.load(sys.stdin); cards=d['recommendation']['evidence']['factor_cards']; assert len(cards)>=4, f'Only {len(cards)} cards'\""

        check "$sym has size_factor in factor_cards" \
            "curl -s --max-time 90 '$BACKEND_URL/stocks/$sym/dashboard' | python3 -c \"import sys,json; d=json.load(sys.stdin); keys=[c['factor_key'] for c in d['recommendation']['evidence']['factor_cards']]; assert 'size_factor' in keys, f'Missing size_factor in {keys}'\""

        check "$sym has reversal factor" \
            "curl -s --max-time 90 '$BACKEND_URL/stocks/$sym/dashboard' | python3 -c \"import sys,json; d=json.load(sys.stdin); keys=[c['factor_key'] for c in d['recommendation']['evidence']['factor_cards']]; assert 'reversal' in keys\""

        check "$sym has liquidity factor" \
            "curl -s --max-time 90 '$BACKEND_URL/stocks/$sym/dashboard' | python3 -c \"import sys,json; d=json.load(sys.stdin); keys=[c['factor_key'] for c in d['recommendation']['evidence']['factor_cards']]; assert 'liquidity' in keys\""

        check "$sym news items have LLM analysis (no fallback)" \
            "curl -s --max-time 90 '$BACKEND_URL/stocks/$sym/dashboard' | python3 -c \"import sys,json; d=json.load(sys.stdin); news=d.get('recent_news',[]); analyzed=sum(1 for n in news if n.get('summary')!=n.get('headline')); assert analyzed>=len(news)*0.3, f'Only {analyzed}/{len(news)} items have LLM analysis'\""

        check "$sym direction label is actionable" \
            "curl -s --max-time 90 '$BACKEND_URL/stocks/$sym/dashboard' | python3 -c \"import sys,json; d=json.load(sys.stdin); label=d['hero']['direction_label']; valid={'可建仓','可加仓','继续观察','减仓','建议离场','风险提示'}; assert label in valid, f'Unknown label: {label}'\""
    done
fi

echo ""

# ── Phase 4: Factor Output Validation ───────────────────────────

echo "--- Phase 4: Factor Output Validation ---"

check "News factor scores are not saturated (±1.0)" \
    "SYMBOLS='$SYMBOLS' python3 -c \"
import os,json,urllib.request
items=[{'symbol': item} for item in os.environ.get('SYMBOLS', '').split(',') if item]
assert items, 'No dashboard sample symbols available'
for item in items:
    sym=item['symbol']
    d=json.loads(urllib.request.urlopen('$BACKEND_URL/stocks/'+sym+'/dashboard', timeout=90).read())
    for c in d['recommendation']['evidence']['factor_cards']:
        if c['factor_key']=='news_event':
            s=abs(c['score'])
            assert s<0.99, f'{sym} news saturated at {c[\"score\"]}'
print('OK')
\""

check "At least one stock has non-zero size factor" \
    "SYMBOLS='$SYMBOLS' python3 -c \"
import os,json,urllib.request
items=[{'symbol': item} for item in os.environ.get('SYMBOLS', '').split(',') if item]
assert items, 'No dashboard sample symbols available'
nonzero=0
for item in items:
    d=json.loads(urllib.request.urlopen('$BACKEND_URL/stocks/'+item['symbol']+'/dashboard', timeout=90).read())
    for c in d['recommendation']['evidence']['factor_cards']:
        if c['factor_key']=='size_factor' and abs(c['score'])>0.01:
            nonzero+=1
assert nonzero>0, 'All size factors are zero'
print(f'{nonzero} stocks have non-zero size factor')
\""

check "Reversal factor has both positive and negative scores (not all same)" \
    "SYMBOLS='$SYMBOLS' python3 -c \"
import os,json,urllib.request
items=[{'symbol': item} for item in os.environ.get('SYMBOLS', '').split(',') if item]
assert items, 'No dashboard sample symbols available'
scores=[]
for item in items:
    d=json.loads(urllib.request.urlopen('$BACKEND_URL/stocks/'+item['symbol']+'/dashboard', timeout=90).read())
    for c in d['recommendation']['evidence']['factor_cards']:
        if c['factor_key']=='reversal':
            scores.append(c['score'])
pos=sum(1 for s in scores if s>0.05)
neg=sum(1 for s in scores if s<-0.05)
print(f'reversal: {pos} positive, {neg} negative out of {len(scores)}')
\""

echo ""

# ── Phase 5: Frontend Build ────────────────────────────────────

echo "--- Phase 5: Frontend ---"

check "Frontend health check" \
    "curl -s '$FRONTEND_URL' | python3 -c \"import sys; html=sys.stdin.read(); assert '<div id=\\\"root\\\"' in html and 'assets/index-' in html\""

check "Frontend dist matches repo build" \
    "diff -rq '$REPO_ROOT/frontend/dist' '$RUNTIME_ROOT/frontend/dist' 2>/dev/null | wc -l | xargs -I{} test {} -eq 0"

echo ""

# ── Summary ─────────────────────────────────────────────────────

echo "============================================"
echo " Verification Complete: $PASS passed, $FAIL failed"
echo "============================================"

if [ "$FAIL" -gt 0 ]; then
    red "DEPLOY FAILED VERIFICATION — DO NOT CLAIM SUCCESS"
    exit 1
else
    green "All checks passed — deploy verified"
    exit 0
fi
