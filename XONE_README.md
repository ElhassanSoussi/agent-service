# XONE - Single-User AI Agent System

## Overview

Xone is a private, single-user AI agent built on Claude (Anthropic API). It features:

- **Autonomous operation** with tool use (file ops, shell commands)
- **Approval workflow** - nothing executes without explicit approval
- **Long-term memory** - stores insights, facts, and preferences
- **Conversation persistence** - full chat history in SQLite
- **Developer mode** - specialized for code tasks

---

## Architecture

```
┌────────────────────────────────────────┐
│          User (Elhassan)               │
└────────────────┬───────────────────────┘
                 ↓
┌────────────────────────────────────────┐
│      FastAPI Backend (main.py)         │
│  - API routes                          │
│  - Authentication (API key)            │
│  - Database (SQLite)                   │
└────────────┬───────────────────────────┘
             ↓
┌────────────────────────────────────────┐
│   Xone Agent API (/api/xone/*)         │
│  - Chat endpoint                       │
│  - Approval endpoint                   │
│  - Conversation management             │
└────────────┬───────────────────────────┘
             ↓
┌────────────────────────────────────────┐
│    Claude Client (Brain)               │
│  - Async streaming                     │
│  - Tool use support                    │
│  - Memory integration                  │
└────────────┬───────────────────────────┘
             ↓
┌────────────────────────────────────────┐
│   Tool System (6 tools)                │
│  - create_file                         │
│  - edit_file                           │
│  - read_file                           │
│  - run_command                         │
│  - list_files                          │
│  - remember (memory storage)           │
└────────────────────────────────────────┘
```

---

## Key Components

### 1. Claude Client (`app/llm/claude_client.py`)

The brain of Xone. Handles all communication with Claude API.

**Functions:**
- `send_message()` - Send message to Claude, get response
- `stream_message()` - Stream response from Claude
- `extract_tool_uses()` - Parse tool use blocks from response
- `extract_text()` - Get text content from response

**System Prompts:**
- `XONE_SYSTEM_PROMPT` - General AI agent prompt
- `DEVELOPER_SYSTEM_PROMPT` - Software engineer prompt

### 2. Tool System (`app/llm/tools.py`)

Defines and executes all tools available to Xone.

**Tool Definitions:**
Each tool has:
- Name
- Description
- Input schema (JSON schema)
- Risk level (low/medium/high)

**Tool Execution:**
- `execute_tool(tool_name, tool_input)` → (success, output, error)
- `assess_tool_risk(tool_name, tool_input)` → risk level

**Safety:**
- All file operations are sandboxed to project root
- Dangerous shell commands are blocked
- Risk assessment before execution

### 3. Memory System (`app/llm/memory_manager.py`)

Long-term memory storage for Xone.

**Functions:**
- `store_memory(content, category)` - Save a memory
- `retrieve_memories(category, limit)` - Get memories
- `get_relevant_memories(context)` - Find relevant memories
- `delete_memory(memory_id)` - Remove a memory

**Categories:**
- `insight` - Learnings from experience
- `preference` - User preferences
- `decision` - Past decisions
- `fact` - Important facts
- `other` - Miscellaneous

**Database:**
- Table: `xone_memories`
- Auto-updates access count
- Keyword-based search (future: embeddings)

### 4. Xone API (`app/api/xone.py`)

Main API endpoints for Xone agent.

**Endpoints:**

#### POST `/api/xone/chat`
Send message to Xone.

**Request:**
```json
{
  "message": "Create a health check endpoint",
  "conversation_id": "optional-conversation-id",
  "mode": "developer",  // or "chat"
  "stream": false
}
```

**Response (normal):**
```json
{
  "conversation_id": "conv-uuid",
  "message_id": "msg-uuid",
  "response": "Here's how I'll do that...",
  "requires_approval": false,
  "status": "ok"
}
```

**Response (needs approval):**
```json
{
  "conversation_id": "conv-uuid",
  "message_id": "msg-uuid",
  "response": "I need to create a file...",
  "proposals": [
    {
      "tool_name": "create_file",
      "tool_input": {"path": "app/api/health.py", "content": "..."},
      "risk": "medium",
      "description": "create_file: {...}"
    }
  ],
  "requires_approval": true,
  "status": "proposal"
}
```

#### POST `/api/xone/approve`
Approve or reject tool execution.

**Request:**
```json
{
  "conversation_id": "conv-uuid",
  "message_id": "msg-uuid",
  "approved": true  // or false
}
```

**Response:**
Executes tools if approved, returns final Claude response.

#### GET `/api/xone/conversations`
List all conversations.

#### GET `/api/xone/conversations/{id}/messages`
Get all messages in a conversation.

---

## Approval Workflow

```
1. User: "Add a /health endpoint"
   ↓
2. Xone analyzes request
   ↓
3. Claude proposes tool use:
   - create_file (app/api/health.py)
   - edit_file (main.py)
   ↓
4. Backend returns proposals with risk assessment
   ↓
5. User reviews and approves
   ↓
6. Backend executes tools
   ↓
7. Tool results sent back to Claude
   ↓
8. Claude generates final response
   ↓
9. Conversation saved to database
```

**Key Feature:** Tools are NEVER executed automatically. User must explicitly approve.

---

## Database Schema

### `xone_conversations`
Stores conversation sessions.

| Column      | Type | Description         |
|-------------|------|---------------------|
| id          | TEXT | UUID                |
| title       | TEXT | Conversation title  |
| created_at  | TEXT | ISO timestamp       |
| updated_at  | TEXT | ISO timestamp       |

### `xone_messages`
Individual messages within conversations.

| Column             | Type | Description              |
|--------------------|------|--------------------------|
| id                 | TEXT | UUID                     |
| conversation_id    | TEXT | FK to conversations      |
| role               | TEXT | "user" or "assistant"    |
| content            | TEXT | Message content          |
| tool_calls_json    | TEXT | JSON array of tool calls |
| created_at         | TEXT | ISO timestamp            |

### `xone_memories`
Long-term memory storage.

| Column           | Type    | Description                    |
|------------------|---------|--------------------------------|
| id               | TEXT    | UUID                           |
| content          | TEXT    | Memory content                 |
| category         | TEXT    | insight/preference/decision... |
| created_at       | TEXT    | ISO timestamp                  |
| accessed_count   | INTEGER | Access counter                 |
| last_accessed_at | TEXT    | Last access timestamp          |

---

## Environment Variables

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Optional
CLAUDE_MODEL=claude-3-5-sonnet-20241022  # Default model
LLM_PROVIDER=anthropic  # For compatibility
```

---

## Installation

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set environment variable
export ANTHROPIC_API_KEY="sk-ant-your-key-here"

# 3. Initialize database
python -c "from app.db.database import init_db; init_db()"

# 4. Run server
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## Usage Examples

### Example 1: Simple Chat

```bash
curl -X POST http://localhost:8000/api/xone/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "message": "What are the benefits of async/await in Python?",
    "mode": "chat"
  }'
```

### Example 2: File Creation (with approval)

```bash
# Step 1: Request file creation
curl -X POST http://localhost:8000/api/xone/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "message": "Create a simple health check endpoint",
    "mode": "developer"
  }'

# Response will include proposals
# {
#   "requires_approval": true,
#   "message_id": "msg-123",
#   "proposals": [...]
# }

# Step 2: Approve execution
curl -X POST http://localhost:8000/api/xone/approve \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "conversation_id": "conv-123",
    "message_id": "msg-123",
    "approved": true
  }'
```

### Example 3: Store Memory

```bash
curl -X POST http://localhost:8000/api/xone/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "message": "Remember this insight: FastAPI is better than Flask for async APIs",
    "mode": "chat"
  }'
```

---

## File Structure

```
agent-service/
├── app/
│   ├── api/
│   │   └── xone.py              # Main Xone API endpoints
│   ├── llm/
│   │   ├── claude_client.py     # Claude API client
│   │   ├── tools.py             # Tool definitions & execution
│   │   └── memory_manager.py    # Memory storage & retrieval
│   ├── db/
│   │   ├── database.py          # Database initialization
│   │   └── models.py            # SQLAlchemy models
│   └── ...
├── main.py                      # FastAPI application
├── requirements.txt             # Python dependencies
└── XONE_README.md              # This file
```

---

## Security

**API Key Authentication:**
- All endpoints require `X-API-Key` header
- Configured via environment variable

**Tool Execution Safety:**
- All file operations sandboxed to project root
- Dangerous shell commands blocked (rm -rf, sudo, etc.)
- Risk assessment before execution
- Approval required for all writes/executes

**Secrets Management:**
- API keys never logged
- Environment variables only
- No secrets in database

---

## Future Enhancements

1. **Semantic Memory Search**
   - Add embeddings to memories
   - Use vector similarity search
   - Requires: pgvector or embeddings library

2. **Streaming Responses**
   - Implement SSE streaming for chat
   - Real-time token-by-token display

3. **Multi-Step Workflows**
   - Chain multiple tool calls
   - Complex task decomposition
   - Progress tracking

4. **Web Browsing Tool**
   - Add web search capability
   - HTML fetching and parsing
   - Whitelisted domains

5. **Code Review Agent**
   - Automatic code analysis
   - Suggestion generation
   - Best practices checking

---

## Troubleshooting

### Error: "ANTHROPIC_API_KEY not set"
```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
```

### Error: "No such table: xone_conversations"
```bash
python -c "from app.db.database import init_db; init_db()"
```

### Error: "Tool execution failed"
Check:
- File paths are relative to project root
- Commands don't contain blocked patterns
- Risk level is appropriate

---

## Contact

Built by Elhassan Soussi
For issues: Check logs in `/logs/` directory

---

## License

Private use only.
