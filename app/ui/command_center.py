"""
Xone UI - Left Navigation Layout

Provides:
- /ui/chat - Main Xone chat interface
- /ui/developer - Developer Xone chat for building/fixing projects
- /ui/command-center - Alias for /ui/chat

Layout:
- LEFT sidebar with navigation (Chat, Developer Xone, Jobs, Approvals, Memory, Audit, Settings)
- CENTER main content area
- NO right drawer/panel

Non-negotiable rules:
- Xone is NOT autonomous - execution requires owner (Elhassan) approval
- Approval model: "Approve once per batch step"
- No auto-execution after approval - must click "Run"
"""
import os
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/ui", tags=["ui"])

# No-cache headers for UI HTML responses
NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


def html_response_no_cache(content: str) -> HTMLResponse:
    """Return HTMLResponse with no-cache headers to prevent stale UI."""
    return HTMLResponse(content=content, headers=NO_CACHE_HEADERS)


# Agent identity
AGENT_NAME = os.environ.get("AGENT_NAME", "Xone by Elhassan Soussi")
# UI version for cache busting and visibility in settings
UI_VERSION = os.environ.get("UI_VERSION") or str(int(os.path.getmtime(__file__)))


def get_base_styles() -> str:
    """Returns the base CSS styles for all pages."""
    return r'''
        :root {
            --bg: #0b0f14;
            --panel: #121821;
            --panel-2: #0f151d;
            --panel-3: #0c1118;
            --border: #1b2432;
            --sidebar: #0b0f14;
            --text: #e7edf5;
            --muted: #9aa9bd;
            --accent: #14b8a6;
            --accent-strong: #0f766e;
            --accent-soft: rgba(20, 184, 166, 0.16);
            --accent-glow: rgba(20, 184, 166, 0.35);
            --shadow: 0 24px 60px rgba(0, 0, 0, 0.45);
        }
        * { box-sizing: border-box; }
        html, body {
            height: 100%;
            margin: 0;
            font-family: "Sora", "Space Grotesk", "Noto Sans", sans-serif;
            background-color: var(--bg);
            color: var(--text);
            text-rendering: optimizeLegibility;
        }
        body::before {
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
            background:
                radial-gradient(1200px 700px at 12% -10%, rgba(20, 184, 166, 0.16), transparent 55%),
                radial-gradient(900px 700px at 90% 12%, rgba(245, 158, 11, 0.1), transparent 60%),
                linear-gradient(180deg, rgba(7, 10, 15, 0.72), rgba(7, 10, 15, 0.95));
            opacity: 0.95;
            z-index: 0;
        }
        #app { position: relative; z-index: 1; animation: appIntro 0.45s ease-out; }
        @keyframes appIntro { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

        #sidebar {
            width: 280px;
            background: var(--sidebar);
            color: var(--text);
            border-right: 1px solid var(--border);
        }
        .sidebar-header {
            padding: 1rem;
            border-bottom: 1px solid var(--border);
        }
        .sidebar-search {
            padding: 0.5rem 0.75rem 0.25rem;
        }
        .sidebar-search-box {
            position: relative;
        }
        .sidebar-search-icon {
            position: absolute;
            left: 0.75rem;
            top: 50%;
            transform: translateY(-50%);
            color: var(--muted);
        }
        .sidebar-input {
            width: 100%;
            padding: 0.6rem 0.75rem 0.6rem 2.25rem;
            border-radius: 0.75rem;
            font-size: 0.8rem;
            border: 1px solid var(--border);
            background: var(--panel-2);
            color: var(--text);
        }
        .sidebar-input::placeholder { color: var(--muted); }
        .sidebar-section {
            padding: 0.25rem 0.75rem 0;
        }
        .sidebar-section-title {
            font-size: 0.65rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--muted);
            padding: 0.5rem 0.75rem 0.25rem;
        }
        .sidebar-footer {
            padding: 0.75rem;
            border-top: 1px solid var(--border);
        }
        .sidebar-link {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.55rem 0.75rem;
            border-radius: 0.75rem;
            font-size: 0.78rem;
            color: var(--muted);
            border: 1px solid transparent;
            transition: all 0.2s ease;
            text-decoration: none;
        }
        .sidebar-link:hover {
            color: var(--text);
            background: var(--panel-3);
            border-color: var(--border);
        }
        .nav-item {
            width: 100%;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.55rem 0.75rem;
            border-radius: 0.75rem;
            font-size: 0.8rem;
            color: var(--muted);
            border: 1px solid transparent;
            background: transparent;
            transition: all 0.2s ease;
            text-decoration: none;
        }
        .nav-item:hover {
            color: var(--text);
            background: var(--panel-3);
            border-color: var(--border);
        }
        .nav-item.active {
            color: var(--text);
            background: var(--accent-soft);
            border-color: rgba(20, 184, 166, 0.45);
            box-shadow: 0 12px 25px rgba(20, 184, 166, 0.12);
        }
        #conversationsList > div { border: 1px solid transparent; }
        #conversationsList > div:hover { background: var(--panel-3); }
        #conversationsList > div.bg-active {
            background: var(--accent-soft);
            border-color: var(--accent);
        }
        #conversationsList button { color: var(--muted); }

        main > header {
            background: rgba(11, 15, 20, 0.85);
            backdrop-filter: blur(14px);
            border-bottom: 1px solid var(--border);
        }

        #mainContent {
            position: relative;
            flex: 1;
            min-height: 0;
        }
        .section-panel {
            position: absolute;
            inset: 0;
            display: flex;
            flex-direction: column;
            min-height: 0;
        }
        .section-panel.hidden { display: none; }

        .section-body {
            flex: 1;
            overflow-y: auto;
            padding: 1.5rem;
        }
        .section-header {
            margin-bottom: 1rem;
        }
        .section-title {
            font-size: 1.25rem;
            font-weight: 600;
            color: var(--text);
        }
        .section-subtitle {
            font-size: 0.85rem;
            color: var(--muted);
        }

        #messagesContainer,
        #developerMessagesContainer {
            flex: 1;
            overflow-y: auto;
            background: rgba(11, 15, 20, 0.7);
        }
        #composer,
        #developerComposer {
            background: rgba(15, 20, 28, 0.86);
            border-top: 1px solid var(--border);
        }

        #newChatBtn,
        #sendBtn,
        #developerSendBtn,
        #saveKeyBtn {
            box-shadow: 0 12px 30px rgba(20, 184, 166, 0.25);
        }

        .content-panel {
            background: var(--panel-2);
            border: 1px solid var(--border);
            border-radius: 0.75rem;
        }

        /* Scrollbar */
        .custom-scrollbar::-webkit-scrollbar { width: 6px; height: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(148, 163, 184, 0.45); border-radius: 3px; }
        .dark .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(100, 116, 139, 0.6); }

        /* Animations */
        .fade-in { animation: fadeIn 0.2s ease-out; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

        /* Typing indicator */
        .typing-dot { animation: typingBounce 1.4s infinite ease-in-out both; }
        .typing-dot:nth-child(1) { animation-delay: -0.32s; }
        .typing-dot:nth-child(2) { animation-delay: -0.16s; }
        @keyframes typingBounce { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); } }

        /* Message bubbles */
        .msg-user { background: linear-gradient(135deg, #1ccfbf 0%, #0f766e 100%); box-shadow: 0 16px 36px rgba(20, 184, 166, 0.25); }
        .msg-agent { background: var(--panel-2); border: 1px solid var(--border); }
        .msg-agent pre {
            background: #0b1220;
            border: 1px solid var(--border);
            color: var(--text);
        }
        .msg-agent code { background: rgba(15, 23, 42, 0.7); color: var(--text); }

        /* Streaming cursor */
        .streaming-cursor::after {
            content: '▋';
            animation: blink 1s step-end infinite;
            margin-left: 2px;
        }
        @keyframes blink { 50% { opacity: 0; } }

        /* Copy button */
        .copy-btn {
            opacity: 0;
            transition: opacity 0.2s;
            background: rgba(12, 18, 28, 0.9);
            border: 1px solid var(--border);
        }
        .group:hover .copy-btn { opacity: 1; }

        /* Mobile sidebar */
        @media (max-width: 1024px) {
            #sidebar {
                position: fixed;
                left: 0;
                top: 0;
                bottom: 0;
                z-index: 50;
                transform: translateX(-100%);
                transition: transform 0.3s ease;
            }
            #sidebar.show { transform: translateX(0); }
        }
    '''


def get_sidebar_html(active_page: str = "chat") -> str:
    """Returns the sidebar HTML with navigation."""
    nav_items = [
        (
            "chat",
            "Chat",
            "/ui/chat#chat",
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h8M8 14h5m-1 7l-4-4H6a2 2 0 01-2-2V7a2 2 0 012-2h12a2 2 0 012 2v6a2 2 0 01-2 2h-3l-4 4z"></path>',
        ),
        (
            "developer",
            "Developer Xone",
            "/ui/developer",
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"></path>',
        ),
        (
            "agents",
            "Agents",
            "/ui/chat#agents",
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path>',
        ),
        (
            "settings",
            "Settings",
            "/ui/chat#settings",
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>',
        ),
    ]

    nav_html = ""
    for key, label, href, icon_path in nav_items:
        active_class = "active" if key == active_page else ""
        element_id = "settingsBtn" if key == "settings" else ""
        nav_html += f'''
            <a href="{href}" class="nav-item {active_class}" data-section="{key}" {'id="' + element_id + '"' if element_id else ''}>
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">{icon_path}</svg>
                <span>{label}</span>
            </a>
        '''

    return f'''
        <!-- ==================== LEFT SIDEBAR ==================== -->
        <aside id="sidebar" class="flex flex-col flex-shrink-0">
            <!-- Header with Brand -->
            <div class="sidebar-header">
                <div class="flex items-center gap-3 mb-2">
                    <div class="w-10 h-10 rounded-xl border-2 border-teal-500/60 bg-gradient-to-br from-teal-500/20 to-blue-500/20 flex items-center justify-center shadow-lg">
                        <svg class="w-6 h-6 text-teal-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path>
                        </svg>
                    </div>
                    <div class="flex-1">
                        <div class="text-lg font-bold tracking-wide text-white">Xone</div>
                        <div class="text-xs text-teal-400/80">by Elhassan Soussi</div>
                    </div>
                </div>
                <div class="mb-3 px-1">
                    <div class="text-sm text-slate-300">Hello, <span class="font-semibold text-white">Elhassan</span></div>
                </div>
                <button id="newChatBtn" class="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-teal-600 hover:bg-teal-700 rounded-lg transition font-medium text-sm shadow-md hover:shadow-lg">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
                    New Chat
                </button>
            </div>

            <!-- Search -->
            <div class="sidebar-search">
                <div class="sidebar-search-box">
                    <svg class="sidebar-search-icon w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 4a7 7 0 105.196 11.708l3.048 3.048 1.414-1.414-3.048-3.048A7 7 0 0011 4z"></path>
                    </svg>
                    <input type="text" id="searchInput" placeholder="Search conversations..." class="sidebar-input">
                </div>
            </div>

            <!-- Primary Navigation -->
            <div class="sidebar-section-title">Navigation</div>
            <nav class="sidebar-section space-y-1">
                {nav_html}
            </nav>

            <!-- Conversations -->
            <div class="sidebar-section-title mt-3">Conversations</div>
            <div id="conversationsList" class="flex-1 overflow-y-auto custom-scrollbar px-2 py-1 space-y-1">
                <!-- Rendered by JS -->
            </div>
        </aside>

        <!-- Mobile sidebar overlay -->
        <div id="sidebarOverlay" class="hidden fixed inset-0 bg-black/50 z-40 lg:hidden" onclick="toggleSidebar()"></div>
    '''


BASE_SCRIPTS = r'''
    // ========== CONFIG ==========
    const UI_VERSION = "__UI_VERSION__";
    const PAGE_MODE = "__PAGE_MODE__";
    const DEFAULT_SECTION = "__DEFAULT_SECTION__";
    const CONVERSATION_SCOPE = PAGE_MODE === "developer" ? "developer" : "chat";

    const API_KEY_STORAGE_KEY = "agent_service_api_key";
    const CONVERSATIONS_STORAGE_KEY = CONVERSATION_SCOPE === "developer"
        ? "agent_service_dev_conversations"
        : "agent_service_conversations";
    const CURRENT_CONV_KEY = CONVERSATION_SCOPE === "developer"
        ? "agent_service_dev_current_conversation"
        : "agent_service_current_conversation";
    const DARK_MODE_KEY = "agent_service_dark_mode";
    const SYSTEM_PROMPT_KEY = "agent_service_system_prompt";
    const STREAMING_MODE_KEY = "agent_service_streaming_mode";
    const MODEL_KEY = "agent_service_claude_model";
    const LEGACY_SYSTEM_PROMPT_KEY = "xone_system_prompt";
    const LEGACY_STREAMING_KEY = "xone_streaming";

    const MAX_POLL_TIME = 60000;
    const POLL_INTERVAL = 1000;

    const CHAT_ENDPOINT = PAGE_MODE === "developer" ? "/api/xone/chat" : "/api/xone/chat";
    const STREAM_ENDPOINT = PAGE_MODE === "developer" ? "/api/xone/chat" : "/api/xone/chat";

    const STORAGE_KEYS = {
        API_KEY: API_KEY_STORAGE_KEY,
        CONVERSATIONS: CONVERSATIONS_STORAGE_KEY,
        CURRENT_CONV: CURRENT_CONV_KEY,
        DARK_MODE: DARK_MODE_KEY,
        SYSTEM_PROMPT: SYSTEM_PROMPT_KEY,
        STREAMING: STREAMING_MODE_KEY,
    };

    const UI_RESET_KEYS = [
        API_KEY_STORAGE_KEY,
        CONVERSATIONS_STORAGE_KEY,
        CURRENT_CONV_KEY,
        DARK_MODE_KEY,
        SYSTEM_PROMPT_KEY,
        STREAMING_MODE_KEY,
        LEGACY_SYSTEM_PROMPT_KEY,
        LEGACY_STREAMING_KEY,
        "agent_service_dev_conversations",
        "agent_service_dev_current_conversation",
    ];

    // ========== STATE ==========
    let conversations = {};
    let currentConvId = null;
    let isProcessing = false;
    let streamingEnabled = localStorage.getItem(STREAMING_MODE_KEY) === "true";

    // ========== DOM ==========
    const $ = id => document.getElementById(id);
    const sidebar = $("sidebar");
    const sidebarOverlay = $("sidebarOverlay");
    const toggleSidebarBtn = $("toggleSidebar");
    const newChatBtn = $("newChatBtn");
    const searchInput = $("searchInput");
    const messagesContainer = $("messagesContainer") || $("developerMessagesContainer");
    const messagesWrapper = $("messagesWrapper") || $("developerMessagesWrapper");
    const emptyState = $("emptyState") || $("developerEmptyState");
    const typingIndicator = $("typingIndicator") || $("developerTypingIndicator");
    const messageInput = $("messageInput") || $("developerMessageInput");
    const chatForm = $("chatForm") || $("developerChatForm");
    const sendBtn = $("sendBtn") || $("developerSendBtn");
    const apiKeyInput = $("apiKeyInput");
    const apiKeyStatus = $("apiKeyStatus");
    const streamingToggle = $("streamingToggle");
    const systemPromptInput = $("systemPromptInput");

    // ========== STORAGE MIGRATION ==========
    function migrateLegacyKeys() {
        const legacyPrompt = localStorage.getItem(LEGACY_SYSTEM_PROMPT_KEY);
        if (legacyPrompt && !localStorage.getItem(SYSTEM_PROMPT_KEY)) {
            localStorage.setItem(SYSTEM_PROMPT_KEY, legacyPrompt);
        }
        const legacyStreaming = localStorage.getItem(LEGACY_STREAMING_KEY);
        if (legacyStreaming && localStorage.getItem(STREAMING_MODE_KEY) === null) {
            localStorage.setItem(STREAMING_MODE_KEY, legacyStreaming);
        }
    }

    // ========== API KEY ==========
    function getApiKey() {
        const key = localStorage.getItem(API_KEY_STORAGE_KEY) || "";
        // Debug: Log key retrieval to help diagnose CSS pollution bug
        if (key && (key.includes('{') || key.includes('px') || key.length > 100)) {
            console.error("WARNING: API key appears to be corrupted with CSS/HTML:", key.substring(0, 100));
            console.error("Clearing corrupted key from localStorage");
            localStorage.removeItem(API_KEY_STORAGE_KEY);
            return "";
        }
        return key;
    }
    function setApiKey(key) {
        // Validate key before storing
        if (key) {
            const trimmedKey = key.trim();
            // Check if key looks like CSS/HTML instead of an actual API key
            if (trimmedKey.includes('{') || trimmedKey.includes('<') || trimmedKey.includes('px')) {
                console.error("ERROR: Attempted to save invalid API key (looks like CSS/HTML):", trimmedKey.substring(0, 100));
                alert("Error: Invalid API key format. Please enter a valid API key.");
                return;
            }
            localStorage.setItem(API_KEY_STORAGE_KEY, trimmedKey);
        } else {
            localStorage.removeItem(API_KEY_STORAGE_KEY);
        }
        updateApiKeyUI();
    }
    function updateApiKeyUI() {
        const key = getApiKey();
        if (apiKeyInput) apiKeyInput.value = key;
        if (apiKeyStatus) {
            apiKeyStatus.textContent = key ? "Key set" : "No key";
            apiKeyStatus.className = key ? "text-xs text-emerald-400" : "text-xs text-amber-400";
        }
    }
    async function testApiKey() {
        const key = apiKeyInput ? apiKeyInput.value.trim() : getApiKey();
        if (!key) {
            if (apiKeyStatus) {
                apiKeyStatus.textContent = "Set a key first";
                apiKeyStatus.className = "text-xs text-amber-400";
            }
            return;
        }
        try {
            if (apiKeyStatus) {
                apiKeyStatus.textContent = "Testing...";
                apiKeyStatus.className = "text-xs text-slate-400";
            }
            const res = await originalFetch("/health", {
                headers: { 'X-API-Key': key },
            });
            if (apiKeyStatus) {
                apiKeyStatus.textContent = res.ok ? "Valid" : "Invalid";
                apiKeyStatus.className = res.ok ? "text-xs text-emerald-400" : "text-xs text-rose-400";
            }
        } catch (e) {
            if (apiKeyStatus) {
                apiKeyStatus.textContent = "Error";
                apiKeyStatus.className = "text-xs text-rose-400";
            }
        }
    }

    // Override fetch to add API key
    const originalFetch = window.fetch;
    window.fetch = function(url, options = {}) {
        const key = getApiKey();
        if (key) {
            options.headers = options.headers || {};
            if (options.headers instanceof Headers) {
                options.headers.set('X-API-Key', key);
            } else {
                options.headers['X-API-Key'] = key;
            }
        }
        return originalFetch(url, options);
    };

    // ========== DARK MODE ==========
    function initDarkMode() {
        const saved = localStorage.getItem(DARK_MODE_KEY);
        const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
        setDarkMode(saved === "true" || (saved === null && prefersDark));
    }
    function setDarkMode(isDark) {
        document.documentElement.classList.toggle("dark", isDark);
        localStorage.setItem(DARK_MODE_KEY, String(isDark));
    }
    function toggleDarkMode() {
        setDarkMode(!document.documentElement.classList.contains("dark"));
    }

    // ========== SIDEBAR ==========
    function toggleSidebar() {
        if (!sidebar) return;
        sidebar.classList.toggle("show");
        if (sidebarOverlay) sidebarOverlay.classList.toggle("hidden");
    }

    // ========== SECTIONS ==========
    const sectionPanels = Array.from(document.querySelectorAll("[data-section-panel]"));
    const navItems = Array.from(document.querySelectorAll("[data-section]"));

    function setActiveNav(section) {
        navItems.forEach(item => {
            const isActive = item.dataset.section === section;
            item.classList.toggle("active", isActive);
        });
    }

    function showSection(section) {
        if (!sectionPanels.length) return;
        let found = false;
        sectionPanels.forEach(panel => {
            const isMatch = panel.dataset.sectionPanel === section;
            panel.classList.toggle("hidden", !isMatch);
            if (isMatch) found = true;
        });
        if (!found && DEFAULT_SECTION) {
            showSection(DEFAULT_SECTION);
            return;
        }
        setActiveNav(section);
        if (window.location.pathname === "/ui/chat") {
            history.replaceState(null, "", `#${section}`);
        }
        loadSectionData(section);
        if ((section === "chat" || section === "developer") && messageInput) {
            messageInput.focus();
        }
    }

    function initSections() {
        if (!sectionPanels.length) return;
        const hash = window.location.hash.replace("#", "");
        showSection(hash || DEFAULT_SECTION);
    }

    function loadSectionData(section) {
        // Only settings needs special handling
        if (section === "settings") {
            fetchLLMHealth(); // Already called in init()
        }
        // Chat and developer sections have no data to load
    }

    // ========== CONVERSATIONS ==========
    function loadConversations() {
        try {
            conversations = JSON.parse(localStorage.getItem(CONVERSATIONS_STORAGE_KEY) || "{}");
            currentConvId = localStorage.getItem(CURRENT_CONV_KEY);
        } catch (e) {
            conversations = {};
            currentConvId = null;
        }
        renderConversationsList();
    }

    function saveConversations() {
        localStorage.setItem(CONVERSATIONS_STORAGE_KEY, JSON.stringify(conversations));
        if (currentConvId) localStorage.setItem(CURRENT_CONV_KEY, currentConvId);
    }

    function createConversation() {
        const id = `conv_${Date.now()}`;
        conversations[id] = { id, title: "New Chat", messages: [], created: Date.now() };
        currentConvId = id;
        saveConversations();
        renderConversationsList();
        renderMessages();
        return id;
    }

    function createNewConversation() {
        return createConversation();
    }

    function switchConversation(id) {
        if (!conversations[id]) return;
        currentConvId = id;
        saveConversations();
        renderConversationsList();
        renderMessages();
    }

    function deleteConversation(id) {
        if (!confirm("Delete this conversation?")) return;
        delete conversations[id];
        if (currentConvId === id) {
            const ids = Object.keys(conversations);
            currentConvId = ids.length > 0 ? ids[0] : null;
        }
        saveConversations();
        renderConversationsList();
        renderMessages();
    }

    function renderConversationsList(filter = "") {
        const list = $("conversationsList");
        if (!list) return;
        const normalized = filter.trim().toLowerCase();
        const convs = Object.values(conversations)
            .filter(c => !normalized || (c.title || "").toLowerCase().includes(normalized))
            .sort((a, b) => b.created - a.created);

        if (convs.length === 0) {
            list.innerHTML = '<p class="text-center text-slate-500 text-sm py-4">No conversations yet</p>';
            return;
        }

        list.innerHTML = convs.map(c => `
            <div class="group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer ${c.id === currentConvId ? "bg-active" : "hover:bg-slate-800"}" onclick="switchConversation('${c.id}')">
                <span class="flex-1 truncate text-sm">${escapeHtml(c.title)}</span>
                <button onclick="event.stopPropagation(); deleteConversation('${c.id}')" class="p-1 hover:bg-slate-700 rounded opacity-0 group-hover:opacity-100">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
                </button>
            </div>
        `).join("");
    }

    // ========== MESSAGES ==========
    function renderMessages() {
        if (!messagesWrapper || !emptyState) return;
        if (!currentConvId || !conversations[currentConvId]) {
            emptyState.classList.remove("hidden");
            messagesWrapper.innerHTML = "";
            return;
        }

        const conv = conversations[currentConvId];
        if (conv.messages.length === 0) {
            emptyState.classList.remove("hidden");
            messagesWrapper.innerHTML = "";
            return;
        }

        emptyState.classList.add("hidden");
        messagesWrapper.innerHTML = conv.messages.map(m => renderMessage(m)).join("");
        scrollToBottom();
    }

    function renderMessage(msg) {
        const messageIdAttr = msg.id ? `data-msg-id="${msg.id}"` : "";
        if (msg.role === "user") {
            return `
                <div class="flex justify-end fade-in" ${messageIdAttr}>
                    <div class="msg-user text-white px-4 py-2 rounded-2xl rounded-br-sm max-w-[80%]">
                        <p class="text-sm whitespace-pre-wrap">${escapeHtml(msg.content)}</p>
                    </div>
                </div>`;
        }
        const streamingClass = msg.streaming ? "streaming-cursor" : "";
        return `
            <div class="flex gap-3 fade-in" ${messageIdAttr}>
                <div class="w-8 h-8 bg-slate-700 rounded-full flex items-center justify-center flex-shrink-0">
                    <div class="w-3 h-3 rounded-full bg-teal-400"></div>
                </div>
                <div class="msg-agent dark:text-white px-4 py-2 rounded-2xl rounded-bl-sm max-w-[80%] ${streamingClass}">
                    <div class="text-sm whitespace-pre-wrap">${formatContent(msg.content)}</div>
                </div>
            </div>`;
    }

    function updateMessageContent(msgId, content, isStreaming) {
        const conv = conversations[currentConvId];
        if (!conv) return;
        const msg = conv.messages.find(m => m.id === msgId);
        if (!msg) return;
        msg.content = content;
        msg.streaming = isStreaming;
        saveConversations();

        const messageEl = messagesWrapper ? messagesWrapper.querySelector(`[data-msg-id="${msgId}"]`) : null;
        if (messageEl) {
            const contentEl = messageEl.querySelector(".msg-agent .text-sm");
            if (contentEl) contentEl.innerHTML = formatContent(content);
            if (isStreaming) {
                const bubble = messageEl.querySelector(".msg-agent");
                if (bubble) bubble.classList.add("streaming-cursor");
            }
        } else {
            renderMessages();
        }
    }

    function addMessage(role, content, options = {}) {
        if (!currentConvId) createConversation();
        if (typeof content !== 'string') {
            content = extractOutputText(content);
        }

        const messageId = options.id || `msg_${Date.now()}_${Math.random().toString(16).slice(2)}`;
        const conv = conversations[currentConvId];
        conv.messages.push({ role, content, ts: Date.now(), id: messageId, streaming: !!options.streaming });

        if (role === "user" && conv.messages.filter(m => m.role === "user").length === 1) {
            conv.title = content.slice(0, 30) + (content.length > 30 ? "..." : "");
        }

        saveConversations();
        renderMessages();
        renderConversationsList(searchInput ? searchInput.value : "");
        return messageId;
    }

    function formatContent(content) {
        let html = escapeHtml(content);
        html = html.replace(/```([\s\S]*?)```/g, (match, code) => `
            <div class="code-block group relative my-2">
                <button class="copy-btn absolute right-2 top-2 px-2 py-1 text-[10px] text-gray-200 rounded-md" onclick="copyCodeBlock(this.parentElement.querySelector('pre').innerText)">Copy</button>
                <pre class="bg-slate-900/80 p-2 rounded text-xs overflow-x-auto">${code}</pre>
            </div>
        `);
        html = html.replace(/`([^`]+)`/g, '<code class="bg-slate-800/70 px-1 rounded text-xs">$1</code>');
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        return html;
    }

    function extractOutputText(output) {
        if (typeof output === 'string') return output;
        if (typeof output === 'object' && output !== null) {
            if (output.final_output) return extractOutputText(output.final_output);
            if (output.response) return extractOutputText(output.response);
            if (output.text) return extractOutputText(output.text);
            if (output.content) return extractOutputText(output.content);
            if (output.message) return extractOutputText(output.message);
            if (output.result) return extractOutputText(output.result);
            return JSON.stringify(output, null, 2);
        }
        return String(output);
    }

    function scrollToBottom() {
        if (!messagesContainer) return;
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function usePrompt(prompt) {
        if (messageInput) {
            messageInput.value = prompt;
            messageInput.focus();
        }
    }

    function usePromptSuggestion(prompt) {
        return usePrompt(prompt);
    }

    function copyMessage(text) {
        navigator.clipboard.writeText(text).catch(() => {});
    }

    function copyCodeBlock(text) {
        copyMessage(text);
    }

    // ========== CHAT SUBMISSION ==========
    async function submitMessage(prompt) {
        if (streamingEnabled) return submitMessageStreaming(prompt);
        return submitMessageNonStreaming(prompt);
    }

    async function submitMessageNonStreaming(prompt) {
        if (isProcessing) return;
        isProcessing = true;
        if (typingIndicator) typingIndicator.classList.remove("hidden");
        scrollToBottom();

        try {
            const apiKey = getApiKey();
            const res = await fetch(CHAT_ENDPOINT, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-API-Key": apiKey || ""
                },
                body: JSON.stringify({
                    message: prompt,
                    mode: PAGE_MODE === "developer" ? "developer" : "chat",
                    stream: false
                }),
            });

            if (res.status === 401 || res.status === 403) {
                addMessage("assistant", "Authentication required. Set your API key in Settings.");
                return;
            }

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || "Request failed");
            }

            const data = await res.json();
            const response = data.response || data.text || data.message || data.content || JSON.stringify(data);
            addMessage("assistant", response);
        } catch (e) {
            addMessage("assistant", `Error: ${e.message}`);
        } finally {
            isProcessing = false;
            if (typingIndicator) typingIndicator.classList.add("hidden");
        }
    }

    async function submitMessageStreaming(prompt) {
        // Note: Streaming not yet implemented for Xone endpoint, fall back to non-streaming
        return submitMessageNonStreaming(prompt);
    }

    async function pollJobStatus(jobId) {
        const startTime = Date.now();
        while (Date.now() - startTime < MAX_POLL_TIME) {
            try {
                const res = await fetch(`/agent/status/${jobId}`);
                if (!res.ok) throw new Error("Failed to poll");
                const data = await res.json();
                if (data.status === "done" || data.status === "error") {
                    return data;
                }
            } catch (e) {
                console.error("Poll error:", e);
            }
            await new Promise(r => setTimeout(r, POLL_INTERVAL));
        }
        throw new Error("Polling timeout");
    }

    function formatAgentMessage(content) {
        return formatContent(content);
    }

    // ========== SETTINGS ==========
    function saveSystemPrompt() {
        if (!systemPromptInput) return;
        const prompt = systemPromptInput.value.trim();
        if (prompt) localStorage.setItem(SYSTEM_PROMPT_KEY, prompt);
        else localStorage.removeItem(SYSTEM_PROMPT_KEY);
        alert("System prompt saved!");
    }

    function initStreamingToggle() {
        if (!streamingToggle) return;
        streamingToggle.checked = streamingEnabled;
        streamingToggle.addEventListener("change", () => {
            streamingEnabled = streamingToggle.checked;
            localStorage.setItem(STREAMING_MODE_KEY, String(streamingEnabled));
        });
    }

    function loadSystemPrompt() {
        if (!systemPromptInput) return;
        const prompt = localStorage.getItem(SYSTEM_PROMPT_KEY) || "";
        systemPromptInput.value = prompt;
    }

    function initModelSelector() {
        const selector = $("modelSelector");
        if (!selector) return;

        // Load saved model preference
        const savedModel = localStorage.getItem(MODEL_KEY);
        if (savedModel) {
            selector.value = savedModel;
        }

        // Save on change
        selector.addEventListener("change", () => {
            const selectedModel = selector.value;
            localStorage.setItem(MODEL_KEY, selectedModel);
            console.log("Model preference saved:", selectedModel);
        });
    }

    function initConnectors() {
        // Chat connectors dropdown
        const chatBtn = $("addChatConnectorBtn");
        const chatDropdown = $("chatConnectorDropdown");
        if (chatBtn && chatDropdown) {
            chatBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                chatDropdown.classList.toggle("hidden");
                const devDropdown = $("devConnectorDropdown");
                if (devDropdown) devDropdown.classList.add("hidden");
            });
        }

        // Developer connectors dropdown
        const devBtn = $("addDevConnectorBtn");
        const devDropdown = $("devConnectorDropdown");
        if (devBtn && devDropdown) {
            devBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                devDropdown.classList.toggle("hidden");
                if (chatDropdown) chatDropdown.classList.add("hidden");
            });
        }

        // Close dropdowns when clicking outside
        document.addEventListener("click", () => {
            if (chatDropdown) chatDropdown.classList.add("hidden");
            if (devDropdown) devDropdown.classList.add("hidden");
        });
    }

    function updateProviderBadge(provider, model) {
        const badge = $("providerBadge");
        const text = $("providerText");
        if (!text) return;
        if (!provider) {
            text.textContent = "Not configured";
            if (badge) badge.classList.add("hidden");
            return;
        }
        text.textContent = `${provider}/${model || "default"}`;
        if (badge) badge.classList.remove("hidden");

        // Update current model display
        const currentModelEl = $("currentModel");
        if (currentModelEl && model) {
            currentModelEl.textContent = model;
        }
    }

    async function fetchLLMHealth() {
        try {
            const res = await fetch("/llm/health");
            if (!res.ok) return;
            const data = await res.json();
            updateProviderBadge(data.provider, data.model);
        } catch (e) {}
    }

    async function resetUiCache() {
        const status = $("cacheResetStatus");
        if (status) status.textContent = "Clearing...";
        try {
            if ("serviceWorker" in navigator) {
                const registrations = await navigator.serviceWorker.getRegistrations();
                await Promise.all(registrations.map(reg => reg.unregister()));
            }
            if ("caches" in window) {
                const keys = await caches.keys();
                await Promise.all(keys.map(key => caches.delete(key)));
            }
            UI_RESET_KEYS.forEach(key => localStorage.removeItem(key));
        } catch (err) {
            console.error("UI cache reset failed", err);
        }
        if (status) status.textContent = "Reloading...";
        window.location.reload();
    }

    // ========== UTILS ==========
    function escapeHtml(str) {
        if (!str) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    // ========== INIT ==========
    async function init() {
        // Debug: Log all localStorage keys on init
        console.log("=== localStorage Debug ===");
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            const value = localStorage.getItem(key);
            console.log(`${key}:`, value ? value.substring(0, 100) : "(empty)");
        }
        console.log("=========================");

        migrateLegacyKeys();
        initDarkMode();
        updateApiKeyUI();
        loadSystemPrompt();
        initStreamingToggle();
        initModelSelector();
        initConnectors();
        loadConversations();
        initSections();

        if (searchInput) {
            searchInput.addEventListener("input", (e) => {
                renderConversationsList(e.target.value || "");
            });
        }

        if (messageInput) {
            messageInput.addEventListener("input", () => {
                messageInput.style.height = "auto";
                messageInput.style.height = Math.min(messageInput.scrollHeight, 150) + "px";
            });
        }

        fetchLLMHealth();

        if (currentConvId && conversations[currentConvId]) {
            renderMessages();
        }

        if (messageInput) {
            messageInput.focus();
        }
    }

    // ========== EVENT LISTENERS ==========
    if (toggleSidebarBtn) toggleSidebarBtn.addEventListener("click", toggleSidebar);
    if (newChatBtn) newChatBtn.addEventListener("click", () => {
        createConversation();
        showSection(PAGE_MODE === "developer" ? "developer" : "chat");
        toggleSidebar();
    });
    if ($("darkModeToggle")) $("darkModeToggle").addEventListener("click", toggleDarkMode);
    if ($("saveKeyBtn")) $("saveKeyBtn").addEventListener("click", () => {
        if (apiKeyInput) setApiKey(apiKeyInput.value.trim());
    });
    if ($("testKeyBtn")) $("testKeyBtn").addEventListener("click", testApiKey);
    if ($("clearKeyBtn")) $("clearKeyBtn").addEventListener("click", () => {
        setApiKey("");
    });
    if ($("savePromptBtn")) $("savePromptBtn").addEventListener("click", saveSystemPrompt);

    navItems.forEach(item => {
        item.addEventListener("click", (event) => {
            const section = item.dataset.section;
            if (!section) return;
            const targetPath = new URL(item.href, window.location.origin).pathname;
            if (targetPath === window.location.pathname) {
                event.preventDefault();
                showSection(section);
            }
        });
    });

    if (chatForm) {
        chatForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const prompt = messageInput ? messageInput.value.trim() : "";
            if (!prompt || isProcessing) return;
            addMessage("user", prompt);
            if (messageInput) messageInput.value = "";
            await submitMessage(prompt);
        });
    }

    if (messageInput) {
        messageInput.addEventListener("keydown", (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (chatForm) chatForm.dispatchEvent(new Event("submit"));
            }
        });
    }

    // ========== AGENT MANAGEMENT ==========
    async function startAgents() {
        const checkboxes = document.querySelectorAll(".agent-checkbox:checked");
        const selectedAgents = Array.from(checkboxes).map(cb => cb.value);

        if (selectedAgents.length === 0) {
            showStatus("agentStartStatus", "Please select at least one agent", "error");
            return;
        }

        const statusEl = $("agentStartStatus");
        if (statusEl) statusEl.textContent = "Starting agents...";

        try {
            const response = await fetch("/api/agent/start", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-API-Key": getApiKey() || "",
                },
                body: JSON.stringify({
                    agents: selectedAgents,
                    auto_approve_low_risk: true
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || "Failed to start agents");
            }

            if (statusEl) statusEl.textContent = `✓ Started ${data.agents_started.length} agents`;
            setTimeout(() => refreshAgentStatus(), 2000);
        } catch (error) {
            if (statusEl) statusEl.textContent = `✗ Error: ${error.message}`;
        }
    }

    async function refreshAgentStatus() {
        try {
            const response = await fetch("/api/agent/status", {
                headers: { "X-API-Key": getApiKey() || "" }
            });

            if (!response.ok) {
                throw new Error("Failed to fetch agent status");
            }

            const data = await response.json();

            // Update active agents
            const statusContainer = $("agentStatusContainer");
            if (statusContainer) {
                if (Object.keys(data.active_agents).length === 0) {
                    statusContainer.innerHTML = '<p class="text-xs text-slate-400">No agents running</p>';
                } else {
                    let html = '';
                    for (const [id, agent] of Object.entries(data.active_agents)) {
                        const statusBadge = agent.status === "running"
                            ? '<span class="px-2 py-0.5 bg-teal-900/40 text-teal-400 rounded text-xs">Running</span>'
                            : '<span class="px-2 py-0.5 bg-slate-700 text-slate-300 rounded text-xs">Completed</span>';
                        html += `
                            <div class="bg-slate-800/40 border border-slate-700 rounded p-2">
                                <div class="flex items-center justify-between mb-1">
                                    <span class="text-xs font-medium text-slate-200">${agent.role}</span>
                                    ${statusBadge}
                                </div>
                                <div class="text-xs text-slate-400">${agent.task.substring(0, 80)}...</div>
                            </div>
                        `;
                    }
                    statusContainer.innerHTML = html;
                }
            }

            // Update results
            const resultsContainer = $("agentResultsContainer");
            if (resultsContainer && data.recent_results && data.recent_results.length > 0) {
                let html = '';
                data.recent_results.slice().reverse().forEach(result => {
                    const resultText = result.result?.response || result.result?.error || "No response";
                    html += `
                        <div class="bg-slate-800/40 border border-slate-700 rounded p-3">
                            <div class="text-xs text-slate-400 mb-1">${new Date(result.completed_at).toLocaleString()}</div>
                            <div class="text-sm text-slate-200">${resultText.substring(0, 200)}${resultText.length > 200 ? '...' : ''}</div>
                        </div>
                    `;
                });
                resultsContainer.innerHTML = html;
            }

            // Update pending approvals
            const approvalsPanel = $("pendingApprovalsPanel");
            const approvalsContainer = $("pendingApprovalsContainer");
            if (data.pending_approvals && data.pending_approvals.length > 0) {
                if (approvalsPanel) approvalsPanel.classList.remove("hidden");
                if (approvalsContainer) {
                    let html = '';
                    data.pending_approvals.forEach(approval => {
                        html += `
                            <div class="bg-amber-900/20 border border-amber-700/40 rounded p-3">
                                <div class="flex items-center justify-between mb-2">
                                    <span class="text-sm font-medium text-slate-200">${approval.context?.role || 'Agent'}</span>
                                    <span class="text-xs text-amber-400">${approval.tools?.length || 0} tools</span>
                                </div>
                                <div class="text-xs text-slate-400 mb-3">${approval.context?.task?.substring(0, 100) || ''}...</div>
                                <div class="flex gap-2">
                                    <button onclick="approveAgent('${approval.id}', true)" class="px-3 py-1 bg-teal-600 text-white rounded text-xs hover:bg-teal-700">Approve</button>
                                    <button onclick="approveAgent('${approval.id}', false)" class="px-3 py-1 bg-slate-700 text-white rounded text-xs hover:bg-slate-600">Reject</button>
                                </div>
                            </div>
                        `;
                    });
                    approvalsContainer.innerHTML = html;
                }
            } else {
                if (approvalsPanel) approvalsPanel.classList.add("hidden");
            }

        } catch (error) {
            console.error("Failed to refresh agent status:", error);
        }
    }

    async function approveAgent(approvalId, approved) {
        try {
            const response = await fetch("/api/agent/approve", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-API-Key": getApiKey() || "",
                },
                body: JSON.stringify({
                    approval_id: approvalId,
                    approved: approved
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || "Failed to process approval");
            }

            // Refresh status after approval
            refreshAgentStatus();
        } catch (error) {
            console.error("Approval error:", error);
            alert(`Error: ${error.message}`);
        }
    }

    // Attach agent event listeners
    if ($("startAgentsBtn")) {
        $("startAgentsBtn").addEventListener("click", startAgents);
    }
    if ($("refreshAgentStatus")) {
        $("refreshAgentStatus").addEventListener("click", refreshAgentStatus);
    }

    // Make approve function global so onclick can access it
    window.approveAgent = approveAgent;

    // Auto-refresh agent status every 10 seconds when on agents page
    setInterval(() => {
        const agentsSection = $("section-agents");
        if (agentsSection && !agentsSection.classList.contains("hidden")) {
            refreshAgentStatus();
        }
    }, 10000);

    // Register service worker for PWA
    if ("serviceWorker" in navigator) {
        navigator.serviceWorker.register(`/static/sw.js?v=${UI_VERSION}`).catch(() => {});
    }

    document.addEventListener("DOMContentLoaded", init);
'''


def get_base_scripts(page_mode: str, default_section: str) -> str:
    """Return base JavaScript with injected config values."""
    return (
        BASE_SCRIPTS.replace("__UI_VERSION__", UI_VERSION)
        .replace("__PAGE_MODE__", page_mode)
        .replace("__DEFAULT_SECTION__", default_section)
    )


def get_chat_sections_html() -> str:
    """Return HTML for chat and left-side panels."""
    return r'''
        <section id="section-chat" data-section-panel="chat" class="section-panel">
            <!-- Connectors Bar -->
            <div class="sticky top-0 z-10 bg-slate-900/95 backdrop-blur-sm border-b border-slate-800 px-4 py-2">
                <div class="max-w-3xl mx-auto flex items-center justify-between">
                    <div class="flex items-center gap-2">
                        <span class="text-xs text-slate-400">Connectors:</span>
                        <div id="chatConnectorsList" class="flex items-center gap-2">
                            <span class="text-xs text-slate-500">None active</span>
                        </div>
                    </div>
                    <div class="relative">
                        <button id="addChatConnectorBtn" class="flex items-center gap-1 px-2 py-1 text-xs bg-teal-600 hover:bg-teal-700 text-white rounded transition">
                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path>
                            </svg>
                            Add Connector
                        </button>
                        <div id="chatConnectorDropdown" class="hidden absolute right-0 mt-1 w-48 bg-slate-800 border border-slate-700 rounded-lg shadow-lg overflow-hidden z-20">
                            <div class="py-1">
                                <button class="w-full text-left px-3 py-2 text-xs text-slate-300 hover:bg-slate-700 transition">
                                    <div class="font-medium">Web Search</div>
                                    <div class="text-slate-500">Search the web</div>
                                </button>
                                <button class="w-full text-left px-3 py-2 text-xs text-slate-300 hover:bg-slate-700 transition">
                                    <div class="font-medium">GitHub</div>
                                    <div class="text-slate-500">Connect repositories</div>
                                </button>
                                <button class="w-full text-left px-3 py-2 text-xs text-slate-300 hover:bg-slate-700 transition">
                                    <div class="font-medium">Calendar</div>
                                    <div class="text-slate-500">Manage events</div>
                                </button>
                                <button class="w-full text-left px-3 py-2 text-xs text-slate-300 hover:bg-slate-700 transition opacity-50 cursor-not-allowed">
                                    <div class="font-medium">More coming soon...</div>
                                    <div class="text-slate-500">Stay tuned</div>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div id="messagesContainer" class="custom-scrollbar">
                <div class="max-w-3xl mx-auto px-4 py-6">
                    <div id="emptyState" class="flex flex-col items-center justify-center py-16 text-center">
                        <div class="w-16 h-16 bg-teal-900/40 rounded-full flex items-center justify-center mb-4">
                            <div class="w-8 h-8 rounded-full border border-teal-400/60 bg-teal-400/15 flex items-center justify-center">
                                <div class="w-2.5 h-2.5 rounded-full bg-teal-400"></div>
                            </div>
                        </div>
                        <h2 class="text-xl font-semibold text-slate-200 mb-2">Welcome to Xone</h2>
                        <p class="text-sm text-slate-400 max-w-md mb-6">How can I help you today?</p>
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-md">
                            <button onclick="usePrompt('What can you help me with?')" class="p-3 text-left border border-slate-700 rounded-lg hover:bg-slate-800/60 transition">
                                <div class="font-medium text-slate-200 text-sm flex items-center gap-2">
                                    <svg class="w-4 h-4 text-teal-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h8M8 14h5m-1 7l-4-4H6a2 2 0 01-2-2V7a2 2 0 012-2h12a2 2 0 012 2v6a2 2 0 01-2 2h-3l-4 4z"></path>
                                    </svg>
                                    <span>Get Started</span>
                                </div>
                                <div class="text-xs text-slate-400">Ask what I can do</div>
                            </button>
                            <button onclick="usePrompt('Search the web for AI news')" class="p-3 text-left border border-slate-700 rounded-lg hover:bg-slate-800/60 transition">
                                <div class="font-medium text-slate-200 text-sm flex items-center gap-2">
                                    <svg class="w-4 h-4 text-teal-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 4a7 7 0 105.196 11.708l3.048 3.048 1.414-1.414-3.048-3.048A7 7 0 0011 4z"></path>
                                    </svg>
                                    <span>Web Search</span>
                                </div>
                                <div class="text-xs text-slate-400">Search for information</div>
                            </button>
                        </div>
                    </div>

                    <div id="messagesWrapper" class="space-y-4"></div>

                    <div id="typingIndicator" class="hidden flex gap-3 fade-in">
                        <div class="w-8 h-8 bg-slate-700 rounded-full flex items-center justify-center flex-shrink-0">
                            <div class="w-3 h-3 rounded-full bg-teal-400"></div>
                        </div>
                        <div class="bg-slate-800 rounded-2xl px-4 py-3">
                            <div class="flex gap-1">
                                <div class="w-2 h-2 bg-slate-400 rounded-full typing-dot"></div>
                                <div class="w-2 h-2 bg-slate-400 rounded-full typing-dot"></div>
                                <div class="w-2 h-2 bg-slate-400 rounded-full typing-dot"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div id="composer" class="px-4 py-3 flex-shrink-0">
                <form id="chatForm" class="max-w-3xl mx-auto">
                    <div class="relative">
                        <textarea id="messageInput" placeholder="Send a message..." rows="1"
                            class="w-full px-4 py-3 pr-12 border border-slate-700 rounded-xl resize-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500 text-sm bg-slate-900/70 text-white"></textarea>
                        <button type="submit" id="sendBtn" class="absolute right-2 bottom-2 p-2 bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:bg-slate-700 disabled:cursor-not-allowed transition">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/></svg>
                        </button>
                    </div>
                    <p class="text-xs text-slate-400 mt-2 text-center">Enter to send • Shift+Enter for new line</p>
                </form>
            </div>
        </section>

        <section id="section-settings" data-section-panel="settings" class="section-panel hidden">
            <div class="section-body custom-scrollbar">
                <div class="section-header">
                    <h2 class="section-title">Settings</h2>
                    <p class="section-subtitle">Configure API access, prompts, and UI tools.</p>
                </div>

                <div class="bg-slate-800/40 border border-slate-700 rounded-lg p-3 mb-4">
                    <p class="text-xs text-slate-300">
                        <strong>Xone</strong> is a simple AI chat interface.
                        Configure your API key below to enable chat functionality.
                    </p>
                </div>

                <div class="grid gap-4">
                    <div class="content-panel p-4">
                        <h3 class="text-sm font-semibold text-slate-200 mb-2">API Key</h3>
                        <div class="flex flex-col gap-2">
                            <input type="password" id="apiKeyInput" placeholder="Enter API key" class="w-full px-3 py-2 rounded-lg bg-slate-900/70 border border-slate-700 text-sm text-white" />
                            <div class="flex items-center gap-2">
                                <button id="saveKeyBtn" class="px-3 py-2 text-xs bg-teal-600 text-white rounded-lg hover:bg-teal-700">Save</button>
                                <button id="testKeyBtn" class="px-3 py-2 text-xs bg-slate-700 text-white rounded-lg hover:bg-slate-600">Test</button>
                                <button id="clearKeyBtn" class="px-3 py-2 text-xs bg-slate-800 text-white rounded-lg hover:bg-slate-700">Clear</button>
                                <span id="apiKeyStatus" class="text-xs text-slate-400">No key</span>
                            </div>
                        </div>
                    </div>

                    <div class="content-panel p-4">
                        <h3 class="text-sm font-semibold text-slate-200 mb-2">System Prompt</h3>
                        <textarea id="systemPromptInput" rows="4" class="w-full px-3 py-2 rounded-lg bg-slate-900/70 border border-slate-700 text-sm text-white" placeholder="Optional system prompt"></textarea>
                        <button id="savePromptBtn" class="mt-2 px-3 py-2 text-xs bg-teal-600 text-white rounded-lg hover:bg-teal-700">Save</button>
                    </div>

                    <div class="content-panel p-4">
                        <h3 class="text-sm font-semibold text-slate-200 mb-2">Streaming</h3>
                        <label class="flex items-center gap-2 text-sm text-slate-300">
                            <input type="checkbox" id="streamingToggle" class="h-4 w-4 rounded border-slate-600 bg-slate-900 text-teal-500" />
                            Enable streaming responses
                        </label>
                    </div>

                    <div class="content-panel p-4">
                        <h3 class="text-sm font-semibold text-slate-200 mb-2">Claude Model</h3>
                        <p class="text-xs text-slate-400 mb-3">Select which Claude model to use for responses.</p>
                        <select id="modelSelector" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-sm text-slate-200 focus:outline-none focus:border-teal-500">
                            <option value="claude-3-5-sonnet-20241022">Claude 3.5 Sonnet (Recommended - Balanced)</option>
                            <option value="claude-3-5-haiku-20241022">Claude 3.5 Haiku (Fastest & Cheapest)</option>
                            <option value="claude-3-opus-20240229">Claude 3 Opus (Most Capable)</option>
                            <option value="claude-3-haiku-20240307">Claude 3 Haiku (Legacy)</option>
                        </select>
                        <div class="mt-2 text-xs text-slate-400">
                            Current: <span id="currentModel" class="text-teal-400 font-mono">Loading...</span>
                        </div>
                    </div>

                    <div class="content-panel p-4">
                        <h3 class="text-sm font-semibold text-slate-200 mb-2">Provider Status</h3>
                        <div id="providerBadge" class="inline-flex items-center gap-2 rounded-full bg-slate-800 px-3 py-1 text-xs text-slate-200">
                            <span class="w-2 h-2 rounded-full bg-teal-400"></span>
                            <span id="providerText">ollama</span>
                        </div>
                    </div>

                    <div class="content-panel p-4">
                        <h3 class="text-sm font-semibold text-slate-200 mb-2">Reset UI</h3>
                        <p class="text-xs text-slate-400">Clear cached data and reload to reset conversations and settings.</p>
                        <div class="flex items-center gap-2 mt-2">
                            <button onclick="resetUiCache()" class="px-3 py-2 text-xs bg-slate-700 text-white rounded-lg hover:bg-slate-600">Reset UI Cache</button>
                            <span id="cacheResetStatus" class="text-xs text-slate-400"></span>
                        </div>
                    </div>

                    <div class="content-panel p-4">
                        <h3 class="text-sm font-semibold text-slate-200 mb-2">UI Version</h3>
                        <p class="text-sm text-slate-400">v__UI_VERSION__</p>
                    </div>
                </div>
            </div>
        </section>

        <section id="section-agents" data-section-panel="agents" class="section-panel hidden">
            <div class="section-body custom-scrollbar">
                <div class="section-header">
                    <h2 class="section-title">Autonomous Agents</h2>
                    <p class="section-subtitle">Start and monitor AI agents that work autonomously to find money-making opportunities.</p>
                </div>

                <div class="bg-teal-900/20 border border-teal-700/40 rounded-lg p-4 mb-4">
                    <div class="flex items-start gap-3">
                        <svg class="w-5 h-5 text-teal-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                        </svg>
                        <div class="text-sm text-slate-300">
                            <strong>How it works:</strong> Agents search the web, find opportunities, and execute low-risk actions automatically.
                            You'll only be asked to approve high-risk actions (file writes, commands, deployments).
                        </div>
                    </div>
                </div>

                <div class="grid gap-4">
                    <!-- Agent Status -->
                    <div class="content-panel p-4">
                        <div class="flex items-center justify-between mb-3">
                            <h3 class="text-sm font-semibold text-slate-200">Agent Status</h3>
                            <button id="refreshAgentStatus" class="px-2 py-1 text-xs bg-slate-700 text-white rounded hover:bg-slate-600">
                                <svg class="w-3 h-3 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
                                </svg>
                                Refresh
                            </button>
                        </div>
                        <div id="agentStatusContainer" class="space-y-2">
                            <p class="text-xs text-slate-400">No agents running</p>
                        </div>
                    </div>

                    <!-- Start Agents -->
                    <div class="content-panel p-4">
                        <h3 class="text-sm font-semibold text-slate-200 mb-3">Start Agent Cycle</h3>
                        <p class="text-xs text-slate-400 mb-3">Select agents to run in parallel</p>

                        <div class="space-y-3 mb-4">
                            <label class="flex items-center gap-3 p-3 text-sm border border-slate-700 rounded-lg hover:bg-slate-800/40 transition cursor-pointer">
                                <input type="checkbox" class="agent-checkbox h-5 w-5 rounded border-slate-600 bg-slate-900 text-teal-500" value="job_hunter" checked />
                                <div class="flex items-center gap-2 flex-1">
                                    <span class="px-2 py-1 bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded text-xs font-semibold">💼 HUNTER</span>
                                    <div class="flex-1">
                                        <div class="font-medium text-white">Job Hunter</div>
                                        <div class="text-xs text-slate-400">Find high-paying freelance jobs</div>
                                    </div>
                                </div>
                            </label>
                            <label class="flex items-center gap-3 p-3 text-sm border border-slate-700 rounded-lg hover:bg-slate-800/40 transition cursor-pointer">
                                <input type="checkbox" class="agent-checkbox h-5 w-5 rounded border-slate-600 bg-slate-900 text-teal-500" value="content_creator" checked />
                                <div class="flex items-center gap-2 flex-1">
                                    <span class="px-2 py-1 bg-purple-500/20 text-purple-400 border border-purple-500/30 rounded text-xs font-semibold">✍️ CREATOR</span>
                                    <div class="flex-1">
                                        <div class="font-medium text-white">Content Creator</div>
                                        <div class="text-xs text-slate-400">Create revenue-generating content</div>
                                    </div>
                                </div>
                            </label>
                            <label class="flex items-center gap-3 p-3 text-sm border border-slate-700 rounded-lg hover:bg-slate-800/40 transition cursor-pointer">
                                <input type="checkbox" class="agent-checkbox h-5 w-5 rounded border-slate-600 bg-slate-900 text-teal-500" value="developer" checked />
                                <div class="flex items-center gap-2 flex-1">
                                    <span class="px-2 py-1 bg-green-500/20 text-green-400 border border-green-500/30 rounded text-xs font-semibold">💻 DEV</span>
                                    <div class="flex-1">
                                        <div class="font-medium text-white">Developer</div>
                                        <div class="text-xs text-slate-400">Build profitable SaaS products</div>
                                    </div>
                                </div>
                            </label>
                            <label class="flex items-center gap-3 p-3 text-sm border border-slate-700 rounded-lg hover:bg-slate-800/40 transition cursor-pointer">
                                <input type="checkbox" class="agent-checkbox h-5 w-5 rounded border-slate-600 bg-slate-900 text-teal-500" value="marketer" checked />
                                <div class="flex items-center gap-2 flex-1">
                                    <span class="px-2 py-1 bg-orange-500/20 text-orange-400 border border-orange-500/30 rounded text-xs font-semibold">📢 MARKET</span>
                                    <div class="flex-1">
                                        <div class="font-medium text-white">Marketer</div>
                                        <div class="text-xs text-slate-400">Promote products and drive traffic</div>
                                    </div>
                                </div>
                            </label>
                            <label class="flex items-center gap-3 p-3 text-sm border border-slate-700 rounded-lg hover:bg-slate-800/40 transition cursor-pointer">
                                <input type="checkbox" class="agent-checkbox h-5 w-5 rounded border-slate-600 bg-slate-900 text-teal-500" value="researcher" checked />
                                <div class="flex items-center gap-2 flex-1">
                                    <span class="px-2 py-1 bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 rounded text-xs font-semibold">🔬 RESEARCH</span>
                                    <div class="flex-1">
                                        <div class="font-medium text-white">Researcher</div>
                                        <div class="text-xs text-slate-400">Discover new opportunities</div>
                                    </div>
                                </div>
                            </label>
                        </div>

                        <div class="flex items-center gap-2">
                            <button id="startAgentsBtn" class="px-4 py-2 bg-teal-600 text-white rounded-lg hover:bg-teal-700 text-sm font-medium">
                                Start Agents
                            </button>
                            <span id="agentStartStatus" class="text-xs text-slate-400"></span>
                        </div>
                    </div>

                    <!-- Agent Results -->
                    <div class="content-panel p-4">
                        <h3 class="text-sm font-semibold text-slate-200 mb-3">Recent Results</h3>
                        <div id="agentResultsContainer" class="space-y-2 max-h-96 overflow-y-auto custom-scrollbar">
                            <p class="text-xs text-slate-400">No results yet</p>
                        </div>
                    </div>

                    <!-- Pending Approvals -->
                    <div id="pendingApprovalsPanel" class="content-panel p-4 hidden">
                        <h3 class="text-sm font-semibold text-slate-200 mb-3">Pending Approvals</h3>
                        <div id="pendingApprovalsContainer" class="space-y-3">
                            <!-- Rendered by JS -->
                        </div>
                    </div>
                </div>
            </div>
        </section>
    '''.replace("__UI_VERSION__", UI_VERSION)


def get_developer_sections_html() -> str:
    """Return HTML for the developer chat page."""
    return r'''
        <section id="section-developer" data-section-panel="developer" class="section-panel">
            <!-- Connectors Bar -->
            <div class="sticky top-0 z-10 bg-slate-900/95 backdrop-blur-sm border-b border-slate-800 px-4 py-2">
                <div class="max-w-3xl mx-auto flex items-center justify-between">
                    <div class="flex items-center gap-2">
                        <span class="text-xs text-slate-400">Connectors:</span>
                        <div id="devConnectorsList" class="flex items-center gap-2">
                            <span class="text-xs text-slate-500">None active</span>
                        </div>
                    </div>
                    <div class="relative">
                        <button id="addDevConnectorBtn" class="flex items-center gap-1 px-2 py-1 text-xs bg-teal-600 hover:bg-teal-700 text-white rounded transition">
                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path>
                            </svg>
                            Add Connector
                        </button>
                        <div id="devConnectorDropdown" class="hidden absolute right-0 mt-1 w-48 bg-slate-800 border border-slate-700 rounded-lg shadow-lg overflow-hidden z-20">
                            <div class="py-1">
                                <button class="w-full text-left px-3 py-2 text-xs text-slate-300 hover:bg-slate-700 transition">
                                    <div class="font-medium">GitHub</div>
                                    <div class="text-slate-500">Connect repositories</div>
                                </button>
                                <button class="w-full text-left px-3 py-2 text-xs text-slate-300 hover:bg-slate-700 transition">
                                    <div class="font-medium">Linear</div>
                                    <div class="text-slate-500">Track issues</div>
                                </button>
                                <button class="w-full text-left px-3 py-2 text-xs text-slate-300 hover:bg-slate-700 transition">
                                    <div class="font-medium">Docker</div>
                                    <div class="text-slate-500">Manage containers</div>
                                </button>
                                <button class="w-full text-left px-3 py-2 text-xs text-slate-300 hover:bg-slate-700 transition opacity-50 cursor-not-allowed">
                                    <div class="font-medium">More coming soon...</div>
                                    <div class="text-slate-500">Stay tuned</div>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div id="developerMessagesContainer" class="custom-scrollbar">
                <div class="max-w-3xl mx-auto px-4 py-6">
                    <div id="developerEmptyState" class="flex flex-col items-center justify-center py-16 text-center">
                        <div class="w-16 h-16 bg-teal-900/40 rounded-full flex items-center justify-center mb-4">
                            <div class="w-8 h-8 rounded-full border border-teal-400/60 bg-teal-400/15 flex items-center justify-center">
                                <div class="w-2.5 h-2.5 rounded-full bg-teal-400"></div>
                            </div>
                        </div>
                        <h2 class="text-xl font-semibold text-slate-200 mb-2">Developer Xone</h2>
                        <p class="text-sm text-slate-400 max-w-md mb-6">Describe a build or fix request and get a plan before execution.</p>
                        <div class="grid grid-cols-1 gap-3 w-full max-w-md">
                            <button onclick="usePrompt('Build a clean dashboard for my app')" class="p-3 text-left border border-slate-700 rounded-lg hover:bg-slate-800/60 transition">
                                <div class="font-medium text-slate-200 text-sm flex items-center gap-2">
                                    <svg class="w-4 h-4 text-teal-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7h16M4 12h16M4 17h10"></path>
                                    </svg>
                                    <span>Build request</span>
                                </div>
                                <div class="text-xs text-slate-400">Start a new project plan</div>
                            </button>
                        </div>
                    </div>

                    <div id="developerMessagesWrapper" class="space-y-4"></div>

                    <div id="developerTypingIndicator" class="hidden flex gap-3 fade-in">
                        <div class="w-8 h-8 bg-slate-700 rounded-full flex items-center justify-center flex-shrink-0">
                            <div class="w-3 h-3 rounded-full bg-teal-400"></div>
                        </div>
                        <div class="bg-slate-800 rounded-2xl px-4 py-3">
                            <div class="flex gap-1">
                                <div class="w-2 h-2 bg-slate-400 rounded-full typing-dot"></div>
                                <div class="w-2 h-2 bg-slate-400 rounded-full typing-dot"></div>
                                <div class="w-2 h-2 bg-slate-400 rounded-full typing-dot"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div id="developerComposer" class="px-4 py-3 flex-shrink-0">
                <form id="developerChatForm" class="max-w-3xl mx-auto">
                    <div class="relative">
                        <textarea id="developerMessageInput" placeholder="Describe your build or fix..." rows="1"
                            class="w-full px-4 py-3 pr-12 border border-slate-700 rounded-xl resize-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500 text-sm bg-slate-900/70 text-white"></textarea>
                        <button type="submit" id="developerSendBtn" class="absolute right-2 bottom-2 p-2 bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:bg-slate-700 disabled:cursor-not-allowed transition">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/></svg>
                        </button>
                    </div>
                    <p class="text-xs text-slate-400 mt-2 text-center">Enter to send • Shift+Enter for new line</p>
                </form>
            </div>
        </section>
    '''


def render_page(title: str, active_page: str, sections_html: str, page_mode: str, default_section: str) -> str:
    """Render a full HTML page with shared layout."""
    return f'''<!DOCTYPE html>
<html lang="en" class="h-full dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>{title}</title>

    <!-- PWA Support -->
    <link rel="manifest" href="/static/manifest.json?v={UI_VERSION}">
    <meta name="theme-color" content="#14b8a6">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="Xone">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;500;600;700&display=swap" rel="stylesheet">

    <script src="https://cdn.tailwindcss.com"></script>
    <script>tailwind.config = {{ darkMode: 'class' }}</script>
    <style>{get_base_styles()}</style>
</head>
<body class="h-full transition-colors dark:bg-slate-900">
    <div id="app" class="h-screen flex overflow-hidden">
        {get_sidebar_html(active_page)}

        <main class="flex-1 flex flex-col min-w-0">
            <header class="px-4 py-3 flex items-center justify-between flex-shrink-0">
                <div class="flex items-center gap-3">
                    <button id="toggleSidebar" class="lg:hidden p-2 hover:bg-slate-800 rounded-lg" aria-label="Toggle sidebar">
                        <svg class="w-5 h-5 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/></svg>
                    </button>
                    <span class="text-lg font-semibold text-white">Xone</span>
                </div>
                <div class="flex items-center gap-2">
                    <button id="darkModeToggle" class="p-2 hover:bg-slate-800 rounded-lg" title="Toggle dark mode">
                        <svg class="w-5 h-5 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/></svg>
                    </button>
                </div>
            </header>

            <div id="mainContent" class="min-h-0">
                {sections_html}
            </div>
        </main>
    </div>

    <script>
        {get_base_scripts(page_mode, default_section)}
    </script>
</body>
</html>'''


def get_command_center_html() -> str:
    """Return the main Chat UI HTML."""
    return render_page(
        title="Chat - Xone",
        active_page="chat",
        sections_html=get_chat_sections_html(),
        page_mode="chat",
        default_section="chat",
    )


def get_developer_html() -> str:
    """Return the Developer Xone UI HTML."""
    return render_page(
        title="Developer Xone - Xone",
        active_page="developer",
        sections_html=get_developer_sections_html(),
        page_mode="developer",
        default_section="developer",
    )


@router.get("/command-center", response_class=HTMLResponse)
async def command_center(request: Request):
    """Alias for the unified chat UI."""
    return html_response_no_cache(get_command_center_html())


@router.get("/chat", response_class=HTMLResponse)
async def command_center_chat(request: Request):
    """Unified Command Center - single UI entrypoint."""
    return html_response_no_cache(get_command_center_html())


@router.get("/developer", response_class=HTMLResponse)
async def developer_chat(request: Request):
    """Developer Xone chat interface."""
    return html_response_no_cache(get_developer_html())
