from typing import Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ProfileSlotItem(BaseModel):
    slot_key: str
    slot_type: str
    slot_value: Any
    confidence: float
    source: str
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class UserProfileResponse(BaseModel):
    profile: List[ProfileSlotItem]


class UpdateProfileSlotRequest(BaseModel):
    slot_value: Any
    source: str = "manual"


class MemoryCandidateItem(BaseModel):
    id: int
    user_id: int
    candidate_text: str
    suggested_slot_key: Optional[str]
    suggested_value: Any
    reason: Optional[str]
    confidence: float
    seen_count: int
    status: str
    source_session_id: Optional[int]
    source_message_id: Optional[int]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MemoryCandidateListResponse(BaseModel):
    candidates: List[MemoryCandidateItem]


class AcceptCandidateRequest(BaseModel):
    slot_value: Optional[Any] = None

