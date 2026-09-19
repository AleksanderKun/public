from .conversation import Conversation
from .config import Config


class ContextManager:
    def __init__(self, config: Config):
        self.config = config

    def get_context(self, conversation: Conversation) -> str:
        system_prompt = "You are a helpful assistant."
        messages = conversation.messages[-self.config.context_window :]
        context = f"{system_prompt}\n"
        for message in messages:
            context += f"{message.sender}: {message.content}\n"
        return context
