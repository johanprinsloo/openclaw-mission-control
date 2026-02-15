from typing import Optional
from pydantic import BaseModel, UUID4, EmailStr
from datetime import datetime
from .common import Role

class UserBase(BaseModel):
    email: Optional[EmailStr] = None
    type: str  # 'human' or 'agent'
    identifier: Optional[str] = None
    display_name: str
    role: Role

class UserCreate(UserBase):
    pass

class UserRead(UserBase):
    id: UUID4
    org_id: UUID4
    created_at: datetime
