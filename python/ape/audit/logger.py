"""
APE Audit Logger

Per architecture spec (§7.9 Audit Logger and related sections):
- Emits audit events
- Logs execution attempts, successes, and failures
- Supports structured logging
- Can be integrated with external logging systems
"""

import datetime
import json
import logging
from typing import Any, Optional, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum


class AuditEventType(str, Enum):
    """Types of audit events."""
    EXECUTION = "EXECUTION"
    DENIED = "DENIED"
    WARNING = "WARNING"
    TOKEN_ISSUED = "TOKEN_ISSUED"
    TOKEN_CONSUMED = "TOKEN_CONSUMED"
    TOKEN_REVOKED = "TOKEN_REVOKED"
    INTENT_SET = "INTENT_SET"
    PLAN_APPROVED = "PLAN_APPROVED"
    STATE_TRANSITION = "STATE_TRANSITION"
    POLICY_LOADED = "POLICY_LOADED"
    ERROR = "ERROR"


@dataclass
class AuditEvent:
    """Structured audit event."""
    event_type: AuditEventType
    timestamp: str
    action_id: Optional[str] = None
    token_id: Optional[str] = None
    success: Optional[bool] = None
    reason: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
        }
        if self.action_id:
            result["action_id"] = self.action_id
        if self.token_id:
            result["token_id"] = self.token_id
        if self.success is not None:
            result["success"] = self.success
        if self.reason:
            result["reason"] = self.reason
        if self.details:
            result["details"] = self.details
        return result
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


class AuditLogger:
    """
    Audit logger for APE events.
    
    Supports multiple output modes:
    - Console (default)
    - Python logging
    - Custom callback
    - In-memory storage
    """
    
    def __init__(
        self,
        enabled: bool = True,
        use_python_logging: bool = False,
        logger_name: str = "ape.audit",
        callback: Optional[Callable[[AuditEvent], None]] = None,
        store_events: bool = False
    ) -> None:
        """
        Initialize the audit logger.
        
        Args:
            enabled: Whether audit logging is enabled
            use_python_logging: Use Python's logging module
            logger_name: Name for the Python logger
            callback: Optional callback for each event
            store_events: Whether to store events in memory
        """
        self._enabled = enabled
        self._use_python_logging = use_python_logging
        self._callback = callback
        self._store_events = store_events
        self._events: list[AuditEvent] = []
        
        if use_python_logging:
            self._logger = logging.getLogger(logger_name)
        else:
            self._logger = None
    
    @property
    def enabled(self) -> bool:
        """Check if audit logging is enabled."""
        return self._enabled
    
    @property
    def events(self) -> list[AuditEvent]:
        """Get stored events (if store_events is True)."""
        return self._events.copy()
    
    def _get_timestamp(self) -> str:
        """Get ISO format timestamp."""
        return datetime.datetime.utcnow().isoformat() + "Z"
    
    def _emit(self, event: AuditEvent) -> None:
        """Emit an audit event."""
        if not self._enabled:
            return
        
        if self._store_events:
            self._events.append(event)
        
        if self._callback:
            self._callback(event)
        
        if self._use_python_logging and self._logger:
            self._logger.info(event.to_json())
        elif not self._callback:
            # Default: print to console
            print(f"[APE AUDIT] {event.to_json()}")
    
    def log(self, message: str) -> None:
        """Log a simple message."""
        event = AuditEvent(
            event_type=AuditEventType.EXECUTION,
            timestamp=self._get_timestamp(),
            details={"message": message}
        )
        self._emit(event)
    
    def log_execution(
        self,
        action_id: str,
        token_id: str,
        success: bool,
        error: Optional[str] = None
    ) -> None:
        """Log an action execution."""
        event = AuditEvent(
            event_type=AuditEventType.EXECUTION,
            timestamp=self._get_timestamp(),
            action_id=action_id,
            token_id=token_id,
            success=success,
            reason=error if not success else None
        )
        self._emit(event)
    
    def log_denied(self, action_id: str, reason: str) -> None:
        """Log a denied action."""
        event = AuditEvent(
            event_type=AuditEventType.DENIED,
            timestamp=self._get_timestamp(),
            action_id=action_id,
            success=False,
            reason=reason
        )
        self._emit(event)
    
    def log_warning(self, message: str, details: Optional[dict] = None) -> None:
        """Log a warning."""
        event = AuditEvent(
            event_type=AuditEventType.WARNING,
            timestamp=self._get_timestamp(),
            reason=message,
            details=details or {}
        )
        self._emit(event)
    
    def log_token_issued(
        self,
        token_id: str,
        action_id: str,
        intent_version: str,
        plan_hash: str
    ) -> None:
        """Log token issuance."""
        event = AuditEvent(
            event_type=AuditEventType.TOKEN_ISSUED,
            timestamp=self._get_timestamp(),
            token_id=token_id,
            action_id=action_id,
            details={
                "intent_version": intent_version[:16] + "...",
                "plan_hash": plan_hash[:16] + "..."
            }
        )
        self._emit(event)
    
    def log_token_consumed(self, token_id: str, action_id: str) -> None:
        """Log token consumption."""
        event = AuditEvent(
            event_type=AuditEventType.TOKEN_CONSUMED,
            timestamp=self._get_timestamp(),
            token_id=token_id,
            action_id=action_id,
            success=True
        )
        self._emit(event)
    
    def log_token_revoked(
        self,
        token_id: Optional[str] = None,
        count: Optional[int] = None,
        reason: str = ""
    ) -> None:
        """Log token revocation."""
        event = AuditEvent(
            event_type=AuditEventType.TOKEN_REVOKED,
            timestamp=self._get_timestamp(),
            token_id=token_id,
            reason=reason,
            details={"count": count} if count else {}
        )
        self._emit(event)
    
    def log_intent_set(self, intent_version: str, scope: str) -> None:
        """Log intent being set."""
        event = AuditEvent(
            event_type=AuditEventType.INTENT_SET,
            timestamp=self._get_timestamp(),
            details={
                "intent_version": intent_version[:16] + "...",
                "scope": scope
            }
        )
        self._emit(event)
    
    def log_plan_approved(self, plan_hash: str, step_count: int) -> None:
        """Log plan approval."""
        event = AuditEvent(
            event_type=AuditEventType.PLAN_APPROVED,
            timestamp=self._get_timestamp(),
            details={
                "plan_hash": plan_hash[:16] + "...",
                "step_count": step_count
            }
        )
        self._emit(event)
    
    def log_state_transition(self, from_state: str, to_state: str) -> None:
        """Log runtime state transition."""
        event = AuditEvent(
            event_type=AuditEventType.STATE_TRANSITION,
            timestamp=self._get_timestamp(),
            details={
                "from_state": from_state,
                "to_state": to_state
            }
        )
        self._emit(event)
    
    def log_policy_loaded(self, policy_version: str, policy_name: Optional[str]) -> None:
        """Log policy being loaded."""
        event = AuditEvent(
            event_type=AuditEventType.POLICY_LOADED,
            timestamp=self._get_timestamp(),
            details={
                "policy_version": policy_version[:16] + "...",
                "policy_name": policy_name or "unnamed"
            }
        )
        self._emit(event)
    
    def log_error(self, error: str, details: Optional[dict] = None) -> None:
        """Log an error."""
        event = AuditEvent(
            event_type=AuditEventType.ERROR,
            timestamp=self._get_timestamp(),
            success=False,
            reason=error,
            details=details or {}
        )
        self._emit(event)
    
    def clear_events(self) -> None:
        """Clear stored events."""
        self._events.clear()
    
    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable audit logging."""
        self._enabled = enabled
    
    def __repr__(self) -> str:
        return f"AuditLogger(enabled={self._enabled}, events={len(self._events)})"
