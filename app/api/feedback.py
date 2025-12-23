"""
Feedback API endpoints for user ratings on agent responses (Phase 21).
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field

from app.db.database import SessionLocal
from app.db.models import Feedback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackCreate(BaseModel):
    """Request to create feedback."""
    conversation_id: Optional[str] = Field(None, description="Conversation ID")
    message_id: Optional[str] = Field(None, description="Message ID")
    user_prompt: Optional[str] = Field(None, max_length=4096, description="The user's message")
    agent_response: Optional[str] = Field(None, max_length=8192, description="The agent's response")
    rating: int = Field(..., ge=-1, le=1, description="Rating: +1 (thumbs up) or -1 (thumbs down)")
    notes: Optional[str] = Field(None, max_length=1000, description="Optional user notes")


class FeedbackResponse(BaseModel):
    """Response for a feedback item."""
    id: str
    conversation_id: Optional[str]
    message_id: Optional[str]
    user_prompt: Optional[str]
    agent_response: Optional[str]
    rating: int
    notes: Optional[str]
    created_at: str


class FeedbackListResponse(BaseModel):
    """Response for listing feedback."""
    items: List[FeedbackResponse]
    total: int
    stats: dict


class FeedbackStats(BaseModel):
    """Feedback statistics."""
    total: int
    positive: int
    negative: int
    positive_rate: float


def get_tenant_id(request: Request) -> Optional[str]:
    """Get tenant_id from request state."""
    auth_context = getattr(request.state, "auth", None)
    if auth_context:
        return auth_context.tenant_id
    return None


@router.post("", response_model=FeedbackResponse)
async def create_feedback(request: Request, body: FeedbackCreate) -> FeedbackResponse:
    """
    Submit feedback for an agent response.
    
    Rating: +1 for thumbs up, -1 for thumbs down.
    """
    tenant_id = get_tenant_id(request)
    now = datetime.now(timezone.utc).isoformat()
    
    db = SessionLocal()
    try:
        feedback = Feedback(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            conversation_id=body.conversation_id,
            message_id=body.message_id,
            user_prompt=body.user_prompt,
            agent_response=body.agent_response,
            rating=body.rating,
            notes=body.notes,
            created_at=now,
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)
        
        rating_text = "positive" if body.rating > 0 else "negative"
        logger.info(f"feedback_created id={feedback.id} rating={rating_text}")
        
        return FeedbackResponse(
            id=feedback.id,
            conversation_id=feedback.conversation_id,
            message_id=feedback.message_id,
            user_prompt=feedback.user_prompt,
            agent_response=feedback.agent_response,
            rating=feedback.rating,
            notes=feedback.notes,
            created_at=feedback.created_at,
        )
    finally:
        db.close()


@router.get("", response_model=FeedbackListResponse)
async def list_feedback(
    request: Request,
    rating: Optional[int] = Query(None, ge=-1, le=1, description="Filter by rating"),
    conversation_id: Optional[str] = Query(None, description="Filter by conversation ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> FeedbackListResponse:
    """
    List feedback with optional filters.
    
    Includes statistics (total, positive, negative counts).
    """
    tenant_id = get_tenant_id(request)
    
    db = SessionLocal()
    try:
        query = db.query(Feedback)
        
        if tenant_id:
            query = query.filter(Feedback.tenant_id == tenant_id)
        
        if rating is not None:
            query = query.filter(Feedback.rating == rating)
        
        if conversation_id:
            query = query.filter(Feedback.conversation_id == conversation_id)
        
        total = query.count()
        items = query.order_by(Feedback.created_at.desc()).offset(offset).limit(limit).all()
        
        # Calculate stats
        stats_query = db.query(Feedback)
        if tenant_id:
            stats_query = stats_query.filter(Feedback.tenant_id == tenant_id)
        
        all_feedback = stats_query.all()
        positive_count = sum(1 for f in all_feedback if f.rating > 0)
        negative_count = sum(1 for f in all_feedback if f.rating < 0)
        total_count = len(all_feedback)
        positive_rate = (positive_count / total_count * 100) if total_count > 0 else 0.0
        
        return FeedbackListResponse(
            items=[
                FeedbackResponse(
                    id=f.id,
                    conversation_id=f.conversation_id,
                    message_id=f.message_id,
                    user_prompt=f.user_prompt,
                    agent_response=f.agent_response,
                    rating=f.rating,
                    notes=f.notes,
                    created_at=f.created_at,
                )
                for f in items
            ],
            total=total,
            stats={
                "total": total_count,
                "positive": positive_count,
                "negative": negative_count,
                "positive_rate": round(positive_rate, 1),
            },
        )
    finally:
        db.close()


@router.get("/stats", response_model=FeedbackStats)
async def get_feedback_stats(request: Request) -> FeedbackStats:
    """
    Get feedback statistics.
    
    Returns total counts and positive feedback rate.
    """
    tenant_id = get_tenant_id(request)
    
    db = SessionLocal()
    try:
        query = db.query(Feedback)
        
        if tenant_id:
            query = query.filter(Feedback.tenant_id == tenant_id)
        
        all_feedback = query.all()
        positive_count = sum(1 for f in all_feedback if f.rating > 0)
        negative_count = sum(1 for f in all_feedback if f.rating < 0)
        total_count = len(all_feedback)
        positive_rate = (positive_count / total_count * 100) if total_count > 0 else 0.0
        
        return FeedbackStats(
            total=total_count,
            positive=positive_count,
            negative=negative_count,
            positive_rate=round(positive_rate, 1),
        )
    finally:
        db.close()


@router.get("/{feedback_id}", response_model=FeedbackResponse)
async def get_feedback(request: Request, feedback_id: str) -> FeedbackResponse:
    """Get a specific feedback by ID."""
    tenant_id = get_tenant_id(request)
    
    db = SessionLocal()
    try:
        query = db.query(Feedback).filter(Feedback.id == feedback_id)
        if tenant_id:
            query = query.filter(Feedback.tenant_id == tenant_id)
        
        feedback = query.first()
        if not feedback:
            raise HTTPException(status_code=404, detail="Feedback not found")
        
        return FeedbackResponse(
            id=feedback.id,
            conversation_id=feedback.conversation_id,
            message_id=feedback.message_id,
            user_prompt=feedback.user_prompt,
            agent_response=feedback.agent_response,
            rating=feedback.rating,
            notes=feedback.notes,
            created_at=feedback.created_at,
        )
    finally:
        db.close()


@router.delete("/{feedback_id}")
async def delete_feedback(request: Request, feedback_id: str):
    """Delete a feedback entry."""
    tenant_id = get_tenant_id(request)
    
    db = SessionLocal()
    try:
        query = db.query(Feedback).filter(Feedback.id == feedback_id)
        if tenant_id:
            query = query.filter(Feedback.tenant_id == tenant_id)
        
        feedback = query.first()
        if not feedback:
            raise HTTPException(status_code=404, detail="Feedback not found")
        
        db.delete(feedback)
        db.commit()
        
        logger.info(f"feedback_deleted id={feedback_id}")
        
        return {"status": "deleted", "id": feedback_id}
    finally:
        db.close()
