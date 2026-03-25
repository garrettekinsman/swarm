#!/usr/bin/env python3
"""
swarm-viz.py — EldrChat iOS Parallel Swarm Visualizer

Tails the latest ios-swarm-*.log and renders a live ASCII dashboard.

Usage:
  python3 swarm-viz.py                   # auto-find latest log
  python3 swarm-viz.py path/to/file.log  # explicit log
  python3 swarm-viz.py --once            # print once and exit (no live refresh)
  python3 swarm-viz.py --serve 8888      # HTTP server with SSE live updates
  python3 swarm-viz.py --serve 8888 --host 127.0.0.1  # bind to specific interface
"""

import sys
import os
import re
import time
import glob
import json
import queue
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

# ── Config ─────────────────────────────────────────────────────────────────────
LOG_GLOB    = str(Path(__file__).parent / "ios-swarm-*.log")
REFRESH_HZ  = 2          # screen redraws per second
CODER_NAMES = [
    ("ContentView",     "local→OR", "Mei"),
    ("ChannelListView", "OpenRouter", "Mei"),
    ("ChatView",        "OpenRouter", "Mei"),
    ("LoginView",       "OpenRouter", "Mei"),
    ("SettingsView",    "OpenRouter", "Mei"),
    ("MessageBubble",   "OpenRouter", "Vera"),
    ("InputBar",        "OpenRouter", "Vera"),
    ("ConversationRow", "OpenRouter", "Vera"),
    ("KeyManager",      "OpenRouter", "Vera"),
    ("NostrClient",     "OpenRouter", "Vera"),
]

# ── ANSI ───────────────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
RED    = "\033[31m"
PURPLE = "\033[35m"
CLEAR  = "\033[2J\033[H"


def col(text, code): return f"{code}{text}{RESET}"


# ── Log parser ─────────────────────────────────────────────────────────────────

@dataclass
class SwarmState:
    started: bool = False
    iteration: int = 0
    max_iter: int = 3
    confidence: int = 0
    next_action: str = "iterate"
    opus_stage: str = "waiting"
    garro_design: str = "waiting"
    coders: List[str] = None
    coder_models: List[str] = None
    vera_stage: str = "waiting"
    garro_review: str = "waiting"
    final_stage: str = "waiting"
    files_written: List[str] = None
    issues: List[str] = None
    vera_score: int = 0
    errors: List[str] = None
    last_line: str = ""
    elapsed_s: int = 0
    start_ts: Optional[float] = None
    last_activity: Optional[str] = None

    def __post_init__(self):
        if self.coders is None:
            self.coders = ["waiting"] * 10
        if self.coder_models is None:
            self.coder_models = [""] * 10
        if self.files_written is None:
            self.files_written = []
        if self.issues is None:
            self.issues = []
        if self.errors is None:
            self.errors = []

    def to_dict(self) -> dict:
        return asdict(self)


def parse_log(path: str) -> SwarmState:
    s = SwarmState()
    try:
        lines = Path(path).read_text(errors="replace").splitlines()
    except Exception:
        return s

    mtime = Path(path).stat().st_mtime
    if lines:
        s.started = True
        s.last_activity = datetime.fromtimestamp(mtime).strftime("%H:%M:%S")

    for line in lines:
        s.last_line = line.strip()

        # Startup
        if "EldrChat iOS Parallel Swarm" in line:
            s.start_ts = mtime - 60  # approximate

        # Iteration
        m = re.search(r"OPUS — Iteration (\d+)/(\d+)", line)
        if m:
            s.iteration  = int(m.group(1))
            s.max_iter   = int(m.group(2))
            s.opus_stage = "active"
            s.garro_design = "waiting"
            s.vera_stage   = "waiting"
            s.garro_review = "waiting"

        if "Terminating" in line or "next_action.*done" in line:
            s.opus_stage   = "done"
            s.next_action  = "done"

        # GARRO design
        if "GARRO — Generating design spec" in line:
            s.garro_design = "active"
        if "Design spec:" in line and "chars" in line:
            s.garro_design = "done"
        if "Design spec cached" in line:
            s.garro_design = "done"
        if "GARRO error" in line:
            s.garro_design = "done"   # fell back to default

        # Coders — spawning
        if "Spawning" in line and "parallel qwen" in line:
            s.coders = ["active"] * 10

        # Individual coder done
        for i, (name, _, _) in enumerate(CODER_NAMES):
            if f"[{name}.swift] done via" in line:
                s.coders[i] = "done"
                m2 = re.search(r"done via (.+)$", line)
                if m2:
                    s.coder_models[i] = m2.group(1).strip()
            if f"[{name}.swift] exception" in line or f"[{name}.swift] All tiers failed" in line:
                s.coders[i] = "error"

        # Files written
        m = re.search(r"Wrote .+/([\w.]+\.swift)", line)
        if m and m.group(1) not in s.files_written:
            s.files_written.append(m.group(1))

        # Vera
        if "VERA — Security audit" in line:
            s.vera_stage = "active"
        if "Vera audit:" in line and "chars" in line:
            s.vera_stage = "done"
        m = re.search(r"Vera confidence estimate:\s*(\d+)", line)
        if m:
            s.vera_score = int(m.group(1))

        # GARRO review
        if "GARRO — Code review" in line:
            s.garro_review = "active"
        if "Confidence:" in line:
            m2 = re.search(r"Confidence:\s*(\d+)", line)
            if m2:
                s.confidence   = int(m2.group(1))
                s.garro_review = "done"
        if "GARRO review error" in line or "GARRO review timed out" in line:
            s.garro_review = "done"

        # Issues
        if "Issues (" in line:
            raw = re.search(r"\[(.+)\]", line)
            if raw:
                s.issues = [x.strip().strip("'\"") for x in raw.group(1).split(",")]

        # Final
        if "PIPELINE COMPLETE" in line:
            s.final_stage  = "done"
            s.opus_stage   = "done"
            s.next_action  = "done"

        # Errors
        if "❌" in line and "ANTHROPIC_API_KEY" not in line:
            s.errors.append(line.strip())

    return s


# ── Renderer (TTY mode) ────────────────────────────────────────────────────────

def stage_icon(st: str) -> str:
    return {
        "waiting": col("○ waiting ", DIM),
        "active":  col("▶ running ", YELLOW),
        "done":    col("✓ done    ", GREEN),
        "error":   col("✗ error   ", RED),
    }.get(st, st)


def bar(filled: int, total: int, width: int = 10) -> str:
    f = round(width * filled / max(total, 1))
    return col("█" * f, CYAN) + col("░" * (width - f), DIM)


def render(s: SwarmState, log_path: str) -> str:
    now = datetime.now().strftime("%H:%M:%S")
    fname = Path(log_path).name

    files_done = len(s.files_written)
    coders_done = s.coders.count("done")
    coders_err  = s.coders.count("error")
    coders_act  = s.coders.count("active")

    lines = []
    W = 58
    div = "─" * W

    lines.append(col("┌" + "─" * W + "┐", DIM))
    lines.append(col("│", DIM) + col(f"  EldrChat iOS Swarm Visualizer  {now}", BOLD).center(W + 9) + col("│", DIM))
    lines.append(col("│", DIM) + col(f"  {fname}", DIM).ljust(W + 4) + col("│", DIM))
    lines.append(col("└" + "─" * W + "┘", DIM))
    lines.append("")

    # Orchestrator
    iter_bar = bar(s.iteration, s.max_iter)
    lines.append(f"  ORCHESTRATOR")
    lines.append(f"  🧠 OPUS (claude-opus-4-6)  {stage_icon(s.opus_stage)}")
    lines.append(f"     iter {s.iteration}/{s.max_iter}  {iter_bar}  confidence {col(str(s.confidence)+'%', CYAN)}")
    lines.append("")

    # Designer
    lines.append(f"  DESIGNER")
    lines.append(f"  🎨 GARRO (kimi-k2.5)       {stage_icon(s.garro_design)}")
    lines.append("")

    # Coders
    lines.append(f"  CODERS  ({coders_done}/10 done  {coders_act} active  {coders_err} err)")
    lines.append(f"  {'─'*54}")
    for i, (name, route, persona) in enumerate(CODER_NAMES):
        st   = s.coders[i]
        icon = stage_icon(st)
        model_hint = ""
        if s.coder_models[i]:
            m = s.coder_models[i]
            if "local" in m:     model_hint = col(" [local]", GREEN)
            elif "fallback" in m: model_hint = col(" [fallback]", RED)
            else:                 model_hint = col(" [OR]", CYAN)
        elif st == "active":
            model_hint = col(f" [{route}]", YELLOW)

        persona_tag = col(f"{persona:4}", PURPLE)
        lines.append(f"  [{i:2d}] {name:<18} {icon}{persona_tag}{model_hint}")

    lines.append("")

    # Auditor + Reviewer
    lines.append(f"  AUDITOR")
    vera_score = f"  (est. {s.vera_score}%)" if s.vera_score else ""
    lines.append(f"  🔒 VERA (claude-sonnet)    {stage_icon(s.vera_stage)}{col(vera_score, DIM)}")
    lines.append("")
    lines.append(f"  REVIEWER")
    lines.append(f"  🎨 GARRO review (kimi)     {stage_icon(s.garro_review)}")
    lines.append("")

    # Files
    files_bar = bar(files_done, 10)
    lines.append(f"  FILES  {files_bar}  {files_done}/10")
    if s.files_written:
        for f in s.files_written:
            lines.append(f"    {col('✓', GREEN)} {f}")
    missing = [n+".swift" for n, _, _ in CODER_NAMES if n+".swift" not in s.files_written]
    if missing and files_done < 10:
        for f in missing[:3]:
            lines.append(f"    {col('○', DIM)} {f}")
        if len(missing) > 3:
            lines.append(f"    {col(f'○ ...+{len(missing)-3} more', DIM)}")
    lines.append("")

    # Issues
    if s.issues:
        lines.append(f"  TOP ISSUES")
        for iss in s.issues[:4]:
            lines.append(f"    {col('•', YELLOW)} {iss[:52]}")
        lines.append("")

    # Errors
    if s.errors:
        lines.append(col(f"  ERRORS ({len(s.errors)})", RED))
        for e in s.errors[-2:]:
            lines.append(f"    {col(e[:54], RED)}")
        lines.append("")

    # Status bar
    if s.final_stage == "done":
        status = col(f"  ✅ COMPLETE — confidence {s.confidence}%  ({files_done}/10 files)", GREEN)
    elif not s.started:
        status = col("  ⏳ Waiting for pipeline to start...", DIM)
    else:
        status = col(f"  ▶  Running — last: {s.last_line[:44]}", YELLOW)
    lines.append(status)
    lines.append("")

    return "\n".join(lines)


# ── HTTP Server Mode ───────────────────────────────────────────────────────────

# Global state for server mode
swarm_tracker: Dict[str, SwarmState] = {}  # path -> SwarmState
swarm_mtimes: Dict[str, float] = {}        # path -> mtime
sse_subscribers: List[queue.Queue] = []
completed_swarms: Dict[str, float] = {}    # path -> completion_time (for fade-out)
server_running = False

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Swarm Visualizer</title>
    <style>
        :root {
            --bg: #0d1117;
            --card-bg: #161b22;
            --border: #30363d;
            --text: #c9d1d9;
            --dim: #484f58;
            --green: #3fb950;
            --yellow: #d29922;
            --red: #f85149;
            --cyan: #58a6ff;
            --purple: #bc8cff;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: var(--bg);
            color: var(--text);
            font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Mono', monospace;
            font-size: 13px;
            line-height: 1.5;
            padding: 20px;
            min-height: 100vh;
        }
        h1 {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 20px;
            color: var(--cyan);
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid var(--border);
        }
        .status {
            color: var(--dim);
            font-size: 11px;
        }
        .status.connected { color: var(--green); }
        .status.disconnected { color: var(--red); }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
            gap: 16px;
        }
        .card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
            transition: opacity 0.5s, border-color 0.3s;
        }
        .card.complete {
            border-color: var(--green);
            border-width: 2px;
        }
        .card.fading {
            opacity: 0.3;
        }
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--border);
        }
        .swarm-id {
            font-weight: 600;
            color: var(--cyan);
            font-size: 12px;
        }
        .badge {
            font-size: 10px;
            padding: 2px 8px;
            border-radius: 4px;
            background: var(--green);
            color: var(--bg);
            font-weight: 600;
        }
        .section {
            margin-bottom: 12px;
        }
        .section-title {
            font-size: 10px;
            text-transform: uppercase;
            color: var(--dim);
            margin-bottom: 4px;
            letter-spacing: 0.5px;
        }
        .row {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 2px;
        }
        .icon { width: 14px; text-align: center; }
        .stage {
            font-size: 11px;
            padding: 1px 6px;
            border-radius: 3px;
        }
        .stage.waiting { color: var(--dim); }
        .stage.active { color: var(--yellow); }
        .stage.done { color: var(--green); }
        .stage.error { color: var(--red); }
        .branch-grid {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 4px;
            margin-top: 6px;
        }
        .branch {
            width: 100%;
            aspect-ratio: 1;
            border-radius: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            background: var(--bg);
            border: 1px solid var(--border);
        }
        .branch.waiting { color: var(--dim); }
        .branch.active { 
            color: var(--yellow); 
            animation: pulse 1s infinite;
        }
        .branch.done { color: var(--green); background: rgba(63, 185, 80, 0.1); }
        .branch.error { color: var(--red); background: rgba(248, 81, 73, 0.1); }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .progress-bar {
            height: 6px;
            background: var(--bg);
            border-radius: 3px;
            overflow: hidden;
            margin-top: 4px;
        }
        .progress-fill {
            height: 100%;
            background: var(--cyan);
            transition: width 0.3s;
        }
        .metrics {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
            margin-top: 8px;
        }
        .metric {
            text-align: center;
            padding: 6px;
            background: var(--bg);
            border-radius: 4px;
        }
        .metric-value {
            font-size: 16px;
            font-weight: 600;
            color: var(--cyan);
        }
        .metric-label {
            font-size: 9px;
            color: var(--dim);
            text-transform: uppercase;
        }
        .last-activity {
            font-size: 10px;
            color: var(--dim);
            margin-top: 8px;
            text-align: right;
        }
        .idle-state {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 200px;
            color: var(--dim);
            animation: idle-pulse 2s infinite;
        }
        .idle-state .icon { font-size: 32px; margin-bottom: 12px; }
        @keyframes idle-pulse {
            0%, 100% { opacity: 0.5; }
            50% { opacity: 1; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🐝 Swarm Visualizer</h1>
        <div class="status disconnected" id="status">Connecting...</div>
    </div>
    <div class="grid" id="grid">
        <div class="idle-state" id="idle">
            <div class="icon">⏳</div>
            <div>Waiting for swarm...</div>
        </div>
    </div>

    <script>
        const grid = document.getElementById('grid');
        const idle = document.getElementById('idle');
        const statusEl = document.getElementById('status');
        const swarms = new Map();
        const fadeTimers = new Map();

        function getStageSymbol(stage) {
            switch(stage) {
                case 'waiting': return '○';
                case 'active': return '▶';
                case 'done': return '✓';
                case 'error': return '✗';
                default: return '?';
            }
        }

        function createCard(id, state) {
            const card = document.createElement('div');
            card.className = 'card';
            card.id = `card-${btoa(id).replace(/=/g, '')}`;
            card.innerHTML = renderCardContent(id, state);
            return card;
        }

        function renderCardContent(id, state) {
            const fname = id.split('/').pop();
            const codersDone = state.coders.filter(c => c === 'done').length;
            const codersErr = state.coders.filter(c => c === 'error').length;
            const codersActive = state.coders.filter(c => c === 'active').length;
            const filesDone = state.files_written.length;
            const iterPct = (state.iteration / state.max_iter) * 100;
            const isComplete = state.final_stage === 'done';

            return `
                <div class="card-header">
                    <span class="swarm-id">${fname}</span>
                    ${isComplete ? '<span class="badge">✅ Complete</span>' : ''}
                </div>
                
                <div class="section">
                    <div class="section-title">Iteration</div>
                    <div>${state.iteration}/${state.max_iter}</div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${iterPct}%"></div>
                    </div>
                </div>

                <div class="section">
                    <div class="section-title">Pipeline Stages</div>
                    <div class="row">
                        <span class="icon">🧠</span>
                        <span>OPUS</span>
                        <span class="stage ${state.opus_stage}">${getStageSymbol(state.opus_stage)}</span>
                    </div>
                    <div class="row">
                        <span class="icon">🎨</span>
                        <span>GARRO Design</span>
                        <span class="stage ${state.garro_design}">${getStageSymbol(state.garro_design)}</span>
                    </div>
                    <div class="row">
                        <span class="icon">🔒</span>
                        <span>VERA Audit</span>
                        <span class="stage ${state.vera_stage}">${getStageSymbol(state.vera_stage)}</span>
                    </div>
                    <div class="row">
                        <span class="icon">🎨</span>
                        <span>GARRO Review</span>
                        <span class="stage ${state.garro_review}">${getStageSymbol(state.garro_review)}</span>
                    </div>
                </div>

                <div class="section">
                    <div class="section-title">Coders (${codersDone}/10 done, ${codersActive} active, ${codersErr} err)</div>
                    <div class="branch-grid">
                        ${state.coders.map((c, i) => `<div class="branch ${c}" title="Coder ${i}">${getStageSymbol(c)}</div>`).join('')}
                    </div>
                </div>

                <div class="metrics">
                    <div class="metric">
                        <div class="metric-value">${filesDone}/10</div>
                        <div class="metric-label">Files</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value">${state.confidence}%</div>
                        <div class="metric-label">Confidence</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value">${state.vera_score || '-'}%</div>
                        <div class="metric-label">Vera Score</div>
                    </div>
                </div>

                ${state.last_activity ? `<div class="last-activity">Last activity: ${state.last_activity}</div>` : ''}
            `;
        }

        function updateCard(id, state) {
            const cardId = `card-${btoa(id).replace(/=/g, '')}`;
            let card = document.getElementById(cardId);
            
            if (!card) {
                card = createCard(id, state);
                grid.appendChild(card);
            } else {
                card.innerHTML = renderCardContent(id, state);
            }

            if (state.final_stage === 'done') {
                card.classList.add('complete');
            }

            swarms.set(id, state);
            updateIdle();
        }

        function removeCard(id) {
            const cardId = `card-${btoa(id).replace(/=/g, '')}`;
            const card = document.getElementById(cardId);
            if (card) {
                card.classList.add('fading');
                setTimeout(() => card.remove(), 500);
            }
            swarms.delete(id);
            if (fadeTimers.has(id)) {
                clearTimeout(fadeTimers.get(id));
                fadeTimers.delete(id);
            }
            updateIdle();
        }

        function scheduleRemoval(id, delayMs) {
            if (fadeTimers.has(id)) {
                clearTimeout(fadeTimers.get(id));
            }
            fadeTimers.set(id, setTimeout(() => removeCard(id), delayMs));
        }

        function updateIdle() {
            idle.style.display = swarms.size === 0 ? 'flex' : 'none';
        }

        function connect() {
            const es = new EventSource('/events');

            es.onopen = () => {
                statusEl.textContent = 'Connected';
                statusEl.className = 'status connected';
            };

            es.onerror = () => {
                statusEl.textContent = 'Disconnected';
                statusEl.className = 'status disconnected';
                setTimeout(connect, 3000);
            };

            es.addEventListener('swarm_added', e => {
                const data = JSON.parse(e.data);
                updateCard(data.id, data.state);
            });

            es.addEventListener('swarm_updated', e => {
                const data = JSON.parse(e.data);
                updateCard(data.id, data.state);
            });

            es.addEventListener('swarm_complete', e => {
                const data = JSON.parse(e.data);
                updateCard(data.id, data.state);
                scheduleRemoval(data.id, 30000);
            });

            es.addEventListener('swarm_removed', e => {
                const data = JSON.parse(e.data);
                removeCard(data.id);
            });

            // Initial state
            fetch('/api/swarms')
                .then(r => r.json())
                .then(data => {
                    for (const [id, state] of Object.entries(data)) {
                        updateCard(id, state);
                    }
                    updateIdle();
                });
        }

        connect();
    </script>
</body>
</html>
"""


def broadcast(event_type: str, data: dict):
    """Push an SSE event to all connected clients."""
    msg = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    dead_subscribers = []
    for q in sse_subscribers[:]:
        try:
            q.put_nowait(msg)
        except:
            dead_subscribers.append(q)
    for q in dead_subscribers:
        if q in sse_subscribers:
            sse_subscribers.remove(q)


def watch_logs():
    """Background thread: poll log files, broadcast changes."""
    global swarm_tracker, swarm_mtimes, completed_swarms

    while server_running:
        try:
            current_files = glob.glob(LOG_GLOB)
            current = {}
            for p in current_files:
                try:
                    current[p] = os.path.getmtime(p)
                except OSError:
                    pass

            now = time.time()

            # Check for new/updated files
            for p, mtime in current.items():
                state = parse_log(p)
                if p not in swarm_mtimes:
                    # New swarm
                    swarm_tracker[p] = state
                    swarm_mtimes[p] = mtime
                    broadcast("swarm_added", {"id": p, "state": state.to_dict()})
                elif mtime != swarm_mtimes[p]:
                    # Updated swarm
                    swarm_tracker[p] = state
                    swarm_mtimes[p] = mtime
                    if state.final_stage == "done" and p not in completed_swarms:
                        completed_swarms[p] = now
                        broadcast("swarm_complete", {"id": p, "state": state.to_dict()})
                    else:
                        broadcast("swarm_updated", {"id": p, "state": state.to_dict()})

            # Check for removed files
            removed = set(swarm_mtimes.keys()) - set(current.keys())
            for p in removed:
                del swarm_mtimes[p]
                if p in swarm_tracker:
                    del swarm_tracker[p]
                if p in completed_swarms:
                    del completed_swarms[p]
                broadcast("swarm_removed", {"id": p})

        except Exception as e:
            print(f"[watcher] error: {e}")

        time.sleep(1)


class SwarmHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the swarm visualizer server."""

    def log_message(self, format, *args):
        # Suppress default access logging
        pass

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode())

        elif path == "/api/swarms":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            data = {k: v.to_dict() for k, v in swarm_tracker.items()}
            self.wfile.write(json.dumps(data).encode())

        elif path.startswith("/api/swarm/"):
            swarm_id = path[11:]  # Remove /api/swarm/
            if swarm_id in swarm_tracker:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(swarm_tracker[swarm_id].to_dict()).encode())
            else:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "swarm not found"}).encode())

        elif path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_cors_headers()
            self.end_headers()

            q = queue.Queue()
            sse_subscribers.append(q)
            
            try:
                # Send initial heartbeat
                self.wfile.write(b": heartbeat\n\n")
                self.wfile.flush()

                while server_running:
                    try:
                        msg = q.get(timeout=15)
                        self.wfile.write(msg.encode())
                        self.wfile.flush()
                    except queue.Empty:
                        # Send keepalive
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                if q in sse_subscribers:
                    sse_subscribers.remove(q)

        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not Found")


def get_tailscale_ip() -> Optional[str]:
    """Try to find the Tailscale IP (100.x.x.x)."""
    try:
        # Try ip addr first (Linux)
        result = subprocess.run(
            ["ip", "addr"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                m = re.search(r"inet (100\.\d+\.\d+\.\d+)", line)
                if m:
                    return m.group(1)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    try:
        # Try ifconfig (macOS)
        result = subprocess.run(
            ["ifconfig"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                m = re.search(r"inet (100\.\d+\.\d+\.\d+)", line)
                if m:
                    return m.group(1)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


def run_server(host: str, port: int):
    """Start the HTTP server with SSE support."""
    global server_running
    server_running = True

    # Start file watcher thread
    watcher_thread = threading.Thread(target=watch_logs, daemon=True)
    watcher_thread.start()

    # Get Tailscale IP for display
    ts_ip = get_tailscale_ip()

    print(f"🐝 Swarm Visualizer Server")
    print(f"   Local:     http://{host}:{port}/")
    if ts_ip:
        print(f"   Tailscale: http://{ts_ip}:{port}/")
    print(f"   Watching:  {LOG_GLOB}")
    print(f"   (Ctrl-C to stop)\n")

    server = HTTPServer((host, port), SwarmHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nStopping server...")
        server_running = False
        server.shutdown()


# ── Main ───────────────────────────────────────────────────────────────────────

def find_latest_log(pattern: str) -> str | None:
    logs = sorted(glob.glob(pattern), key=os.path.getmtime)
    return logs[-1] if logs else None


def main():
    args = sys.argv[1:]
    
    # Parse --serve mode
    if "--serve" in args:
        serve_idx = args.index("--serve")
        port = 8888
        if serve_idx + 1 < len(args) and not args[serve_idx + 1].startswith("--"):
            try:
                port = int(args[serve_idx + 1])
            except ValueError:
                print(f"Invalid port: {args[serve_idx + 1]}")
                sys.exit(1)
        
        # Parse --host
        host = "0.0.0.0"
        if "--host" in args:
            host_idx = args.index("--host")
            if host_idx + 1 < len(args):
                host = args[host_idx + 1]
        
        run_server(host, port)
        return

    # Original TTY mode
    once = "--once" in args
    args = [a for a in args if not a.startswith("--")]
    log_path = args[0] if args else find_latest_log(LOG_GLOB)

    if not log_path:
        print(f"No log found matching: {LOG_GLOB}")
        sys.exit(1)

    print(f"Watching: {log_path}")
    if not once:
        print("(Ctrl-C to exit)\n")
        time.sleep(0.5)

    try:
        while True:
            state = parse_log(log_path)
            screen = render(state, log_path)
            if once:
                print(screen)
                break
            else:
                sys.stdout.write(CLEAR + screen)
                sys.stdout.flush()
                if state.final_stage == "done":
                    print("\n✅ Pipeline complete. Exiting.\n")
                    break
                time.sleep(1.0 / REFRESH_HZ)
    except KeyboardInterrupt:
        print("\n\nStopped.")


if __name__ == "__main__":
    main()
