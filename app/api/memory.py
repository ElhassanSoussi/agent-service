"""
Memory API endpoints for persistent agent memory (Phase 21).
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field

from app.db.database import SessionLocal
from app.db.models import Memory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryCreate(BaseModel):
    """Request to create a memory."""
    key: str = Field(..., min_length=1, max_length=200, description="Memory key/title")
    value: str = Field(..., min_length=1, max_length=4096, description="Memory content")
    scope: str = Field(default="global", description="Scope: global, conversation, or user")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for conversation-scoped memories")
    tags: Optional[str] = Field(None, max_length=500, description="Comma-separated tags")


class MemoryUpdate(BaseModel):
    """Request to update a memory."""
    key: Optional[str] = Field(None, min_length=1, max_length=200)
    value: Optional[str] = Field(None, min_length=1, max_length=4096)
    tags: Optional[str] = Field(None, max_length=500)


class MemoryResponse(BaseModel):
    """Response for a memory item."""
    id: str
    scope: str
    conversation_id: Optional[str]
    key: str
    value: str
    tags: Optional[str]
    created_at: str
    updated_at: str


class MemoryListResponse(BaseModel):
    """Response for listing memories."""
    items: List[MemoryResponse]
    total: int


def get_tenant_id(request: Request) -> Optional[str]:
    """Get tenant_id from request state."""
    auth_context = getattr(request.state, "auth", None)
    if auth_context:
        return auth_context.tenant_id
    return None


@router.post("", response_model=MemoryResponse)
async def create_memory(request: Request, body: MemoryCreate) -> MemoryResponse:
    """
    Create or update a memory.
    
    If a memory with the same key and scope already exists, it will be updated.
    """
    tenant_id = get_tenant_id(request)
    now = datetime.now(timezone.utc).isoformat()
    
    db = SessionLocal()
    try:
        # Check if memory with same key/scope exists
        query = db.query(Memory).filter(
            Memory.key == body.key,
            Memory.scope == body.scope,
        )
        if tenant_id:
            query = query.filter(Memory.tenant_id == tenant_id)
        if body.conversation_id:
            query = query.filter(Memory.conversation_id == body.conversation_id)
        
        existing = query.first()
        
        if existing:
            # Update existing
            existing.value = body.value
            existing.tags = body.tags
            existing.updated_at = now
            db.commit()
            db.refresh(existing)
            memory = existing
            logger.info(f"memory_updated id={memory.id} key={body.key}")
        else:
            # Create new
            memory = Memory(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                scope=body.scope,
                conversation_id=body.conversation_id,
                key=body.key,
                value=body.value,
                tags=body.tags,
                created_at=now,
                updated_at=now,
            )
            db.add(memory)
            db.commit()
            db.refresh(memory)
            logger.info(f"memory_created id={memory.id} key={body.key}")
        
        return MemoryResponse(
            id=memory.id,
            scope=memory.scope,
            conversation_id=memory.conversation_id,
            key=memory.key,
            value=memory.value,
            tags=memory.tags,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
        )
    finally:
        db.close()


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    request: Request,
    scope: Optional[str] = Query(None, description="Filter by scope"),
    conversation_id: Optional[str] = Query(None, description="Filter by conversation ID"),
    search: Optional[str] = Query(None, description="Search in key and value"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> MemoryListResponse:
    """
    List memories with optional filters.
    """
    tenant_id = get_tenant_id(request)
    
    db = SessionLocal()
    try:
        query = db.query(Memory)
        
        if tenant_id:
            query = query.filter(Memory.tenant_id == tenant_id)
        
        if scope:
            query = query.filter(Memory.scope == scope)
        
        if conversation_id:
            query = query.filter(Memory.conversation_id == conversation_id)
        
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                (Memory.key.ilike(search_pattern)) | 
                (Memory.value.ilike(search_pattern))
            )
        
        total = query.count()
        items = query.order_by(Memory.updated_at.desc()).offset(offset).limit(limit).all()
        
        return MemoryListResponse(
            items=[
                MemoryResponse(
                    id=m.id,
                    scope=m.scope,
                    conversation_id=m.conversation_id,
                    key=m.key,
                    value=m.value,
                    tags=m.tags,
                    created_at=m.created_at,
                    updated_at=m.updated_at,
                )
                for m in items
            ],
            total=total,
        )
    finally:
        db.close()


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(request: Request, memory_id: str) -> MemoryResponse:
    """Get a specific memory by ID."""
    tenant_id = get_tenant_id(request)
    
    db = SessionLocal()
    try:
        query = db.query(Memory).filter(Memory.id == memory_id)
        if tenant_id:
            query = query.filter(Memory.tenant_id == tenant_id)
        
        memory = query.first()
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")
        
        return MemoryResponse(
            id=memory.id,
            scope=memory.scope,
            conversation_id=memory.conversation_id,
            key=memory.key,
            value=memory.value,
            tags=memory.tags,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
        )
    finally:
        db.close()


@router.put("/{memory_id}", response_model=MemoryResponse)
async def update_memory(request: Request, memory_id: str, body: MemoryUpdate) -> MemoryResponse:
    """Update a memory."""
    tenant_id = get_tenant_id(request)
    now = datetime.now(timezone.utc).isoformat()
    
    db = SessionLocal()
    try:
        query = db.query(Memory).filter(Memory.id == memory_id)
        if tenant_id:
            query = query.filter(Memory.tenant_id == tenant_id)
        
        memory = query.first()
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")
        
        if body.key is not None:
            memory.key = body.key
        if body.value is not None:
            memory.value = body.value
        if body.tags is not None:
            memory.tags = body.tags
        memory.updated_at = now
        
        db.commit()
        db.refresh(memory)
        
        logger.info(f"memory_updated id={memory_id}")
        
        return MemoryResponse(
            id=memory.id,
            scope=memory.scope,
            conversation_id=memory.conversation_id,
            key=memory.key,
            value=memory.value,
            tags=memory.tags,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
        )
    finally:
        db.close()


@router.delete("/{memory_id}")
async def delete_memory(request: Request, memory_id: str):
    """Delete a memory."""
    tenant_id = get_tenant_id(request)
    
    db = SessionLocal()
    try:
        query = db.query(Memory).filter(Memory.id == memory_id)
        if tenant_id:
            query = query.filter(Memory.tenant_id == tenant_id)
        
        memory = query.first()
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")
        
        db.delete(memory)
        db.commit()
        
        logger.info(f"memory_deleted id={memory_id}")
        
        return {"status": "deleted", "id": memory_id}
    finally:
        db.close()


def get_relevant_memories(
    tenant_id: Optional[str],
    conversation_id: Optional[str] = None,
    keywords: Optional[str] = None,
    limit: int = 5,
) -> List[dict]:
    """
    Retrieve relevant memories for prompt injection.
    
    Returns memories matching:
    - Global scope
    - Conversation scope (if conversation_id provided)
    - Keyword matches (if keywords provided)
    """
    db = SessionLocal()
    try:
        query = db.query(Memory)
        
        if tenant_id:
            query = query.filter(Memory.tenant_id == tenant_id)
        
        # Include global and conversation-specific memories
        if conversation_id:
            query = query.filter(
                (Memory.scope == "global") |
                ((Memory.scope == "conversation") & (Memory.conversation_id == conversation_id))
            )
        else:
            query = query.filter(Memory.scope == "global")
        
        # Simple keyword matching if provided
        if keywords:
            # Split keywords and search for any match
            for word in keywords.split()[:5]:  # Limit to 5 keywords
                if len(word) >= 3:  # Only search for words >= 3 chars
                    pattern = f"%{word}%"
                    query = query.filter(
                        (Memory.key.ilike(pattern)) |
                        (Memory.value.ilike(pattern)) |
                        (Memory.tags.ilike(pattern))
                    )
        
        memories = query.order_by(Memory.updated_at.desc()).limit(limit).all()
        
        return [
            {"key": m.key, "value": m.value}
            for m in memories
        ]
    finally:
        db.close()


def format_memories_for_prompt(memories: List[dict]) -> str:
    """Format memories for injection into system prompt."""
    if not memories:
        return ""
    
    lines = ["Known preferences and facts:"]
    for m in memories:
        lines.append(f"- {m['key']}: {m['value']}")
    
    return "\n".join(lines)
