#!/usr/bin/env python3
"""
EldrChat iOS Parallel Swarm — Opus orchestrator + 10 qwen CODER branches + Kimi designer + Vera auditor

Architecture (from xcode-langgraph-team-setup-v1-2026-03-24.md §9):
  - OPUS (Claude Opus 4-6) — orchestrator, breaks design into tasks, iterates
  - GARRO (kimi-k2.5 via OpenRouter) — design spec, visual review, confidence scoring
  - 10x QWEN (qwen3-coder-next via OpenRouter) — parallel implementation branches
    • 1 local branch via model router (Framework1) — free
    • up to 10 cloud branches via OpenRouter — fast parallel
  - VERA (Claude Sonnet 4-6) — security audit

Lessons from web_swarm.py first run (2026-03-24):
  - OPENROUTER_TIMEOUT must be 120s (kimi timed out at 60s during GARRO review)
  - CODER must output ALL referenced files or use inline-only styles
  - Fake SRI hashes: VERA flags, pipeline auto-strips them
  - Confidence 72% on iter 1 is normal — pipeline correctly continues
  - Sanitizer call sig: sanitize_text(text) only — no kwargs like tier=

Output: projects/eldrchat/ios-swarm-output/
"""

import os
import sys
import json
import re
import logging
import pathlib
import concurrent.futures
import subprocess
from pathlib import Path
from datetime import datetime
from typing import TypedDict, List, Dict, Literal, Optional

import requests
from anthropic import Anthropic

# ── Sanitizer ─────────────────────────────────────────────────────────────────
_SANITIZER_PATH = Path("/Users/garrett/.openclaw/workspace/projects/agent-collaboration")
sys.path.insert(0, str(_SANITIZER_PATH))
from sanitizer_v2 import sanitize_text, sanitize_pipeline_field

# ── Paths ──────────────────────────────────────────────────────────────────────
WORKSPACE   = Path("/Users/garrett/.openclaw/workspace/projects/eldrchat")
OUTPUT_DIR  = WORKSPACE / "ios-swarm-output"
LOG_DIR     = WORKSPACE
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
(OUTPUT_DIR / "Sources" / "EldrChat").mkdir(parents=True, exist_ok=True)

TIMESTAMP    = datetime.now().strftime("%Y%m%d-%H%M%S")
LOG_FILE     = LOG_DIR / f"ios-swarm-{TIMESTAMP}.log"
METRICS_FILE = LOG_DIR / f"ios-swarm-metrics-{TIMESTAMP}.json"
AGENTS_DIR   = Path("/Users/garrett/.openclaw/workspace/agents")

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

# ── Config ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not ANTHROPIC_API_KEY:
    log("❌ ANTHROPIC_API_KEY not set"); sys.exit(1)
if not OPENROUTER_API_KEY:
    log("❌ OPENROUTER_API_KEY not set"); sys.exit(1)

anthropic = Anthropic(api_key=ANTHROPIC_API_KEY)

MAX_ITERATIONS   = 3
CONFIDENCE_GOAL  = 80
MAX_QWEN_CLOUD   = 10   # parallel OpenRouter qwen branches
OPENROUTER_TIMEOUT = 120  # learned from web sprint — kimi needs 120s

# ── Personas ───────────────────────────────────────────────────────────────────
def load_persona(name: str) -> str:
    p = AGENTS_DIR / f"{name.lower()}.md"
    return p.read_text() if p.exists() else f"You are {name}."

GARRO_PERSONA = load_persona("garro")
VERA_PERSONA  = load_persona("vera")

# ── Component definitions (10 Swift files across 3 layers) ────────────────────
SWIFT_COMPONENTS = [
    # Views layer (5 files — Mei persona)
    {
        "id": 0, "persona": "Mei", "layer": "views",
        "filename": "ContentView.swift",
        "desc": "Root app view — NavigationSplitView sidebar+detail. Sidebar shows ChannelListView. Detail shows ChatView. iPad/macOS adaptive layout. Dark theme #0a0a0f bg, #7c3aed accent."
    },
    {
        "id": 1, "persona": "Mei", "layer": "views",
        "filename": "ChannelListView.swift",
        "desc": "Sidebar channel/contact list. List of ConversationRow items. Search bar at top. Empty state with 'Add contact' CTA. Pulls from MessageStore."
    },
    {
        "id": 2, "persona": "Mei", "layer": "views",
        "filename": "ChatView.swift",
        "desc": "Main chat view. ScrollView of MessageBubble items. InputBar pinned to bottom. Shows contact name/npub in header. Loads messages from MessageStore."
    },
    {
        "id": 3, "persona": "Mei", "layer": "views",
        "filename": "LoginView.swift",
        "desc": "Onboarding/key setup. Two options: generate new keypair or import nsec. Shows npub on success. Uses KeyManager. Clean, minimal, dark."
    },
    {
        "id": 4, "persona": "Mei", "layer": "views",
        "filename": "SettingsView.swift",
        "desc": "Settings screen. Shows npub (copyable), relay list (add/remove), app version. Uses RelayPool for relay management."
    },
    # Components layer (3 files — Vera persona)
    {
        "id": 5, "persona": "Vera", "layer": "components",
        "filename": "MessageBubble.swift",
        "desc": "Reusable message bubble. Outgoing: right-aligned, #7c3aed bg. Incoming: left-aligned, #1a1a2e bg. Timestamp shown subtly. Supports text only (v1)."
    },
    {
        "id": 6, "persona": "Vera", "layer": "components",
        "filename": "InputBar.swift",
        "desc": "Message input bar. TextField + send button. Pinned bottom, respects safe area. Send button uses #7c3aed. Clears on send. Min 44pt touch target."
    },
    {
        "id": 7, "persona": "Vera", "layer": "components",
        "filename": "ConversationRow.swift",
        "desc": "Sidebar row. Avatar circle (initials fallback), display name, last message preview, timestamp. Truncates long names. 44pt min height."
    },
    # Models + networking layer (2 files — Vera persona)
    {
        "id": 8, "persona": "Vera", "layer": "models",
        "filename": "KeyManager.swift",
        "desc": "Nostr key management. Generate secp256k1 keypair, store nsec in Keychain (NOT UserDefaults), derive npub. Import/export nsec. Zero private key exposure in memory beyond what's needed."
    },
    {
        "id": 9, "persona": "Vera", "layer": "models",
        "filename": "NostrClient.swift",
        "desc": "Nostr protocol client stub. Connect to relay URLs via WebSocket (URLSessionWebSocketTask). Send REQ and EVENT messages. Parse incoming events. NIP-04 encrypted DM structure (stub — full crypto in v1.1). Thread-safe with actor."
    },
]

# ── Helpers ────────────────────────────────────────────────────────────────────

def call_openrouter(messages: list, model: str = "moonshotai/kimi-k2.5", max_tokens: int = 4096) -> str:
    import time as _time
    max_retries = 3
    for attempt in range(max_retries):
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://openclaw.ai",
                "X-Title": "EldrChat iOS Swarm",
                "Content-Type": "application/json",
            },
            json={"model": model, "messages": messages, "max_tokens": max_tokens},
            timeout=OPENROUTER_TIMEOUT,
        )
        if resp.status_code == 429:
            wait = 5 * (attempt + 1)
            log(f"   ⏳ OpenRouter 429 — retrying in {wait}s (attempt {attempt+1}/{max_retries})")
            _time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    # Final attempt failed
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def call_claude(prompt: str, model: str = "claude-opus-4-6", max_tokens: int = 4096,
                system: Optional[str] = None) -> str:
    msgs = [{"role": "user", "content": prompt}]
    kwargs = {"model": model, "max_tokens": max_tokens, "messages": msgs}
    if system:
        kwargs["system"] = system
    resp = anthropic.messages.create(**kwargs)
    return resp.content[0].text


def call_model_router_local(prompt: str) -> Optional[str]:
    """Try Framework1 qwen via model router. Returns content or None on failure."""
    router_sock = Path(os.path.expanduser("~/.openclaw/data/model-router.sock"))
    if not router_sock.exists():
        return None
    try:
        import socket, http.client
        conn = http.client.HTTPConnection("localhost")
        conn.sock = socket.socket(socket.AF_UNIX)
        conn.sock.settimeout(180)
        conn.sock.connect(str(router_sock))
        body = json.dumps({"role": "coder", "prompt": prompt, "max_tokens": 4096})
        conn.request("POST", "/dispatch", body, {"Content-Type": "application/json"})
        r = conn.getresponse()
        if r.status == 200:
            data = json.loads(r.read())
            return data.get("result", data.get("content", ""))
    except Exception as e:
        log(f"   ⚠️  Model router error: {e}")
    return None


def extract_swift_files(text: str) -> dict:
    """
    Parse ```swift:FILENAME.swift blocks from LLM output.
    Falls back to plain ```swift blocks if no filename tag.
    """
    files = {}
    # Primary: ```swift:Filename.swift
    for m in re.finditer(r"```swift:([\w./]+\.swift)\n(.*?)```", text, re.DOTALL):
        fname, content = m.group(1).strip(), m.group(2).strip()
        files[fname] = content
    # Fallback: ```swift (no filename) — use component default
    if not files:
        for m in re.finditer(r"```swift\n(.*?)```", text, re.DOTALL):
            content = m.group(1).strip()
            if content and "import SwiftUI" in content:
                # Try to extract struct/class name for filename
                nm = re.search(r"(?:struct|class)\s+(\w+View|\w+Client|\w+Manager|\w+Store|\w+Bar|\w+Row|\w+Bubble)", content)
                fname = f"{nm.group(1)}.swift" if nm else "Output.swift"
                files[fname] = content
    return files


def strip_sri_hashes(content: str) -> str:
    """Remove integrity= attributes from script/link tags (VERA lesson from web sprint)."""
    return re.sub(r'\s+integrity="[^"]*"', '', content)


def write_swift_files(files: dict):
    sources = OUTPUT_DIR / "Sources" / "EldrChat"
    for fname, content in files.items():
        out = sources / fname
        out.write_text(content)
        log(f"   📄 Wrote {out.relative_to(WORKSPACE)}")


# ── Persona-injected qwen prompt ───────────────────────────────────────────────

def build_coder_prompt(component: dict, design_spec: str, issues: list, iteration: int) -> str:
    persona_name = component["persona"]
    if persona_name == "Mei":
        persona_text = """You are Mei (梅) — Lin Mei, PhD candidate at Tsinghua KEG Lab.
Specialist in inference optimization and heterogeneous computing. Direct, technical, no fluff.
You write clean, idiomatic Swift."""
    else:
        persona_text = f"""You are Vera — a security-focused cryptography specialist from Tallinn.
You write Swift that is correct, safe, and parsimonious. No shortcuts on security primitives.
No unnecessary complexity either."""

    issues_block = ""
    if issues and iteration > 1:
        issues_block = f"\n\nFix these issues from the previous iteration:\n" + "\n".join(f"- {i}" for i in issues[:5])

    return f"""{persona_text}

---

TASK: Implement one SwiftUI component for EldrChat — a privacy-focused NOSTR messaging app.

TARGET FILE: {component['filename']}
LAYER: {component['layer']}
REQUIREMENTS: {component['desc']}

DESIGN SYSTEM (from GARRO):
{design_spec[:2000]}
{issues_block}

CRITICAL OUTPUT FORMAT — you MUST follow this exactly:

```swift:{component['filename']}
import SwiftUI
// ... your complete implementation here
```

Rules:
- Output ONLY the code block above. Zero explanations. Zero commentary.
- The file must be complete and compilable (no TODOs in critical paths)
- Dark theme: background #0a0a0f, accent #7c3aed, text white
- iOS 17+ / macOS 14+ APIs only
- Touch targets minimum 44pt
- No hardcoded test data except clearly commented placeholder text
"""


# ── Parallel coder fleet ────────────────────────────────────────────────────────

def run_one_coder(component: dict, design_spec: str, issues: list, iteration: int,
                  use_local: bool = False) -> tuple[str, str, str]:
    """
    Run one coder branch. Returns (filename, swift_content, model_used).
    use_local=True tries Framework1 first (component id 0 only).
    """
    prompt = build_coder_prompt(component, design_spec, issues, iteration)
    fname  = component["filename"]
    model_used = "openrouter/qwen3-coder-next"

    # Local branch (Framework1) — only for component 0
    if use_local:
        log(f"   🏠 [{fname}] Trying local (Framework1)...")
        result = call_model_router_local(prompt)
        if result:
            files = extract_swift_files(result)
            if files:
                content = list(files.values())[0]
                return fname, content, "local/qwen3-coder-next"
            log(f"   ⚠️  [{fname}] Local returned 0 files — falling back to OpenRouter")

    # OpenRouter qwen (primary cloud path)
    log(f"   ☁️  [{fname}] Calling OpenRouter qwen3-coder-next...")
    try:
        result = call_openrouter(
            messages=[{"role": "user", "content": prompt}],
            model="qwen/qwen3-coder-next",
            max_tokens=4096,
        )
        files = extract_swift_files(result)
        if files:
            content = list(files.values())[0]
            return fname, content, model_used
        log(f"   ⚠️  [{fname}] OpenRouter returned 0 files — falling back to Sonnet")
    except Exception as e:
        log(f"   ⚠️  [{fname}] OpenRouter error: {e} — falling back to Sonnet")

    # Sonnet fallback (cheaper than Opus for code gen)
    log(f"   🔄 [{fname}] Sonnet fallback...")
    result = call_claude(prompt, model="claude-sonnet-4-6", max_tokens=4096)
    files = extract_swift_files(result)
    if files:
        return fname, list(files.values())[0], "anthropic/claude-sonnet-4-6 (fallback)"

    # Last resort: return whatever we got, raw
    log(f"   ❌ [{fname}] All tiers failed — returning raw output")
    return fname, f"// GENERATION FAILED for {fname}\n// Raw output:\n// {result[:500]}", "FAILED"


def run_parallel_coders(design_spec: str, issues: list, iteration: int) -> dict:
    """
    Spawn up to MAX_QWEN_CLOUD parallel coder branches.
    Component 0 also tries local first.
    Returns {filename: swift_content}.
    """
    log(f"\n💻 Spawning {len(SWIFT_COMPONENTS)} parallel qwen coders...")

    results = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_QWEN_CLOUD) as pool:
        futures = {}
        for comp in SWIFT_COMPONENTS:
            use_local = (comp["id"] == 0)  # only first component tries local
            f = pool.submit(run_one_coder, comp, design_spec, issues, iteration, use_local)
            futures[f] = comp["filename"]

        for f in concurrent.futures.as_completed(futures, timeout=300):
            fname = futures[f]
            try:
                out_fname, content, model = f.result()
                results[out_fname] = content
                log(f"   ✅ [{out_fname}] done via {model}")
            except Exception as e:
                log(f"   ❌ [{fname}] exception: {e}")

    log(f"   📦 Collected {len(results)}/{len(SWIFT_COMPONENTS)} Swift files")
    return results


# ── Pipeline nodes ─────────────────────────────────────────────────────────────

def node_opus_orchestrate(state: dict) -> dict:
    """OPUS — plan iteration, decide continue/done."""
    state["iteration"] = state.get("iteration", 0) + 1
    it = state["iteration"]
    score = state.get("confidence_score", 0)

    log(f"\n{'='*60}")
    log(f"🧠 OPUS — Iteration {it}/{MAX_ITERATIONS}  (confidence so far: {score}%)")

    if score >= CONFIDENCE_GOAL or it > MAX_ITERATIONS:
        state["next_action"] = "done"
        log(f"   ✅ Terminating — confidence={score}% iterations={it}")
    else:
        state["next_action"] = "iterate"

    # Sanitize requirements on first pass
    if it == 1 and state.get("requirements"):
        state["requirements"] = sanitize_text(state["requirements"])

    return state


def node_garro_design(state: dict) -> dict:
    """GARRO (kimi-k2.5) — generate design spec (iteration 1 only) or re-review."""
    if state.get("iteration", 1) > 1 and state.get("design_spec"):
        log("\n🎨 GARRO — Design spec cached, skipping redesign")
        return state

    log("\n🎨 GARRO — Generating design spec...")

    prompt = f"""{GARRO_PERSONA}

---

Create a detailed SwiftUI design spec for EldrChat — a private NOSTR messaging app.

Requirements:
{state.get('requirements', 'See below')}

Outputs expected:
{json.dumps([c['filename'] for c in SWIFT_COMPONENTS], indent=2)}

Spec must include:
- Color palette (primary bg, secondary bg, accent, text colors with hex values)
- Typography (SF Pro sizes for title/body/caption)
- Layout rules (NavigationSplitView structure, sidebar width, safe area handling)
- Component-specific notes for each of the 10 Swift files above
- iPad + macOS adaptive rules
- Dark mode only (v1)

Be specific. Pixel values. No vibes.
"""

    try:
        result = call_openrouter(
            messages=[{"role": "user", "content": prompt}],
            model="moonshotai/kimi-k2.5",
            max_tokens=4096,
        )
        design_spec = sanitize_pipeline_field("design_spec", result)
        state["design_spec"] = design_spec
        log(f"   ✅ Design spec: {len(design_spec)} chars")
    except Exception as e:
        log(f"   ⚠️  GARRO error: {e} — using fallback spec")
        state["design_spec"] = """EldrChat Design Spec (fallback):
Colors: bg=#0a0a0f, surface=#1a1a2e, accent=#7c3aed, text=#ffffff, muted=#6b7280
Typography: SF Pro Display 28pt title, SF Pro Text 16pt body, 12pt caption
Layout: NavigationSplitView, sidebar 280pt, detail fills remaining
All touch targets: 44pt minimum"""

    return state


def node_parallel_coders(state: dict) -> dict:
    """10x QWEN — parallel implementation branches."""
    log(f"\n💻 CODER FLEET — Iteration {state.get('iteration', 1)}")

    files = run_parallel_coders(
        design_spec=state.get("design_spec", ""),
        issues=state.get("issues", []),
        iteration=state.get("iteration", 1),
    )

    # Sanitize all outputs
    sanitized = {}
    for fname, content in files.items():
        sanitized[fname] = sanitize_pipeline_field(f"swift_{fname}", content)

    state["current_files"] = sanitized

    # Write to disk
    write_swift_files(sanitized)
    return state


def node_vera_audit(state: dict) -> dict:
    """VERA — security audit all generated Swift files."""
    log("\n🔒 VERA — Security audit...")

    all_code = "\n\n".join(
        f"// === {fname} ===\n{content}"
        for fname, content in state.get("current_files", {}).items()
    )

    prompt = f"""{VERA_PERSONA}

---

Audit this Swift/SwiftUI code for EldrChat (NOSTR messaging app).

Focus on:
1. CRITICAL: Private keys in UserDefaults, logs, or non-Keychain storage
2. HIGH: Injected data from NOSTR relays rendered without escaping
3. HIGH: WebSocket connections to unvalidated URLs
4. MEDIUM: Missing input validation (npub/nsec format checks)
5. MEDIUM: Hardcoded relay URLs (should be configurable)
6. LOW: Architecture issues (P0 MVVM violations, massive views)

For each issue: SEVERITY | FILE | LINE_HINT | DESCRIPTION | FIX

Then: confidence score (0-100) and list of top issues for next iteration.

Code:
{all_code[:8000]}
"""

    result = call_claude(prompt, model="claude-sonnet-4-6", max_tokens=2048)
    vera_audit = sanitize_pipeline_field("vera_audit", result)
    state["vera_audit"] = vera_audit
    log(f"   ✅ Vera audit: {len(vera_audit)} chars")

    # Extract confidence if Vera included one
    m = re.search(r"confidence[:\s]+(\d+)", vera_audit, re.IGNORECASE)
    if m:
        vera_score = min(int(m.group(1)), 85)
        state["vera_confidence"] = vera_score
        log(f"   📊 Vera confidence estimate: {vera_score}%")

    return state


def node_garro_review(state: dict) -> dict:
    """GARRO — review code quality + design fidelity, score confidence."""
    log("\n🎨 GARRO — Code review + confidence score...")

    # Build file list summary
    file_summary = "\n".join(
        f"- {fname}: {len(content)} chars"
        for fname, content in state.get("current_files", {}).items()
    )

    # Sample of actual code for review
    sample_files = list(state.get("current_files", {}).items())[:3]
    code_sample = "\n\n".join(f"// {f}\n{c[:800]}" for f, c in sample_files)

    prompt = f"""{GARRO_PERSONA}

---

Review this SwiftUI implementation for EldrChat.

Files produced ({len(state.get('current_files', {}))}/10):
{file_summary}

Design spec (your spec):
{state.get('design_spec', '')[:1000]}

Vera's security audit:
{state.get('vera_audit', '')[:800]}

Code sample (first 3 files):
{code_sample}

Score: 0-100 (cap at 85 — reserve 86-100 for human-verified builds).
Be brutal. Design issues, missing files, architecture problems all cost points.

Output JSON:
{{
  "confidence_score": 0-85,
  "issues": ["issue1", "issue2", ...],
  "feedback": "One paragraph for next iteration"
}}
"""

    try:
        result = call_openrouter(
            messages=[{"role": "user", "content": prompt}],
            model="moonshotai/kimi-k2.5",
            max_tokens=1024,
        )
        result = sanitize_pipeline_field("garro_review", result)

        # Parse JSON
        m = re.search(r"\{.*\}", result, re.DOTALL)
        if m:
            data = json.loads(m.group(0))
            score = min(int(data.get("confidence_score", 0)), 85)
            issues = data.get("issues", [])
            feedback = data.get("feedback", "")
        else:
            score = 60
            issues = ["Could not parse GARRO review"]
            feedback = result[:500]

    except Exception as e:
        log(f"   ⚠️  GARRO review error: {e} — using Vera score")
        score = state.get("vera_confidence", 55)
        issues = ["GARRO review timed out"]
        feedback = "Review failed — using Vera estimate"

    state["confidence_score"] = score
    state["issues"]            = issues
    state["garro_review"]      = feedback

    log(f"   📊 Confidence: {score}%")
    log(f"   🐛 Issues ({len(issues)}): {issues[:3]}")

    return state


def node_final_report(state: dict) -> dict:
    """Write final report + metrics."""
    log(f"\n{'='*60}")
    log(f"✅ PIPELINE COMPLETE")
    log(f"   Confidence: {state.get('confidence_score', 0)}%")
    log(f"   Iterations: {state.get('iteration', 0)}")
    log(f"   Files written: {len(state.get('current_files', {}))}")
    log(f"   Output: {OUTPUT_DIR}")

    metrics = {
        "timestamp":        TIMESTAMP,
        "iterations":       state.get("iteration", 0),
        "confidence_score": state.get("confidence_score", 0),
        "files_generated":  list(state.get("current_files", {}).keys()),
        "issues":           state.get("issues", []),
        "log_file":         str(LOG_FILE),
    }
    METRICS_FILE.write_text(json.dumps(metrics, indent=2))
    log(f"   📊 Metrics: {METRICS_FILE}")

    return state


# ── Graph ──────────────────────────────────────────────────────────────────────

def build_graph():
    try:
        from langgraph.graph import StateGraph as LG, END
    except ImportError:
        log("❌ langgraph not installed. Run: pip3 install langgraph"); sys.exit(1)

    graph = LG(dict)

    graph.add_node("orchestrate",    node_opus_orchestrate)
    graph.add_node("garro_design",   node_garro_design)
    graph.add_node("coders",         node_parallel_coders)
    graph.add_node("vera",           node_vera_audit)
    graph.add_node("garro_review",   node_garro_review)
    graph.add_node("final",          node_final_report)

    graph.set_entry_point("orchestrate")
    graph.add_edge("orchestrate", "garro_design")
    graph.add_edge("garro_design", "coders")
    graph.add_edge("coders", "vera")
    graph.add_edge("vera", "garro_review")

    def route(state):
        return "final" if state.get("next_action") == "done" else "orchestrate"

    graph.add_conditional_edges("garro_review", route, {
        "orchestrate": "orchestrate",
        "final":       "final",
    })
    graph.add_edge("final", END)

    return graph.compile()


# ── Entry point ────────────────────────────────────────────────────────────────

REQUIREMENTS = """
EldrChat v1 — iOS/iPadOS/macOS NOSTR messaging app.

Must have:
- Send/receive NIP-04 encrypted direct messages
- Keypair identity (secp256k1) stored in Keychain
- Multiple relay support (WebSocket, URLSessionWebSocketTask)
- NavigationSplitView layout for iPad + Mac (sidebar + chat)
- Dark theme: bg #0a0a0f, accent #7c3aed
- Minimum iOS 17 / macOS 14

Files to generate (all 10):
ContentView.swift, ChannelListView.swift, ChatView.swift, LoginView.swift,
SettingsView.swift, MessageBubble.swift, InputBar.swift, ConversationRow.swift,
KeyManager.swift, NostrClient.swift
"""


def main():
    log("🚀 EldrChat iOS Parallel Swarm")
    log(f"   {len(SWIFT_COMPONENTS)} components × up to {MAX_QWEN_CLOUD} parallel qwen branches")
    log(f"   1 local branch (Framework1) + up to {MAX_QWEN_CLOUD} cloud (OpenRouter)")
    log(f"   Designer: kimi-k2.5  |  Auditor: Claude Sonnet  |  Orchestrator: Claude Opus")
    log(f"   Output: {OUTPUT_DIR}")
    log(f"   Log: {LOG_FILE}\n")

    app = build_graph()

    initial_state = {
        "requirements":    REQUIREMENTS,
        "iteration":       0,
        "next_action":     "iterate",
        "design_spec":     "",
        "current_files":   {},
        "vera_audit":      "",
        "vera_confidence": 0,
        "garro_review":    "",
        "confidence_score": 0,
        "issues":          [],
    }

    final_state = app.invoke(initial_state)

    log(f"\n🏁 Done. Confidence: {final_state.get('confidence_score', 0)}%  "
        f"Iterations: {final_state.get('iteration', 0)}")
    return final_state


if __name__ == "__main__":
    main()
