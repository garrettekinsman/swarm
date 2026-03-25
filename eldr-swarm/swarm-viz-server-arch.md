# Swarm Viz — Server Architecture
*Prepared by **Agent: Vera** — Security-focused code reviewer, cryptography specialist. Tallinn, Estonia.*

---

## Overview

Browser-based dashboard for monitoring parallel EldrChat iOS swarms. Pure Python stdlib — no Flask, no WebSocket libs. SSE for live updates.

**Modes:**
- `python3 swarm-viz.py` — TTY live viz (existing)
- `python3 swarm-viz.py --once` — single print (existing)
- `python3 swarm-viz.py --serve 8888` — HTTP server with SSE

---

## Component Diagram (ASCII)

```
┌──────────────────────────────────────────────────────────────┐
│                      BROWSER (Dashboard)                      │
│  ┌─────────────────┐   ┌─────────────────┐                   │
│  │   Swarm Card    │   │   Swarm Card    │  ... N cards      │
│  │   (active)      │   │   (complete)    │                   │
│  └─────────────────┘   └─────────────────┘                   │
│            │                                                  │
│            │  EventSource('/events')                          │
│            ▼                                                  │
└──────────────────────────────────────────────────────────────┘
             │ SSE stream
             ▼
┌──────────────────────────────────────────────────────────────┐
│                   HTTP SERVER (stdlib)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐ │
│  │  GET /   │  │ /api/    │  │ /api/    │  │  GET /events  │ │
│  │  (HTML)  │  │ swarms   │  │ swarm/id │  │  (SSE stream) │ │
│  └──────────┘  └──────────┘  └──────────┘  └───────────────┘ │
│                       │                           ▲           │
│                       │ reads                     │ pushes    │
│                       ▼                           │           │
│            ┌─────────────────────────┐            │           │
│            │    SwarmTracker         │────────────┘           │
│            │  (shared state dict)    │                        │
│            └─────────────────────────┘                        │
│                       ▲                                       │
│                       │ updates every 1s                      │
│            ┌─────────────────────────┐                        │
│            │   FileWatcher Thread    │                        │
│            │  glob ios-swarm-*.log   │                        │
│            └─────────────────────────┘                        │
└──────────────────────────────────────────────────────────────┘
                        │
                        │ reads
                        ▼
             ┌─────────────────────────┐
             │  ios-swarm-*.log files  │
             │  (filesystem)           │
             └─────────────────────────┘
```

---

## Data Flow

1. **FileWatcher** thread polls `ios-swarm-*.log` every 1s
2. On file add/change/remove → updates `SwarmTracker` dict → calls `broadcast()`
3. `broadcast()` pushes JSON event to all SSE subscriber queues
4. Browser's `EventSource` receives event, updates DOM
5. REST endpoints (`/api/swarms`, `/api/swarm/<id>`) pull from `SwarmTracker` synchronously

---

## SSE Event Schema

| Event Type | Payload | When |
|------------|---------|------|
| `swarm_added` | `{"id": "ios-swarm-2026-03-24-1842.log", "state": {...}}` | New log file detected |
| `swarm_updated` | `{"id": "...", "state": {...}}` | Log file modified |
| `swarm_removed` | `{"id": "..."}` | Log file deleted |
| `swarm_complete` | `{"id": "...", "state": {...}}` | `final_stage == "done"` |

**State object** (matches `SwarmState.__dict__`):
```json
{
  "iteration": 2,
  "max_iter": 3,
  "confidence": 85,
  "opus_stage": "active",
  "garro_design": "done",
  "coders": ["done", "done", "active", ...],
  "vera_stage": "waiting",
  "files_written": ["ContentView.swift", ...],
  "errors": []
}
```

---

## Security Notes

**Tailscale exposure is fine.** This is read-only, serves no secrets, accepts no input beyond path params.

**Worth calling out:**
1. **No auth** — anyone on your tailnet can view. Acceptable for internal tooling.
2. **No input sanitization needed** — the only dynamic path is `/api/swarm/<id>` which does a dict lookup (no file path traversal possible, we never touch the filesystem based on client input).
3. **SSE connections are long-lived** — if an attacker floods `/events`, they get... a queue object per connection. No amplification. Memory grows linearly with concurrent viewers — fine unless you have 10k tabs open.
4. **Log file content is displayed** — if log files contain secrets (API keys, tokens), they'll render. The existing log parser only extracts status info, not raw content. But: don't put secrets in swarm logs.

**Not a concern:** CSRF (read-only), XSS (no user input rendered), SSRF (no outbound requests).

---

## Limitations & Future Work

- **1s poll interval** — not instant, but good enough. Could drop to 0.5s if latency matters.
- **No auth** — add a shared secret query param or Tailscale identity header if needed later.
- **Single-page reload required** for dashboard code updates — acceptable.
- **Memory** — holds all log state in RAM. For 10 swarms with 100 lines each: ~50KB. Not a concern.
- **No history** — completed swarms fade after 30s, then gone. Logs on disk remain.

---

*2026-03-24 — Agent: Vera*
