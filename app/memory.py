"""Bounded typed history and a separate, explicit pending user goal."""
from collections import OrderedDict
from pydantic import BaseModel, Field
from typing import Literal
from app.config import settings

class Message(BaseModel):
    role: Literal['user', 'assistant']
    content: str

class Session(BaseModel):
    messages: list[Message] = Field(default_factory=list)
    pending_goal: str | None = None

class Memory:
    def __init__(self):
        self.sessions = OrderedDict()

    def get(self, session):
        return self.sessions.get(session, Session()).model_copy(deep=True)

    def add(self, session, user, assistant, pending_goal=None):
        entry = self.get(session)
        entry.messages += [Message(role='user', content=user), Message(role='assistant', content=assistant)]
        while len(entry.messages) > settings.history_messages or sum(len(m.content) for m in entry.messages) > settings.history_chars:
            entry.messages = entry.messages[2:]
        entry.pending_goal = pending_goal
        self.sessions[session] = entry
        self.sessions.move_to_end(session)
        while len(self.sessions) > settings.max_sessions:
            self.sessions.popitem(last=False)

    def clear(self, session):
        self.sessions.pop(session, None)

