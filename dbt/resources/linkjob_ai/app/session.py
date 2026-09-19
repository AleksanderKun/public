from datetime import datetime
from typing import Optional


class ConversationSession:
    def __init__(self):
        self.start_time: datetime = datetime.now()
        self.end_time: Optional[datetime] = None
        self.transcription: str = ""
        self.questions: list[str] = []
        self.responses: list[str] = []
        self.status: str = "active"

    def add_transcription(self, text: str):
        self.transcription += text + "\n"

    def add_question(self, question: str):
        self.questions.append(question)

    def add_response(self, response: str):
        self.responses.append(response)

    def end_session(self):
        self.end_time = datetime.now()
        self.status = "ended"

    def __repr__(self) -> str:
        return (
            f"ConversationSession(start_time={self.start_time}, end_time={self.end_time}, "
            f"transcription={self.transcription}, questions={self.questions}, "
            f"responses={self.responses}, status={self.status})"
        )
