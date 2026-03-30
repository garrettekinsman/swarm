# xcode-swarm

An autonomous LangGraph-based swarm for iterative iOS/Swift app development. Runs parallel coding agents (Sonnet + Qwen), validates builds, and loops until `xcodebuild BUILD SUCCEEDED`.

## What It Does

- **Parallel coders**: Sonnet handles crypto/networking, Qwen handles UI boilerplate — 40× cheaper on the easy work
- **Spec-driven**: Claude Code reads actual build errors and writes targeted specs each iteration
- **Vera audit gate**: Security + quality review before accepting each sprint
- **Autonomous loop**: Runs until the app builds, then hands off to you
- **QA extension**: Expandable to XCUITest, local relay integration testing

## Structure

```
xcode-swarm/
├── README.md           — this file
├── SKILL.md            — OpenClaw skill definition (how to invoke)
└── SWARM-PATTERNS.md   — field notes: what worked, what didn't, lessons learned
```

## Key Lessons (from EldrChat iOS)

- Always use `python3.14` — system `python3` (3.9 on macOS) silently hangs with no output
- `--skip-spec-gen` + `spec_generation: manual` in config — BOTH required when using Claude Code specs
- Sonnet for crypto/secp256k1/WebSocket, Qwen for SwiftUI views
- Package.swift must be written to project ROOT, not `Sources/`
- GigaBitcoin `swift-secp256k1` for secp256k1 — never hand-roll crypto
- `nostr-sdk-ios` v0.3.0 API is completely different from v0.15.0 — drop it, use raw Nostr JSON

## QA Loop (Sprint 16+)

```
xcodebuild ✅ → swift test ✅ → XCUITest ✅ → local relay integration ✅ → hand off to human
```

## Adapting for Other Projects

Replace the EldrChat-specific Sprint config with your own. The k_eff pipeline, model routing, and loop controller are generic — works for any Swift/iOS project.

For yapCAD / other swarms: see sibling directories in this repo.
