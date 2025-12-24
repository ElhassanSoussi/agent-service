"""
Agent Controller API - Autonomous Agent Management

Endpoints for starting, monitoring, and controlling autonomous agents.
"""
import logging
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.agent.orchestrator import (
    AgentRole,
    run_autonomous_cycle,
    get_pending_approvals,
    approve_pending,
    _agent_state,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])


# =============================================================================
# Request/Response Models
# =============================================================================

class StartCycleRequest(BaseModel):
    """Request to start an autonomous agent cycle."""
    agents: List[AgentRole] = Field(
        default=[
            AgentRole.JOB_HUNTER,
            AgentRole.CONTENT_CREATOR,
            AgentRole.DEVELOPER,
            AgentRole.MARKETER,
            AgentRole.RESEARCHER,
        ],
        description="List of agents to run in this cycle"
    )
    auto_approve_low_risk: bool = Field(
        default=True,
        description="Auto-approve low-risk tools (web searches, reads)"
    )


class StartCycleResponse(BaseModel):
    """Response from starting an autonomous cycle."""
    status: str
    message: str
    agents_started: List[str]
    timestamp: str


class AgentStatusResponse(BaseModel):
    """Current status of all agents."""
    active_agents: dict
    pending_approvals: List[dict]
    recent_results: List[dict]
    timestamp: str


class ApprovalDecisionRequest(BaseModel):
    """Request to approve or reject pending tools."""
    approval_id: str
    approved: bool


class ApprovalDecisionResponse(BaseModel):
    """Response from approval decision."""
    status: str
    message: str
    result: Optional[dict] = None


# =============================================================================
# Background Task: Run Autonomous Cycle
# =============================================================================

async def _run_cycle_background(
    agents: List[AgentRole],
    auto_approve_low_risk: bool
):
    """Run autonomous cycle in background."""
    try:
        logger.info(f"background_cycle_started agents={[a.value for a in agents]}")
        result = await run_autonomous_cycle(agents, auto_approve_low_risk)
        logger.info(f"background_cycle_completed result={result}")
    except Exception as e:
        logger.error(f"background_cycle_error: {type(e).__name__}: {str(e)}")


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/start", response_model=StartCycleResponse)
async def start_agent_cycle(
    request: StartCycleRequest,
    background_tasks: BackgroundTasks
):
    """
    Start an autonomous agent cycle.

    Agents will run in the background and execute low-risk tools automatically.
    High-risk tools will be queued for approval.
    """
    try:
        # Validate agents
        if not request.agents:
            raise HTTPException(status_code=400, detail="No agents specified")

        # Add to background tasks
        background_tasks.add_task(
            _run_cycle_background,
            request.agents,
            request.auto_approve_low_risk
        )

        logger.info(f"agent_cycle_queued agents={[a.value for a in request.agents]}")

        return StartCycleResponse(
            status="started",
            message=f"Autonomous cycle started with {len(request.agents)} agents",
            agents_started=[a.value for a in request.agents],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as e:
        logger.error(f"start_cycle_error: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=AgentStatusResponse)
async def get_agent_status():
    """
    Get current status of all agents.

    Returns:
    - Active agents currently running
    - Pending approvals waiting for user decision
    - Recent agent results
    """
    try:
        pending = get_pending_approvals()

        return AgentStatusResponse(
            active_agents=_agent_state.active_agents,
            pending_approvals=pending,
            recent_results=_agent_state.results[-10:],  # Last 10 results
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as e:
        logger.error(f"get_status_error: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approve", response_model=ApprovalDecisionResponse)
async def approve_agent_action(request: ApprovalDecisionRequest):
    """
    Approve or reject a pending tool execution.

    If approved, the tools will be executed and the result will be returned.
    If rejected, the agent will be notified and no tools will be executed.
    """
    try:
        result = await approve_pending(request.approval_id, request.approved)

        if result["status"] == "error":
            raise HTTPException(status_code=404, detail=result["error"])

        message = "Tools approved and executed" if request.approved else "Tools rejected"

        return ApprovalDecisionResponse(
            status=result["status"],
            message=message,
            result=result if request.approved else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"approve_error: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results")
async def get_agent_results(
    agent_role: Optional[str] = None,
    limit: int = 20
):
    """
    Get recent agent execution results.

    Optional filters:
    - agent_role: Filter by specific agent role
    - limit: Number of results to return (default 20)
    """
    try:
        results = _agent_state.results

        # Filter by agent role if specified
        if agent_role:
            # Note: results store agent_id, not role directly
            # We'd need to enhance the result structure to filter by role
            # For now, return all results
            pass

        # Return most recent results
        recent = results[-limit:] if len(results) > limit else results

        return {
            "results": recent,
            "total": len(results),
            "filtered": len(recent),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"get_results_error: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/reset")
async def reset_agent_state():
    """
    Reset agent state (for testing/debugging).

    Clears all active agents, pending approvals, and results.
    """
    try:
        _agent_state.active_agents.clear()
        _agent_state.pending_approvals.clear()
        _agent_state.results.clear()

        logger.info("agent_state_reset")

        return {
            "status": "success",
            "message": "Agent state reset successfully",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"reset_error: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
