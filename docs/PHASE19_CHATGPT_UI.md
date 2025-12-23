# Phase 19: ChatGPT-style Chat UI

This document describes the implementation of Phase 19, which upgrades the `/ui/chat` endpoint to a ChatGPT-style user interface with modern design, conversation management, and robust error handling.

## Quick Start

1. **Navigate to the Chat UI**: Open `http://YOUR_SERVER:8000/ui/chat` in your browser
2. **Enter your API Key**: In the top bar, paste your API key into the input field
3. **Save the Key**: Click the **Save** button (key is stored in browser localStorage)
4. **Test the Key**: Click **Test** to verify the key works (green = valid)
5. **Start Chatting**: Type a message and press **Enter** to send

### Where to Find Your API Key

Your API key is configured in the server's environment file (`/etc/agent-service.env`):
```
AGENT_API_KEY=your-api-key-here
```

If you're an admin, you can retrieve it with:
```bash
sudo grep AGENT_API_KEY /etc/agent-service.env
```

## Features

### 🌙 Dark Mode
- Toggle between light and dark themes using the button in the sidebar
- Preference is automatically saved and persists across sessions
- Respects system preference on first visit

### 📋 Copy Messages
- Hover over any agent message to reveal a copy button
- Code blocks have their own copy button for easy copying
- Click to copy the full message content to clipboard

### 💬 Conversation Management
- Create multiple conversations with the "New Chat" button
- Switch between conversations in the sidebar
- Delete conversations you no longer need
- Conversations persist in localStorage

### ⌨️ Keyboard Shortcuts
- **Enter**: Send message
- **Shift+Enter**: New line in message

### 🎨 Modern UI
- ChatGPT-style layout with dark sidebar and light main area
- Message bubbles with timestamps (hover to see full date/time)
- Typing indicator while agent processes your request
- Smooth animations and transitions

### 📱 Mobile Friendly
- Responsive design works on all screen sizes
- Collapsible sidebar on mobile devices
- Touch-friendly interface

## Overview

Phase 19 enhances the chat interface introduced in Phase 18 with:

1. **ChatGPT-style Layout**: Left sidebar with conversations list, main chat panel
2. **Conversation Management**: Create, switch between, and delete multiple conversations
3. **Foolproof API Key Handling**: Never shows raw JSON errors, friendly warnings
4. **Rich Message Formatting**: Markdown-like rendering with code blocks, bold, italic
5. **Keyboard Shortcuts**: Enter to send, Shift+Enter for newline
6. **Persistent Storage**: All conversations saved to localStorage
7. **Real-time Status Polling**: Animated typing indicator while waiting for agent

## Features

### 1. ChatGPT-style Layout

The UI is a full-page application with:

- **Dark Sidebar (Left)**
  - New Chat button
  - Conversations list with titles
  - Delete button for each conversation
  - Links to Jobs Dashboard and API Docs

- **Main Chat Area (Right)**
  - Top bar with API key management
  - Messages container with user/agent bubbles
  - Typing indicator during agent processing
  - Auto-resizing input textarea with character count
  - Send button with loading state

### 2. API Key Management

The chat UI includes robust API key handling:

```
┌─────────────────────────────────────────────────────────────┐
│  🔑 API Key: [••••••••••••••]  [Save] [Test]  ● Connected  │
└─────────────────────────────────────────────────────────────┘
```

- **Input Field**: Password-masked input for API key
- **Save Button**: Stores key in localStorage
- **Test Button**: Validates key against `/agent/status/test-id` endpoint
- **Status Indicator**: Shows connection status (●/○ Connected/Not set)
- **Warning Banner**: Yellow warning shown when no API key is set

### 3. Conversation Management

Conversations are stored as an array in localStorage:

```javascript
// Storage keys
const CONVERSATIONS_STORAGE_KEY = 'agent_service_conversations';
const CURRENT_CONV_KEY = 'agent_service_current_conversation';

// Conversation structure
{
  id: 'conv_1234567890_abc',
  title: 'First few words...',  // Auto-generated from first message
  messages: [
    { role: 'user', content: '...', timestamp: '...' },
    { role: 'agent', content: '...', timestamp: '...' }
  ],
  createdAt: '2024-01-15T10:30:00Z',
  updatedAt: '2024-01-15T10:35:00Z'
}
```

Functions:
- `createNewConversation()`: Creates a new empty conversation
- `switchConversation(id)`: Switches to a different conversation
- `deleteConversation(id)`: Removes a conversation
- `loadConversations()`: Loads from localStorage
- `saveConversations()`: Persists to localStorage

### 4. Message Submission Flow

```
User types message
       │
       ▼
submitMessage() called
       │
       ▼
Add user message to conversation
       │
       ▼
POST /agent/run with prompt
       │
       ▼
Receive job_id
       │
       ▼
Start pollJobStatus(job_id)
       │
       ├──▶ Show typing indicator
       │
       ▼
Poll GET /agent/status/{job_id}
       │
       ├──▶ If status == "done": Add agent message, stop polling
       ├──▶ If status == "error": Show error message, stop polling
       └──▶ If status == "running"/"queued": Continue polling
```

### 5. Polling Configuration

```javascript
const MAX_POLL_TIME = 60000;  // 60 seconds timeout
const POLL_INTERVAL = 1000;   // Poll every 1 second
```

The polling shows an animated typing indicator:
```html
<div class="typing-indicator">
  <span></span><span></span><span></span>
</div>
```

### 6. Message Formatting

The `formatAgentMessage()` function provides rich text rendering:

| Markdown | Rendered |
|----------|----------|
| `` `code` `` | `<code>code</code>` |
| ` ```code block``` ` | `<pre><code>code block</code></pre>` |
| `**bold**` | `<strong>bold</strong>` |
| `*italic*` | `<em>italic</em>` |
| `- item` | `• item` |
| `1. item` | `1. item` |

All user input is HTML-escaped to prevent XSS attacks.

### 7. Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Enter | Send message |
| Shift+Enter | Insert newline |

The textarea auto-resizes as you type, up to a maximum height.

### 8. Error Handling

The UI never shows raw JSON errors. Instead:

- **No API Key**: Yellow warning banner with setup instructions
- **Invalid API Key**: Red toast notification with "Test Key" button
- **Network Error**: Friendly error message with retry suggestion
- **Timeout**: Message indicating the request took too long

### 9. Output Text Extraction

The `extractOutputText()` function ensures agent responses are always displayed as readable text, preventing `[object Object]` from being shown when the API returns structured data:

```javascript
function extractOutputText(output) {
    // Handle null/undefined
    if (!output) return null;
    
    // If output is a string, return as-is
    if (typeof output === 'string') return output;
    
    // If output is an object, try common field names
    if (typeof output === 'object') {
        if (output.final_output) return String(output.final_output);
        if (output.text) return String(output.text);
        if (output.content) return String(output.content);
        // ... etc
    }
    
    // Last resort: JSON.stringify
    return JSON.stringify(output, null, 2);
}
```

This function:
- Handles string, object, and null/undefined inputs
- Extracts text from common API response fields (`final_output`, `text`, `content`, etc.)
- Formats bullet points nicely when present
- Falls back to pretty-printed JSON for unknown structures

## API Endpoints Used

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/health` | GET | No | Test if server is running |
| `/agent/run` | POST | Yes | Submit chat message |
| `/agent/status/{job_id}` | GET | Yes | Poll for response |

## localStorage Keys

| Key | Value Type | Purpose |
|-----|------------|---------|
| `agent_service_api_key` | string | User's API key |
| `agent_service_conversations` | JSON array | All conversations |
| `agent_service_current_conversation` | string | ID of active conversation |
| `agent_service_dark_mode` | boolean | Dark mode preference |

## Styling

The UI uses:
- **Tailwind CSS** via CDN with dark mode support
- **Custom CSS** for scrollbars, animations
- **Dark sidebar** (gray-900 background)
- **Light/Dark main area** (white/gray-800 depending on mode)
- **Blue accent** for user messages
- **Gray accent** for agent messages

### CSS Animations

```css
/* Typing indicator dots */
@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-10px); }
}

/* Message fade-in */
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
```

## Responsive Design

- **Toggle Sidebar Button**: Hidden on desktop, visible on mobile
- **Sidebar**: Full-width on mobile when toggled
- **Main Area**: Adapts to available space

## Testing

Phase 19 includes 61 tests in `tests/test_phase19_chat_ui.py`:

- **TestChatPageStructure**: HTML structure tests
- **TestApiKeyUI**: API key UI elements
- **TestLocalStorageKeys**: Storage key constants
- **TestFetchWrapper**: X-API-Key header injection
- **TestKeyboardShortcuts**: Enter/Shift+Enter handling
- **TestChatFunctions**: All JavaScript functions
- **TestPollingConfiguration**: Timeout and interval values
- **TestApiEndpoints**: Endpoint references
- **TestNavigationLinks**: Sidebar navigation
- **TestMessageFormatting**: Code blocks, bold, etc.
- **TestEmptyState**: Initial empty state
- **TestNoRawJsonErrors**: Error handling
- **TestAgentEndpointAuth**: Authentication tests
- **TestUIStyles**: CSS and Tailwind
- **TestResponsiveDesign**: Mobile responsiveness

Run tests:
```bash
pytest tests/test_phase19_chat_ui.py -v
```

## Usage

1. Navigate to `/ui/chat`
2. Enter your API key in the top bar and click "Save"
3. Click "Test" to verify the key works
4. Type a message and press Enter (or click Send)
5. Wait for the agent response (typing indicator shows progress)
6. Create new conversations with the "New Chat" button
7. Switch between conversations in the sidebar

## Future Improvements

- [ ] Streaming responses (SSE)
- [ ] Message editing
- [ ] Message regeneration
- [ ] Export conversation history
- [ ] Search conversations
- [ ] Dark mode toggle
- [ ] Custom system prompts per conversation
