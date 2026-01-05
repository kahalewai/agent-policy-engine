"""
APE Error Types

All errors in APE are typed, deterministic, and explicit.
Errors are non-recoverable unless explicitly handled by the application.

Per the architecture specification (§10 Error Model):
- Errors are deterministic and explicit
- Errors are typed
- Errors are non-recoverable unless explicitly handled
"""

from typing import Optional, Any


class APEError(Exception):
    """Base exception for all APE errors."""
    
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
    
    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.message!r}, details={self.details!r})"


class IntentError(APEError):
    """
    Raised when intent construction, validation, or mutation fails.
    
    This includes:
    - Schema validation failures
    - Immutability violations
    - Invalid intent updates
    """
    pass


class PlanError(APEError):
    """
    Raised when plan validation, approval, or mutation fails.
    
    This includes:
    - Schema validation failures
    - Plan not matching intent constraints
    - Invalid plan structure
    """
    pass


class PlanMutationError(PlanError):
    """
    Raised when an immutable plan is modified after approval.
    
    Per architecture spec: Any plan change invalidates the plan,
    plan hash, runtime execution state, and revokes all issued AuthorityTokens.
    """
    
    def __init__(self, message: str = "Plan mutation detected after approval"):
        super().__init__(message)


class ActionError(APEError):
    """
    Raised when action construction or validation fails.
    
    This includes:
    - Missing required fields
    - Schema validation failures
    - Invalid action bindings
    """
    pass


class PolicyError(APEError):
    """
    Raised when policy loading, validation, or parsing fails.
    
    This includes:
    - Invalid YAML syntax
    - Schema validation failures
    - Missing required policy fields
    """
    pass


class PolicyDenyError(APEError):
    """
    Raised when policy explicitly denies an action.
    
    Per architecture spec (§4.4 Default Deny):
    Any action not explicitly allowed is denied.
    """
    
    def __init__(self, action_id: str, reason: str = "Action denied by policy"):
        super().__init__(reason, {"action_id": action_id})
        self.action_id = action_id


class EscalationRequiredError(APEError):
    """
    Raised when an action requires escalation approval.
    
    Note: In v1.0, escalation is not fully implemented.
    This error indicates that the action requires additional authority
    that must be obtained from an external resolver.
    """
    
    def __init__(self, action_id: str, reason: str = "Action requires escalation"):
        super().__init__(reason, {"action_id": action_id})
        self.action_id = action_id


class AuthorityExpiredError(APEError):
    """
    Raised when an AuthorityToken has expired.
    
    Per architecture spec (§5.5.3):
    AuthorityTokens are automatically invalid on expiration.
    """
    
    def __init__(self, token_id: str):
        super().__init__("Authority token has expired", {"token_id": token_id})
        self.token_id = token_id


class UnauthorizedActionError(APEError):
    """
    Raised when execution is attempted without valid authority.
    
    Per architecture spec (§5.5.5 Mandatory Enforcement Contract):
    No tool execution may occur without a valid AuthorityToken.
    """
    
    def __init__(self, reason: str = "Unauthorized action"):
        super().__init__(reason)


class RuntimeStateError(APEError):
    """
    Raised when an illegal state transition is attempted.
    
    Per architecture spec (§8.2 State Transition Rules):
    Illegal transitions are security violations, not warnings.
    """
    
    def __init__(self, current_state: str, attempted_state: str):
        super().__init__(
            f"Illegal state transition: {current_state} → {attempted_state}",
            {"current_state": current_state, "attempted_state": attempted_state}
        )
        self.current_state = current_state
        self.attempted_state = attempted_state


class ProvenanceError(APEError):
    """
    Raised when provenance rules are violated.
    
    Per architecture spec (§5.4):
    EXTERNAL_UNTRUSTED data may not participate in authority creation,
    modification, escalation, or approval.
    """
    pass


class VerificationError(APEError):
    """
    Raised when schema or hash verification fails.
    
    This includes:
    - JSON Schema validation failures
    - Hash mismatch errors
    - Integrity check failures
    """
    pass


class SchemaValidationError(VerificationError):
    """
    Raised when JSON Schema validation fails.
    
    Per architecture spec (§7.9 Schema Validators):
    Failure behavior is hard reject.
    """
    
    def __init__(self, schema_type: str, errors: list[str]):
        super().__init__(
            f"Schema validation failed for {schema_type}",
            {"schema_type": schema_type, "errors": errors}
        )
        self.schema_type = schema_type
        self.validation_errors = errors


class TokenConsumedError(APEError):
    """
    Raised when attempting to use an already-consumed token.
    
    Per architecture spec (§5.5.1):
    AuthorityTokens are single-use.
    """
    
    def __init__(self, token_id: str):
        super().__init__("Token has already been consumed", {"token_id": token_id})
        self.token_id = token_id


class TokenRevokedError(APEError):
    """
    Raised when attempting to use a revoked token.
    
    Per architecture spec (§5.5.3):
    AuthorityTokens are revoked on intent update, plan invalidation,
    runtime termination, policy violation, etc.
    """
    
    def __init__(self, token_id: str):
        super().__init__("Token has been revoked", {"token_id": token_id})
        self.token_id = token_id


class TokenNotFoundError(APEError):
    """
    Raised when a token is not found in the authority manager registry.
    """
    
    def __init__(self, token_id: str):
        super().__init__("Token not found in registry", {"token_id": token_id})
        self.token_id = token_id


class TenantMismatchError(APEError):
    """
    Raised when tenant isolation is violated.
    
    Per architecture spec (§13.1 Multi-Tenant Mode):
    Multi-tenant isolation is enforced at token, intent, plan, and runtime levels.
    """
    
    def __init__(self, expected_tenant: str, actual_tenant: str):
        super().__init__(
            f"Tenant mismatch: expected {expected_tenant}, got {actual_tenant}",
            {"expected_tenant": expected_tenant, "actual_tenant": actual_tenant}
        )
        self.expected_tenant = expected_tenant
        self.actual_tenant = actual_tenant
