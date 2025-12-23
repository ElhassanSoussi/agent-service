# Phase 21: Xone Agent Identity, Memory & Feedback

This phase implements agent branding, persistent memory, and user feedback systems.

## Features

### A) Agent Identity (Xone)

The agent is branded as **"Xone by Elhassan Soussi"**.

**Environment Variables:**
```bash
# Agent name displayed in UI and /meta endpoint
AGENT_NAME=Xone by Elhassan Soussi

# Default system prompt for agent conversations
AGENT_SYSTEM_PROMPT_DEFAULT=You are Xone, a helpful AI assistant created by Elhassan Soussi. Be concise, accurate, and helpful.
```

**Features:**
- Agent name shown in Chat UI header
- "About" modal with provider info and privacy notice
- `/meta` endpoint includes agent info

### B) Memory System

Persistent memory for storing user preferences and conversation context.

**Database Model:**
```python
class Memory:
    id: str              # UUID
    tenant_id: str       # Multi-tenant support
    scope: str           # "global", "conversation", "user"
    conversation_id: str # For conversation-scoped memories
    key: str             # Memory key/title
    value: str           # Memory content
    tags: str            # Comma-separated tags
    created_at: str
    updated_at: str
```

**API Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/memory` | Create or update a memory |
| GET | `/memory` | List memories with filters |
| GET | `/memory/{id}` | Get specific memory |
| PUT | `/memory/{id}` | Update memory |
| DELETE | `/memory/{id}` | Delete memory |

**Query Parameters for GET /memory:**
- `scope`: Filter by scope (global, conversation, user)
- `conversation_id`: Filter by conversation
- `search`: Search in key and value
- `limit`: Max results (1-200, default 50)
- `offset`: Pagination offset

**Example - Create Memory:**
```bash
curl -X POST http://localhost:8000/memory \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{
    "key": "user_preference",
    "value": "Prefers concise answers with code examples",
    "scope": "global",
    "tags": "preference,style"
  }'
```

**Example - List Memories:**
```bash
curl http://localhost:8000/memory?scope=global \
  -H "X-API-Key: YOUR_KEY"
```

### C) Feedback System

Thumbs up/down feedback on agent responses.

**Database Model:**
```python
class Feedback:
    id: str
    tenant_id: str
    conversation_id: str
    message_id: str
    user_prompt: str      # The user's question
    agent_response: str   # The agent's answer
    rating: int           # +1 (good) or -1 (bad)
    notes: str            # Optional user notes
    created_at: str
```

**API Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/feedback` | Submit feedback |
| GET | `/feedback` | List feedback with stats |
| GET | `/feedback/stats` | Get feedback statistics |
| GET | `/feedback/{id}` | Get specific feedback |
| DELETE | `/feedback/{id}` | Delete feedback |

**Example - Submit Feedback:**
```bash
curl -X POST http://localhost:8000/feedback \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{
    "conversation_id": "conv_123",
    "message_id": "msg_456",
    "user_prompt": "What is Python?",
    "agent_response": "Python is a programming language...",
    "rating": 1
  }'
```

**Example - Get Stats:**
```bash
curl http://localhost:8000/feedback/stats \
  -H "X-API-Key: YOUR_KEY"
```

Response:
```json
{
  "total": 100,
  "positive": 85,
  "negative": 15,
  "positive_rate": 85.0
}
```

### D) Chat UI Updates

**New Features:**
1. **Header Branding**: Shows "Xone" with About button
2. **About Modal**: Displays agent name, LLM provider, model, and privacy notice
3. **Feedback Buttons**: Thumbs up/down on each agent message
4. **Privacy Notice**: "No OpenAI calls" warning when using Ollama

### E) Enhanced /meta Endpoint

The `/meta` endpoint now returns:

```json
{
  "agent_name": "Xone by Elhassan Soussi",
  "public_base_url": null,
  "computed_base_url": "http://localhost:8000",
  "listen_host": "0.0.0.0",
  "port": 8000,
  "version": "1.0.0",
  "docs_url": "http://localhost:8000/docs",
  "ui_url": "http://localhost:8000/ui",
  "health_url": "http://localhost:8000/health",
  "llm": {
    "provider": "ollama",
    "model": "llama3.2:3b",
    "planner_mode": "rules",
    "base_url": "http://127.0.0.1:11434"
  },
  "features": {
    "memory": true,
    "feedback": true,
    "streaming": true
  }
}
```

## No-OpenAI Guard

When `LLM_PROVIDER=ollama`, the system ensures:
- `/llm/generate` uses Ollama client, never OpenAI
- `/llm/stream` uses Ollama streaming
- Privacy notice in UI shows "No data sent to OpenAI"

## Files Modified/Created

| File | Change |
|------|--------|
| `app/db/models.py` | Added `Memory` and `Feedback` models |
| `app/db/database.py` | Updated `init_db()` imports |
| `app/api/memory.py` | **NEW** - Memory CRUD API |
| `app/api/feedback.py` | **NEW** - Feedback API |
| `app/api/ui.py` | Updated Chat UI with branding and feedback |
| `main.py` | Registered routers, enhanced `/meta` |
| `.env.example` | Added `AGENT_NAME`, `AGENT_SYSTEM_PROMPT_DEFAULT` |
| `docs/PHASE21_MEMORY_FEEDBACK.md` | **NEW** - This documentation |
| `tests/test_phase21_memory_feedback.py` | **NEW** - Tests |

## Running Tests

```bash
# Run Phase 21 tests
pytest tests/test_phase21_memory_feedback.py -v

# Run all tests
pytest -v
```

## Future Enhancements

1. **Memory Auto-Injection**: Automatically inject relevant memories into LLM prompts
2. **Memory UI**: Add memory management tab in settings
3. **Feedback Analytics**: Dashboard for feedback trends
4. **System Prompt Persistence**: Save system prompt per conversation in DB
5. **Learning from Feedback**: Use feedback to improve responses (without fine-tuning)
