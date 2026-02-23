"""
APE Session Manager

Provides session/conversation continuity for multi-turn agent interactions.

Sessions track cumulative behavior across multiple execute() calls,
enforce rate limits, and correlate audit events.

Usage:
    from ape.session import SessionManager, Session

    sessions = SessionManager(default_ttl_minutes=30)
    session = sessions.create(user_id="user_123")

    result = session.execute("Read config.json")
    print(session.actions_executed)
    print(session.time_remaining)
"""

from ape.session.manager import (
    SessionManager,
    Session,
    SessionUsageSummary,
)

__all__ = [
    "SessionManager",
    "Session",
    "SessionUsageSummary",
]
