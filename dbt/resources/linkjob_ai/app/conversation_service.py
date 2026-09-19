from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
from .config import Config
from .ollama_client import OllamaClient
from .context_manager import ContextManager


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


class ConversationService:
    def __init__(self, config: Config):
        self.config = config
        self.conversations = {}
        self.messages = {}
        self.ollama_client = OllamaClient(config)
        self.context_manager = ContextManager(config)

    def create_conversation(self, title: str, user_id: int) -> Conversation:
        conversation_id = len(self.conversations) + 1
        conversation = Conversation(
            id=conversation_id,
            title=title,
            messages=[],
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self.conversations[conversation_id] = conversation
        return conversation

    def list_conversations(self, user_id: int) -> List[Conversation]:
        return list(self.conversations.values())

    def get_conversation(
        self, conversation_id: int, user_id: int
    ) -> Optional[Conversation]:
        return self.conversations.get(conversation_id)

    def get_messages(self, conversation_id: int, user_id: int) -> List[Message]:
        conversation = self.get_conversation(conversation_id, user_id)
        if conversation:
            return conversation.messages
        return []

    def rename_conversation(
        self, conversation_id: int, new_title: str, user_id: int
    ) -> Optional[Conversation]:
        conversation = self.get_conversation(conversation_id, user_id)
        if conversation:
            conversation.title = new_title
            conversation.updated_at = datetime.now()
            return conversation
        return None

    def delete_conversation(self, conversation_id: int, user_id: int) -> bool:
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]
            return True
        return False

    def send_message(
        self, conversation_id: int, content: str, sender: str, user_id: int
    ) -> Optional[Message]:
        conversation = self.get_conversation(conversation_id, user_id)
        if conversation:
            message_id = len(self.messages) + 1
            message = Message(
                id=message_id,
                conversation_id=conversation_id,
                content=content,
                timestamp=datetime.now(),
                sender=sender,
            )
            conversation.messages.append(message)
            self.messages[message_id] = message
            return message
        return None

    def generate_ai_response(self, conversation_id: int, user_id: int) -> Optional[str]:
        conversation = self.get_conversation(conversation_id, user_id)
        if conversation:
            context = self.context_manager.get_context(conversation)
            response = self.ollama_client.generate(context)
            message_id = len(self.messages) + 1
            message = Message(
                id=message_id,
                conversation_id=conversation_id,
                content=response,
                timestamp=datetime.now(),
                sender="AI",
            )
            conversation.messages.append(message)
            self.messages[message_id] = message
            return response
        return None
