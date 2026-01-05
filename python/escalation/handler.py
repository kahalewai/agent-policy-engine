"""
APE Escalation Handler

- Is an integration hook only
- Does not implement UI or approval logic
- Must be provided by the host application
- Default behavior: deny escalation

Note: In APE v1.0, escalation is not fully implemented.
This module provides the interface and a default deny handler.
Future versions will include:
- EscalationResolver interface
- Multiple resolver implementations
- Async escalation support
"""

from abc import ABC, abstractmethod
from typing import Any, Optional
from dataclasses import dataclass
from enum import Enum

from ape.errors import EscalationRequiredError
from ape.action.action import Action


class EscalationDecision(str, Enum):
    """Possible escalation decisions."""
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    PENDING = "PENDING"


@dataclass
class EscalationRequest:
    """Request for escalation approval."""
    action_id: str
    tool_id: str
    reason: str
    context: dict[str, Any]
    
    @classmethod
    def from_action(cls, action: Action, reason: str = "") -> "EscalationRequest":
        """Create an escalation request from an action."""
        return cls(
            action_id=action.action_id,
            tool_id=action.tool_id,
            reason=reason or "Action requires escalation approval",
            context={
                "intent_version": action.intent_version,
                "plan_hash": action.plan_hash,
                "plan_step_index": action.plan_step_index,
            }
        )


@dataclass
class EscalationResult:
    """Result of an escalation request."""
    decision: EscalationDecision
    reason: str
    approved_by: Optional[str] = None
    
    def is_approved(self) -> bool:
        return self.decision == EscalationDecision.APPROVED
    
    def is_denied(self) -> bool:
        return self.decision == EscalationDecision.DENIED
    
    def is_pending(self) -> bool:
        return self.decision == EscalationDecision.PENDING


class EscalationResolver(ABC):
    """
    Abstract base class for escalation resolvers.
    
    Implementations may include:
    - AutoPolicyResolver: Automated approval based on secondary policy
    - HumanApprovalResolver: Human-in-the-loop approval
    - DelegatedAuthorityResolver: Delegated authority service
    
    This interface is provided for future implementation.
    """
    
    @abstractmethod
    def resolve(
        self,
        request: EscalationRequest
    ) -> EscalationResult:
        """
        Resolve an escalation request.
        
        Args:
            request: The escalation request
            
        Returns:
            EscalationResult with decision
        """
        pass


class DefaultDenyResolver(EscalationResolver):
    """
    Default escalation resolver that always denies.
    
    Per architecture spec: Default behavior is deny escalation.
    """
    
    def resolve(self, request: EscalationRequest) -> EscalationResult:
        """Always deny escalation requests."""
        return EscalationResult(
            decision=EscalationDecision.DENIED,
            reason="Default deny: No escalation resolver configured"
        )


class EscalationHandler:
    """
    Handler for escalation requests.
    
    This is an integration hook. The host application should:
    1. Provide a custom EscalationResolver
    2. Or handle EscalationRequiredError directly
    
    Per architecture spec: This component does not implement
    UI or approval logic.
    """
    
    def __init__(
        self,
        resolver: Optional[EscalationResolver] = None
    ) -> None:
        """
        Initialize the escalation handler.
        
        Args:
            resolver: Optional custom resolver (defaults to deny all)
        """
        self._resolver = resolver or DefaultDenyResolver()
    
    def request(self, action_id: str) -> None:
        """
        Raise an escalation required error.
        
        This is the simplest interface - just raises an exception
        that the host application can catch and handle.
        
        Args:
            action_id: The action requiring escalation
            
        Raises:
            EscalationRequiredError: Always raised
        """
        raise EscalationRequiredError(action_id)
    
    def handle(self, request: EscalationRequest) -> EscalationResult:
        """
        Handle an escalation request through the resolver.
        
        Args:
            request: The escalation request
            
        Returns:
            EscalationResult from the resolver
        """
        return self._resolver.resolve(request)
    
    def handle_action(self, action: Action, reason: str = "") -> EscalationResult:
        """
        Handle escalation for an action.
        
        Args:
            action: The action requiring escalation
            reason: Optional reason for escalation
            
        Returns:
            EscalationResult from the resolver
        """
        request = EscalationRequest.from_action(action, reason)
        return self.handle(request)
    
    def set_resolver(self, resolver: EscalationResolver) -> None:
        """
        Set a custom escalation resolver.
        
        Args:
            resolver: The resolver to use
        """
        self._resolver = resolver
    
    def __repr__(self) -> str:
        resolver_name = self._resolver.__class__.__name__
        return f"EscalationHandler(resolver={resolver_name})"
