#!/usr/bin/env python3
"""
EldrChat Web Swarm — LangGraph 4-agent pipeline
Builds an EldrChat landing page (HTML/CSS/JS) via multi-agent iteration.

Team:
  GAHO    — Claude Opus 4-6 (orchestrator)
  GARRO   — kimi-k2.5 via OpenRouter (design spec + review)
  CODER   — qwen3-coder via model router → Opus fallback (HTML/CSS/JS)
  VERA    — Claude Sonnet 4-6 (security audit)

Output: projects/eldrchat/langgraph-ui-sprint/web-test/index.html + style.css
"""

import os
import sys
import json
import re
import logging
import pathlib
from pathlib import Path
from datetime import datetime
from typing import TypedDict, Literal

import requests
from anthropic import Anthropic
from langgraph.graph import StateGraph, END

# ── Sanitizer ────────────────────────────────────────────────────────────────
_SANITIZER_PATH = Path("~/.openclaw/workspace/projects/agent-collaboration")
sys.path.insert(0, str(_SANITIZER_PATH))
from sanitizer_v2 import sanitize_text, sanitize_pipeline_field

# ── Paths ─────────────────────────────────────────────────────────────────────
WORKSPACE       = Path("~/.openclaw/workspace/projects/eldrchat")
OUTPUT_DIR      = WORKSPACE / "langgraph-ui-sprint" / "web-test"
LOG_DIR         = WORKSPACE / "langgraph-ui-sprint"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE     = LOG_DIR / f"web-swarm-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
METRICS_FILE = LOG_DIR / "web-swarm-metrics.json"

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE),
    ],
)
log = logging.info

# ── API Keys ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not ANTHROPIC_API_KEY:
    log("❌ ANTHROPIC_API_KEY not set"); sys.exit(1)
if not OPENROUTER_API_KEY:
    log("❌ OPENROUTER_API_KEY not set"); sys.exit(1)

anthropic = Anthropic(api_key=ANTHROPIC_API_KEY)

MAX_ITERATIONS  = 3
CONFIDENCE_GOAL = 80  # %, capped at 85 to prevent premature convergence

# ── State ─────────────────────────────────────────────────────────────────────
class TeamState(TypedDict):
    brief:            str          # product brief fed in at start
    iteration:        int
    next_action:      Literal["iterate", "done"]
    design_spec:      str          # GARRO output
    current_files:    dict         # {filename: content}
    garro_review:     str
    vera_audit:       str
    confidence_score: int
    issues:           list
    coder_model_used: str

# ── Helpers ───────────────────────────────────────────────────────────────────
def call_openrouter(messages: list, model: str = "moonshotai/kimi-k2.5") -> str:
    """Call OpenRouter (GARRO)."""
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://openclaw.ai",
            "X-Title": "EldrChat Web Swarm",
            "Content-Type": "application/json",
        },
        json={"model": model, "messages": messages, "max_tokens": 4096},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def call_model_router(prompt: str) -> tuple[str, str]:
    """
    Try qwen3-coder via model router first, fall back to Opus.
    Returns (content, model_used).
    """
    router_sock = Path(os.path.expanduser("~/.openclaw/data/model-router.sock"))
    if router_sock.exists():
        try:
            import socket, http.client
            conn = http.client.HTTPConnection("localhost")
            conn.sock = socket.socket(socket.AF_UNIX)
            conn.sock.connect(str(router_sock))
            body = json.dumps({"role": "coder", "prompt": prompt, "max_tokens": 4096})
            conn.request("POST", "/dispatch", body, {"Content-Type": "application/json"})
            r = conn.getresponse()
            if r.status == 200:
                data = json.loads(r.read())
                return data.get("result", data.get("content", "")), data.get("model", "router/qwen")
        except Exception as e:
            log(f"   ⚠️  Model router unavailable: {e} — falling back to Opus")

    # Opus fallback
    resp = anthropic.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text, "anthropic/claude-opus-4-6 (fallback)"


def extract_files(text: str) -> dict:
    """
    Parse code blocks from LLM output into {filename: content}.
    Looks for ```html, ```css, ```js patterns with optional filename comment.
    """
    files = {}
    # Pattern: ```[lang] ... ``` with optional // filename or <!-- filename --> header
    pattern = re.compile(
        r"```(\w+)\n(?://\s*([\w./]+)\n|<!--\s*([\w./]+)\s*-->\n)?(.*?)```",
        re.DOTALL,
    )
    for m in pattern.finditer(text):
        lang     = m.group(1).lower()
        fname1   = m.group(2)
        fname2   = m.group(3)
        content  = m.group(4).strip()
        filename = fname1 or fname2
        if not filename:
            ext_map  = {"html": "index.html", "css": "style.css",
                        "js": "main.js", "javascript": "main.js"}
            filename = ext_map.get(lang, f"output.{lang}")
        files[filename] = content

    # Fallback: if nothing parsed, look for entire html block
    if not files:
        m = re.search(r"(<!DOCTYPE html>.*?</html>)", text, re.DOTALL | re.IGNORECASE)
        if m:
            files["index.html"] = m.group(1).strip()

    return files


def write_files(files: dict):
    for fname, content in files.items():
        out = OUTPUT_DIR / fname
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content)
        log(f"   📄 Wrote {out}")


# ── Nodes ─────────────────────────────────────────────────────────────────────

def node_orchestrate(state: TeamState) -> TeamState:
    """GAHO — increment iteration, sanitize brief on iter 1, decide termination."""
    state["iteration"] += 1
    it = state["iteration"]
    log(f"\n{'='*60}")
    log(f"🔄 GAHO — Iteration {it}/{MAX_ITERATIONS}")

    if it == 1:
        cleaned = sanitize_text(state["brief"])
        state["brief"] = cleaned

    score = state.get("confidence_score", 0)
    if score >= CONFIDENCE_GOAL or it > MAX_ITERATIONS:
        state["next_action"] = "done"
        log(f"   ✅ Done — confidence={score}%  iterations={it}")
    else:
        state["next_action"] = "iterate"

    return state


def node_garro_design(state: TeamState) -> TeamState:
    """GARRO — generate design spec (iteration 1 only)."""
    if state["iteration"] > 1:
        log("\n🎨 GARRO — Design spec cached, skipping redesign")
        return state

    log("\n🎨 GARRO — Generating design spec")
    prompt = f"""You are GARRO, a senior UI/UX designer. Create a detailed web design spec for:

{state['brief']}

Output a clear spec covering:
1. Color palette (hex values)
2. Typography (fonts, sizes, weights)
3. Layout structure (sections, grid)
4. Key components (nav, hero, features, CTA, footer)
5. Tone and visual style
6. Any copy/content direction

Be specific — a developer will implement this exactly."""

    raw = call_openrouter([{"role": "user", "content": prompt}])
    clean = sanitize_pipeline_field("design_spec", raw)
    state["design_spec"] = clean
    log(f"   ✅ Design spec ({len(clean)} chars)")
    return state


def node_coder(state: TeamState) -> TeamState:
    """CODER — implement HTML/CSS/JS from design spec."""
    log("\n💻 CODER — Building web files")
    issues_str = "\n".join(f"- {i}" for i in state.get("issues", [])) or "None yet."
    prompt = f"""You are a senior frontend developer. Build a complete, polished landing page for EldrChat.

## Design Spec
{state['design_spec']}

## Previous Issues to Fix
{issues_str}

## Requirements
- Single-page HTML landing page
- Separate CSS file (style.css)
- Mobile-responsive
- No external dependencies except Google Fonts (optional) and a CDN icon set
- Clean, modern design matching the spec exactly
- Real placeholder content (not Lorem Ipsum) — use EldrChat-appropriate copy
- No backend, no JS frameworks — vanilla only

Output ONLY code blocks:
```html
<!-- index.html -->
[full HTML file]
```

```css
/* style.css */
[full CSS file]
```"""

    content, model = call_model_router(prompt)
    clean = sanitize_pipeline_field("current_code", content)
    files = extract_files(clean)

    if not files:
        log("   ⚠️  No files parsed from coder output — dumping raw to debug.txt")
        (LOG_DIR / "coder-debug.txt").write_text(clean)
    else:
        state["current_files"] = files
        write_files(files)

    state["coder_model_used"] = model
    log(f"   ✅ Coder done — model={model}  files={list(files.keys())}")
    return state


def node_vera_audit(state: TeamState) -> TeamState:
    """VERA — security audit of generated code."""
    log("\n🔒 VERA — Security audit")
    if not state.get("current_files"):
        log("   ⚠️  No files to audit")
        state["vera_audit"] = "No files provided."
        return state

    combined = "\n\n".join(
        f"=== {fname} ===\n{content}"
        for fname, content in state["current_files"].items()
    )
    resp = anthropic.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": f"""You are Vera, a security auditor. Review this web code:

{combined}

Check for:
- Hardcoded secrets or API keys
- Inline event handlers that could enable XSS
- Dangerous external script loads
- Data URI abuse
- Any other security red flags

Output a brief audit report (3-5 lines max). Rate risk: LOW / MEDIUM / HIGH."""}],
    )
    clean = sanitize_pipeline_field("audit_issues", resp.content[0].text)
    state["vera_audit"] = clean
    log(f"   ✅ Vera audit done — {clean[:120]}…")
    return state


def node_garro_review(state: TeamState) -> TeamState:
    """GARRO — review built output against spec, score confidence."""
    log("\n🔍 GARRO — Reviewing output")
    if not state.get("current_files"):
        state["garro_review"] = "No files to review."
        state["confidence_score"] = 0
        return state

    combined = "\n\n".join(
        f"=== {fname} ===\n{content}"
        for fname, content in state["current_files"].items()
    )
    prompt = f"""You are GARRO reviewing built web code against your design spec.

## Your Original Design Spec
{state['design_spec']}

## Built Code
{combined}

## Vera Security Audit
{state.get('vera_audit', 'N/A')}

Review the code against the spec. Output:
1. CONFIDENCE: [0-85]%  (cap at 85 — never claim 100%)
2. ISSUES: bullet list of specific problems (max 5)
3. VERDICT: one sentence summary

Be honest and precise."""

    raw = call_openrouter([{"role": "user", "content": prompt}])
    clean = sanitize_pipeline_field("iteration_plan", raw)
    state["garro_review"] = clean

    # Extract confidence score
    m = re.search(r"CONFIDENCE:\s*(\d+)%?", clean, re.IGNORECASE)
    score = min(int(m.group(1)), 85) if m else 50
    state["confidence_score"] = score

    # Extract issues
    issues = []
    for line in clean.splitlines():
        line = line.strip()
        if line.startswith(("-", "•", "*")) and len(line) > 5:
            issues.append(line.lstrip("-•* "))
    state["issues"] = issues[:5]

    log(f"   ✅ Review — confidence={score}%  issues={len(issues)}")
    return state


# ── Graph ──────────────────────────────────────────────────────────────────────

def should_continue(state: TeamState) -> Literal["iterate", "done"]:
    return state["next_action"]


def build_graph() -> StateGraph:
    g = StateGraph(TeamState)

    g.add_node("orchestrate",   node_orchestrate)
    g.add_node("garro_design",  node_garro_design)
    g.add_node("coder",         node_coder)
    g.add_node("vera_audit",    node_vera_audit)
    g.add_node("garro_review",  node_garro_review)

    g.set_entry_point("orchestrate")
    g.add_conditional_edges("orchestrate", should_continue, {
        "iterate": "garro_design",
        "done":    END,
    })
    g.add_edge("garro_design", "coder")
    g.add_edge("coder",        "vera_audit")
    g.add_edge("vera_audit",   "garro_review")
    g.add_edge("garro_review", "orchestrate")

    return g.compile()


# ── Main ───────────────────────────────────────────────────────────────────────

BRIEF = """
EldrChat is a privacy-first, Nostr-based messaging app.
Key selling points:
- End-to-end encrypted by default (NIP-17)
- No central server — runs on the Nostr protocol
- Open source, self-sovereign identity
- Beautiful, minimal UI
- Designed for people who care about digital privacy

Build a landing page that:
- Sells EldrChat to privacy-conscious users
- Communicates "fast, private, beautiful"
- Has a hero section with tagline + download CTA
- Features section (3-4 key features)
- Brief "how it works" section
- Footer with GitHub link placeholder
"""


def main():
    log("🚀 EldrChat Web Swarm")
    log(f"   Output: {OUTPUT_DIR}")
    log(f"   Log:    {LOG_FILE}\n")

    initial_state: TeamState = {
        "brief":            BRIEF.strip(),
        "iteration":        0,
        "next_action":      "iterate",
        "design_spec":      "",
        "current_files":    {},
        "garro_review":     "",
        "vera_audit":       "",
        "confidence_score": 0,
        "issues":           [],
        "coder_model_used": "unknown",
    }

    app = build_graph()

    try:
        result = app.invoke(initial_state)
    except Exception as e:
        import traceback
        log(f"\n❌ Pipeline failed: {e}")
        log(traceback.format_exc())
        sys.exit(1)

    log("\n" + "="*60)
    log("✅ Swarm complete")
    log(f"   Confidence: {result.get('confidence_score', 0)}%")
    log(f"   Iterations: {result.get('iteration', 0)}")
    log(f"   Model used: {result.get('coder_model_used', '?')}")
    log(f"   Files:      {list(result.get('current_files', {}).keys())}")
    log(f"   Output:     {OUTPUT_DIR}/index.html")

    metrics = {
        "run_timestamp":    datetime.now().isoformat(),
        "iterations":       result.get("iteration", 0),
        "final_confidence": result.get("confidence_score", 0),
        "files":            list(result.get("current_files", {}).keys()),
        "coder_model":      result.get("coder_model_used", "unknown"),
        "vera_audit":       result.get("vera_audit", ""),
        "issues":           result.get("issues", []),
        "log_file":         str(LOG_FILE),
    }
    METRICS_FILE.write_text(json.dumps(metrics, indent=2))
    log(f"   Metrics:    {METRICS_FILE}")

    # Print final output path for easy browser open
    print(f"\n👉 open {OUTPUT_DIR}/index.html")


if __name__ == "__main__":
    main()
