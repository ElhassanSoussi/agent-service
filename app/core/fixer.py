"""
Issue Fixer for diagnosing and fixing bugs in repositories.
Analyzes repos and generates patches based on error logs and problem descriptions.

Features:
- Repository structure analysis
- Root cause identification
- Reproduction plan generation
- Patch generation as unified diffs
- Verification checklist

Security:
- Read-only repository access
- No shell command execution
- Patch proposals only (never applied)
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Optional, Any

from app.core.repo_tools import (
    repo_get_tree,
    repo_get_file,
    repo_get_readme,
    repo_get_info,
    repo_search_code,
)

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

MAX_FILES_TO_ANALYZE = 20
MAX_FILE_SIZE_FOR_ANALYSIS = 100 * 1024  # 100KB


@dataclass
class ReproStep:
    """A step in the reproduction plan."""
    step_number: int
    description: str
    command: Optional[str] = None
    expected_result: Optional[str] = None


@dataclass
class VerificationItem:
    """An item in the verification checklist."""
    description: str
    command: Optional[str] = None
    is_manual: bool = False


@dataclass
class FixerPatch:
    """A proposed patch."""
    path: str
    diff_type: str  # "add", "modify", "delete"
    description: str
    unified_diff: str
    original_content: Optional[str] = None
    new_content: Optional[str] = None
    confidence: str = "medium"  # "high", "medium", "low"


@dataclass
class FixerAnalysis:
    """Complete analysis of an issue."""
    # Repository info
    owner: str
    repo: str
    ref: str
    
    # Analysis results
    repo_summary: str
    likely_cause: str
    affected_files: list[str] = field(default_factory=list)
    
    # Plans and patches
    repro_plan: list[ReproStep] = field(default_factory=list)
    patches: list[FixerPatch] = field(default_factory=list)
    verification_checklist: list[VerificationItem] = field(default_factory=list)
    
    # Metadata
    risk_notes: Optional[str] = None
    analysis_steps: list[dict] = field(default_factory=list)
    files_analyzed: int = 0
    error: Optional[str] = None


class FixerError(Exception):
    """Error during issue fixing."""
    pass


async def analyze_issue(
    owner: str,
    repo: str,
    ref: str,
    prompt: str,
    error_log: Optional[str] = None,
    stacktrace: Optional[str] = None,
    failing_test: Optional[str] = None,
    expected_behavior: Optional[str] = None,
    path_prefix: Optional[str] = None,
) -> FixerAnalysis:
    """
    Analyze an issue in a repository and propose fixes.
    
    Args:
        owner: Repository owner
        repo: Repository name
        ref: Git reference (branch, tag, commit)
        prompt: Problem description
        error_log: Optional error log text
        stacktrace: Optional stack trace
        failing_test: Optional failing test name
        expected_behavior: Optional expected behavior description
        path_prefix: Optional path prefix to limit analysis scope
        
    Returns:
        FixerAnalysis with diagnosis and proposed patches
    """
    analysis = FixerAnalysis(owner=owner, repo=repo, ref=ref, repo_summary="", likely_cause="")
    
    try:
        # Step 1: Get repository info
        _add_step(analysis, "get_repo_info", f"{owner}/{repo}")
        info_result = await repo_get_info(owner, repo)
        
        if "error" in info_result:
            analysis.error = f"Failed to access repository: {info_result['error']}"
            return analysis
        
        language = info_result.get("language", "Unknown")
        default_branch = info_result.get("default_branch", "main")
        description = info_result.get("description", "")
        
        # Step 2: Get repository tree
        _add_step(analysis, "get_tree", ref)
        tree_result = await repo_get_tree(owner, repo, ref=ref, recursive=True)
        
        if "error" in tree_result:
            analysis.error = f"Failed to get repository tree: {tree_result['error']}"
            return analysis
        
        tree = tree_result.get("tree", [])
        
        # Filter by path prefix if provided
        if path_prefix:
            tree = [f for f in tree if f.get("path", "").startswith(path_prefix)]
        
        # Step 3: Identify relevant files based on context
        _add_step(analysis, "identify_files", prompt[:100])
        relevant_files = await _identify_relevant_files(
            owner, repo, ref, tree, prompt, error_log, stacktrace, failing_test
        )
        
        analysis.affected_files = [f["path"] for f in relevant_files[:MAX_FILES_TO_ANALYZE]]
        analysis.files_analyzed = len(analysis.affected_files)
        
        # Step 4: Build repository summary
        analysis.repo_summary = _build_repo_summary(
            owner, repo, language, description, tree, analysis.affected_files
        )
        
        # Step 5: Analyze the issue
        _add_step(analysis, "analyze_issue", "determining root cause")
        analysis.likely_cause = _determine_likely_cause(
            prompt, error_log, stacktrace, failing_test, relevant_files
        )
        
        # Step 6: Generate reproduction plan
        _add_step(analysis, "generate_repro_plan", "")
        analysis.repro_plan = _generate_repro_plan(
            language, prompt, error_log, failing_test
        )
        
        # Step 7: Generate patches
        _add_step(analysis, "generate_patches", "")
        file_contents = {}
        for file_info in relevant_files[:5]:  # Limit to top 5 files
            path = file_info["path"]
            file_result = await repo_get_file(owner, repo, path, ref=ref)
            if "content" in file_result:
                file_contents[path] = file_result["content"]
        
        analysis.patches = _generate_patches(
            prompt, error_log, stacktrace, failing_test, file_contents, language
        )
        
        # Step 8: Generate verification checklist
        _add_step(analysis, "generate_verification", "")
        analysis.verification_checklist = _generate_verification_checklist(
            language, analysis.patches, failing_test
        )
        
        # Step 9: Add risk notes
        analysis.risk_notes = _generate_risk_notes(analysis.patches, prompt)
        
        logger.info(
            f"fixer_analysis_complete owner={owner} repo={repo} "
            f"files_analyzed={analysis.files_analyzed} patches={len(analysis.patches)}"
        )
        
        return analysis
        
    except Exception as e:
        logger.error(f"fixer_analysis_failed owner={owner} repo={repo} error={type(e).__name__}")
        analysis.error = f"Analysis failed: {type(e).__name__}"
        return analysis


def _add_step(analysis: FixerAnalysis, action: str, target: str) -> None:
    """Add an analysis step."""
    analysis.analysis_steps.append({
        "step_number": len(analysis.analysis_steps) + 1,
        "action": action,
        "target": target,
        "status": "done",
    })


async def _identify_relevant_files(
    owner: str,
    repo: str,
    ref: str,
    tree: list[dict],
    prompt: str,
    error_log: Optional[str],
    stacktrace: Optional[str],
    failing_test: Optional[str],
) -> list[dict]:
    """Identify files that are likely relevant to the issue."""
    relevant = []
    seen_paths = set()
    
    # Extract file paths from stacktrace
    if stacktrace:
        # Common patterns: "File "path/to/file.py", line 123"
        # Or: "at module.function (path/to/file.js:123:45)"
        patterns = [
            r'File ["\']([^"\']+)["\']',
            r'at .+ \(([^:]+):\d+',
            r'([a-zA-Z0-9_/.-]+\.(py|js|ts|go|rs|java|rb|php)):',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, stacktrace)
            for match in matches:
                path = match[0] if isinstance(match, tuple) else match
                path = path.lstrip("./")
                if path not in seen_paths:
                    for f in tree:
                        if f.get("path", "").endswith(path) or path in f.get("path", ""):
                            relevant.append(f)
                            seen_paths.add(f["path"])
                            break
    
    # Extract paths from error log
    if error_log:
        for f in tree:
            path = f.get("path", "")
            if f.get("type") == "file" and path not in seen_paths:
                # Check if file is mentioned in error
                if path in error_log or path.split("/")[-1] in error_log:
                    relevant.append(f)
                    seen_paths.add(path)
    
    # Look for test files if failing_test specified
    if failing_test:
        test_patterns = ["test_", "_test.", ".test.", ".spec.", "_spec."]
        for f in tree:
            path = f.get("path", "")
            if f.get("type") == "file" and path not in seen_paths:
                if any(p in path.lower() for p in test_patterns):
                    if failing_test.lower() in path.lower():
                        relevant.append(f)
                        seen_paths.add(path)
    
    # Extract keywords from prompt and search
    prompt_lower = prompt.lower()
    keywords = re.findall(r'\b[a-z_][a-z0-9_]+\b', prompt_lower)
    important_keywords = [k for k in keywords if len(k) > 3][:10]
    
    for f in tree:
        if f.get("type") != "file":
            continue
        path = f.get("path", "")
        if path in seen_paths:
            continue
            
        path_lower = path.lower()
        # Score by keyword matches
        score = sum(1 for k in important_keywords if k in path_lower)
        if score > 0:
            f["_relevance_score"] = score
            relevant.append(f)
            seen_paths.add(path)
    
    # Look for common entry points
    entry_points = [
        "main.py", "app.py", "index.js", "index.ts", "main.go",
        "app/main.py", "src/main.py", "src/index.ts", "src/index.js",
    ]
    for ep in entry_points:
        if ep not in seen_paths:
            for f in tree:
                if f.get("path", "") == ep or f.get("path", "").endswith(f"/{ep}"):
                    relevant.append(f)
                    seen_paths.add(f["path"])
                    break
    
    # Sort by relevance
    relevant.sort(key=lambda x: x.get("_relevance_score", 0), reverse=True)
    
    return relevant


def _build_repo_summary(
    owner: str,
    repo: str,
    language: str,
    description: str,
    tree: list[dict],
    affected_files: list[str],
) -> str:
    """Build a summary of the repository structure."""
    # Count file types
    extensions = {}
    for f in tree:
        if f.get("type") == "file":
            path = f.get("path", "")
            ext = path.rsplit(".", 1)[-1] if "." in path else "other"
            extensions[ext] = extensions.get(ext, 0) + 1
    
    top_extensions = sorted(extensions.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # Find key directories
    dirs = set()
    for f in tree:
        path = f.get("path", "")
        parts = path.split("/")
        if len(parts) > 1:
            dirs.add(parts[0])
    
    summary_parts = [
        f"Repository: {owner}/{repo}",
        f"Primary Language: {language}",
    ]
    
    if description:
        summary_parts.append(f"Description: {description}")
    
    summary_parts.append(f"Total Files: {len([f for f in tree if f.get('type') == 'file'])}")
    
    if top_extensions:
        ext_str = ", ".join(f".{ext} ({count})" for ext, count in top_extensions)
        summary_parts.append(f"File Types: {ext_str}")
    
    if dirs:
        summary_parts.append(f"Top-level Directories: {', '.join(sorted(dirs)[:10])}")
    
    if affected_files:
        summary_parts.append(f"Files of Interest: {', '.join(affected_files[:5])}")
    
    return "\n".join(summary_parts)


def _determine_likely_cause(
    prompt: str,
    error_log: Optional[str],
    stacktrace: Optional[str],
    failing_test: Optional[str],
    relevant_files: list[dict],
) -> str:
    """Determine the likely root cause based on available information."""
    causes = []
    
    # Analyze error patterns
    if error_log:
        error_lower = error_log.lower()
        if "import" in error_lower or "module not found" in error_lower:
            causes.append("Missing or incorrect import/dependency")
        if "undefined" in error_lower or "is not defined" in error_lower:
            causes.append("Reference to undefined variable or function")
        if "null" in error_lower or "none" in error_lower or "nil" in error_lower:
            causes.append("Null/None reference error")
        if "timeout" in error_lower:
            causes.append("Operation timeout - possible performance issue or deadlock")
        if "permission" in error_lower or "access denied" in error_lower:
            causes.append("Permission or access control issue")
        if "connection" in error_lower:
            causes.append("Connection/network issue")
        if "syntax" in error_lower:
            causes.append("Syntax error in code")
        if "type" in error_lower and ("error" in error_lower or "mismatch" in error_lower):
            causes.append("Type mismatch or type error")
    
    if stacktrace:
        # Extract the actual error message (usually last line or after "Error:")
        lines = stacktrace.strip().split("\n")
        for line in reversed(lines):
            line = line.strip()
            if line and not line.startswith(("at ", "File ", "  ")):
                if "Error" in line or "Exception" in line:
                    causes.append(f"Exception: {line[:100]}")
                    break
    
    if failing_test:
        causes.append(f"Test failure in: {failing_test}")
    
    # Default analysis based on prompt
    prompt_lower = prompt.lower()
    if "crash" in prompt_lower:
        causes.append("Application crash - check error handling")
    if "slow" in prompt_lower or "performance" in prompt_lower:
        causes.append("Performance issue - check for inefficient operations")
    if "memory" in prompt_lower:
        causes.append("Memory issue - check for leaks or excessive allocation")
    
    if not causes:
        causes.append(f"Issue described: {prompt[:200]}")
    
    return " | ".join(causes[:3])


def _generate_repro_plan(
    language: str,
    prompt: str,
    error_log: Optional[str],
    failing_test: Optional[str],
) -> list[ReproStep]:
    """Generate a reproduction plan for the issue."""
    steps = []
    step_num = 1
    
    # Language-specific setup
    lang_setup = {
        "Python": ("python -m venv venv && source venv/bin/activate", "pip install -r requirements.txt"),
        "JavaScript": (None, "npm install"),
        "TypeScript": (None, "npm install"),
        "Go": (None, "go mod download"),
        "Rust": (None, "cargo build"),
    }
    
    setup = lang_setup.get(language, (None, None))
    
    steps.append(ReproStep(
        step_number=step_num,
        description="Clone the repository",
        command="git clone <repo_url> && cd <repo>",
        expected_result="Repository cloned successfully",
    ))
    step_num += 1
    
    if setup[0]:
        steps.append(ReproStep(
            step_number=step_num,
            description="Set up virtual environment",
            command=setup[0],
            expected_result="Environment activated",
        ))
        step_num += 1
    
    if setup[1]:
        steps.append(ReproStep(
            step_number=step_num,
            description="Install dependencies",
            command=setup[1],
            expected_result="Dependencies installed without errors",
        ))
        step_num += 1
    
    if failing_test:
        test_cmd = {
            "Python": f"pytest {failing_test} -v",
            "JavaScript": f"npm test -- {failing_test}",
            "TypeScript": f"npm test -- {failing_test}",
            "Go": f"go test -v -run {failing_test}",
            "Rust": f"cargo test {failing_test}",
        }.get(language, f"<test_command> {failing_test}")
        
        steps.append(ReproStep(
            step_number=step_num,
            description=f"Run the failing test: {failing_test}",
            command=test_cmd,
            expected_result="Test should fail, reproducing the issue",
        ))
        step_num += 1
    else:
        # Generic reproduction step
        steps.append(ReproStep(
            step_number=step_num,
            description="Reproduce the issue",
            command="# Follow the steps described in the issue",
            expected_result="Issue should be reproducible",
        ))
        step_num += 1
    
    if error_log:
        steps.append(ReproStep(
            step_number=step_num,
            description="Verify error matches reported log",
            command=None,
            expected_result=f"Error should contain: {error_log[:100]}...",
        ))
    
    return steps


def _generate_patches(
    prompt: str,
    error_log: Optional[str],
    stacktrace: Optional[str],
    failing_test: Optional[str],
    file_contents: dict[str, str],
    language: str,
) -> list[FixerPatch]:
    """
    Generate patch proposals based on analysis.
    
    NOTE: This is a simplified implementation. In a production system,
    this would use an LLM to generate actual code fixes.
    """
    patches = []
    
    # For now, create placeholder patches showing the analysis
    for path, content in file_contents.items():
        # Identify potential issues in the file based on error context
        issues = []
        
        if error_log:
            # Look for related patterns in the file
            for line_num, line in enumerate(content.split("\n"), 1):
                # Check for common issues
                if "TODO" in line or "FIXME" in line:
                    issues.append((line_num, "TODO/FIXME marker found"))
                if "except:" in line and "Exception" not in line:
                    issues.append((line_num, "Bare except clause"))
                if "pass" in line and "except" in content.split("\n")[line_num-2:line_num-1]:
                    issues.append((line_num, "Silent exception handling"))
        
        if issues:
            description = f"Potential issues found in {path}:\n"
            description += "\n".join(f"  Line {ln}: {issue}" for ln, issue in issues[:5])
            
            patches.append(FixerPatch(
                path=path,
                diff_type="modify",
                description=description,
                unified_diff=_create_analysis_comment(path, issues, language),
                original_content=content,
                new_content=content,  # Placeholder - no actual changes
                confidence="low",
            ))
    
    # Add a summary patch if no specific patches found
    if not patches and file_contents:
        first_file = list(file_contents.keys())[0]
        patches.append(FixerPatch(
            path=first_file,
            diff_type="modify",
            description=(
                f"Analysis based on: {prompt[:100]}...\n"
                "Manual review recommended for the identified files."
            ),
            unified_diff=f"# Analysis for: {first_file}\n# Review needed based on reported issue",
            confidence="low",
        ))
    
    return patches


def _create_analysis_comment(path: str, issues: list[tuple], language: str) -> str:
    """Create a unified diff with analysis comments."""
    comment_style = {
        "Python": "#",
        "JavaScript": "//",
        "TypeScript": "//",
        "Go": "//",
        "Rust": "//",
        "Ruby": "#",
    }
    comment = comment_style.get(language, "#")
    
    lines = [
        f"--- a/{path}",
        f"+++ b/{path}",
        "@@ -1,0 +1,0 @@",
        f"+{comment} ANALYSIS: Potential issues identified:",
    ]
    for line_num, issue in issues[:5]:
        lines.append(f"+{comment}   Line {line_num}: {issue}")
    lines.append(f"+{comment} Review and fix as needed")
    
    return "\n".join(lines)


def _generate_verification_checklist(
    language: str,
    patches: list[FixerPatch],
    failing_test: Optional[str],
) -> list[VerificationItem]:
    """Generate a verification checklist."""
    items = []
    
    # Language-specific test commands
    test_commands = {
        "Python": "pytest",
        "JavaScript": "npm test",
        "TypeScript": "npm test",
        "Go": "go test ./...",
        "Rust": "cargo test",
    }
    
    items.append(VerificationItem(
        description="Review all proposed patches carefully before applying",
        is_manual=True,
    ))
    
    items.append(VerificationItem(
        description="Create a backup or work on a branch",
        command="git checkout -b fix-branch",
    ))
    
    if patches:
        items.append(VerificationItem(
            description="Apply patches and review changes",
            command="git apply <patch_file>",
        ))
    
    test_cmd = test_commands.get(language, "# run your test suite")
    items.append(VerificationItem(
        description="Run the full test suite",
        command=test_cmd,
    ))
    
    if failing_test:
        specific_test = {
            "Python": f"pytest {failing_test} -v",
            "JavaScript": f"npm test -- --grep '{failing_test}'",
            "TypeScript": f"npm test -- --grep '{failing_test}'",
            "Go": f"go test -v -run {failing_test}",
            "Rust": f"cargo test {failing_test}",
        }.get(language, f"# run {failing_test}")
        
        items.append(VerificationItem(
            description=f"Verify the specific failing test now passes",
            command=specific_test,
        ))
    
    items.append(VerificationItem(
        description="Test the fix manually in your environment",
        is_manual=True,
    ))
    
    items.append(VerificationItem(
        description="Check for any regressions",
        is_manual=True,
    ))
    
    return items


def _generate_risk_notes(patches: list[FixerPatch], prompt: str) -> str:
    """Generate risk notes for the proposed changes."""
    notes = []
    
    notes.append("⚠️ IMPORTANT: These are proposed changes only. Review carefully before applying.")
    
    if any(p.confidence == "low" for p in patches):
        notes.append("• Some patches have low confidence - additional analysis may be needed.")
    
    if "database" in prompt.lower() or "migration" in prompt.lower():
        notes.append("• Database changes detected - ensure proper backup before applying.")
    
    if "auth" in prompt.lower() or "security" in prompt.lower():
        notes.append("• Security-related changes - thorough review and testing required.")
    
    if "api" in prompt.lower():
        notes.append("• API changes may affect clients - check for breaking changes.")
    
    notes.append("• Always test in a non-production environment first.")
    
    return "\n".join(notes)
