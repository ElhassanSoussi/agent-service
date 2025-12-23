# Phase A2: Xone Command Center

## Overview

Phase A2 introduces the **Xone Command Center** - a unified single-page interface that consolidates all agent functionality into one cohesive experience. The Command Center serves as the primary interface for interacting with Xone.

## Key Features

### 1. Single-Page Command Center (`/ui/command-center`)

The Command Center provides:

- **Main Chat Area**: Full-featured chat interface for interacting with Xone
- **Left Sidebar**: Conversation management (New Chat, Search, History)
- **Right Drawer**: Tabbed panel with administrative functions

### 2. Right Drawer Tabs

The slide-out drawer on the right contains five tabs:

| Tab | Purpose |
|-----|---------|
| **Approvals** | View and manage pending action batches |
| **Jobs** | Monitor running and completed jobs |
| **Memory** | View and manage agent memory entries |
| **Audit** | Review audit logs for all actions |
| **Settings** | Configure API key, system prompt, dark mode |

### 3. Non-Negotiable Rules

> **CRITICAL**: Xone is NOT autonomous. All execution requires owner approval.

- **Approval Model**: "Approve once per batch step"
- **No Auto-Execution**: After approval, user must explicitly click "Run"
- **Server-Side Enforcement**: The `/v1/batches/{id}/run` endpoint returns `403` for unapproved batches

### 4. PWA Support

The Command Center is a Progressive Web App:

- `manifest.json` - App manifest for installation
- `sw.js` - Service worker for offline caching
- Mobile-responsive design
- Install prompts in Settings tab

## Architecture

```
/ui/command-center
├── Left Sidebar
│   ├── New Chat Button
│   ├── Search Input
│   └── Conversations List
├── Main Chat Area
│   ├── Messages Container
│   ├── Typing Indicator
│   └── Input Form
└── Right Drawer (slide-out)
    ├── Tab: Approvals
    ├── Tab: Jobs
    ├── Tab: Memory
    ├── Tab: Audit
    └── Tab: Settings
```

## API Integration

The Command Center integrates with these endpoints:

| Feature | Endpoint | Method |
|---------|----------|--------|
| Chat | `/v1/chat` | POST (streaming) |
| List Batches | `/v1/batches` | GET |
| Approve Batch | `/v1/batches/{id}/approve` | POST |
| Reject Batch | `/v1/batches/{id}/reject` | POST |
| Run Batch | `/v1/batches/{id}/run` | POST |
| List Jobs | `/v1/jobs` | GET |
| Get Memory | `/v1/memory` | GET |
| Add Memory | `/v1/memory` | POST |
| Delete Memory | `/v1/memory/{id}` | DELETE |
| Audit Logs | `/v1/audit-logs` | GET |

## File Structure

```
agent-service/
├── app/
│   └── ui/
│       ├── __init__.py
│       └── command_center.py    # Command Center UI (~1000 lines)
├── static/
│   ├── manifest.json            # PWA manifest
│   ├── sw.js                    # Service worker
│   └── icon-192.svg             # App icon
├── main.py                      # Updated with router
└── tests/
    └── test_phase_a2_command_center.py
```

## Usage

### Accessing the Command Center

Navigate to:
```
https://your-domain/ui/command-center
```

Or for local development:
```
http://localhost:8000/ui/command-center
```

### Managing Approvals

1. Click the drawer toggle (☰) to open the right panel
2. Select the "Approvals" tab
3. View pending batches with their actions
4. Click "Approve" to approve a batch
5. Click "Run" to execute an approved batch
6. Click "Reject" to reject a batch

### Configuring Settings

1. Open the drawer and select "Settings"
2. Enter your API key (stored in browser localStorage)
3. Optionally modify the system prompt
4. Toggle dark mode
5. Install as PWA using the provided instructions

## Security

### Authentication

- All API calls require the `X-API-Key` header
- API key is stored in browser localStorage
- Key must be configured before using protected features

### Approval Gate Enforcement

The server enforces approval requirements:

```python
# In /v1/batches/{id}/run endpoint
if batch.status != "approved":
    raise HTTPException(
        status_code=403,
        detail="Batch must be approved before running"
    )
```

This ensures that even if the UI is bypassed, unapproved actions cannot be executed.

## Mobile Support

The Command Center is fully responsive:

- Sidebar collapses to hamburger menu on mobile
- Drawer becomes full-screen overlay
- Touch-friendly buttons and inputs
- PWA installable on mobile devices

## Testing

Run Phase A2 tests:

```bash
pytest tests/test_phase_a2_command_center.py -v
```

Expected tests:
- UI loads successfully
- All drawer tabs present
- PWA files available
- Approval enforcement works
- Mobile responsive elements present

## Changelog

### Phase A2 (December 2024)

- Created `/ui/command-center` unified interface
- Added right drawer with 5 tabs
- Implemented PWA support (manifest, service worker)
- Added mobile responsive design
- Created comprehensive test suite
- Integrated with Phase A1 approval system

## Related Documentation

- [Phase A1: Approval Gate](PHASE_A1_APPROVAL_GATE.md) - Batch approval system
- [Phase 19: Chat UI](PHASE19_CHATGPT_UI.md) - Original chat interface
- [Phase 21: Memory & Feedback](PHASE21_MEMORY_FEEDBACK.md) - Memory system
