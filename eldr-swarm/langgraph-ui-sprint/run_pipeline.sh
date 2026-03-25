#!/bin/bash
# EldrChat LangGraph UI Pipeline — runner with live logging + metrics
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$SCRIPT_DIR/pipeline-$(date +%Y%m%d-%H%M%S).log"
METRICS_FILE="$SCRIPT_DIR/pipeline-metrics.json"
PIPELINE="$SCRIPT_DIR/eldrchat_ui_pipeline.py"

echo "🚀 EldrChat LangGraph UI Pipeline"
echo "   Log: $LOG_FILE"
echo "   Started: $(date)"
echo ""

# Capture start time
START_TS=$(date +%s)

# Run pipeline, tee to log file
python3 "$PIPELINE" 2>&1 | tee "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}

END_TS=$(date +%s)
ELAPSED=$((END_TS - START_TS))

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⏱  Elapsed: ${ELAPSED}s"
echo "📋 Exit code: $EXIT_CODE"
echo "📄 Log: $LOG_FILE"

# Write metrics JSON
python3 -c "
import json, time
metrics = {
    'run_timestamp': '$(date -u +%Y-%m-%dT%H:%M:%SZ)',
    'elapsed_seconds': $ELAPSED,
    'exit_code': $EXIT_CODE,
    'log_file': '$LOG_FILE',
    'nodes': {}
}

# Parse log for per-node timing
with open('$LOG_FILE') as f:
    lines = f.readlines()

node_times = {}
current_node = None
node_start = None
start_ts = $START_TS

for i, line in enumerate(lines):
    line = line.strip()
    if 'GARRO: Designing' in line:
        current_node = 'garro_design'
        node_start = start_ts  # approximate
    elif 'Coder: Implementing' in line:
        if current_node:
            node_times[current_node] = {'status': 'done'}
        current_node = 'coder_implement'
    elif 'Build: Writing' in line:
        if current_node:
            node_times[current_node] = {'status': 'done'}
        current_node = 'build_and_screenshot'
    elif 'GARRO: Reviewing' in line:
        if current_node:
            node_times[current_node] = {'status': 'done'}
        current_node = 'garro_review'
    elif 'Writing final report' in line:
        if current_node:
            node_times[current_node] = {'status': 'done'}
        current_node = 'write_report'
    elif 'Pipeline complete' in line:
        if current_node:
            node_times[current_node] = {'status': 'done'}

# Extract success/failure from log
build_success = any('Build succeeded' in l or 'Build status: ✅' in l for l in lines)
report_line = next((l for l in lines if 'REPORT PATH:' in l), None)
report_path = report_line.split('REPORT PATH:')[-1].strip() if report_line else None

metrics['nodes'] = node_times
metrics['build_success'] = build_success
metrics['report_path'] = report_path
metrics['pipeline_success'] = ($EXIT_CODE == 0)

print(json.dumps(metrics, indent=2))
" > "$METRICS_FILE"

echo "📊 Metrics: $METRICS_FILE"
cat "$METRICS_FILE"
