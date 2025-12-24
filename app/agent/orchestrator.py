"""
Multi-agent orchestrator for autonomous money-making system.

Manages multiple specialized agents working in parallel.
"""
import uuid
import logging
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from enum import Enum

from app.llm.claude_client import send_message
from app.llm.tools import execute_tool, assess_tool_risk, TOOLS
from app.llm.memory_manager import get_relevant_memories, store_memory
from app.agent.prompts import (
    JOB_HUNTER_PROMPT,
    CONTENT_CREATOR_PROMPT,
    DEVELOPER_PROMPT,
    MARKETER_PROMPT,
    RESEARCHER_PROMPT,
    ORCHESTRATOR_PROMPT,
)
from app.db.database import SessionLocal
from app.db.models import XoneConversation, XoneMessage

logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    """Agent roles in the system."""
    JOB_HUNTER = "job_hunter"
    CONTENT_CREATOR = "content_creator"
    DEVELOPER = "developer"
    MARKETER = "marketer"
    RESEARCHER = "researcher"
    ORCHESTRATOR = "orchestrator"


AGENT_PROMPTS = {
    AgentRole.JOB_HUNTER: JOB_HUNTER_PROMPT,
    AgentRole.CONTENT_CREATOR: CONTENT_CREATOR_PROMPT,
    AgentRole.DEVELOPER: DEVELOPER_PROMPT,
    AgentRole.MARKETER: MARKETER_PROMPT,
    AgentRole.RESEARCHER: RESEARCHER_PROMPT,
    AgentRole.ORCHESTRATOR: ORCHESTRATOR_PROMPT,
}


# =============================================================================
# Agent State Management
# =============================================================================

class AgentState:
    """Tracks state of running agents."""

    def __init__(self):
        self.active_agents: Dict[str, Dict[str, Any]] = {}
        self.pending_approvals: Dict[str, Dict[str, Any]] = {}
        self.results: List[Dict[str, Any]] = []

    def start_agent(self, agent_id: str, role: AgentRole, task: str):
        """Mark agent as active."""
        self.active_agents[agent_id] = {
            "role": role,
            "task": task,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
        }
        logger.info(f"agent_started id={agent_id} role={role}")

    def complete_agent(self, agent_id: str, result: Any):
        """Mark agent as completed."""
        if agent_id in self.active_agents:
            self.active_agents[agent_id]["status"] = "completed"
            self.active_agents[agent_id]["completed_at"] = datetime.now(timezone.utc).isoformat()

        self.results.append({
            "agent_id": agent_id,
            "result": result,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"agent_completed id={agent_id}")

    def add_pending_approval(self, approval_id: str, agent_id: str, tools: List, context: Dict):
        """Add pending tool approval."""
        self.pending_approvals[approval_id] = {
            "agent_id": agent_id,
            "tools": tools,
            "context": context,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info(f"pending_approval_added id={approval_id} agent={agent_id} tools={len(tools)}")

    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        """Get all pending approvals."""
        return [
            {"id": k, **v}
            for k, v in self.pending_approvals.items()
        ]


# Global agent state
_agent_state = AgentState()


# =============================================================================
# Agent Execution
# =============================================================================

async def run_agent(
    role: AgentRole,
    task: str,
    auto_approve_low_risk: bool = True
) -> Dict[str, Any]:
    """
    Run a single agent with a specific task.

    Args:
        role: Agent role
        task: Task description
        auto_approve_low_risk: Automatically approve low-risk tools

    Returns:
        Agent execution result
    """
    agent_id = str(uuid.uuid4())
    _agent_state.start_agent(agent_id, role, task)

    # Get agent system prompt
    system_prompt = AGENT_PROMPTS[role]

    # Get relevant memories
    memories = get_relevant_memories(task)
    if memories:
        system_prompt = f"{system_prompt}\n\nRELEVANT MEMORIES:\n{memories}"

    # Build messages
    messages = [{
        "role": "user",
        "content": f"TASK: {task}\n\nAnalyze this task and propose actions using your tools."
    }]

    try:
        # Send to Claude
        response = await send_message(
            messages=messages,
            system=system_prompt,
            tools=TOOLS,
        )

        # Check for tool use
        tool_uses = []
        for block in response.content:
            if block.type == "tool_use":
                tool_uses.append(block)

        if tool_uses:
            # Assess risk
            all_low_risk = all(
                assess_tool_risk(tu.name, tu.input) == "low"
                for tu in tool_uses
            )

            if auto_approve_low_risk and all_low_risk:
                # Auto-approve low-risk tools
                logger.info(f"auto_approving agent={agent_id} tools={len(tool_uses)}")

                # Execute tools
                tool_results = []
                for tu in tool_uses:
                    success, output, error = execute_tool(tu.name, tu.input)
                    tool_results.append({
                        "tool_use_id": tu.id,
                        "type": "tool_result",
                        "content": output if success else error,
                        "is_error": not success,
                    })

                # Send results back to Claude for final response
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

                final_response = await send_message(
                    messages=messages,
                    system=system_prompt,
                    tools=TOOLS,
                )

                # Extract final text
                final_text = ""
                for block in final_response.content:
                    if block.type == "text":
                        final_text += block.text

                result = {
                    "status": "completed",
                    "response": final_text,
                    "tools_executed": len(tool_uses),
                    "auto_approved": True,
                }

                _agent_state.complete_agent(agent_id, result)
                return result

            else:
                # Needs approval
                approval_id = str(uuid.uuid4())
                _agent_state.add_pending_approval(
                    approval_id,
                    agent_id,
                    tool_uses,
                    {
                        "role": role,
                        "task": task,
                        "messages": messages,
                        "response": response,
                    }
                )

                return {
                    "status": "pending_approval",
                    "approval_id": approval_id,
                    "agent_id": agent_id,
                    "role": role,
                    "tools_proposed": len(tool_uses),
                    "tool_details": [
                        {
                            "name": tu.name,
                            "input": tu.input,
                            "risk": assess_tool_risk(tu.name, tu.input),
                        }
                        for tu in tool_uses
                    ]
                }

        else:
            # No tools, just text response
            text_response = ""
            for block in response.content:
                if block.type == "text":
                    text_response += block.text

            result = {
                "status": "completed",
                "response": text_response,
                "tools_executed": 0,
            }

            _agent_state.complete_agent(agent_id, result)
            return result

    except Exception as e:
        logger.error(f"agent_error id={agent_id} role={role}: {type(e).__name__}: {str(e)}")
        result = {
            "status": "error",
            "error": str(e),
        }
        _agent_state.complete_agent(agent_id, result)
        return result


# =============================================================================
# Multi-Agent Orchestration
# =============================================================================

async def run_autonomous_cycle(
    agents: List[AgentRole],
    auto_approve_low_risk: bool = True
) -> Dict[str, Any]:
    """
    Run multiple agents in parallel for one autonomous cycle.

    Args:
        agents: List of agent roles to run
        auto_approve_low_risk: Auto-approve low-risk tools

    Returns:
        Results from all agents
    """
    logger.info(f"autonomous_cycle_started agents={[a.value for a in agents]}")

    # Define tasks for each agent
    tasks = {
        AgentRole.JOB_HUNTER: "Find the top 5 highest-paying freelance jobs available today that Elhassan can do. Focus on Python, web scraping, data entry, or content writing.",
        AgentRole.CONTENT_CREATOR: "Research trending tech topics for 2025 and propose 3 article ideas that would perform well on Medium or Dev.to.",
        AgentRole.DEVELOPER: "Search for profitable micro-SaaS ideas that can be built in 1-2 weeks using free tools. Find the top 3 opportunities.",
        AgentRole.MARKETER: "Analyze successful indie hacker marketing strategies and propose 3 tactics we can use for free.",
        AgentRole.RESEARCHER: "Explore the web for new money-making opportunities that emerged in the last month. Find unconventional methods.",
    }

    # Run agents in parallel
    agent_tasks = []
    for agent_role in agents:
        task = tasks.get(agent_role, f"Perform your role as {agent_role.value}")
        agent_tasks.append(run_agent(agent_role, task, auto_approve_low_risk))

    # Wait for all agents
    results = await asyncio.gather(*agent_tasks, return_exceptions=True)

    # Process results
    completed = []
    pending_approvals = []
    errors = []

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            errors.append({
                "agent": agents[i].value,
                "error": str(result),
            })
        elif result.get("status") == "pending_approval":
            pending_approvals.append(result)
        elif result.get("status") == "completed":
            completed.append({
                "agent": agents[i].value,
                "response": result.get("response"),
                "tools_executed": result.get("tools_executed", 0),
            })
        else:
            errors.append({
                "agent": agents[i].value,
                "result": result,
            })

    logger.info(f"autonomous_cycle_completed completed={len(completed)} pending={len(pending_approvals)} errors={len(errors)}")

    # Store summary in memory
    if completed:
        summary = f"Autonomous cycle completed at {datetime.now(timezone.utc).isoformat()}:\n"
        for c in completed:
            summary += f"- {c['agent']}: {c['response'][:200]}...\n"

        store_memory(summary, category="insight")

    return {
        "completed": completed,
        "pending_approvals": pending_approvals,
        "errors": errors,
        "total_agents": len(agents),
    }


# =============================================================================
# Approval Management
# =============================================================================

def get_pending_approvals() -> List[Dict[str, Any]]:
    """Get all pending approvals."""
    return _agent_state.get_pending_approvals()


async def approve_pending(approval_id: str, approved: bool) -> Dict[str, Any]:
    """
    Approve or reject pending tool execution.

    Args:
        approval_id: Approval ID
        approved: Whether approved

    Returns:
        Execution result
    """
    pending = _agent_state.pending_approvals.get(approval_id)

    if not pending:
        return {
            "status": "error",
            "error": "Approval not found",
        }

    if not approved:
        # Rejected
        del _agent_state.pending_approvals[approval_id]
        return {
            "status": "rejected",
            "message": "Tool execution rejected by user",
        }

    # Approved - execute tools
    agent_id = pending["agent_id"]
    tool_uses = pending["tools"]
    context = pending["context"]

    try:
        # Execute tools
        tool_results = []
        for tu in tool_uses:
            success, output, error = execute_tool(tu.name, tu.input)
            tool_results.append({
                "tool_use_id": tu.id,
                "type": "tool_result",
                "content": output if success else error,
                "is_error": not success,
            })

        # Send results back to Claude
        messages = context["messages"]
        messages.append({"role": "assistant", "content": context["response"].content})
        messages.append({"role": "user", "content": tool_results})

        system_prompt = AGENT_PROMPTS[context["role"]]

        final_response = await send_message(
            messages=messages,
            system=system_prompt,
            tools=TOOLS,
        )

        # Extract final text
        final_text = ""
        for block in final_response.content:
            if block.type == "text":
                final_text += block.text

        # Clean up
        del _agent_state.pending_approvals[approval_id]

        result = {
            "status": "completed",
            "response": final_text,
            "tools_executed": len(tool_uses),
        }

        _agent_state.complete_agent(agent_id, result)

        return result

    except Exception as e:
        logger.error(f"approval_execution_error id={approval_id}: {type(e).__name__}: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
        }
