"""
Agent Control Panel - Web UI for job management.
Provides HTML pages for viewing and managing jobs.
UI pages are PUBLIC (no server-side auth). API calls from UI use client-side API key stored in localStorage.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.jobs import job_store, JobStatus
from app.schemas.agent import JobMode, ToolName
from app.core.executor import get_job_steps, get_job_result_with_citations

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ui", tags=["ui"])


def get_tenant_id(request: Request) -> str:
    """Get tenant_id from request state, set by auth middleware."""
    auth_context = getattr(request.state, "auth", None)
    if auth_context:
        return auth_context.tenant_id
    return "legacy"


def format_datetime(dt: Optional[datetime]) -> str:
    """Format datetime for display."""
    if not dt:
        return "-"
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def format_duration(ms: Optional[int]) -> str:
    """Format duration in milliseconds."""
    if not ms:
        return "-"
    if ms < 1000:
        return f"{ms}ms"
    elif ms < 60000:
        return f"{ms/1000:.1f}s"
    else:
        return f"{ms/60000:.1f}m"


def status_badge_class(status: str) -> str:
    """Get Tailwind CSS classes for status badge."""
    return {
        "queued": "bg-yellow-100 text-yellow-800",
        "running": "bg-blue-100 text-blue-800 animate-pulse",
        "done": "bg-green-100 text-green-800",
        "error": "bg-red-100 text-red-800",
    }.get(status, "bg-gray-100 text-gray-800")


def mode_badge_class(mode: str) -> str:
    """Get Tailwind CSS classes for mode badge."""
    return {
        "tool": "bg-purple-100 text-purple-800",
        "agent": "bg-indigo-100 text-indigo-800",
        "builder": "bg-cyan-100 text-cyan-800",
    }.get(mode, "bg-gray-100 text-gray-800")


# Base HTML template with Tailwind CSS

# Base HTML template with Tailwind CSS and API Key authentication
BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" class="h-full bg-gray-50">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Agent Control Panel</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .fade-in {{ animation: fadeIn 0.3s ease-in; }}
        @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
        .code-block {{ font-family: ui-monospace, monospace; font-size: 0.875rem; }}
    </style>
    <script>
        // API Key management
        const API_KEY_STORAGE_KEY = 'agent_service_api_key';
        
        function getApiKey() {{
            return localStorage.getItem(API_KEY_STORAGE_KEY) || '';
        }}
        
        function setApiKey(key) {{
            if (key) {{
                localStorage.setItem(API_KEY_STORAGE_KEY, key);
            }} else {{
                localStorage.removeItem(API_KEY_STORAGE_KEY);
            }}
            updateApiKeyUI();
        }}
        
        function updateApiKeyUI() {{
            const key = getApiKey();
            const input = document.getElementById('apiKeyInput');
            const status = document.getElementById('apiKeyStatus');
            
            if (input) input.value = key;
            if (status) {{
                if (key) {{
                    status.textContent = '✓ Key set';
                    status.className = 'text-xs text-green-600';
                }} else {{
                    status.textContent = '⚠ No key';
                    status.className = 'text-xs text-yellow-600';
                }}
            }}
        }}
        
        // Override fetch to automatically add API key header
        const originalFetch = window.fetch;
        window.fetch = function(url, options = {{}}) {{
            const apiKey = getApiKey();
            if (apiKey) {{
                options.headers = options.headers || {{}};
                if (options.headers instanceof Headers) {{
                    options.headers.set('X-API-Key', apiKey);
                }} else {{
                    options.headers['X-API-Key'] = apiKey;
                }}
            }}
            return originalFetch(url, options);
        }};
        
        // Initialize on page load
        document.addEventListener('DOMContentLoaded', function() {{
            updateApiKeyUI();
            
            // Handle API key form
            const form = document.getElementById('apiKeyForm');
            if (form) {{
                form.addEventListener('submit', function(e) {{
                    e.preventDefault();
                    const input = document.getElementById('apiKeyInput');
                    setApiKey(input.value.trim());
                    
                    // Show saved feedback
                    const btn = document.getElementById('apiKeySaveBtn');
                    const originalText = btn.textContent;
                    btn.textContent = 'Saved!';
                    btn.classList.add('bg-green-600');
                    setTimeout(() => {{
                        btn.textContent = originalText;
                        btn.classList.remove('bg-green-600');
                    }}, 1500);
                }});
            }}
            
            // Handle clear button
            const clearBtn = document.getElementById('apiKeyClearBtn');
            if (clearBtn) {{
                clearBtn.addEventListener('click', function() {{
                    setApiKey('');
                    const input = document.getElementById('apiKeyInput');
                    if (input) input.value = '';
                }});
            }}
        }});
    </script>
</head>
<body class="h-full">
    <div class="min-h-full">
        <!-- Navigation -->
        <nav class="bg-white shadow-sm border-b border-gray-200">
            <div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
                <div class="flex h-16 justify-between items-center">
                    <div class="flex items-center">
                        <a href="/ui" class="flex items-center space-x-2">
                            <span class="text-2xl">🤖</span>
                            <span class="text-xl font-bold text-gray-900">Agent Control Panel</span>
                        </a>
                    </div>
                    <div class="flex items-center space-x-4">
                        <a href="/ui/jobs" class="text-gray-600 hover:text-gray-900 px-3 py-2 rounded-md text-sm font-medium {jobs_active}">Jobs</a>
                        <a href="/ui/run" class="text-gray-600 hover:text-gray-900 px-3 py-2 rounded-md text-sm font-medium {run_active}">New Job</a>
                        <a href="/ui/chat" class="text-gray-600 hover:text-gray-900 px-3 py-2 rounded-md text-sm font-medium {chat_active}">Chat</a>
                        <a href="/docs" target="_blank" class="text-gray-600 hover:text-gray-900 px-3 py-2 rounded-md text-sm font-medium">API Docs ↗</a>
                        
                        <!-- API Key Input -->
                        <div class="border-l border-gray-200 pl-4 ml-2">
                            <form id="apiKeyForm" class="flex items-center space-x-2">
                                <div class="relative">
                                    <input 
                                        type="password" 
                                        id="apiKeyInput" 
                                        placeholder="API Key" 
                                        class="w-32 px-2 py-1 text-xs border border-gray-300 rounded focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
                                    >
                                    <span id="apiKeyStatus" class="absolute -bottom-4 left-0 text-xs text-yellow-600">⚠ No key</span>
                                </div>
                                <button 
                                    type="submit" 
                                    id="apiKeySaveBtn"
                                    class="px-2 py-1 text-xs bg-indigo-600 text-white rounded hover:bg-indigo-700 transition-colors"
                                >Save</button>
                                <button 
                                    type="button" 
                                    id="apiKeyClearBtn"
                                    class="px-2 py-1 text-xs bg-gray-200 text-gray-600 rounded hover:bg-gray-300 transition-colors"
                                >Clear</button>
                            </form>
                        </div>
                    </div>
                </div>
            </div>
        </nav>

        <!-- Main Content -->
        <main class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8 fade-in">
            {content}
        </main>

        <!-- Footer -->
        <footer class="bg-white border-t border-gray-200 mt-auto">
            <div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-4">
                <p class="text-center text-sm text-gray-500">
                    Agent Service v1.0.0 • <a href="/health" class="text-indigo-600 hover:text-indigo-800">Health Check</a>
                </p>
            </div>
        </footer>
    </div>
</body>
</html>
"""


def render_page(title: str, content: str, active_page: str = "") -> str:
    """Render a full HTML page."""
    return BASE_TEMPLATE.format(
        title=title,
        content=content,
        jobs_active="bg-gray-100" if active_page == "jobs" else "",
        run_active="bg-gray-100" if active_page == "run" else "",
        chat_active="bg-gray-100" if active_page == "chat" else "",
    )


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def ui_root(request: Request):
    """Redirect to unified chat UI."""
    return RedirectResponse(url="/ui/chat", status_code=302)


@router.get("/jobs", response_class=HTMLResponse)
async def ui_jobs_list(request: Request):
    """Redirect old jobs page to new UI."""
    return RedirectResponse(url="/ui/chat#settings", status_code=302)


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def ui_job_detail(job_id: str, request: Request):
    """Redirect old job detail to new UI."""
    return RedirectResponse(url="/ui/chat#settings", status_code=302)


@router.get("/run", response_class=HTMLResponse)
async def ui_run_form(request: Request):
    """Redirect old run form to new UI."""
    return RedirectResponse(url="/ui/chat", status_code=302)


# POST routes for job submissions still work (not redirected)


@router.post("/run/tool", response_class=HTMLResponse)
async def ui_submit_tool_job(
    request: Request,
    tool: str = Form(...),
    input_json: str = Form(...),
):
    """Submit a tool mode job."""
    tenant_id = get_tenant_id(request)
    
    # Parse input JSON
    try:
        input_data = json.loads(input_json)
    except json.JSONDecodeError as e:
        return HTMLResponse(
            render_page("Error", f"""
            <div class="bg-red-50 border border-red-200 rounded-lg p-4">
                <h2 class="text-lg font-medium text-red-800">Invalid JSON</h2>
                <p class="mt-1 text-sm text-red-700">{str(e)}</p>
                <a href="/ui/run" class="mt-4 inline-block text-indigo-600 hover:text-indigo-800">← Back to form</a>
            </div>
            """, active_page="run"),
            status_code=400
        )
    
    # Validate tool
    try:
        tool_enum = ToolName(tool)
    except ValueError:
        return HTMLResponse(
            render_page("Error", f"""
            <div class="bg-red-50 border border-red-200 rounded-lg p-4">
                <h2 class="text-lg font-medium text-red-800">Invalid Tool</h2>
                <p class="mt-1 text-sm text-red-700">Unknown tool: {tool}</p>
                <a href="/ui/run" class="mt-4 inline-block text-indigo-600 hover:text-indigo-800">← Back to form</a>
            </div>
            """, active_page="run"),
            status_code=400
        )
    
    # Create job
    job = job_store.create(tool_enum, input_data, tenant_id=tenant_id)
    
    # Queue background task (import here to avoid circular imports)
    from app.api.agent import run_tool_job_background
    import asyncio
    asyncio.create_task(run_tool_job_background(job.id))
    
    return RedirectResponse(url=f"/ui/jobs/{job.id}", status_code=303)


@router.post("/run/agent", response_class=HTMLResponse)
async def ui_submit_agent_job(
    request: Request,
    prompt: str = Form(...),
    max_steps: int = Form(default=3),
):
    """Submit an agent mode job."""
    tenant_id = get_tenant_id(request)
    
    # Create job
    job = job_store.create_job(
        mode=JobMode.AGENT,
        prompt=prompt,
        max_steps=max_steps,
        tenant_id=tenant_id,
    )
    
    # Queue background task
    from app.api.agent import run_agent_job_background
    import asyncio
    asyncio.create_task(run_agent_job_background(job.id))
    
    return RedirectResponse(url=f"/ui/jobs/{job.id}", status_code=303)


@router.post("/run/builder", response_class=HTMLResponse)
async def ui_submit_builder_job(
    request: Request,
    repo_url: str = Form(...),
    ref: str = Form(default=""),
    template: str = Form(default="fastapi_api"),
):
    """Submit a repo builder job."""
    tenant_id = get_tenant_id(request)
    
    # Validate repo URL
    try:
        from app.core.repo_builder import validate_repo_url
        validate_repo_url(repo_url)
    except Exception as e:
        return HTMLResponse(
            render_page("Error", f"""
            <div class="bg-red-50 border border-red-200 rounded-lg p-4">
                <h2 class="text-lg font-medium text-red-800">Invalid Repository URL</h2>
                <p class="mt-1 text-sm text-red-700">{str(e)}</p>
                <a href="/ui/run" class="mt-4 inline-block text-indigo-600 hover:text-indigo-800">← Back to form</a>
            </div>
            """, active_page="run"),
            status_code=400
        )
    
    # Create job
    input_data = {
        "repo_url": repo_url,
        "ref": ref or "main",
        "template": template,
    }
    job = job_store.create_job(
        mode=JobMode.BUILDER,
        input_data=input_data,
        prompt=f"Apply {template} template to {repo_url}",
        tenant_id=tenant_id,
    )
    
    # Update with repo URL
    from app.db.database import SessionLocal
    from app.db.models import Job as JobModel
    db = SessionLocal()
    try:
        job_model = db.query(JobModel).filter(JobModel.id == job.id).first()
        if job_model:
            job_model.repo_url = repo_url
            job_model.repo_ref = ref or "main"
            db.commit()
    finally:
        db.close()
    
    # Queue background task
    from app.api.builder import run_repo_builder_job
    import asyncio
    asyncio.create_task(run_repo_builder_job(job.id))
    
    return RedirectResponse(url=f"/ui/jobs/{job.id}", status_code=303)


@router.post("/run/build_runner", response_class=HTMLResponse)
async def ui_submit_build_runner_job(
    request: Request,
    repo_url: str = Form(...),
    ref: str = Form(default="main"),
    pipeline: str = Form(default="auto"),
):
    """Submit a build runner job (Phase 16)."""
    tenant_id = get_tenant_id(request)
    
    # Validate repo URL against allowlist
    try:
        from app.core.build_runner import validate_repo_url as validate_build_repo
        validate_build_repo(repo_url)
    except Exception as e:
        return HTMLResponse(
            render_page("Error", f"""
            <div class="bg-red-50 border border-red-200 rounded-lg p-4">
                <h2 class="text-lg font-medium text-red-800">Invalid Repository URL</h2>
                <p class="mt-1 text-sm text-red-700">{str(e)}</p>
                <p class="mt-2 text-sm text-gray-500">Only GitHub and GitLab repositories are allowed.</p>
                <a href="/ui/run" class="mt-4 inline-block text-indigo-600 hover:text-indigo-800">← Back to form</a>
            </div>
            """, active_page="run"),
            status_code=400
        )
    
    # Validate pipeline type
    if pipeline not in {"auto", "python", "node"}:
        return HTMLResponse(
            render_page("Error", f"""
            <div class="bg-red-50 border border-red-200 rounded-lg p-4">
                <h2 class="text-lg font-medium text-red-800">Invalid Pipeline Type</h2>
                <p class="mt-1 text-sm text-red-700">Pipeline must be 'auto', 'python', or 'node'.</p>
                <a href="/ui/run" class="mt-4 inline-block text-indigo-600 hover:text-indigo-800">← Back to form</a>
            </div>
            """, active_page="run"),
            status_code=400
        )
    
    # Create job
    input_data = {
        "mode": "build_runner",
        "repo_url": repo_url,
        "ref": ref or "main",
        "pipeline": pipeline,
    }
    job = job_store.create_job(
        mode=JobMode.BUILDER,
        input_data=input_data,
        prompt=f"Run build pipeline for {repo_url}",
        tenant_id=tenant_id,
    )
    
    # Queue background task
    from app.api.builder import run_build_runner_job
    import asyncio
    asyncio.create_task(run_build_runner_job(job.id))
    
    return RedirectResponse(url=f"/ui/jobs/{job.id}", status_code=303)

