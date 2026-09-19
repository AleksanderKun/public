from datetime import datetime
from typing import List
from pydantic import BaseModel


class Message(BaseModel):
    id: int
    conversation_id: int
    content: str
    timestamp: datetime
    sender: str


class Conversation(BaseModel):
    id: int
    title: str
    messages: List[Message]
    created_at: datetime
    updated_at: datetime
