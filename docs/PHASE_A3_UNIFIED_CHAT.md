# Phase A3: Unified /ui/chat as Command Center

## Overview

Phase A3 unifies the UI experience by making `/ui/chat` serve the same Command Center interface as `/ui/command-center`. Users now have a single, unified interface for all agent interactions.

## What Changed

### Before (Phase A2)
- `/ui/chat` - Old chat interface (standalone)
- `/ui/command-center` - New unified Command Center

### After (Phase A3)
- `/ui/chat` - **Now serves the Command Center UI**
- `/ui/command-center` - Same Command Center UI
- Both routes return identical HTML

### Key Changes

1. **`/ui/chat` now loads Command Center**
   - Route handler updated to call `get_command_center_html()`
   - Old 1400+ lines of inline HTML removed
   - File size reduced from 2490 to 1068 lines

2. **Visible "Agent Control Panel" header**
   - Header shows "Agent Control Panel" title
   - "Command Center" badge clearly visible
   - User immediately sees this is the new unified UI

3. **Right drawer accessible from chat**
   - Drawer toggle button in header
   - 5 tabs: Approvals, Jobs, Memory, Audit, Settings
   - Control everything without navigating away

## How to Verify

### URLs to Check

| URL | Expected |
|-----|----------|
| `/ui/chat` | Shows Command Center with "Agent Control Panel" header |
| `/ui/command-center` | Same content as `/ui/chat` |

### Visual Checklist

- [ ] Header shows "Agent Control Panel" with "Command Center" badge
- [ ] Left sidebar has conversations list, search, "New Chat" button
- [ ] Main area has chat input and messages
- [ ] Drawer toggle button visible (☰ icon in header)
- [ ] Clicking drawer toggle opens right panel
- [ ] Drawer has 5 tabs: Approvals, Jobs, Memory, Audit, Settings
- [ ] Approval banner shows "Xone proposes → You approve → You run"
- [ ] Dark mode toggle works
- [ ] API key input visible

### Terminal Verification

```bash
# Check /ui/chat returns 200
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:8000/ui/chat

# Check /ui/chat has Command Center markers
curl -s http://127.0.0.1:8000/ui/chat | grep -o "Agent Control Panel"
curl -s http://127.0.0.1:8000/ui/chat | grep -o "Command Center"

# Verify both routes return same content
diff <(curl -s http://127.0.0.1:8000/ui/chat) <(curl -s http://127.0.0.1:8000/ui/command-center)
# Should output nothing (no differences)
```

## How the Drawer Works

### Opening the Drawer

1. Click the drawer toggle button (☰) in the top-right header
2. Drawer slides in from the right
3. On mobile, drawer covers the full screen with overlay

### Drawer Tabs

| Tab | Purpose | API Endpoints Used |
|-----|---------|-------------------|
| **Approvals** | View pending batches, approve/reject/run | `GET /v1/batches?status=pending`, `POST /v1/batches/{id}/approve` |
| **Jobs** | View agent/builder jobs | `GET /agent/jobs`, `GET /builder/jobs` |
| **Memory** | Search/add/delete agent memory | `GET /memory`, `POST /memory`, `DELETE /memory/{id}` |
| **Audit** | View audit logs | `GET /v1/audit-logs` |
| **Settings** | API key, system prompt, streaming, PWA install | Client-side localStorage |

### Closing the Drawer

- Click the X button in drawer header
- Click outside the drawer (on overlay)
- Press Escape key

## Non-Negotiable Rules

> **Xone is NOT autonomous**

The approval model remains enforced:

1. **Xone proposes** - Agent suggests actions in batches
2. **You approve** - Owner reviews and approves each batch
3. **You run** - Owner explicitly clicks "Run" to execute

Server-side enforcement ensures unapproved batches cannot execute:

```python
# /v1/batches/{id}/run returns 403 if not approved
if batch.status != "approved":
    raise HTTPException(status_code=403, detail="Batch must be approved before running")
```

## Files Changed

| File | Change |
|------|--------|
| `app/api/ui.py` | Replaced `/ui/chat` handler to use `get_command_center_html()` |
| `app/ui/command_center.py` | Updated header to show "Agent Control Panel" + "Command Center" badge |
| `tests/test_phase_a3_unified_chat.py` | **NEW** - 21 tests for unified UI |
| `docs/PHASE_A3_UNIFIED_CHAT.md` | **NEW** - This documentation |

## Test Results

```bash
pytest tests/test_phase_a3_unified_chat.py -v
# 21 passed
```

Tests verify:
- `/ui/chat` returns HTTP 200
- Contains "Agent Control Panel" header
- Contains "Command Center" badge
- Has all drawer tabs
- Same content as `/ui/command-center`
- Approval enforcement works

## Related Documentation

- [Phase A1: Approval Gate](PHASE_A1_APPROVAL_GATE.md) - Batch approval system
- [Phase A2: Command Center](PHASE_A2_COMMAND_CENTER.md) - Command Center implementation
