"""
APE Session Manager

Provides session/conversation continuity for multi-turn agent interactions.

In v1.0.1, every execute() call created a fresh runtime with no memory
of previous actions. Real agents are multi-turn — they need to:
- Track cumulative behavior across a conversation
- Enforce rate limits across multiple executions
- Correlate audit events within a session
- Allow administrative session revocation

The v1.0.2 Session Manager solves this by providing:
1. Session creation with configurable TTL
2. Session-scoped execution that tracks state
3. Cumulative usage metrics (actions, risk, tokens)
4. Session-level rate limiting integration
5. Administrative revocation
6. Audit event correlation via session_id

Usage:
    from ape.session import SessionManager

    sessions = SessionManager()
    session = sessions.create(user_id="user_123", ttl_minutes=30)

    # Execute within session context
    result = session.execute("Read config.json")

    # Check session state
    print(session.actions_executed)
    print(session.cumulative_risk)
    print(session.time_remaining)

    # Admin revocation
    sessions.revoke(session.session_id)
"""

import time
import secrets
import threading
import logging
from typing import Any, Optional, Callable
from dataclasses import dataclass, field

from ape.errors import (
    SessionError,
    SessionExpiredError,
    SessionRevokedError,
    SessionNotFoundError,
)
from ape.rate_limiter import RateLimiter, RateLimitConfig
from ape.audit.logger import AuditLogger

logger = logging.getLogger("ape.session")


# =============================================================================
# Session Data
# =============================================================================

@dataclass
class SessionUsageSummary:
    """Summary of session usage for reporting and audit."""
    session_id: str
    user_id: str
    created_at: float
    expires_at: float
    time_remaining: float
    is_active: bool
    is_expired: bool
    is_revoked: bool
    total_actions: int
    actions_executed: list[str]
    cumulative_risk: float
    tokens_issued: int
    executions_completed: int
    executions_failed: int
    rate_limit_usage: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "time_remaining": round(self.time_remaining, 1),
            "is_active": self.is_active,
            "is_expired": self.is_expired,
            "is_revoked": self.is_revoked,
            "total_actions": self.total_actions,
            "actions_executed": self.actions_executed,
            "cumulative_risk": round(self.cumulative_risk, 4),
            "tokens_issued": self.tokens_issued,
            "executions_completed": self.executions_completed,
            "executions_failed": self.executions_failed,
            "rate_limit_usage": self.rate_limit_usage,
        }


class Session:
    """
    A single agent session representing a multi-turn conversation.

    Sessions track cumulative behavior across multiple execute() calls
    and enforce session-level constraints including TTL, rate limits,
    and risk budgets.

    Sessions are created by SessionManager and should not be
    instantiated directly.

    Thread Safety:
        This class uses internal locks and is safe for concurrent
        execute() calls within the same session.
    """

    def __init__(
        self,
        session_id: str,
        user_id: str,
        ttl_seconds: float,
        rate_limiter: Optional[RateLimiter] = None,
        audit_logger: Optional[AuditLogger] = None,
        execute_fn: Optional[Callable] = None,
    ) -> None:
        """
        Initialize a session.

        Args:
            session_id: Unique session identifier
            user_id: User who owns this session
            ttl_seconds: Session time-to-live in seconds
            rate_limiter: Optional rate limiter for this session
            audit_logger: Optional audit logger
            execute_fn: The orchestrator's execute function to delegate to
        """
        self._session_id = session_id
        self._user_id = user_id
        self._created_at = time.time()
        self._expires_at = self._created_at + ttl_seconds
        self._revoked = False
        self._lock = threading.Lock()

        # Usage tracking
        self._actions_executed: list[str] = []
        self._cumulative_risk: float = 0.0
        self._tokens_issued: int = 0
        self._executions_completed: int = 0
        self._executions_failed: int = 0

        # Dependencies
        self._rate_limiter = rate_limiter or RateLimiter()
        self._audit = audit_logger
        self._execute_fn = execute_fn

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def session_id(self) -> str:
        """Get the session ID."""
        return self._session_id

    @property
    def user_id(self) -> str:
        """Get the user ID."""
        return self._user_id

    @property
    def created_at(self) -> float:
        """Get session creation timestamp."""
        return self._created_at

    @property
    def expires_at(self) -> float:
        """Get session expiration timestamp."""
        return self._expires_at

    @property
    def time_remaining(self) -> float:
        """Get remaining session time in seconds."""
        remaining = self._expires_at - time.time()
        return max(0.0, remaining)

    @property
    def is_expired(self) -> bool:
        """Check if session has expired."""
        return time.time() > self._expires_at

    @property
    def is_revoked(self) -> bool:
        """Check if session has been revoked."""
        return self._revoked

    @property
    def is_active(self) -> bool:
        """Check if session is active (not expired and not revoked)."""
        return not self.is_expired and not self.is_revoked

    @property
    def actions_executed(self) -> list[str]:
        """Get list of action IDs executed in this session."""
        return self._actions_executed.copy()

    @property
    def cumulative_risk(self) -> float:
        """Get cumulative risk score for this session."""
        return self._cumulative_risk

    @property
    def tokens_issued(self) -> int:
        """Get total tokens issued in this session."""
        return self._tokens_issued

    @property
    def total_actions(self) -> int:
        """Get total number of actions executed."""
        return len(self._actions_executed)

    # =========================================================================
    # Execution
    # =========================================================================

    def execute(self, prompt: str, **kwargs) -> Any:
        """
        Execute a prompt within this session context.

        This delegates to the orchestrator's execute function while
        tracking session-level metrics and enforcing session constraints.

        Args:
            prompt: Natural language prompt
            **kwargs: Additional arguments passed to the orchestrator

        Returns:
            OrchestrationResult from the execution

        Raises:
            SessionExpiredError: If the session has expired
            SessionRevokedError: If the session has been revoked
            RateLimitExceededError: If rate limits are exceeded
        """
        self._assert_active()

        if self._execute_fn is None:
            raise SessionError("No execute function bound to session")

        result = self._execute_fn(prompt, **kwargs)

        # Track results
        with self._lock:
            if hasattr(result, 'success') and result.success:
                self._executions_completed += 1
                if hasattr(result, 'plan') and result.plan:
                    for step in result.plan.steps:
                        self._actions_executed.append(step.action_id)
                        self._rate_limiter.record_action(step.action_id)
                        self._tokens_issued += 1
            else:
                self._executions_failed += 1

        return result

    def record_action(
        self,
        action_id: str,
        risk_score: float = 0.0,
        target: Optional[str] = None,
    ) -> None:
        """
        Manually record an action execution in this session.

        Use this when executing outside the session.execute() path
        but still wanting to track the action in the session.

        Args:
            action_id: The action that was executed
            risk_score: Risk score of the action
            target: Optional target identifier
        """
        self._assert_active()
        with self._lock:
            self._actions_executed.append(action_id)
            self._cumulative_risk += risk_score
            self._tokens_issued += 1
            self._rate_limiter.record_action(
                action_id, risk_score=risk_score, target=target
            )

    def check_rate_limit(
        self,
        action_id: str,
        target: Optional[str] = None,
        risk_score: float = 0.0,
    ) -> None:
        """
        Check if an action is allowed under session rate limits.

        Args:
            action_id: The action to check
            target: Optional target identifier
            risk_score: Risk score of the action

        Raises:
            RateLimitExceededError: If rate limit would be exceeded
            QuotaExhaustedError: If quota would be exceeded
        """
        self._assert_active()
        self._rate_limiter.check_allowed(
            action_id, target=target, risk_score=risk_score
        )

    # =========================================================================
    # Session Management
    # =========================================================================

    def revoke(self) -> None:
        """
        Revoke this session, preventing any further operations.

        This is an immediate, irreversible operation.
        """
        with self._lock:
            self._revoked = True
        logger.info("Session '%s' revoked", self._session_id)

    def extend(self, additional_seconds: float) -> None:
        """
        Extend the session TTL.

        Args:
            additional_seconds: Additional time to add in seconds
        """
        self._assert_active()
        with self._lock:
            self._expires_at += additional_seconds
        logger.info(
            "Session '%s' extended by %.0f seconds",
            self._session_id, additional_seconds
        )

    def get_usage_summary(self) -> SessionUsageSummary:
        """
        Get a comprehensive summary of session usage.

        Returns:
            SessionUsageSummary with all tracked metrics
        """
        return SessionUsageSummary(
            session_id=self._session_id,
            user_id=self._user_id,
            created_at=self._created_at,
            expires_at=self._expires_at,
            time_remaining=self.time_remaining,
            is_active=self.is_active,
            is_expired=self.is_expired,
            is_revoked=self.is_revoked,
            total_actions=self.total_actions,
            actions_executed=self.actions_executed,
            cumulative_risk=self._cumulative_risk,
            tokens_issued=self._tokens_issued,
            executions_completed=self._executions_completed,
            executions_failed=self._executions_failed,
            rate_limit_usage=self._rate_limiter.get_usage_summary(),
        )

    def _assert_active(self) -> None:
        """Assert the session is still active."""
        if self.is_revoked:
            raise SessionRevokedError(self._session_id)
        if self.is_expired:
            raise SessionExpiredError(self._session_id)

    def __repr__(self) -> str:
        status = "active" if self.is_active else ("revoked" if self.is_revoked else "expired")
        return (
            f"Session(id='{self._session_id[:12]}...', "
            f"user='{self._user_id}', "
            f"status={status}, "
            f"actions={self.total_actions})"
        )


# =============================================================================
# Session Manager
# =============================================================================

class SessionManager:
    """
    Manages the lifecycle of agent sessions.

    The SessionManager is responsible for:
    - Creating new sessions with configurable TTL and rate limits
    - Looking up existing sessions by ID
    - Revoking sessions (admin operation)
    - Cleaning up expired sessions
    - Providing session-level audit correlation

    Usage:
        manager = SessionManager(
            rate_limit_config=RateLimitConfig.from_dict({...}),
            default_ttl_minutes=30,
        )

        session = manager.create(user_id="user_123")
        result = session.execute("Read config.json")

        # Admin operations
        manager.revoke(session.session_id)
        manager.cleanup_expired()

    Thread Safety:
        This class is thread-safe for all operations.
    """

    def __init__(
        self,
        rate_limit_config: Optional[RateLimitConfig] = None,
        default_ttl_minutes: int = 30,
        audit_logger: Optional[AuditLogger] = None,
    ) -> None:
        """
        Initialize the session manager.

        Args:
            rate_limit_config: Default rate limit config for new sessions
            default_ttl_minutes: Default session TTL in minutes
            audit_logger: Optional audit logger for session events
        """
        self._rate_limit_config = rate_limit_config
        self._default_ttl_minutes = default_ttl_minutes
        self._audit = audit_logger
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(
        self,
        user_id: str,
        ttl_minutes: Optional[int] = None,
        rate_limit_config: Optional[RateLimitConfig] = None,
        execute_fn: Optional[Callable] = None,
    ) -> Session:
        """
        Create a new session.

        Args:
            user_id: User identifier for audit and tracking
            ttl_minutes: Session TTL in minutes (uses default if None)
            rate_limit_config: Optional per-session rate limit config
            execute_fn: The orchestrator's execute function

        Returns:
            New Session instance
        """
        session_id = secrets.token_urlsafe(24)
        ttl = (ttl_minutes or self._default_ttl_minutes) * 60

        # Create a rate limiter for this session
        rl_config = rate_limit_config or self._rate_limit_config
        rate_limiter = RateLimiter(rl_config) if rl_config else RateLimiter()

        session = Session(
            session_id=session_id,
            user_id=user_id,
            ttl_seconds=ttl,
            rate_limiter=rate_limiter,
            audit_logger=self._audit,
            execute_fn=execute_fn,
        )

        with self._lock:
            self._sessions[session_id] = session

        logger.info(
            "Created session '%s' for user '%s' (TTL: %d minutes)",
            session_id[:12], user_id, ttl // 60
        )
        return session

    def get(self, session_id: str) -> Session:
        """
        Get a session by ID.

        Args:
            session_id: The session ID to look up

        Returns:
            Session instance

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session

    def revoke(self, session_id: str) -> None:
        """
        Revoke a session by ID.

        This is an administrative operation that immediately
        terminates a session.

        Args:
            session_id: The session ID to revoke

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        session = self.get(session_id)
        session.revoke()
        logger.info("Admin revoked session '%s'", session_id[:12])

    def cleanup_expired(self) -> int:
        """
        Remove expired sessions from the registry.

        Returns:
            Number of sessions removed
        """
        with self._lock:
            expired = [
                sid for sid, session in self._sessions.items()
                if session.is_expired
            ]
            for sid in expired:
                del self._sessions[sid]

        if expired:
            logger.info("Cleaned up %d expired sessions", len(expired))
        return len(expired)

    def list_active(self) -> list[Session]:
        """Get all active (non-expired, non-revoked) sessions."""
        with self._lock:
            return [s for s in self._sessions.values() if s.is_active]

    def list_all(self) -> list[Session]:
        """Get all sessions (including expired and revoked)."""
        with self._lock:
            return list(self._sessions.values())

    @property
    def active_count(self) -> int:
        """Get count of active sessions."""
        return len(self.list_active())

    @property
    def total_count(self) -> int:
        """Get total count of sessions in registry."""
        with self._lock:
            return len(self._sessions)

    def __repr__(self) -> str:
        return (
            f"SessionManager(active={self.active_count}, "
            f"total={self.total_count})"
        )
