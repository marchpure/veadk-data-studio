from __future__ import annotations

import secrets
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class LaunchSession:
    expires_at: int


class LaunchSessionStore:
    def __init__(self, ttl_seconds: int = 300):
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, LaunchSession] = {}

    def create(self) -> tuple[str, LaunchSession]:
        self._prune()
        session_id = secrets.token_urlsafe(32)
        session = LaunchSession(expires_at=int(time.time()) + self.ttl_seconds)
        self._sessions[session_id] = session
        return session_id, session

    def valid(self, session_id: str | None) -> bool:
        if not session_id:
            return False
        session = self._sessions.get(session_id)
        if not session or session.expires_at <= int(time.time()):
            self._sessions.pop(session_id, None)
            return False
        return True

    def _prune(self) -> None:
        now = int(time.time())
        expired = [session_id for session_id, session in self._sessions.items() if session.expires_at <= now]
        for session_id in expired:
            self._sessions.pop(session_id, None)


launch_sessions = LaunchSessionStore()
