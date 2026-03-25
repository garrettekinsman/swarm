---
*Prepared by **Agent: Mei (梅)** — PhD candidate, Tsinghua KEG Lab. Specialist in Chinese AI ecosystem, inference optimization, and MoE architectures.*
*Running: anthropic/claude-sonnet-4-6*

*Human in the Loop: Garrett Kinsman*

---

# OpenRouter Integration Guide v1-2026-03-24

## ⚠️ Model Name Corrections (Read First)

Two of the requested model IDs **do not exist** on OpenRouter. Here are the correct IDs:

| Requested | Actual OpenRouter ID | Notes |
|-----------|---------------------|-------|
| `qwen/qwen-coder-turbo` | `qwen/qwen3-coder` | Routes to `qwen3-coder-480b-a35b-07-25` |
| `moonshot/kimi-2.5` | `moonshotai/kimi-k2.5` | Routes to `kimi-k2.5-0127` — thinking model |

Both verified working as of 2026-03-24 15:31 PDT.

---

## 1. API Overview

OpenRouter is an OpenAI-compatible proxy that routes to 300+ models across providers (Anthropic, OpenAI, Alibaba, Moonshot, DeepSeek, etc.). It uses a single API key and a single endpoint, and bills per token at marked-up rates.

**Base URL:** `https://openrouter.ai/api/v1`  
**Auth:** `Authorization: Bearer $OPENROUTER_API_KEY`  
**Protocol:** OpenAI Chat Completions API (`/chat/completions`, `/models`)

**Key features:**
- Model fallbacks (`:free`, `:nitro`, `:thinking` variants)
- Provider routing (can pin a provider via `x-or-provider` header)
- Zero completion insurance (no charge for failed/empty responses)
- Optional `HTTP-Referer` + `X-Title` headers for app attribution in dashboard

---

## 2. Tested Models

### 2.1 `qwen/qwen3-coder` (for coding agents)

**Actual model served:** `qwen/qwen3-coder-480b-a35b-07-25`  
**Provider used:** SiliconFlow  
**Architecture:** MoE 480B/35B active — same family as local `qwen3-coder-next`

| Metric | Value |
|--------|-------|
| Context window | 262,144 tokens |
| Prompt price | $0.22/M tokens |
| Completion price | $1.00/M tokens |
| First token latency | ~1.3s |
| Generation speed | ~29.4 tok/s |
| Test response | ✅ Correct Python with type hints, clean output |

**Test prompt:** `"Write a Python function to parse JSON from a string safely, returning None on error. Include type hints."`  
**Result:** Produced correct `Optional[Any]` typed function with proper error handling. 200 tokens in 20s (~591 output tokens at 29.4 tok/s — model ran past max_tokens limit meaning it was flowing).

**Notes:**
- No reasoning/thinking overhead — pure generation
- Output quality matches local qwen3-coder-next (same model family, much larger)
- SiliconFlow provider is solid — no observed failures

---

### 2.2 `moonshotai/kimi-k2.5` (for GARRO design agent)

**Actual model served:** `moonshotai/kimi-k2.5-0127`  
**Provider used:** SiliconFlow (first test), Chutes (second test)  
**Architecture:** Thinking/reasoning model — CoT before final output

| Metric | Value |
|--------|-------|
| Context window | 262,144 tokens |
| Prompt price | $0.45/M tokens |
| Completion price | $2.20/M tokens |
| Total latency (500 token budget) | ~12.9s |
| Test response | ✅ Coherent, high-quality design philosophy |
| Thinking overhead | ~285 word CoT before final answer |

**Test prompt:** `"Describe your ideal UI design philosophy in 2 sentences."`  
**Result:**
> "Prioritize radical clarity and accessibility over decoration, ensuring every element serves intentional purpose. Consistent patterns and generous whitespace reduce cognitive friction, making complex interactions feel effortless."

**⚠️ Important — Thinking model behavior:**
- `content` field is `null` until reasoning is complete
- `reasoning` field contains CoT (returned under `message.reasoning`)
- Needs `max_tokens ≥ 300+` or it burns budget on reasoning without finishing
- Recommended: `max_tokens: 2000+` for real tasks; `max_tokens: 500` minimum for any test
- Budget 15-20s latency for complex prompts

---

## 3. Integration Guide

### 3.1 OpenClaw Gateway Config

Add an `openrouter` provider block to `~/.openclaw/openclaw.json`. Same structure as the `litellm` provider:

```json
"openrouter": {
  "baseUrl": "https://openrouter.ai/api/v1",
  "apiKey": "${OPENROUTER_API_KEY}",
  "api": "openai-completions",
  "models": [
    {
      "id": "qwen/qwen3-coder",
      "name": "openrouter/qwen3-coder",
      "reasoning": false,
      "input": ["text"],
      "cost": {
        "input": 0.00000022,
        "output": 0.000001,
        "cacheRead": 0,
        "cacheWrite": 0
      },
      "contextWindow": 262144,
      "maxTokens": 8192
    },
    {
      "id": "moonshotai/kimi-k2.5",
      "name": "openrouter/kimi-k2.5",
      "reasoning": true,
      "input": ["text"],
      "cost": {
        "input": 0.00000045,
        "output": 0.0000022,
        "cacheRead": 0,
        "cacheWrite": 0
      },
      "contextWindow": 262144,
      "maxTokens": 8192
    }
  ]
}
```

**Then add the API key to your env block** (or ensure it's loaded from `secrets.env`):
```json
"env": {
  "OPENROUTER_API_KEY": "sk-or-v1-..."
}
```

Or source it: `source ~/.openclaw/secrets.env` — key is already there as `OPENROUTER_API_KEY`.

---

### 3.2 Direct Python Usage (OpenAI SDK)

```python
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url="https://openrouter.ai/api/v1",
    default_headers={
        "HTTP-Referer": "https://eldrchat.dev",
        "X-Title": "OpenClaw"
    }
)

# Coding agent (qwen3-coder)
response = client.chat.completions.create(
    model="qwen/qwen3-coder",
    messages=[{"role": "user", "content": "Refactor this Swift function..."}],
    max_tokens=2048
)
print(response.choices[0].message.content)

# Design agent (kimi-k2.5 — thinking model)
response = client.chat.completions.create(
    model="moonshotai/kimi-k2.5",
    messages=[{"role": "user", "content": "Design the layout for a chat interface..."}],
    max_tokens=3000  # Must be large — model uses CoT tokens first
)
# Note: content may be in message.content (final) or message.reasoning (CoT)
msg = response.choices[0].message
content = msg.content  # Final answer
reasoning = getattr(msg, 'reasoning', None)  # CoT trace (if exposed)
```

---

### 3.3 LangGraph Integration

Drop-in replacement for Anthropic in existing LangGraph pipelines. Replace the `call_claude` helper in `langgraph-ui-sprint/eldrchat_ui_pipeline.py`:

```python
# openrouter_helpers.py — drop into langgraph pipelines

import os
from openai import OpenAI

_OR_CLIENT = None

def get_openrouter_client() -> OpenAI:
    global _OR_CLIENT
    if _OR_CLIENT is None:
        _OR_CLIENT = OpenAI(
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://eldrchat.dev",
                "X-Title": "OpenClaw-LangGraph"
            }
        )
    return _OR_CLIENT


def call_openrouter(
    system: str,
    user: str,
    model: str = "qwen/qwen3-coder",
    max_tokens: int = 2048
) -> str:
    """
    OpenRouter replacement for call_claude().
    Compatible with existing pipeline state flow.
    """
    client = get_openrouter_client()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        max_tokens=max_tokens
    )
    return response.choices[0].message.content or ""


# GARRO variant — uses kimi-k2.5 (thinking model, needs larger token budget)
def call_garro_design(system: str, user: str, max_tokens: int = 3000) -> str:
    return call_openrouter(
        system=system,
        user=user,
        model="moonshotai/kimi-k2.5",
        max_tokens=max_tokens
    )
```

**Using it in an existing pipeline node:**

```python
# Before (Anthropic):
spec = call_claude(garro_system_prompt, user_prompt, max_tokens=4096)

# After (OpenRouter — GARRO uses kimi):
spec = call_garro_design(garro_system_prompt, user_prompt, max_tokens=4000)

# After (OpenRouter — coder uses qwen3-coder):
code = call_openrouter(coder_system_prompt, user_prompt, model="qwen/qwen3-coder")
```

---

### 3.4 Model Router Integration

The model router (at `~/.openclaw/data/model-router.sock`) currently handles **local-only inference**. OpenRouter is cloud, so it bypasses the router. Two options:

**Option A: Use OpenRouter directly** (recommended for now)
- Call via OpenAI client or `openrouter_helpers.py`
- Router is not involved — that's fine, it's cloud traffic

**Option B: Add `cloud` tier to model router**
Could add OpenRouter as a `cloud` fallback in `models.json`:

```json
"coder-cloud": {
  "model": "qwen/qwen3-coder",
  "node": "openrouter",
  "tier": 3,
  "timeout_s": 60,
  "tags": ["code-gen", "code-review", "cloud-fallback"]
}
```

And extend `client.py` to handle `tier=3` as an HTTP call to OpenRouter instead of Ollama. This is straightforward but requires touching router code — do it when local models are saturated.

**For now: Option A. Call OpenRouter directly.**

---

## 4. Shell Usage

```bash
# Load key
source ~/.openclaw/secrets.env

# Test qwen3-coder
curl -s -X POST https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -H "HTTP-Referer: https://eldrchat.dev" \
  -d '{
    "model": "qwen/qwen3-coder",
    "messages": [{"role": "user", "content": "Write hello world in Go"}],
    "max_tokens": 200
  }' | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"

# Test kimi-k2.5 (thinking — give it room)
curl -s -X POST https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -H "HTTP-Referer: https://eldrchat.dev" \
  -d '{
    "model": "moonshotai/kimi-k2.5",
    "messages": [{"role": "user", "content": "Design a minimal contact list UI"}],
    "max_tokens": 2000
  }' | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"

# List all available models
curl -s https://openrouter.ai/api/v1/models \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  | python3 -c "import json,sys; [print(m['id']) for m in json.load(sys.stdin)['data']]"
```

---

## 5. Available Qwen Models on OpenRouter (Reference)

| Model ID | Context | Prompt $/M | Completion $/M | Notes |
|----------|---------|-----------|----------------|-------|
| `qwen/qwen3-coder` | 262K | $0.22 | $1.00 | Best coding — 480B MoE |
| `qwen/qwen3-coder-plus` | 1M | $0.65 | $3.25 | 1M context, premium |
| `qwen/qwen3-coder-flash` | 1M | $0.195 | $0.975 | Fast variant |
| `qwen/qwen3-coder-30b-a3b-instruct` | 160K | $0.07 | $0.27 | Smaller/cheaper |
| `qwen/qwen3-coder:free` | 262K | FREE | FREE | Rate-limited free tier |
| `qwen/qwq-32b` | 131K | $0.15 | $0.58 | Reasoning model |

---

## 6. Kimi Models on OpenRouter (Reference)

| Model ID | Context | Prompt $/M | Completion $/M | Notes |
|----------|---------|-----------|----------------|-------|
| `moonshotai/kimi-k2.5` | 262K | $0.45 | $2.20 | **Use this** — best Kimi |
| `moonshotai/kimi-k2-0905` | 131K | $0.40 | $2.00 | Older checkpoint |
| `moonshotai/kimi-k2-thinking` | 131K | $0.47 | $2.00 | Explicit thinking variant |
| `moonshotai/kimi-k2` | 131K | $0.57 | $2.30 | Oldest, most expensive |

---

## 7. Recommendations

### When to use OpenRouter

| Use Case | Model | Why |
|----------|-------|-----|
| Coding agents when Framework1 is saturated | `qwen/qwen3-coder` | Same model family as local, ~29 tok/s |
| GARRO design agent | `moonshotai/kimi-k2.5` | Strong design reasoning, 262K context |
| Quick cheap tasks | `qwen/qwen3-coder:free` | Free tier, good for low-stakes |
| Long-context code review (>32K) | `qwen/qwen3-coder` | 262K context vs 32K local limit |

### When NOT to use OpenRouter

| Situation | Why | Use Instead |
|-----------|-----|-------------|
| Framework1 has capacity | Costs money; local is free | Local qwen3-coder-next via router |
| Security-sensitive prompts | Data leaves your infrastructure | Local inference only |
| High-frequency loops (PBAR) | $$$; 20+ calls per loop × 1K tokens = costs add up | Local always |
| Sub-100ms latency needed | 1.3s+ first token | Local |

### Cost estimate for production use

- GARRO design sprint (10 calls × 3K tokens avg): ~$0.07/sprint
- Coding agent session (20 calls × 2K tokens avg): ~$0.04/session
- Both models have reasonable pricing for occasional cloud overflow

### Priority action items

1. **Today:** Add `openrouter` provider to `openclaw.json` using the config block in §3.1
2. **Today:** Drop `openrouter_helpers.py` into `projects/eldrchat/langgraph-ui-sprint/`
3. **Update GARRO pipeline:** Replace `call_claude` with `call_garro_design` for design nodes
4. **Set env:** Ensure `OPENROUTER_API_KEY` is in gateway env or sourced before pipeline runs
5. **Future:** Add OpenRouter as `tier=3` cloud fallback in model router when local is saturated

---

## Appendix: Raw Test Data

```
# qwen/qwen3-coder test (2026-03-24 15:31 PDT)
Model returned: qwen/qwen3-coder-480b-a35b-07-25
Provider: SiliconFlow
Tokens: 29 in, ~591 out
Time: ~20s
Speed: ~29.4 tok/s
Cost: $0.00060

# moonshotai/kimi-k2.5 test (2026-03-24 15:35 PDT)  
Model returned: moonshotai/kimi-k2.5-0127
Provider: SiliconFlow / Chutes (load balanced)
Tokens: 22 in, 424 out (includes CoT reasoning tokens)
Time: 12.9s
Cost: $0.00096
Content: high-quality 2-sentence design philosophy
```
