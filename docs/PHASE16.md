# Phase 16: Safe Build Runner

## Overview

Phase 16 implements a safe, deterministic build runner that executes predefined CI-style pipelines (install dependencies, lint, test, build) on repositories without allowing arbitrary command execution.

## Security Features

### Domain Allowlist
Only repositories from trusted domains are allowed:
- `github.com`
- `codeload.github.com` (for downloads)
- `gitlab.com`

All other domains are rejected.

### No Shell Execution
All commands are executed using `subprocess.run()` with a list of arguments, **never** `shell=True`:

```python
# SAFE: List-based command execution
subprocess.run(["npm", "ci"], cwd=workspace, env=safe_env)

# REJECTED: Shell string execution (NOT USED)
subprocess.run("npm ci", shell=True)  # NEVER!
```

### Isolated Workspaces
Each job gets its own workspace directory:
- Path: `data/workspaces/{job_id}/`
- Auto-cleanup: 24 hours
- No cross-job access

### Command Timeouts
- Per-command timeout: 5 minutes
- Total build timeout: 15 minutes
- Prevents DoS via infinite loops

### Sanitized Environment
Subprocess environment includes only safe variables:
- `PATH`: `/usr/local/bin:/usr/bin:/bin`
- `HOME`: `/tmp`
- `CI`: `true`
- `NODE_ENV`: `test`
- `PYTHONDONTWRITEBYTECODE`: `1`

### No Secrets in Logs
Build logs are saved as artifacts but are designed to avoid capturing secrets.

## Implementation

### Files Created/Modified

| File | Description |
|------|-------------|
| `app/core/build_runner.py` | Core build runner implementation (~1000 lines) |
| `app/api/builder.py` | API endpoints for build runner |
| `app/core/planner.py` | Planner integration for build requests |
| `app/api/ui.py` | Web UI integration (Build Runner tab) |
| `tests/test_phase16.py` | Comprehensive test suite (64 tests) |
| `docs/PHASE16.md` | This documentation |

### Core Components

#### `validate_repo_url(url)`
Validates repository URL against domain allowlist:
- Checks HTTPS scheme
- Validates domain against allowlist
- Extracts owner/repo from path
- Validates owner/repo characters

#### `WorkspaceManager`
Manages isolated workspaces:
- `create_workspace(job_id)`: Create new workspace
- `get_workspace(job_id)`: Get existing workspace
- `cleanup_workspace(job_id)`: Remove workspace
- `cleanup_old_workspaces()`: Remove workspaces older than 24h

#### `detect_project_type(workspace)`
Detects project type from files:
- **Python**: `pyproject.toml`, `requirements.txt`, `setup.py`
- **Node.js**: `package.json`
- Python takes priority when both exist

#### `run_command(cmd, cwd, timeout)`
Safe command execution:
- Takes list (NOT string)
- Uses sanitized environment
- Captures stdout/stderr
- Handles timeouts

#### `build_python_pipeline(workspace, metadata)`
Creates Python pipeline steps:
1. **setup**: Create venv
2. **install**: pip install dependencies
3. **test**: Run pytest

#### `build_node_pipeline(workspace, metadata)`
Creates Node.js pipeline steps:
1. **install**: npm ci / npm install
2. **lint**: npm run lint (if exists)
3. **test**: npm test (if exists)
4. **build**: npm run build (if exists)

## API Endpoints

### POST /builder/build
Start a build runner job.

**Request:**
```json
{
  "repo_url": "https://github.com/owner/repo",
  "ref": "main",
  "pipeline": "auto"
}
```

**Response (202 Accepted):**
```json
{
  "job_id": "uuid",
  "status": "queued",
  "message": "Build runner job created",
  "repo_url": "https://github.com/owner/repo",
  "ref": "main",
  "pipeline": "auto",
  "status_url": "/builder/build/{job_id}/status",
  "logs_url": "/builder/build/{job_id}/logs"
}
```

### GET /builder/build/{job_id}/status
Get build status and pipeline steps.

**Response:**
```json
{
  "job_id": "uuid",
  "status": "done",
  "project_type": "python",
  "pipeline_steps": [
    {
      "name": "setup",
      "status": "success",
      "duration_ms": 2500,
      "commands": [...]
    }
  ],
  "overall_status": "success",
  "total_duration_ms": 22500
}
```

### GET /builder/build/{job_id}/logs
Get full build logs.

### GET /builder/build/{job_id}/logs/download
Download build logs as file.

## Web UI Integration

The Build Runner is available in the Agent Control Panel at `/ui/run`:
- Fourth tab: "Build Runner"
- Form fields: Repository URL, Branch/Tag, Pipeline Type
- Green submit button: "🚀 Run Build Pipeline"

## Planner Integration

The agent planner detects build/test requests:
- Keywords: "run tests", "verify build", "run pytest", "npm test", etc.
- Extracts GitHub/GitLab URLs from prompts
- Creates `build_tool` plan step

## Tests

64 comprehensive tests in `tests/test_phase16.py`:

### Test Categories

1. **Repo URL Validation** (12 tests)
   - Valid GitHub/GitLab URLs
   - HTTP rejection
   - Unknown domain rejection
   - SSRF protection (localhost, private IPs)

2. **Path Safety** (4 tests)
   - Relative path acceptance
   - Absolute path rejection
   - Path traversal prevention

3. **Project Detection** (6 tests)
   - Python detection
   - Node.js detection
   - Unknown project handling
   - Priority rules

4. **Pipeline Builder** (3 tests)
   - Python pipeline steps
   - Node.js pipeline steps
   - Script availability detection

5. **Command Execution** (7 tests)
   - Success/failure handling
   - Shell injection prevention
   - Timeout handling
   - Environment sanitization

6. **Build Logs** (2 tests)
   - Log saving
   - SHA256 generation

7. **Workspace Manager** (4 tests)
   - Create/get/cleanup operations

8. **Planner Integration** (11 tests)
   - Build request detection
   - URL extraction
   - Plan generation

9. **API Endpoints** (6 tests)
   - Job creation
   - Validation errors
   - Authentication

10. **Security** (5 tests)
    - Shell injection
    - SSRF
    - Timeout DoS prevention

11. **UI Integration** (3 tests)
    - Tab presence
    - Form fields
    - Error handling

## Running Tests

```bash
# Run all Phase 16 tests
pytest tests/test_phase16.py -v

# Run with coverage
pytest tests/test_phase16.py -v --cov=app.core.build_runner
```

## Non-Goals (Security Boundaries)

The following are explicitly NOT supported:
- ❌ `shell=True` anywhere
- ❌ Arbitrary command execution
- ❌ Storing secrets in logs
- ❌ Cloning from unknown domains
- ❌ Cross-workspace file access
- ❌ Unlimited execution time

## Future Enhancements

Potential improvements for future phases:
- [ ] Custom pipeline definitions (YAML-based, predefined commands only)
- [ ] Artifact upload to object storage
- [ ] Webhook notifications on completion
- [ ] Pipeline caching for faster builds
- [ ] Support for more project types (Go, Rust, etc.)
