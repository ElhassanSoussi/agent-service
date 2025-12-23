# Phase 15: Agent Control Panel Web UI

## Overview

Phase 15 adds a web-based control panel for the Agent Service. The UI provides a user-friendly interface to:

- **View Jobs**: List all jobs with pagination and filters
- **Job Details**: View job status, execution steps, results, and citations
- **Submit Jobs**: Create new jobs in tool mode, agent mode, or builder mode
- **Download Artifacts**: Access generated files (ZIP/diff) for builder jobs
- **Copy Curl Commands**: Easy API integration with curl examples

## Architecture

The UI is built directly into the FastAPI application using:

- **Tailwind CSS** (via CDN) for modern styling
- **Pure HTML/JavaScript** - no frontend framework required
- **Same auth as API** - X-API-Key or Bearer token required

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ui` | GET | Redirect to jobs list |
| `/ui/jobs` | GET | Jobs list with pagination |
| `/ui/jobs/{job_id}` | GET | Job detail page |
| `/ui/run` | GET | New job form |
| `/ui/run/tool` | POST | Submit tool mode job |
| `/ui/run/agent` | POST | Submit agent mode job |
| `/ui/run/builder` | POST | Submit repo builder job |

## Authentication

All `/ui/*` endpoints require authentication (same as API endpoints):

### Using X-API-Key Header
```bash
# Access via curl (for testing)
curl -H "X-API-Key: your-api-key" http://localhost:8000/ui/jobs
```

### Using Browser
For browser access, you can use a browser extension to add the `X-API-Key` header, or configure a reverse proxy that adds the header.

### Example: ModHeader Extension
1. Install ModHeader browser extension
2. Add header: `X-API-Key: your-api-key`
3. Navigate to `http://localhost:8000/ui`

## Features

### Jobs List Page (`/ui/jobs`)

- **Table View**: Shows job ID, mode, status, tool, created date, and duration
- **Filters**: Filter by status (queued, running, done, error) and mode (tool, agent, builder)
- **Pagination**: Navigate through large job lists
- **Quick Actions**: Click any row to view job details

### Job Detail Page (`/ui/jobs/{job_id}`)

- **Job Info**: Full job ID, mode badge, status badge
- **Timestamps**: Created, started, completed times
- **Duration**: Total execution time
- **Input**: JSON view of job input
- **Execution Steps** (agent mode): Timeline of executed steps with tool names and outputs
- **Results**: Final output with summary and bullets
- **Citations** (agent mode): Links to sources used
- **Artifacts** (builder mode): Download links for ZIP and diff files
- **Curl Example**: Ready-to-copy curl command for API access

### New Job Form (`/ui/run`)

Three-tab interface for different job modes:

#### Tool Mode Tab
- **Tool Selector**: Dropdown with all available tools
- **Input JSON**: Text area for tool-specific input
- Example: `{"message": "Hello, World!"}`

#### Agent Mode Tab
- **Prompt**: Natural language instruction
- **Max Steps**: Number of steps (1-5)
- Example: "Search for recent AI news and summarize"

#### Repo Builder Tab
- **Repository URL**: GitHub repo URL (public repos only)
- **Branch/Tag**: Optional ref (default: main)
- **Template**: Template to apply (e.g., fastapi_api)

## UI Components

### Status Badges
- 🟡 **Queued**: Yellow background
- 🔵 **Running**: Blue background with pulse animation
- 🟢 **Done**: Green background
- 🔴 **Error**: Red background

### Mode Badges
- 🟣 **Tool**: Purple background
- 🔵 **Agent**: Indigo background
- 🔷 **Builder**: Cyan background

## Security

- All UI endpoints require authentication
- `/health` remains public (as before)
- Session state is not stored - stateless design
- API key is never displayed in the UI

## Customization

### Styling
The UI uses Tailwind CSS via CDN. To customize:

1. Fork the repo
2. Modify `app/api/ui.py`
3. Update CSS classes in the HTML templates

### Adding Tools
When new tools are added to the API:

1. Add to `ToolName` enum in `app/schemas/agent.py`
2. UI automatically picks up new tools in the dropdown

## Deployment Notes

### Requirements
No additional dependencies required for basic UI. The following are included:
- `jinja2` - For potential template expansion
- `python-multipart` - For form data handling

### Static Assets
The UI uses Tailwind CSS CDN - no static file serving required.

### Performance
- HTML pages are generated server-side
- No client-side JavaScript framework
- Fast page loads (<100ms typical)

## Screenshots

### Jobs List
```
┌─────────────────────────────────────────────────────────────┐
│ 🤖 Agent Control Panel    Jobs  New Job  API Docs ↗        │
├─────────────────────────────────────────────────────────────┤
│ Jobs                                           [+ New Job]  │
│ Showing 5 of 100 jobs                                       │
├─────────────────────────────────────────────────────────────┤
│ Filters: [Status ▼] [Mode ▼] [Apply]                       │
├─────────────────────────────────────────────────────────────┤
│ Job ID    │ Mode   │ Status │ Tool  │ Created    │ Duration│
│ abc123... │ agent  │ done   │ -     │ 2025-12-20 │ 2.5s    │
│ def456... │ tool   │ done   │ echo  │ 2025-12-20 │ 50ms    │
│ ghi789... │ builder│ running│ -     │ 2025-12-20 │ -       │
├─────────────────────────────────────────────────────────────┤
│                              [← Prev] [Next →]              │
└─────────────────────────────────────────────────────────────┘
```

### Job Detail
```
┌─────────────────────────────────────────────────────────────┐
│ ← Back to Jobs                                              │
├─────────────────────────────────────────────────────────────┤
│ Job Details                            [agent] [done]       │
│ abc12345-6789-abcd-ef01-234567890abc                        │
├─────────────────────────────────────────────────────────────┤
│ Created: 2025-12-20 10:30:00 UTC                            │
│ Started: 2025-12-20 10:30:01 UTC                            │
│ Duration: 2.5s                                              │
├─────────────────────────────────────────────────────────────┤
│ Execution Steps                                             │
│ ▌ Step 1 • web_search                         [done]        │
│ │ {"result_count": 5, "urls": [...]}                        │
│ ▌ Step 2 • web_page_text                      [done]        │
│ │ {"title": "AI News", "text_length": 5000}                 │
├─────────────────────────────────────────────────────────────┤
│ Result                                                      │
│ Found 5 articles about AI developments...                   │
│ • AI advances in natural language processing                │
│ • New models achieve state-of-the-art results               │
├─────────────────────────────────────────────────────────────┤
│ Citations                                                   │
│ • Example Article (https://example.com/ai-news)             │
├─────────────────────────────────────────────────────────────┤
│ API Example                                    [📋 Copy]    │
│ curl -X GET 'http://localhost:8000/agent/status/abc123...'  │
│   -H 'X-API-Key: YOUR_API_KEY'                              │
└─────────────────────────────────────────────────────────────┘
```

## Troubleshooting

### 401 Unauthorized
Ensure your API key is being sent. Check:
- Header name is exactly `X-API-Key`
- API key is valid and not expired
- Browser extension is active

### Form Submission Errors
- **Invalid JSON**: Ensure proper JSON syntax in tool mode input
- **Invalid Tool**: Use only tools from the dropdown
- **Invalid URL**: Use full GitHub URL (https://github.com/owner/repo)

### Missing Steps/Citations
- Steps only shown for agent mode jobs
- Citations depend on which tools were used (web_search, web_page_text)

## API Integration

The UI is complementary to the REST API. For programmatic access:

```bash
# List jobs
curl -H "X-API-Key: YOUR_KEY" http://localhost:8000/agent/jobs

# Get job status
curl -H "X-API-Key: YOUR_KEY" http://localhost:8000/agent/status/{job_id}

# Get job result
curl -H "X-API-Key: YOUR_KEY" http://localhost:8000/agent/result/{job_id}
```

See [USAGE.md](./USAGE.md) for complete API documentation.
