"""
Announcement endpoints for the High School Management System API
"""

import logging
import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from ..database import announcements_collection, teachers_collection

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)

MAX_MESSAGE_LENGTH = 500


class AnnouncementInput(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    start_date: Optional[date] = None
    expiration_date: date

    @model_validator(mode="after")
    def validate_fields(self):
        self.message = self.message.strip()
        if not self.message:
            raise ValueError("Message cannot be empty")
        if self.start_date and self.start_date > self.expiration_date:
            raise ValueError("Start date must be on or before the expiration date")
        return self


def _require_teacher(teacher_username: Optional[str]) -> Dict[str, Any]:
    if not teacher_username:
        raise HTTPException(
            status_code=401, detail="Authentication required for this action")
    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(
            status_code=401, detail="Invalid teacher credentials")
    return teacher


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": doc["_id"],
        "message": doc["message"],
        "start_date": doc.get("start_date"),
        "expiration_date": doc["expiration_date"],
    }


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get announcements that are currently active (public)"""
    today = date.today().isoformat()
    query = {
        "expiration_date": {"$gte": today},
        "$or": [
            {"start_date": None},
            {"start_date": {"$lte": today}}
        ]
    }
    cursor = announcements_collection.find(query).sort("expiration_date", 1)
    return [_serialize(doc) for doc in cursor]


@router.get("/all", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Get all announcements, including scheduled and expired - requires teacher authentication"""
    _require_teacher(teacher_username)
    cursor = announcements_collection.find().sort("expiration_date", -1)
    return [_serialize(doc) for doc in cursor]


@router.post("", response_model=Dict[str, Any], status_code=201)
def create_announcement(
    announcement: AnnouncementInput,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Create an announcement - requires teacher authentication"""
    teacher = _require_teacher(teacher_username)

    doc = {
        "_id": str(uuid.uuid4()),
        "message": announcement.message,
        "start_date": announcement.start_date.isoformat() if announcement.start_date else None,
        "expiration_date": announcement.expiration_date.isoformat(),
        "created_by": teacher["_id"],
    }
    try:
        announcements_collection.insert_one(doc)
    except Exception:
        logger.exception("Failed to create announcement")
        raise HTTPException(
            status_code=500, detail="Failed to create announcement")

    return _serialize(doc)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    announcement: AnnouncementInput,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Update an announcement - requires teacher authentication"""
    _require_teacher(teacher_username)

    updates = {
        "message": announcement.message,
        "start_date": announcement.start_date.isoformat() if announcement.start_date else None,
        "expiration_date": announcement.expiration_date.isoformat(),
    }
    try:
        result = announcements_collection.update_one(
            {"_id": announcement_id}, {"$set": updates})
    except Exception:
        logger.exception("Failed to update announcement %s", announcement_id)
        raise HTTPException(
            status_code=500, detail="Failed to update announcement")

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return _serialize({"_id": announcement_id, **updates})


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    """Delete an announcement - requires teacher authentication"""
    _require_teacher(teacher_username)

    try:
        result = announcements_collection.delete_one({"_id": announcement_id})
    except Exception:
        logger.exception("Failed to delete announcement %s", announcement_id)
        raise HTTPException(
            status_code=500, detail="Failed to delete announcement")

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
