"""
Phase A1: Approval Gate UI

Provides web UI pages for managing action batches:
- /ui/approvals - Pending batches list (approval queue)
- /ui/batches - All batches list
- /ui/batches/{id} - Batch detail page with approve/reject/run buttons
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db.database import SessionLocal
from app.db.models import ActionBatch, BatchAction, AuditLog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ui", tags=["approval-ui"])


# =============================================================================
# HTML Templates
# =============================================================================

def get_base_template(title: str, content: str, extra_head: str = "") -> str:
    """Generate base HTML template with navigation."""
    return f"""
<!DOCTYPE html>
<html lang="en" class="h-full bg-gray-50">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Xone Approval Gate</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .fade-in {{ animation: fadeIn 0.3s ease-in; }}
        @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
        .status-badge {{ @apply px-2 py-1 rounded-full text-xs font-medium; }}
        .risk-safe {{ @apply bg-green-100 text-green-800; }}
        .risk-medium {{ @apply bg-yellow-100 text-yellow-800; }}
        .risk-risky {{ @apply bg-red-100 text-red-800; }}
        .action-shell {{ @apply bg-purple-100 text-purple-800; }}
        .action-file {{ @apply bg-blue-100 text-blue-800; }}
        .action-http {{ @apply bg-cyan-100 text-cyan-800; }}
        .action-git {{ @apply bg-orange-100 text-orange-800; }}
        .action-note {{ @apply bg-gray-100 text-gray-800; }}
    </style>
    {extra_head}
    <script>
        const API_KEY_STORAGE_KEY = 'agent_service_api_key';
        
        function getApiKey() {{
            return localStorage.getItem(API_KEY_STORAGE_KEY) || '';
        }}
        
        function setApiKey(key) {{
            if (key) localStorage.setItem(API_KEY_STORAGE_KEY, key);
            else localStorage.removeItem(API_KEY_STORAGE_KEY);
        }}
        
        async function apiCall(method, url, body = null) {{
            const apiKey = getApiKey();
            if (!apiKey) {{
                alert('Please set your API key first');
                window.location.href = '/ui';
                return null;
            }}
            
            const options = {{
                method,
                headers: {{
                    'X-API-Key': apiKey,
                    'Content-Type': 'application/json',
                }},
            }};
            
            if (body) options.body = JSON.stringify(body);
            
            try {{
                const response = await fetch(url, options);
                const data = await response.json();
                
                if (!response.ok) {{
                    throw new Error(data.detail || 'API error');
                }}
                
                return data;
            }} catch (error) {{
                console.error('API error:', error);
                alert('Error: ' + error.message);
                return null;
            }}
        }}
        
        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }}
    </script>
</head>
<body class="h-full">
    <div class="min-h-full">
        <!-- Navigation -->
        <nav class="bg-gradient-to-r from-indigo-600 to-purple-600 shadow-lg">
            <div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
                <div class="flex h-16 items-center justify-between">
                    <div class="flex items-center space-x-4">
                        <a href="/ui" class="text-white font-bold text-xl">🤖 Xone</a>
                        <span class="text-indigo-200 text-sm">Approval Gate</span>
                    </div>
                    <div class="flex items-center space-x-4">
                        <a href="/ui/approvals" class="text-white hover:bg-indigo-500 px-3 py-2 rounded-md text-sm font-medium">
                            📋 Pending
                        </a>
                        <a href="/ui/batches" class="text-white hover:bg-indigo-500 px-3 py-2 rounded-md text-sm font-medium">
                            📦 All Batches
                        </a>
                        <a href="/ui/chat" class="text-white hover:bg-indigo-500 px-3 py-2 rounded-md text-sm font-medium">
                            💬 Chat
                        </a>
                        <a href="/ui/jobs" class="text-white hover:bg-indigo-500 px-3 py-2 rounded-md text-sm font-medium">
                            ⚙️ Jobs
                        </a>
                    </div>
                </div>
            </div>
        </nav>
        
        <!-- Main Content -->
        <main class="py-6">
            <div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
                {content}
            </div>
        </main>
        
        <!-- Footer -->
        <footer class="bg-gray-100 py-4 mt-8">
            <div class="mx-auto max-w-7xl px-4 text-center text-gray-500 text-sm">
                Xone by Elhassan Soussi • Phase A1: Approval Gate
            </div>
        </footer>
    </div>
</body>
</html>
"""


def status_badge_html(status: str) -> str:
    """Generate HTML for status badge."""
    colors = {
        "draft": "bg-gray-100 text-gray-800",
        "pending": "bg-yellow-100 text-yellow-800 animate-pulse",
        "approved": "bg-green-100 text-green-800",
        "rejected": "bg-red-100 text-red-800",
        "executing": "bg-blue-100 text-blue-800 animate-pulse",
        "executed": "bg-emerald-100 text-emerald-800",
        "failed": "bg-red-100 text-red-800",
    }
    color = colors.get(status, "bg-gray-100 text-gray-800")
    return f'<span class="px-2 py-1 rounded-full text-xs font-medium {color}">{status.upper()}</span>'


def risk_badge_html(risk: str) -> str:
    """Generate HTML for risk badge."""
    colors = {
        "safe": "bg-green-100 text-green-800",
        "medium": "bg-yellow-100 text-yellow-800",
        "risky": "bg-red-100 text-red-800",
    }
    icons = {"safe": "✓", "medium": "⚠️", "risky": "🔴"}
    color = colors.get(risk, "bg-gray-100 text-gray-800")
    icon = icons.get(risk, "")
    return f'<span class="px-2 py-1 rounded-full text-xs font-medium {color}">{icon} {risk}</span>'


def action_kind_badge_html(kind: str) -> str:
    """Generate HTML for action kind badge."""
    colors = {
        "shell": "bg-purple-100 text-purple-800",
        "file_write": "bg-blue-100 text-blue-800",
        "file_patch": "bg-blue-100 text-blue-800",
        "http_request": "bg-cyan-100 text-cyan-800",
        "git": "bg-orange-100 text-orange-800",
        "note": "bg-gray-100 text-gray-800",
    }
    icons = {
        "shell": "💻",
        "file_write": "📝",
        "file_patch": "🔧",
        "http_request": "🌐",
        "git": "🔀",
        "note": "📌",
    }
    color = colors.get(kind, "bg-gray-100 text-gray-800")
    icon = icons.get(kind, "")
    return f'<span class="px-2 py-1 rounded-full text-xs font-medium {color}">{icon} {kind}</span>'


def action_status_badge_html(status: str) -> str:
    """Generate HTML for action status badge."""
    colors = {
        "pending": "bg-gray-100 text-gray-600",
        "running": "bg-blue-100 text-blue-800 animate-pulse",
        "done": "bg-green-100 text-green-800",
        "error": "bg-red-100 text-red-800",
        "skipped": "bg-gray-100 text-gray-500",
    }
    color = colors.get(status, "bg-gray-100 text-gray-800")
    return f'<span class="px-2 py-1 rounded-full text-xs font-medium {color}">{status}</span>'


def escape_html(text: str) -> str:
    """Escape HTML characters."""
    if not text:
        return ""
    return (text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;"))


# =============================================================================
# UI Endpoints
# =============================================================================

@router.get("/approvals", response_class=HTMLResponse)
def approvals_page(request: Request):
    """Redirect to unified chat UI."""
    return RedirectResponse(url="/ui/chat", status_code=302)


@router.get("/batches", response_class=HTMLResponse)
def batches_list_page(request: Request):
    """Redirect to unified chat UI."""
    return RedirectResponse(url="/ui/chat", status_code=302)


@router.get("/batches/{batch_id}", response_class=HTMLResponse)
def batch_detail_page(batch_id: str, request: Request):
    """Redirect to unified chat UI."""
    return RedirectResponse(url="/ui/chat", status_code=302)
