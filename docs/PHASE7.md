# Phase 7: Optional LLM-Powered Planning

This phase adds optional LLM-powered planning with strict safety controls.

## Overview

The agent service now supports two planning modes:

1. **Rules Mode** (default): Fast, deterministic, no external dependencies
2. **LLM Mode** (optional): Uses OpenAI/Anthropic for intelligent plan generation

The LLM planner is **OFF by default** and requires explicit configuration.

## Architecture

```
app/llm/
├── __init__.py
├── config.py           # Environment-based configuration
├── client.py           # LLMClient interface + security validation
├── prompts.py          # System/user prompts with safety rules
├── schemas.py          # Pydantic schemas for plan validation
└── providers/
    ├── __init__.py
    ├── openai_client.py    # OpenAI API client (httpx)
    └── anthropic_client.py # Anthropic API client (httpx)
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENT_PLANNER_MODE` | `"rules"` or `"llm"` | `"rules"` |
| `LLM_PROVIDER` | `"openai"`, `"anthropic"`, or `"local"` | unset |
| `LLM_API_KEY` | API key for the provider | unset |
| `LLM_MODEL` | Model to use | provider default |
| `LLM_MAX_TOKENS` | Max tokens in response | `500` |
| `LLM_TIMEOUT_S` | Request timeout in seconds | `20` |
| `LLM_MAX_PLAN_STEPS` | Maximum steps allowed | `6` |

### Enabling LLM Mode

```bash
# In /etc/agent-service.env
AGENT_PLANNER_MODE=llm
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini   # optional
```

### Fallback Behavior

If LLM mode is enabled but fails, the system **automatically falls back** to rules:

- Missing `LLM_PROVIDER` → fallback
- Missing `LLM_API_KEY` → fallback
- LLM timeout → fallback
- Invalid JSON response → fallback
- Security validation failure → fallback

The fallback reason is stored in the planner step (step 0) for debugging.

## LLM Output Contract

The LLM must return **strict JSON** matching this schema:

```json
{
  "goal": "Brief description of what we're accomplishing",
  "steps": [
    {
      "id": 1,
      "tool": "echo" | "http_fetch",
      "input": { "...tool-specific..." },
      "why": "Reason for this step"
    }
  ]
}
```

## Security Controls

### 1. Tool Allowlist

- Only `echo` and `http_fetch` tools are allowed
- LLM cannot introduce new tools
- Executor re-validates every step before execution

### 2. URL Restrictions

- `http_fetch` requires `https://` URLs only
- Private networks are blocked:
  - `127.0.0.1`, `localhost`
  - `192.168.x.x`
  - `10.x.x.x`
  - `172.16-31.x.x`
  - IPv6 loopback `[::1]`

### 3. Step Limits

- Maximum `LLM_MAX_PLAN_STEPS` (default 6) steps per plan
- Plans exceeding this are rejected

### 4. Prompt Injection Resistance

The system prompt explicitly:
- Forbids shell execution
- Forbids local network access
- Requires strict JSON output
- Limits available tools
- Instructs to use echo for clarification if unsure

### 5. No Secret Logging

- `LLM_API_KEY` is **never logged**
- Request bodies are not logged
- Response bodies are not logged
- Only metadata is logged (e.g., `provider=openai status=200`)

## API Endpoints

### New: GET /agent/plan/{job_id}

Returns planning information for an agent-mode job:

```json
{
  "job_id": "uuid",
  "planner": {
    "mode": "llm" | "rules" | "llm_fallback",
    "output": {
      "planner_mode": "llm",
      "step_count": 2,
      "fallback_reason": null  // or reason if fallback
    }
  },
  "plan": {
    "steps": [
      {"tool": "http_fetch", "description": "Fetch the page"},
      {"tool": "echo", "description": "Summarize content"}
    ],
    "total_steps": 2
  }
}
```

## Steps Tracking

When using LLM mode, steps are stored as:

| Step Number | Type | Description |
|-------------|------|-------------|
| 0 | `planner` | Planning phase metadata |
| 1+ | `echo`/`http_fetch` | Execution steps |

The planner step (step 0) contains:
- `mode`: Which planner was used
- `fallback_reason`: Why fallback occurred (if any)
- `step_count`: Number of steps generated

## Example Usage

### 1. Using Rules Mode (Default)

```bash
curl -X POST https://your-domain/agent/run \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "fetch https://example.com"}'
```

### 2. Enabling LLM Mode

```bash
# Set environment variables (on server)
export AGENT_PLANNER_MODE=llm
export LLM_PROVIDER=openai
export LLM_API_KEY=sk-...

# Restart service
sudo systemctl restart agent-service
```

### 3. Checking Plan Details

```bash
# Get job plan
curl https://your-domain/agent/plan/{job_id} \
  -H "X-API-Key: $API_KEY"
```

## Cost Controls

To minimize LLM costs:

1. **Low token limit**: Default 500 tokens max
2. **Low temperature**: 0.1 for consistent JSON output
3. **Fast timeout**: 20s default to fail fast
4. **Automatic fallback**: Rules planner handles errors gracefully

## Testing

Run LLM planner tests (no real API calls):

```bash
cd /home/elhassan/agent-service
source venv/bin/activate
pytest tests/test_llm_planner.py -v
```

## Troubleshooting

### LLM Always Falls Back

Check the planner step output:

```bash
curl https://your-domain/agent/plan/{job_id} -H "X-API-Key: $API_KEY"
```

Common issues:
- `LLM_PROVIDER not set` - Set the provider env var
- `LLM_API_KEY not set` - Set your API key
- `OpenAI API timeout` - Increase `LLM_TIMEOUT_S`
- `Invalid JSON` - Model may not support JSON mode

### View Logs

```bash
sudo journalctl -u agent-service -f | jq 'select(.message | contains("llm"))'
```

## Security Audit Checklist

- [ ] `LLM_API_KEY` not in logs
- [ ] Private IPs blocked
- [ ] Only HTTPS URLs allowed
- [ ] Tool allowlist enforced
- [ ] Step limit enforced
- [ ] Fallback works when LLM fails
