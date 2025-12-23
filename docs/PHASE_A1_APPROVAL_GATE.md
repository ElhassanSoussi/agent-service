# Phase A1: Approval Gate + Staged Execution + Audit Logs

## Overview

Phase A1 implements a **real, enforced approval system** for Xone (the AI agent). This ensures that:

1. **Xone can PROPOSE** batches of actions (shell commands, file writes, HTTP requests, etc.)
2. **Only a human admin can APPROVE** each batch
3. **Approval does NOT auto-execute** - it's staged
4. **Human must click "Run Now"** to execute
5. **Every action is logged** in an audit trail

## Key Concepts

### Action Batch

A batch is a collection of actions that Xone proposes. Each batch has:

- **Title**: Short description
- **Description**: Detailed explanation (optional)
- **Status**: draft → pending → approved → executing → executed/failed
- **Actions**: List of actions to execute
- **Audit Logs**: Complete history of events

### Action Types

| Kind | Description | Risk Levels |
|------|-------------|-------------|
| `shell` | Execute shell command | safe, medium, risky |
| `file_write` | Write content to a file | safe, medium, risky |
| `file_patch` | Modify existing file | safe, medium, risky |
| `http_request` | Make HTTP request | safe, medium |
| `git` | Run git command | safe, medium, risky |
| `note` | Informational note | safe |

### Status Flow

```
draft → pending → approved → executing → executed
              ↘           ↘              ↘
               rejected    (blocked)      failed
```

- `draft`: Initial state, can be edited
- `pending`: Submitted for approval, awaiting admin decision
- `approved`: Admin approved, ready to run (but NOT executed)
- `rejected`: Admin rejected, cannot run
- `executing`: Currently running actions
- `executed`: All actions completed successfully
- `failed`: One or more actions failed

## Enforcement (The Important Part)

**This is a REAL gate, not just UI.**

The backend enforces:
- `POST /v1/batches/{id}/run` returns **403 Forbidden** unless `status == "approved"`
- No actions execute until admin explicitly clicks "Run Now"
- All execution is logged in audit trail

## API Endpoints

All endpoints require `X-API-Key` header.

### Create Batch

```bash
curl -X POST http://localhost:8000/v1/batches \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Install dependencies",
    "description": "Install npm packages for the project",
    "actions": [
      {
        "kind": "shell",
        "risk": "medium",
        "payload": {"command": "npm install", "cwd": "/app"},
        "preview_text": "Run npm install in /app directory"
      }
    ],
    "created_by": "xone",
    "auto_submit": true
  }'
```

### Submit Batch (draft → pending)

```bash
curl -X POST http://localhost:8000/v1/batches/{batch_id}/submit \
  -H "X-API-Key: YOUR_API_KEY"
```

### Approve Batch (pending → approved)

```bash
curl -X POST http://localhost:8000/v1/batches/{batch_id}/approve \
  -H "X-API-Key: YOUR_API_KEY"
```

### Reject Batch (pending → rejected)

```bash
curl -X POST http://localhost:8000/v1/batches/{batch_id}/reject \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Too risky"}'
```

### Run Batch (approved → executing)

**⚠️ Only works if status is "approved"**

```bash
curl -X POST http://localhost:8000/v1/batches/{batch_id}/run \
  -H "X-API-Key: YOUR_API_KEY"
```

### List Batches

```bash
# All batches
curl http://localhost:8000/v1/batches \
  -H "X-API-Key: YOUR_API_KEY"

# Filter by status
curl "http://localhost:8000/v1/batches?status=pending" \
  -H "X-API-Key: YOUR_API_KEY"
```

### Get Batch Details

```bash
curl http://localhost:8000/v1/batches/{batch_id} \
  -H "X-API-Key: YOUR_API_KEY"
```

### List Audit Logs

```bash
# All logs
curl http://localhost:8000/v1/audit-logs \
  -H "X-API-Key: YOUR_API_KEY"

# Filter by batch
curl "http://localhost:8000/v1/audit-logs?batch_id={batch_id}" \
  -H "X-API-Key: YOUR_API_KEY"

# Filter by event type
curl "http://localhost:8000/v1/audit-logs?event_type=batch_approved" \
  -H "X-API-Key: YOUR_API_KEY"
```

## Web UI

### Pages

| URL | Description |
|-----|-------------|
| `/ui/approvals` | Pending batches queue (approval dashboard) |
| `/ui/batches` | All batches with status filters |
| `/ui/batches/{id}` | Batch detail with approve/reject/run buttons |

### Features

- **Mobile-friendly** responsive design
- **Status badges** with color coding
- **Risk indicators** (safe=green, medium=yellow, risky=red)
- **Action preview** with payload details
- **Audit log stream** showing all events
- **Action buttons** that appear based on batch status

### Chat UI Banner

The chat UI (`/ui/chat`) includes a banner:

> 🛡️ **Approval Gate**: Xone proposes batches. You approve + run.

## How It Works

### 1. Xone Proposes a Batch

When Xone wants to perform actions, it creates a batch:

```json
{
  "title": "Fix bug in auth module",
  "description": "Apply patches to fix login issue",
  "actions": [
    {
      "kind": "file_patch",
      "risk": "medium",
      "payload": {
        "path": "src/auth.py",
        "modified": "... new content ..."
      },
      "preview_text": "Patch src/auth.py to fix login validation"
    },
    {
      "kind": "shell",
      "risk": "safe",
      "payload": {"command": "pytest tests/test_auth.py"},
      "preview_text": "Run auth tests to verify fix"
    }
  ],
  "created_by": "xone",
  "auto_submit": true
}
```

### 2. Admin Reviews

Admin visits `/ui/approvals` or `/ui/batches` to see pending batches.

The batch detail page shows:
- All actions with their risk levels
- Payload details (expandable)
- Audit log of all events

### 3. Admin Approves or Rejects

- **Approve**: Click "✓ Approve" button
- **Reject**: Click "✕ Reject" button (can add reason)

**Approval does NOT execute anything!**

### 4. Admin Runs (Staged Execution)

Only after approval, admin can click "▶️ Run Now" to execute.

This triggers sequential execution of all actions:
1. Each action runs one at a time
2. Success/failure is logged
3. If any action fails, remaining actions are skipped
4. Final status is `executed` or `failed`

## Database Schema

### action_batches

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT | UUID primary key |
| tenant_id | TEXT | Multi-tenant FK |
| title | TEXT | Batch title |
| description | TEXT | Detailed description |
| created_by | TEXT | "xone" or "admin" |
| status | TEXT | draft/pending/approved/rejected/executing/executed/failed |
| created_at | TEXT | ISO timestamp |
| updated_at | TEXT | ISO timestamp |
| approved_at | TEXT | When approved |
| approved_by | TEXT | Who approved |
| executed_at | TEXT | When executed |
| execution_summary | TEXT | Result summary |

### batch_actions

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT | UUID primary key |
| batch_id | TEXT | FK to action_batches |
| seq | INTEGER | Sequence number |
| kind | TEXT | shell/file_write/file_patch/http_request/git/note |
| risk | TEXT | safe/medium/risky |
| payload_json | TEXT | Action details as JSON |
| preview_text | TEXT | Human-readable description |
| status | TEXT | pending/running/done/error/skipped |
| output_summary | TEXT | Execution output |
| error | TEXT | Error message if failed |
| created_at | TEXT | ISO timestamp |
| started_at | TEXT | When started |
| completed_at | TEXT | When completed |

### audit_logs

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT | UUID primary key |
| ts | TEXT | ISO timestamp |
| actor | TEXT | "xone", "admin", or "system" |
| event_type | TEXT | Event type (see below) |
| batch_id | TEXT | FK to action_batches |
| action_id | TEXT | FK to batch_actions |
| message | TEXT | Human-readable message |
| data_json | TEXT | Additional JSON data |

### Event Types

- `batch_created`: Batch was created
- `batch_submitted`: Batch submitted for approval
- `batch_approved`: Admin approved batch
- `batch_rejected`: Admin rejected batch
- `batch_run_requested`: Admin clicked Run
- `action_started`: Individual action started
- `action_finished`: Individual action completed
- `batch_finished`: All actions completed successfully
- `batch_failed`: Batch execution failed

## Security Considerations

1. **All API endpoints require X-API-Key**
2. **UI escapes all output** to prevent XSS
3. **Shell commands run with timeout** (60 seconds)
4. **No arbitrary code execution** - must go through batch system
5. **Complete audit trail** of all operations

## Testing

Run the tests:

```bash
# Run all Phase A1 tests
python -m pytest tests/test_phase_a1_approval.py -v

# Run specific test class
python -m pytest tests/test_phase_a1_approval.py::TestEnforcement -v

# Run with output
python -m pytest tests/test_phase_a1_approval.py -v -s
```

Key test cases:
- Cannot run draft batch → 403
- Cannot run pending batch → 403
- Cannot run rejected batch → 403
- Can run approved batch → 200
- Approval moves pending → approved
- All events logged in audit trail

## Verification Commands

```bash
# 1. Create a batch
curl -X POST http://localhost:8000/v1/batches \
  -H "X-API-Key: test-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test batch",
    "actions": [
      {"kind": "note", "risk": "safe", "payload": {"note": "Hello!"}, "preview_text": "Say hello"}
    ],
    "auto_submit": true
  }'

# 2. Try to run without approval (should fail with 403)
curl -X POST http://localhost:8000/v1/batches/{BATCH_ID}/run \
  -H "X-API-Key: test-api-key"

# 3. Approve the batch
curl -X POST http://localhost:8000/v1/batches/{BATCH_ID}/approve \
  -H "X-API-Key: test-api-key"

# 4. Run the batch (should succeed now)
curl -X POST http://localhost:8000/v1/batches/{BATCH_ID}/run \
  -H "X-API-Key: test-api-key"

# 5. Check audit log
curl "http://localhost:8000/v1/audit-logs?batch_id={BATCH_ID}" \
  -H "X-API-Key: test-api-key"
```

## URLs to Check in Browser

- http://localhost:8000/ui/approvals - Pending batches
- http://localhost:8000/ui/batches - All batches
- http://localhost:8000/ui/chat - Chat with approval banner
- http://localhost:8000/docs - API documentation
