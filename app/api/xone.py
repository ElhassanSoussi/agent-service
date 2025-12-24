"""
Xone API - Single-user AI agent with approval workflow.

Flow:
1. User sends message
2. Xone retrieves relevant memories
3. Claude generates response (may include tool use)
4. If tool use detected -> return proposal for approval
5. User approves -> execute tools -> send results back to Claude
6. Store conversation and return final response
"""
import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.llm.claude_client import (
    send_message,
    stream_message,
    extract_tool_uses,
    extract_text,
    has_tool_use,
    XONE_SYSTEM_PROMPT,
    DEVELOPER_SYSTEM_PROMPT,
)
from app.llm.tools import TOOLS, execute_tool, assess_tool_risk
from app.llm.memory_manager import get_relevant_memories
from app.db.database import SessionLocal
from app.db.models import XoneConversation, XoneMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/xone", tags=["xone"])


# =============================================================================
# Request/Response Schemas
# =============================================================================

class ChatRequest(BaseModel):
    """Request for Xone chat."""
    message: str = Field(..., min_length=1, max_length=10000, description="User message")
    conversation_id: Optional[str] = Field(None, description="Conversation ID (creates new if not provided)")
    mode: str = Field("chat", description="Mode: 'chat' or 'developer'")
    stream: bool = Field(False, description="Enable streaming")


class ToolProposal(BaseModel):
    """Proposed tool execution awaiting approval."""
    tool_name: str
    tool_input: Dict[str, Any]
    risk: str  # low, medium, high
    description: str  # Human-readable description


class ChatResponse(BaseModel):
    """Response from Xone."""
    conversation_id: str
    message_id: str
    response: Optional[str] = None
    proposals: Optional[List[ToolProposal]] = None
    requires_approval: bool = False
    status: str  # "ok", "proposal", "error"
    error: Optional[str] = None


class ApprovalRequest(BaseModel):
    """Approval decision for tool proposals."""
    conversation_id: str
    message_id: str
    approved: bool


# =============================================================================
# In-Memory Approval State
# =============================================================================

# Stores pending tool proposals
# Format: {message_id: {"tools": [...], "conversation_id": "...", "timestamp": "..."}}
_pending_approvals: Dict[str, Dict[str, Any]] = {}


def store_pending_approval(message_id: str, conversation_id: str, tools: List, claude_message):
    """Store pending approval for tool execution."""
    _pending_approvals[message_id] = {
        "conversation_id": conversation_id,
        "tools": tools,
        "claude_message": claude_message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    logger.info(f"pending_approval_stored message_id={message_id} tools={len(tools)}")


def get_pending_approval(message_id: str) -> Optional[Dict[str, Any]]:
    """Get pending approval by message ID."""
    return _pending_approvals.get(message_id)


def clear_pending_approval(message_id: str):
    """Clear pending approval after processing."""
    if message_id in _pending_approvals:
        del _pending_approvals[message_id]
        logger.info(f"pending_approval_cleared message_id={message_id}")


# =============================================================================
# Conversation Management
# =============================================================================

def get_or_create_conversation(conversation_id: Optional[str] = None) -> str:
    """Get existing conversation or create a new one."""
    db = SessionLocal()
    try:
        if conversation_id:
            conv = db.query(XoneConversation).filter(XoneConversation.id == conversation_id).first()
            if conv:
                return conversation_id

        # Create new conversation
        conv_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        conversation = XoneConversation(
            id=conv_id,
            title="New Conversation",
            created_at=now,
            updated_at=now,
        )

        db.add(conversation)
        db.commit()

        logger.info(f"conversation_created id={conv_id}")
        return conv_id

    finally:
        db.close()


def save_message(conversation_id: str, role: str, content: str, tool_calls: Optional[List] = None) -> str:
    """Save a message to the database."""
    db = SessionLocal()
    try:
        message_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        message = XoneMessage(
            id=message_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_calls_json=json.dumps(tool_calls) if tool_calls else None,
            created_at=now,
        )

        db.add(message)

        # Update conversation updated_at
        conv = db.query(XoneConversation).filter(XoneConversation.id == conversation_id).first()
        if conv:
            conv.updated_at = now

        db.commit()

        logger.info(f"message_saved id={message_id} conversation_id={conversation_id} role={role}")
        return message_id

    finally:
        db.close()


def get_conversation_history(conversation_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent conversation history."""
    db = SessionLocal()
    try:
        messages = db.query(XoneMessage).filter(
            XoneMessage.conversation_id == conversation_id
        ).order_by(XoneMessage.created_at.desc()).limit(limit).all()

        # Reverse to get chronological order
        messages = list(reversed(messages))

        history = []
        for msg in messages:
            history.append({
                "role": msg.role,
                "content": msg.content,
            })

        return history

    finally:
        db.close()


# =============================================================================
# Main Chat Endpoint
# =============================================================================

@router.post("/chat", response_model=ChatResponse)
async def xone_chat(request: ChatRequest, http_request: Request):
    """
    Main Xone chat endpoint.

    Handles:
    - New messages
    - Tool proposals
    - Memory integration
    """
    try:
        # Get or create conversation
        conversation_id = get_or_create_conversation(request.conversation_id)

        # Save user message
        user_message_id = save_message(conversation_id, "user", request.message)

        # Get conversation history
        history = get_conversation_history(conversation_id)

        # Get relevant memories
        memories = get_relevant_memories(request.message)

        # Build system prompt
        base_prompt = DEVELOPER_SYSTEM_PROMPT if request.mode == "developer" else XONE_SYSTEM_PROMPT
        if memories:
            system_prompt = f"{base_prompt}\n\n{memories}"
        else:
            system_prompt = base_prompt

        # Build messages for Claude
        messages = history + [{"role": "user", "content": request.message}]

        # Call Claude with tools
        claude_response = await send_message(
            messages=messages,
            system=system_prompt,
            tools=TOOLS,
        )

        # Check if Claude wants to use tools
        if has_tool_use(claude_response):
            tool_uses = extract_tool_uses(claude_response)

            # Create proposals
            proposals = []
            for tool_use in tool_uses:
                risk = assess_tool_risk(tool_use.name, tool_use.input)
                proposals.append(ToolProposal(
                    tool_name=tool_use.name,
                    tool_input=tool_use.input,
                    risk=risk,
                    description=f"{tool_use.name}: {json.dumps(tool_use.input, indent=2)}"
                ))

            # Store pending approval
            assistant_message_id = str(uuid.uuid4())
            store_pending_approval(assistant_message_id, conversation_id, tool_uses, claude_response)

            # Extract any text response before tools
            text_response = extract_text(claude_response)

            return ChatResponse(
                conversation_id=conversation_id,
                message_id=assistant_message_id,
                response=text_response if text_response else "I need to execute some tools to complete this task.",
                proposals=proposals,
                requires_approval=True,
                status="proposal",
            )

        else:
            # No tools, just text response
            text_response = extract_text(claude_response)

            # Save assistant message
            assistant_message_id = save_message(conversation_id, "assistant", text_response)

            return ChatResponse(
                conversation_id=conversation_id,
                message_id=assistant_message_id,
                response=text_response,
                requires_approval=False,
                status="ok",
            )

    except Exception as e:
        logger.error(f"xone_chat_error: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")


# =============================================================================
# Approval Endpoint
# =============================================================================

@router.post("/approve", response_model=ChatResponse)
async def approve_tools(request: ApprovalRequest):
    """
    Approve or reject tool execution.

    If approved: execute tools and return results.
    If rejected: cancel and return.
    """
    try:
        # Get pending approval
        pending = get_pending_approval(request.message_id)

        if not pending:
            raise HTTPException(status_code=404, detail="No pending approval found for this message")

        conversation_id = pending["conversation_id"]
        tools = pending["tools"]
        claude_message = pending["claude_message"]

        if not request.approved:
            # User rejected
            clear_pending_approval(request.message_id)

            response_text = "Tool execution cancelled by user."
            save_message(conversation_id, "assistant", response_text)

            return ChatResponse(
                conversation_id=conversation_id,
                message_id=request.message_id,
                response=response_text,
                requires_approval=False,
                status="ok",
            )

        # User approved - execute tools
        tool_results = []

        for tool_use in tools:
            success, output, error = execute_tool(tool_use.name, tool_use.input)

            tool_results.append({
                "tool_use_id": tool_use.id,
                "type": "tool_result",
                "content": output if success else error,
                "is_error": not success,
            })

        # Send tool results back to Claude for final response
        history = get_conversation_history(conversation_id)

        # Build messages with tool results
        messages = history + [
            {"role": "assistant", "content": claude_message.content},
            {"role": "user", "content": tool_results},
        ]

        # Get relevant memories again
        memories = get_relevant_memories(history[-1]["content"] if history else "")
        system_prompt = DEVELOPER_SYSTEM_PROMPT
        if memories:
            system_prompt = f"{system_prompt}\n\n{memories}"

        # Get final response from Claude
        final_response = await send_message(
            messages=messages,
            system=system_prompt,
            tools=TOOLS,
        )

        final_text = extract_text(final_response)

        # Save assistant message with tool execution
        save_message(
            conversation_id,
            "assistant",
            final_text,
            tool_calls=[{"name": tu.name, "input": tu.input} for tu in tools]
        )

        # Clear pending approval
        clear_pending_approval(request.message_id)

        return ChatResponse(
            conversation_id=conversation_id,
            message_id=request.message_id,
            response=final_text,
            requires_approval=False,
            status="ok",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"approve_tools_error: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Approval error: {str(e)}")


# =============================================================================
# Utility Endpoints
# =============================================================================

@router.get("/conversations")
async def list_conversations():
    """List all conversations."""
    db = SessionLocal()
    try:
        conversations = db.query(XoneConversation).order_by(
            XoneConversation.updated_at.desc()
        ).limit(50).all()

        return {
            "conversations": [
                {
                    "id": conv.id,
                    "title": conv.title,
                    "created_at": conv.created_at,
                    "updated_at": conv.updated_at,
                }
                for conv in conversations
            ]
        }

    finally:
        db.close()


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str):
    """Get all messages in a conversation."""
    db = SessionLocal()
    try:
        messages = db.query(XoneMessage).filter(
            XoneMessage.conversation_id == conversation_id
        ).order_by(XoneMessage.created_at).all()

        return {
            "messages": [
                {
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.created_at,
                }
                for msg in messages
            ]
        }

    finally:
        db.close()
