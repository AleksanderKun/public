import os


class Config:
    def __init__(self):
        self.api_base: str = os.getenv("OLLAMA_API_BASE", "http://127.0.0.1:11434")
        self.model: str = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:14b")
        self.context_length: int = int(os.getenv("OLLAMA_CONTEXT_LENGTH", "16384"))
        self.timeout: int = int(os.getenv("OLLAMA_TIMEOUT", "120"))

    def __repr__(self) -> str:
        return (
            f"Config(api_base={self.api_base}, model={self.model}, "
            f"context_length={self.context_length}, timeout={self.timeout})"
        )
