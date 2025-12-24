"""
Tool definitions and execution for Xone.

All tools follow the approval workflow:
1. Claude proposes tool use
2. Backend returns proposal
3. Owner approves
4. Backend executes
5. Result returned to Claude
"""
import os
import subprocess
import logging
from typing import Dict, Any, Tuple, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# =============================================================================
# Tool Definitions (for Claude)
# =============================================================================

TOOLS = [
    {
        "name": "create_file",
        "description": "Create a new file with specified content. Use this to generate new source files, configs, or documentation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to project root (e.g., 'app/api/new_feature.py')"
                },
                "content": {
                    "type": "string",
                    "description": "Complete file content to write"
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of what this file does"
                }
            },
            "required": ["path", "content", "description"]
        }
    },
    {
        "name": "edit_file",
        "description": "Modify an existing file by replacing old content with new content. Use this for targeted edits to existing files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to project root"
                },
                "old_content": {
                    "type": "string",
                    "description": "Exact text to find and replace (must be unique in the file)"
                },
                "new_content": {
                    "type": "string",
                    "description": "New text to replace the old content with"
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of the change"
                }
            },
            "required": ["path", "old_content", "new_content", "description"]
        }
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file. Use this to examine existing code before making changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to project root"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "run_command",
        "description": "Execute a shell command. Use for running tests, installing packages, git operations, etc. CAUTION: Use only safe, non-destructive commands.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute"
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory (optional, defaults to project root)"
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of what this command does"
                }
            },
            "required": ["command", "description"]
        }
    },
    {
        "name": "list_files",
        "description": "List files in a directory. Use this to explore the project structure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path relative to project root (default: '.')"
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g., '*.py', '**/test_*.py')"
                }
            },
            "required": []
        }
    },
    {
        "name": "remember",
        "description": "Store information in long-term memory for future reference. Use this to save insights, decisions, preferences, or important facts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "What to remember"
                },
                "category": {
                    "type": "string",
                    "description": "Category: 'insight', 'preference', 'decision', 'fact', or 'other'"
                }
            },
            "required": ["content", "category"]
        }
    }
]


# =============================================================================
# Tool Execution (Backend)
# =============================================================================

PROJECT_ROOT = Path("/home/elhassan/agent-service")


def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
    """
    Execute a tool.

    Args:
        tool_name: Name of the tool
        tool_input: Tool input parameters

    Returns:
        (success, output, error)
        - success: True if tool executed successfully
        - output: Tool output or result
        - error: Error message if failed, None otherwise
    """
    logger.info(f"execute_tool tool={tool_name} input_keys={list(tool_input.keys())}")

    try:
        if tool_name == "create_file":
            return _create_file(tool_input)
        elif tool_name == "edit_file":
            return _edit_file(tool_input)
        elif tool_name == "read_file":
            return _read_file(tool_input)
        elif tool_name == "run_command":
            return _run_command(tool_input)
        elif tool_name == "list_files":
            return _list_files(tool_input)
        elif tool_name == "remember":
            return _remember(tool_input)
        else:
            return False, "", f"Unknown tool: {tool_name}"

    except Exception as e:
        logger.error(f"tool_execution_error tool={tool_name}: {type(e).__name__}: {str(e)}")
        return False, "", f"Tool execution error: {str(e)}"


# =============================================================================
# Tool Implementations
# =============================================================================

def _create_file(tool_input: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
    """Create a new file."""
    path = tool_input["path"]
    content = tool_input["content"]
    description = tool_input.get("description", "")

    file_path = PROJECT_ROOT / path

    # Check if file already exists
    if file_path.exists():
        return False, "", f"File already exists: {path}"

    # Create parent directories if needed
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Write file
    file_path.write_text(content)

    output = f"Created {path} ({len(content)} bytes)\n{description}"
    logger.info(f"file_created path={path} size={len(content)}")
    return True, output, None


def _edit_file(tool_input: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
    """Edit an existing file."""
    path = tool_input["path"]
    old_content = tool_input["old_content"]
    new_content = tool_input["new_content"]
    description = tool_input.get("description", "")

    file_path = PROJECT_ROOT / path

    # Check if file exists
    if not file_path.exists():
        return False, "", f"File not found: {path}"

    # Read current content
    current_content = file_path.read_text()

    # Check if old_content exists in file
    if old_content not in current_content:
        return False, "", f"Old content not found in {path}. The file may have changed."

    # Check if old_content is unique
    if current_content.count(old_content) > 1:
        return False, "", f"Old content appears {current_content.count(old_content)} times in {path}. Must be unique."

    # Perform replacement
    new_file_content = current_content.replace(old_content, new_content, 1)

    # Write updated file
    file_path.write_text(new_file_content)

    output = f"Edited {path}\n{description}"
    logger.info(f"file_edited path={path}")
    return True, output, None


def _read_file(tool_input: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
    """Read a file."""
    path = tool_input["path"]
    file_path = PROJECT_ROOT / path

    if not file_path.exists():
        return False, "", f"File not found: {path}"

    if not file_path.is_file():
        return False, "", f"Not a file: {path}"

    content = file_path.read_text()
    logger.info(f"file_read path={path} size={len(content)}")
    return True, content, None


def _run_command(tool_input: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
    """Run a shell command."""
    command = tool_input["command"]
    cwd = tool_input.get("cwd", ".")
    description = tool_input.get("description", "")

    work_dir = PROJECT_ROOT / cwd

    if not work_dir.exists():
        return False, "", f"Directory not found: {cwd}"

    # Security check: block dangerous commands
    dangerous_patterns = ["rm -rf", "sudo ", "mkfs", "dd if=", "> /dev/"]
    for pattern in dangerous_patterns:
        if pattern in command.lower():
            return False, "", f"Blocked dangerous command pattern: {pattern}"

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=60,  # 60 second timeout
        )

        output = result.stdout if result.stdout else result.stderr
        output = output[:5000]  # Limit output size

        if result.returncode != 0:
            logger.warning(f"command_failed command='{command}' exit_code={result.returncode}")
            return False, output, f"Command exited with code {result.returncode}"

        logger.info(f"command_success command='{command}'")
        return True, f"{description}\n\nOutput:\n{output}", None

    except subprocess.TimeoutExpired:
        return False, "", "Command timed out (60s limit)"
    except Exception as e:
        return False, "", f"Command error: {str(e)}"


def _list_files(tool_input: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
    """List files in a directory."""
    path = tool_input.get("path", ".")
    pattern = tool_input.get("pattern", "*")

    dir_path = PROJECT_ROOT / path

    if not dir_path.exists():
        return False, "", f"Directory not found: {path}"

    if not dir_path.is_dir():
        return False, "", f"Not a directory: {path}"

    # List files matching pattern
    files = sorted(dir_path.glob(pattern))

    # Limit to 100 files
    if len(files) > 100:
        files = files[:100]
        truncated = f"\n... (showing first 100 of {len(list(dir_path.glob(pattern)))} files)"
    else:
        truncated = ""

    file_list = "\n".join(str(f.relative_to(PROJECT_ROOT)) for f in files)
    output = f"Files in {path} (pattern: {pattern}):\n{file_list}{truncated}"

    logger.info(f"files_listed path={path} count={len(files)}")
    return True, output, None


def _remember(tool_input: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
    """Store a memory."""
    from app.llm.memory_manager import store_memory

    content = tool_input["content"]
    category = tool_input.get("category", "other")

    # Validate category
    valid_categories = ["insight", "preference", "decision", "fact", "other"]
    if category not in valid_categories:
        category = "other"

    try:
        memory_id = store_memory(content, category)
        output = f"Memory stored (ID: {memory_id}, category: {category})\n{content[:200]}{'...' if len(content) > 200 else ''}"
        return True, output, None
    except Exception as e:
        return False, "", f"Failed to store memory: {str(e)}"


# =============================================================================
# Tool Risk Assessment
# =============================================================================

def assess_tool_risk(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """
    Assess the risk level of a tool execution.

    Returns:
        "low", "medium", or "high"
    """
    if tool_name in ["read_file", "list_files"]:
        return "low"  # Read-only operations

    if tool_name == "remember":
        return "low"  # Just storing data

    if tool_name == "create_file":
        # Check if it's creating in a safe location
        path = tool_input.get("path", "")
        if any(danger in path for danger in ["/etc/", "/usr/", "/bin/", "/sys/"]):
            return "high"
        return "medium"

    if tool_name == "edit_file":
        # Editing is medium risk
        path = tool_input.get("path", "")
        if any(critical in path for critical in ["main.py", "database.py", ".env"]):
            return "high"
        return "medium"

    if tool_name == "run_command":
        # Commands are always at least medium risk
        command = tool_input.get("command", "")
        dangerous_keywords = ["rm", "delete", "drop", "truncate", "kill", "sudo"]
        if any(keyword in command.lower() for keyword in dangerous_keywords):
            return "high"
        return "medium"

    return "medium"  # Default to medium for unknown tools
