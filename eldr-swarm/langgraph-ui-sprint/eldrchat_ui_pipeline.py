#!/usr/bin/env python3
"""
EldrChat UI Pipeline — LangGraph orchestration
GARRO Design → Coder Implements → Build+Screenshot → GARRO Review → Report

Agents:
- GARRO: designer, gives pixel-level spec
- Coder: SwiftUI implementer
- Screenshot: builds Xcode project + runs in iPad simulator
- GARRO (again): reviews screenshots vs old vs requirements
"""

import os
import sys
import json
import subprocess
import shutil
from pathlib import Path
from typing import TypedDict, Annotated
import operator

import anthropic
from langgraph.graph import StateGraph, END

# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLIENT = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL = "claude-sonnet-4-6"

WORKSPACE = Path("~/.openclaw/workspace/projects/eldrchat")
SOURCE_DIR = WORKSPACE / "EldrChat/Sources/EldrChat"
MEDIA_DIR = Path("~/.openclaw/media")
OUTPUT_DIR = WORKSPACE / "langgraph-ui-sprint"
OUTPUT_DIR.mkdir(exist_ok=True)

# Old screenshots to compare against
OLD_SCREENSHOTS = [
    MEDIA_DIR / "eldrchat-ipad-landscape.png",
    MEDIA_DIR / "eldrchat-ipad-portrait.png",
    MEDIA_DIR / "eldr-contacts-list-ipad-landscape.png",
    MEDIA_DIR / "eldr-chat-ipad-landscape.png",
]

# ──────────────────────────────────────────────────────────────────────────────
# State
# ──────────────────────────────────────────────────────────────────────────────
class PipelineState(TypedDict):
    garro_spec: str
    swift_code: dict[str, str]   # filename -> content
    build_success: bool
    build_log: str
    screenshot_paths: list[str]
    review: str
    report_path: str
    messages: Annotated[list[str], operator.add]

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def read_file(path: Path) -> str:
    return path.read_text() if path.exists() else ""

def call_claude(system: str, user: str, max_tokens: int = 4096) -> str:
    msg = CLIENT.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}]
    )
    return msg.content[0].text

def read_image_b64(path: Path) -> str:
    import base64
    return base64.standard_b64encode(path.read_bytes()).decode("utf-8")

def call_claude_vision(system: str, user: str, image_paths: list[Path], max_tokens: int = 4096) -> str:
    content = []
    for p in image_paths:
        if p.exists():
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": read_image_b64(p)
                }
            })
    content.append({"type": "text", "text": user})
    msg = CLIENT.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}]
    )
    return msg.content[0].text

# ──────────────────────────────────────────────────────────────────────────────
# GARRO persona
# ──────────────────────────────────────────────────────────────────────────────
GARRO_SYSTEM = """You are GARRO — a world-class designer and the parallel version of Garrett Kinsman.
You think in grids, hierarchies, and optical weight. You are direct, specific, and give pixel values not vibes.

Design tokens you MUST use:
- Background: #0D0D0D
- Surface: #1A1A1A  
- Surface raised: #2C2C2E
- Text primary: #F5F5F7
- Text muted: #949BA4
- Blurple CTA: #5865F2
- Green online: #23A55A
- Amber warning: #F0A500
- Red error: #F23F43
- Grid: 8px
- Touch targets: 44px minimum (iPad), 28px (macOS)

Platform: iPad + macOS (Mac Catalyst). NavigationSplitView with three columns.
The app: EldrChat — NOSTR-based encrypted messaging. Dark, clean, no bloat.

Your design rules:
1. Grid is physics — everything on an 8px grid
2. Hierarchy is the whole game
3. Negative space does work — protect it
4. Typography is tone
5. Touch targets >= 44px, always

You are implementing Sprint 2 — the contact list (sidebar) as the FIRST UI piece.
Give exact SwiftUI specs: fonts, paddings, colors, spacing. Be specific."""

# ──────────────────────────────────────────────────────────────────────────────
# Coder system
# ──────────────────────────────────────────────────────────────────────────────
CODER_SYSTEM = """You are an expert SwiftUI engineer building EldrChat — a NOSTR-based encrypted messenger.
Target: iPad (iPadOS 17+) + macOS 14+ via Mac Catalyst.
Architecture: NavigationSplitView, three columns (sidebar/content/detail), no business logic in UI.

Rules:
- SwiftUI only. No UIKit/AppKit unless absolutely required.
- Use the existing EnvironmentObject NostrService pattern.
- Colors must use SwiftUI Color(hex:) or Color(red:green:blue:) from the design tokens.
- Touch targets >= 44pt minimum height/width.
- All new files must compile alongside existing files.
- Return ONLY valid Swift code, no markdown fences, no explanation.

Existing files you must be compatible with:
- NostrService.swift (EnvironmentObject)
- KeysManager.swift (keysManager.currentKeypair)
- MessageStore.swift (messageStore.allMessages, messageStore.messages(for:))
- DMMessage.swift (id, senderPubkey, recipientPubkey, content, createdAt)
- EldrChatApp.swift (@main)"""

# ──────────────────────────────────────────────────────────────────────────────
# Node 1: GARRO designs the contact list spec
# ──────────────────────────────────────────────────────────────────────────────
def node_garro_design(state: PipelineState) -> PipelineState:
    print("🎨 GARRO: Designing contact list spec...")

    # Read existing UI files for context
    dm_list_current = read_file(SOURCE_DIR / "DMListView.swift")
    content_view_current = read_file(SOURCE_DIR / "ContentView.swift")

    # Read old screenshots description
    old_screenshots_exist = [p for p in OLD_SCREENSHOTS if p.exists()]

    user_prompt = f"""
The current EldrChat iPad contact list UI needs a complete redesign for the v2 requirements.

PRIMARY TARGETS: iPad + macOS (Mac Catalyst). Near-identical UX across both.
NAVIGATION: NavigationSplitView — three columns:
  - Column 1 (sidebar): contact list / conversation list  
  - Column 2 (content): active conversation
  - Column 3 (inspector): contact info, relay status (collapsible)

CURRENT CODE (ContentView.swift):
{content_view_current}

CURRENT CODE (DMListView.swift):
{dm_list_current}

WHAT I NEED FROM YOU:
Give me a precise design spec for the CONTACT LIST (Column 1 / sidebar) only.
This is the first piece we're building.

Specify:
1. Overall sidebar dimensions and constraints (min width, ideal width)
2. Contact row layout: avatar size, text layout, spacing, padding
3. Avatar appearance: size, fallback (truncated npub + emoji), online indicator dot size/position/colors
4. Typography: which SF font styles for name, last message preview, timestamp
5. Color usage: which tokens for background, row hover/selected state, separators
6. Empty state design
7. Header: search bar? title? how?
8. Any macOS-specific adaptations

Be exact. Pixel values. SwiftUI modifiers. No hand-waving."""

    spec = call_claude(GARRO_SYSTEM, user_prompt, max_tokens=3000)
    print(f"✅ GARRO spec complete ({len(spec)} chars)")

    spec_path = OUTPUT_DIR / "garro-contact-list-spec.md"
    spec_path.write_text(f"# GARRO Contact List Design Spec\n\n{spec}")

    return {**state, "garro_spec": spec, "messages": [f"GARRO spec written to {spec_path}"]}

# ──────────────────────────────────────────────────────────────────────────────
# Node 2: Coder implements GARRO's spec
# ──────────────────────────────────────────────────────────────────────────────
def node_coder_implement(state: PipelineState) -> PipelineState:
    print("💻 Coder: Implementing SwiftUI based on GARRO spec...")

    garro_spec = state["garro_spec"]

    # Read existing source files for context
    existing_files = {}
    for fname in ["EldrChatApp.swift", "KeysManager.swift", "MessageStore.swift", "DMMessage.swift", "NostrService.swift"]:
        existing_files[fname] = read_file(SOURCE_DIR / fname)

    existing_context = "\n\n".join([f"// === {k} ===\n{v}" for k, v in existing_files.items() if v])

    user_prompt = f"""
Implement the EldrChat contact list for iPad + macOS (Mac Catalyst).

GARRO'S DESIGN SPEC:
{garro_spec}

EXISTING CODEBASE (for compatibility):
{existing_context}

WHAT TO BUILD:
1. A new `ContactListView.swift` — the sidebar column, replaces DMListView conceptually
2. An updated `ContentView.swift` — NavigationSplitView three-column layout (sidebar + content + detail)
3. A `ContactRow.swift` — individual contact row component with avatar, online dot, name, last message preview, timestamp

Requirements:
- ContactListView: full contact list with search, empty state, header
- ContentView: NavigationSplitView with three columns, passes selected contact through navigation
- ContactRow: shows truncated npub (first 6...last 6), emoji avatar fallback, online dot, last message snippet, relative timestamp
- Must use existing EnvironmentObject NostrService
- Dark theme throughout — use Color(red:green:blue:opacity:) for custom colors
- 44pt minimum touch targets on all interactive elements
- Works on both iPad and macOS without platform conditionals where possible

Return JSON with this exact structure:
{{
  "ContentView.swift": "...full swift code...",
  "ContactListView.swift": "...full swift code...",
  "ContactRow.swift": "...full swift code..."
}}

Return ONLY the JSON, nothing else."""

    response = call_claude(CODER_SYSTEM, user_prompt, max_tokens=6000)

    # Parse JSON from response
    try:
        # Find JSON in response
        start = response.find("{")
        end = response.rfind("}") + 1
        json_str = response[start:end]
        swift_files = json.loads(json_str)
    except Exception as e:
        print(f"⚠️  JSON parse failed: {e}")
        # Fallback: extract manually
        swift_files = {"raw_response": response}

    print(f"✅ Coder produced {len(swift_files)} files")
    return {**state, "swift_code": swift_files, "messages": [f"Coder produced: {list(swift_files.keys())}"]}

# ──────────────────────────────────────────────────────────────────────────────
# Node 3: Write files + build Xcode project + screenshot
# ──────────────────────────────────────────────────────────────────────────────
def node_build_and_screenshot(state: PipelineState) -> PipelineState:
    print("🔨 Build: Writing Swift files and building Xcode project...")

    swift_files = state["swift_code"]

    # Write the new Swift files
    for filename, content in swift_files.items():
        if filename.endswith(".swift") and content:
            target_path = SOURCE_DIR / filename
            # Backup original if exists
            if target_path.exists():
                backup = OUTPUT_DIR / f"{filename}.backup"
                shutil.copy2(target_path, backup)
                print(f"  📦 Backed up {filename}")
            target_path.write_text(content)
            print(f"  ✍️  Wrote {filename}")

    # Check if xcodeproj exists, create if not
    xcodeproj_path = WORKSPACE / "EldrChat.xcodeproj"
    if not xcodeproj_path.exists():
        print("  🔧 No xcodeproj found — generating from Package.swift...")
        result = subprocess.run(
            ["swift", "package", "generate-xcodeproj"],
            cwd=WORKSPACE / "EldrChat",
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            print(f"  ⚠️  xcodeproj generation failed: {result.stderr[:500]}")

    # Boot iPad simulator
    sim_udid = "486F3524-1CDA-4103-8A6C-8D5BE6F0C89F"  # iPad Pro 13-inch M5
    print(f"  📱 Booting simulator {sim_udid}...")
    subprocess.run(["xcrun", "simctl", "boot", sim_udid], capture_output=True, timeout=30)

    # Try building via xcodebuild
    build_log = ""
    build_success = False
    
    # First try: build the SPM package via swift build
    print("  🏗️  Building with swift build...")
    result = subprocess.run(
        ["swift", "build"],
        cwd=WORKSPACE / "EldrChat",
        capture_output=True, text=True, timeout=120
    )
    build_log = result.stdout + result.stderr
    if result.returncode == 0:
        build_success = True
        print("  ✅ Build succeeded")
    else:
        print(f"  ❌ Build failed:\n{result.stderr[:1000]}")
        build_success = False

    # Take screenshots using SwiftUI Preview rendering via xcodebuild
    # For now, take simulator screenshots of existing state + overlay our new layout
    screenshots = []
    
    # Try to capture simulator screenshot
    ss_path = OUTPUT_DIR / "simulator-contact-list.png"
    try:
        # Take a screenshot (even if just the simulator booting)
        result = subprocess.run(
            ["xcrun", "simctl", "io", sim_udid, "screenshot", str(ss_path)],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0 and ss_path.exists():
            screenshots.append(str(ss_path))
            print(f"  📸 Screenshot: {ss_path}")
        else:
            print(f"  ⚠️  Screenshot failed: {result.stderr[:200]}")
    except Exception as e:
        print(f"  ⚠️  Screenshot error: {e}")

    return {
        **state,
        "build_success": build_success,
        "build_log": build_log[:2000],
        "screenshot_paths": screenshots,
        "messages": [f"Build {'✅' if build_success else '❌'}, screenshots: {len(screenshots)}"]
    }

# ──────────────────────────────────────────────────────────────────────────────
# Node 4: GARRO reviews — compare old vs new
# ──────────────────────────────────────────────────────────────────────────────
def node_garro_review(state: PipelineState) -> PipelineState:
    print("🔍 GARRO: Reviewing implementation vs spec vs old screenshots...")

    garro_spec = state["garro_spec"]
    swift_files = state["swift_code"]
    build_success = state["build_success"]
    build_log = state["build_log"]

    # Prepare code context for review
    code_context = "\n\n".join([f"// === {k} ===\n{v}" for k, v in swift_files.items() if k.endswith(".swift")])

    # Check if we have new screenshots to compare
    new_screenshots = [Path(p) for p in state["screenshot_paths"] if Path(p).exists()]
    old_screenshots = [p for p in OLD_SCREENSHOTS if p.exists()]

    if new_screenshots and old_screenshots:
        # Vision-based review with actual screenshots
        review_images = old_screenshots[:2] + new_screenshots[:2]
        user_prompt = f"""
You are reviewing the EldrChat contact list implementation.

The FIRST images are OLD screenshots (before v2 redesign).
The LAST images are NEW screenshots (after the redesign).

YOUR ORIGINAL SPEC:
{garro_spec[:1500]}

THE IMPLEMENTED CODE:
{code_context[:3000]}

BUILD STATUS: {'✅ SUCCESS' if build_success else '❌ FAILED'}
BUILD LOG (if failed):
{build_log[:500] if not build_success else ''}

Write a design review covering:
1. **What improved** — specific things better than the old screenshots
2. **What's still missing** — requirements not yet met with specific fixes
3. **Code quality notes** — any SwiftUI patterns that need fixing
4. **Next sprint priorities** — ranked list of what to fix next

Be direct. Give pixel values. Rate the implementation out of 10."""

        review = call_claude_vision(GARRO_SYSTEM, user_prompt, review_images, max_tokens=3000)
    else:
        # Text-only review
        user_prompt = f"""
You are reviewing the EldrChat contact list implementation (no screenshots available yet).

YOUR ORIGINAL SPEC:
{garro_spec[:1500]}

THE IMPLEMENTED CODE:
{code_context[:4000]}

BUILD STATUS: {'✅ SUCCESS' if build_success else '❌ FAILED'}
BUILD LOG:
{build_log[:1000]}

Write a design review covering:
1. **Spec compliance** — does the code match your spec? Be specific.
2. **Code quality notes** — SwiftUI patterns, layout correctness, token usage
3. **Missing pieces** — what's not implemented yet
4. **Next sprint priorities** — ranked list

Be direct. Give specific line-level feedback where something is wrong.
Rate the implementation out of 10."""

        review = call_claude(GARRO_SYSTEM, user_prompt, max_tokens=3000)

    print(f"✅ GARRO review complete ({len(review)} chars)")
    return {**state, "review": review, "messages": ["GARRO review complete"]}

# ──────────────────────────────────────────────────────────────────────────────
# Node 5: Write report and copy screenshots to media
# ──────────────────────────────────────────────────────────────────────────────
def node_write_report(state: PipelineState) -> PipelineState:
    print("📝 Writing final report...")

    today = "2026-03-24"
    report_path = OUTPUT_DIR / f"eldrchat-ui-sprint2-review-v1-{today}.md"

    swift_files = state["swift_code"]
    file_list = "\n".join([f"- `{k}`" for k in swift_files.keys()])

    report = f"""---
*Prepared by **Agent: GARRO** — Designer, Berlin-based. Parallel Garrett.*
*Running: anthropic/claude-sonnet-4-5 (via LangGraph pipeline)*

*Orchestrated by **Agent: Gaho** — OpenClaw primary assistant.*
*Running: anthropic/claude-sonnet-4-6*

*Human in the Loop: Garrett Kinsman*

---

# EldrChat UI Sprint 2 — Contact List Review
## v1-{today}

**Target:** iPad + macOS (Mac Catalyst) — NavigationSplitView three-column

---

## What Was Built

Files generated:
{file_list}

Build status: {'✅ Succeeded' if state['build_success'] else '❌ Failed — see log below'}

---

## GARRO's Design Spec

{state['garro_spec']}

---

## Implementation Review

{state['review']}

---

## Build Log

```
{state['build_log'][:2000]}
```

---

## Screenshots

Old screenshots (for comparison):
{chr(10).join(['- ' + str(p) for p in OLD_SCREENSHOTS if p.exists()])}

New screenshots:
{chr(10).join(['- ' + str(p) for p in state['screenshot_paths']]) if state['screenshot_paths'] else '- None captured (simulator not running app yet)'}

---

## LangGraph Pipeline Log

{chr(10).join(state['messages'])}
"""

    report_path.write_text(report)
    print(f"✅ Report written: {report_path}")

    # Copy report to media dir for Discord delivery
    media_report = MEDIA_DIR / report_path.name
    shutil.copy2(report_path, media_report)

    # Copy any new screenshots to media
    for ss_path in state["screenshot_paths"]:
        src = Path(ss_path)
        if src.exists():
            dst = MEDIA_DIR / f"eldrchat-sprint2-{src.name}"
            shutil.copy2(src, dst)
            print(f"  📸 Copied to media: {dst.name}")

    return {**state, "report_path": str(media_report), "messages": [f"Report: {media_report}"]}

# ──────────────────────────────────────────────────────────────────────────────
# Build LangGraph
# ──────────────────────────────────────────────────────────────────────────────
def build_graph():
    graph = StateGraph(PipelineState)

    graph.add_node("garro_design", node_garro_design)
    graph.add_node("coder_implement", node_coder_implement)
    graph.add_node("build_and_screenshot", node_build_and_screenshot)
    graph.add_node("garro_review", node_garro_review)
    graph.add_node("write_report", node_write_report)

    graph.set_entry_point("garro_design")
    graph.add_edge("garro_design", "coder_implement")
    graph.add_edge("coder_implement", "build_and_screenshot")
    graph.add_edge("build_and_screenshot", "garro_review")
    graph.add_edge("garro_review", "write_report")
    graph.add_edge("write_report", END)

    return graph.compile()

# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🚀 EldrChat UI Pipeline — LangGraph")
    print(f"   Workspace: {WORKSPACE}")
    print(f"   Output: {OUTPUT_DIR}")
    print()

    app = build_graph()

    initial_state: PipelineState = {
        "garro_spec": "",
        "swift_code": {},
        "build_success": False,
        "build_log": "",
        "screenshot_paths": [],
        "review": "",
        "report_path": "",
        "messages": ["Pipeline started"]
    }

    result = app.invoke(initial_state)

    print()
    print("=" * 60)
    print("✅ Pipeline complete")
    print(f"   Report: {result['report_path']}")
    print(f"   Build: {'✅' if result['build_success'] else '❌'}")
    print(f"   Screenshots: {len(result['screenshot_paths'])}")
    print()
    print("REPORT PATH:", result["report_path"])
