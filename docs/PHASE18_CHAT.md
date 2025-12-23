# Phase 18: Chat UI

## Overview

Phase 18 adds a **Chat UI** to the Agent Control Panel, providing a conversational interface for interacting with the agent. Users can type prompts, submit them to the agent, and see responses in a chat-style message transcript.

## Features

### Chat Interface (`/ui/chat`)

- **Message Transcript**: Displays a scrollable list of messages with user and agent bubbles
- **Input Box**: Text input for typing prompts with a Send button
- **New Chat Button**: Clears the transcript and starts a fresh conversation
- **Real-time Status**: Shows job status while waiting for agent response
- **localStorage Persistence**: Messages are saved to browser localStorage under `agent_service_chat_messages`

### Message Styling

- **User Messages**: Blue bubbles aligned to the right
- **Agent Messages**: Gray bubbles aligned to the left
- **Timestamps**: Each message shows when it was sent
- **Job Links**: Agent responses include links to view the full job details

### API Integration

The chat interface uses the existing agent API endpoints:

1. **Submit Job**: `POST /agent/run` with `{mode: "agent", prompt: "..."}`
2. **Poll Status**: `GET /agent/status/{job_id}` every ~1 second
3. **Timeout**: 60 seconds maximum polling time

### Authentication

- **API Key Required**: Chat functionality requires an API key set in the navbar
- **Warning Banner**: Shows when no API key is configured
- **Client-side Auth**: API key is automatically attached to fetch requests via the global fetch override

## Usage

### Setting Up

1. Navigate to `/ui/chat`
2. Enter your API key in the navbar input field (top right)
3. Click "Save" to store the key in localStorage

### Starting a Conversation

1. Type your prompt in the input box at the bottom
2. Click "Send" or press Enter
3. Wait for the agent to process your request
4. View the response in the chat transcript

### Example Prompts

```
What tools are available?
Summarize the contents of https://example.com
Search the web for Python best practices
```

### Clearing History

Click the "New Chat" button to clear all messages and start fresh.

## Technical Details

### localStorage Keys

| Key | Description |
|-----|-------------|
| `agent_service_api_key` | User's API key for authentication |
| `agent_service_chat_messages` | JSON array of chat messages |

### Message Format

```json
{
  "id": "1703123456789",
  "role": "user|agent",
  "content": "Message text...",
  "timestamp": "2024-12-21T10:30:00.000Z",
  "jobId": "job-uuid-here"  // Only for agent messages
}
```

### Polling Configuration

| Setting | Value | Description |
|---------|-------|-------------|
| `POLL_INTERVAL` | 1000ms | Time between status checks |
| `MAX_POLL_TIME` | 60000ms | Maximum time to wait for completion |

### Error Handling

- **No API Key**: Shows error message in chat
- **API Errors**: Displays error details from server response
- **Timeouts**: Shows timeout message with link to job details
- **Network Errors**: Caught and displayed in chat

## Navigation

The Chat link appears in the navbar alongside:
- **Jobs**: View all jobs
- **New Job**: Create jobs via form (tool, agent, builder modes)
- **Chat**: Conversational agent interface
- **API Docs**: OpenAPI documentation

## Files Changed

| File | Changes |
|------|---------|
| `app/api/ui.py` | Added Chat nav link, `chat_active` param, `/ui/chat` route |
| `tests/test_phase18_chat.py` | 25 tests for chat functionality |
| `docs/PHASE18_CHAT.md` | This documentation |

## Tests

Run the Phase 18 tests:

```bash
python -m pytest tests/test_phase18_chat.py -v
```

### Test Coverage

- Chat route accessibility (200 status)
- HTML content and required elements
- API key warning presence
- localStorage key constants
- Polling logic functions
- Navigation links across pages
- Agent endpoint authentication requirements
- Integration with job system

## Security Considerations

1. **API Key Storage**: Keys are stored in browser localStorage (client-side only)
2. **Server Validation**: All API calls are validated server-side with the API key
3. **No Server-Side State**: Chat history is client-side only
4. **XSS Prevention**: Message content is HTML-escaped before rendering
