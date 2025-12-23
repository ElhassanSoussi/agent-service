# Phase 20: Local Agent Chat UI

This phase completes the integration of the ChatGPT-style chat UI with the local Ollama LLM, ensuring the agent runs entirely on your own infrastructure with no external API calls.

## Features

### 1. Provider/Model Badge
- Shows current LLM provider and model in the chat header
- Automatically fetched from `/llm/health` endpoint
- Visual indicator (green badge with pulse) when connected

### 2. System Prompt Settings
- Custom system prompt stored in localStorage
- Accessible via Settings button in sidebar
- Sent with every message to customize AI behavior

### 3. Streaming Mode
- Real-time token streaming for Ollama provider
- SSE (Server-Sent Events) based streaming
- Toggle in Settings modal
- Shows typing cursor while streaming

### 4. Provider Guard
- When `LLM_PROVIDER=ollama`, OpenAI code is never called
- Strict provider routing in `/llm/generate` and `/llm/stream`
- No external API calls when using local LLM

## Configuration

### Environment Variables

```bash
# Required for Ollama
LLM_PROVIDER=ollama
LLM_BASE_URL=http://127.0.0.1:11434
LLM_MODEL=llama3.2:3b

# Optional
LLM_TIMEOUT_S=120
AGENT_PLANNER_MODE=llm  # or "rules" for rule-based planning
```

### System Service Configuration

For systemd service, edit `/etc/agent-service.env`:

```bash
LLM_PROVIDER=ollama
LLM_BASE_URL=http://127.0.0.1:11434
LLM_MODEL=llama3.2:3b
LLM_TIMEOUT_S=120
```

Then restart:
```bash
sudo systemctl restart agent-service
```

## API Endpoints

### GET /llm/health
Check LLM service status (public, no auth required).

```bash
curl http://localhost:8000/llm/health
```

Response:
```json
{
  "status": "ok",
  "provider": "ollama",
  "model": "llama3.2:3b",
  "base_url": "http://127.0.0.1:11434",
  "message": "Ollama is running. Models available: llama3.2:3b",
  "planner_mode": "rules"
}
```

### POST /llm/generate
Generate text response (requires API key).

```bash
curl -X POST http://localhost:8000/llm/generate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"prompt": "What is the capital of France?", "system_prompt": "Be concise."}'
```

Response:
```json
{
  "status": "ok",
  "response": "The capital of France is Paris.",
  "error": null,
  "provider": "ollama",
  "model": "llama3.2:3b"
}
```

### POST /llm/stream
Stream text response via SSE (requires API key, Ollama only).

```bash
curl -X POST http://localhost:8000/llm/stream \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"prompt": "Explain quantum computing"}'
```

Returns Server-Sent Events:
```
data: Quantum
data:  computing
data:  is
data: ...
data: [DONE]
```

## Setup Instructions

### 1. Install Ollama

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull llama3.2:3b

# Verify it's running
curl http://127.0.0.1:11434/api/tags
```

### 2. Configure Agent Service

```bash
# Edit environment file
sudo nano /etc/agent-service.env

# Add:
LLM_PROVIDER=ollama
LLM_BASE_URL=http://127.0.0.1:11434
LLM_MODEL=llama3.2:3b
LLM_TIMEOUT_S=120

# Restart service
sudo systemctl restart agent-service
```

### 3. Verify Setup

```bash
# Check LLM health
curl http://localhost:8000/llm/health

# Expected: {"status":"ok","provider":"ollama","model":"llama3.2:3b",...}
```

### 4. Test Chat UI

1. Open http://YOUR_SERVER:8000/ui/chat
2. Enter your API key in the top bar
3. Click "Save" then "Test"
4. You should see the provider badge showing "ollama / llama3.2:3b"
5. Send a message to test

## Verification Commands

```bash
# 1. Check Ollama is running
systemctl status ollama
curl http://127.0.0.1:11434/api/tags

# 2. Check Agent Service health
curl http://localhost:8000/health
curl http://localhost:8000/llm/health

# 3. Test generation (replace YOUR_KEY)
curl -X POST http://localhost:8000/llm/generate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{"prompt": "Hello, who are you?"}'

# 4. Run tests
cd /home/elhassan/agent-service
python -m pytest tests/test_phase20_local_agent.py -v
```

## UI Features

### Chat Interface
- Provider/model badge in header
- Settings modal (gear icon in sidebar)
- System prompt customization
- Streaming mode toggle
- Dark/light mode
- Conversation history (localStorage)
- Markdown rendering
- Code syntax highlighting
- Copy message/code buttons

### Settings
- **System Prompt**: Customize AI behavior (e.g., "You are a helpful coding assistant")
- **Streaming Mode**: Enable real-time token streaming (Ollama only)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Chat UI (/ui/chat)                    │
│  ┌──────────────┐  ┌─────────────┐  ┌────────────────┐ │
│  │ Provider     │  │ System      │  │ Streaming      │ │
│  │ Badge        │  │ Prompt      │  │ Mode           │ │
│  └──────────────┘  └─────────────┘  └────────────────┘ │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                   FastAPI Backend                        │
│  ┌──────────────┐  ┌─────────────┐  ┌────────────────┐ │
│  │ /llm/health  │  │ /llm/       │  │ /llm/stream    │ │
│  │ (public)     │  │ generate    │  │ (SSE)          │ │
│  └──────────────┘  └─────────────┘  └────────────────┘ │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              LLM Provider Router                         │
│  ┌────────────────────────────────────────────────────┐ │
│  │  if provider == "ollama":                          │ │
│  │      → ollama_client.py (NEVER calls OpenAI)       │ │
│  │  elif provider == "openai":                        │ │
│  │      → openai_client.py (requires API key)         │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                 Ollama Server                            │
│               http://127.0.0.1:11434                     │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Model: llama3.2:3b (or your chosen model)         │ │
│  │  100% Local - No external API calls                │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## Security Notes

- System prompt is stored in browser localStorage (client-side only)
- API key is required for `/llm/generate` and `/llm/stream`
- `/llm/health` is public for monitoring
- All LLM traffic stays on local network when using Ollama

## Troubleshooting

### Provider badge not showing
- Check `/llm/health` returns status "ok"
- Verify Ollama is running: `curl http://127.0.0.1:11434/api/tags`

### Streaming not working
- Ensure `LLM_PROVIDER=ollama` (streaming only supported for Ollama)
- Enable streaming in Settings modal
- Check browser console for errors

### Slow responses
- Increase `LLM_TIMEOUT_S` in environment
- Use a smaller model (e.g., `llama3.2:1b`)
- Check system resources (RAM, CPU)

### "Cannot connect to Ollama"
- Verify Ollama service: `systemctl status ollama`
- Check base URL: `curl http://127.0.0.1:11434/api/tags`
- Ensure `LLM_BASE_URL` matches Ollama's address
