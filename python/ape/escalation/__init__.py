"""
APE Escalation Module

Contains escalation handling (stub for v1.0).
"""

from ape.escalation.handler import (
    EscalationHandler,
    EscalationResolver,
    EscalationRequest,
    EscalationResult,
    EscalationDecision,
    DefaultDenyResolver,
)

__all__ = [
    "EscalationHandler",
    "EscalationResolver",
    "EscalationRequest",
    "EscalationResult",
    "EscalationDecision",
    "DefaultDenyResolver",
]
