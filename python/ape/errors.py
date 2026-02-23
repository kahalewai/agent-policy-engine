"""
APE Error Types

All errors in APE are typed, deterministic, and explicit.
Errors are non-recoverable unless explicitly handled by the application.

Per the architecture specification (§10 Error Model):
- Errors are deterministic and explicit
- Errors are typed
- Errors are non-recoverable unless explicitly handled

Error categories:
- Core errors: Intent, Plan, Action, Policy, Authority, Runtime, Provenance
- Action Repository errors: Registration, lookup, parameter validation
- Intent Compilation errors: Prompt-to-intent transformation failures
- Plan Generation errors: Plan creation and validation failures
- Orchestrator errors: Agent/tool/execution failures
- Session errors: Session lifecycle and state failures
- Rate Limit errors: Quota and velocity limit violations
- Policy Adapter errors: External policy engine integration failures
- Policy Condition errors: Parameter-level condition evaluation failures
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


# =============================================================================
# Core APE Errors (v1.0)
# =============================================================================

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


# =============================================================================
# Action Repository Errors
# =============================================================================

class ActionRepositoryError(APEError):
    """
    Base error for Action Repository operations.

    The Action Repository maintains the canonical set of known actions.
    This error is raised when repository operations fail.
    """
    pass


class ActionNotFoundError(ActionRepositoryError):
    """
    Raised when an action_id is not found in the Action Repository.

    This indicates that the requested action is not registered in
    the bounded action universe.
    """

    def __init__(self, action_id: str):
        super().__init__(
            f"Action '{action_id}' not found in Action Repository",
            {"action_id": action_id}
        )
        self.action_id = action_id


class ActionAlreadyExistsError(ActionRepositoryError):
    """
    Raised when attempting to register an action that already exists.
    """

    def __init__(self, action_id: str):
        super().__init__(
            f"Action '{action_id}' already exists in Action Repository",
            {"action_id": action_id}
        )
        self.action_id = action_id


class ActionParameterError(ActionRepositoryError):
    """
    Raised when action parameters fail schema validation.
    """

    def __init__(self, action_id: str, message: str, errors: list[str] = None):
        super().__init__(
            f"Invalid parameters for action '{action_id}': {message}",
            {"action_id": action_id, "errors": errors or []}
        )
        self.action_id = action_id
        self.validation_errors = errors or []


class RepositoryFrozenError(ActionRepositoryError):
    """
    Raised when attempting to modify a frozen Action Repository.

    Once frozen, the repository cannot accept new registrations.
    """

    def __init__(self):
        super().__init__("Cannot modify frozen Action Repository")


# =============================================================================
# Intent Compilation Errors
# =============================================================================

class IntentCompilationError(APEError):
    """
    Base error for intent compilation operations.

    The Intent Compiler transforms natural language prompts into
    structured APE Intent objects.
    """
    pass


class IntentNarrowingError(IntentCompilationError):
    """
    Raised when policy narrowing removes all actions from intent.

    This indicates that the prompt requested actions that are
    entirely outside what the policy allows.
    """

    def __init__(self, message: str, narrowing_log: list[str] = None):
        super().__init__(
            message,
            {"narrowing_log": narrowing_log or []}
        )
        self.narrowing_log = narrowing_log or []


class IntentAmbiguityError(IntentCompilationError):
    """
    Raised when a prompt is too ambiguous to compile.

    This indicates that the Intent Compiler could not extract
    sufficient action signals from the user prompt.
    """

    def __init__(self, message: str, prompt: str = None):
        super().__init__(
            message,
            {"prompt": prompt[:100] + "..." if prompt and len(prompt) > 100 else prompt}
        )
        self.prompt = prompt


# =============================================================================
# Plan Generation Errors
# =============================================================================

class PlanGenerationError(APEError):
    """
    Base error for plan generation operations.

    The Plan Generator creates and validates execution plans
    from Intent objects or LLM output.
    """
    pass


class PlanValidationError(PlanGenerationError):
    """
    Raised when plan validation fails.

    This includes validation against intent constraints, policy
    compliance, and action parameter schemas.
    """

    def __init__(self, message: str, errors: list[str] = None):
        super().__init__(
            message,
            {"errors": errors or []}
        )
        self.validation_errors = errors or []


class PlanParseError(PlanGenerationError):
    """
    Raised when LLM output cannot be parsed into a valid plan.

    This indicates that the LLM's plan proposal was not in a
    recognized format (JSON, numbered list, etc.).
    """

    def __init__(self, message: str, raw_output: str = None):
        super().__init__(
            message,
            {"raw_output_preview": raw_output[:200] + "..." if raw_output and len(raw_output) > 200 else raw_output}
        )
        self.raw_output = raw_output


class PlanIntentViolationError(PlanValidationError):
    """
    Raised when a plan violates intent constraints.

    This indicates that the plan contains actions not allowed
    by the current intent, or uses forbidden actions.
    """
    pass


class PlanPolicyViolationError(PlanValidationError):
    """
    Raised when a plan would violate policy.

    This is a pre-check error indicating that plan execution
    would be blocked by policy enforcement.
    """
    pass


# =============================================================================
# Agent Errors
# =============================================================================

class AgentError(APEError):
    """
    Base error for APEAgent operations.

    The APEAgent provides a one-call API from prompt to execution.
    """
    pass


class ToolNotRegisteredError(AgentError):
    """
    Raised when a required tool is not registered with the agent.
    """

    def __init__(self, tool_id: str):
        super().__init__(
            f"Tool '{tool_id}' is not registered",
            {"tool_id": tool_id}
        )
        self.tool_id = tool_id


class ExecutionError(AgentError):
    """
    Raised when plan execution fails.

    Contains information about which step failed and any
    partial results from earlier steps.
    """

    def __init__(
        self,
        message: str,
        step_index: int = None,
        partial_results: list = None
    ):
        super().__init__(
            message,
            {
                "step_index": step_index,
                "partial_results_count": len(partial_results) if partial_results else 0
            }
        )
        self.step_index = step_index
        self.partial_results = partial_results or []


# =============================================================================
# Session Errors
# =============================================================================

class SessionError(APEError):
    """
    Base error for session management operations.

    Sessions track cumulative agent behavior across multiple
    executions within a conversation or workflow.
    """
    pass


class SessionExpiredError(SessionError):
    """
    Raised when an operation is attempted on an expired session.

    Sessions have a configurable TTL. Once expired, no further
    actions can be executed within the session.
    """

    def __init__(self, session_id: str):
        super().__init__(
            f"Session '{session_id}' has expired",
            {"session_id": session_id}
        )
        self.session_id = session_id


class SessionRevokedError(SessionError):
    """
    Raised when an operation is attempted on a revoked session.

    Sessions can be administratively revoked at any time,
    immediately terminating all further operations.
    """

    def __init__(self, session_id: str):
        super().__init__(
            f"Session '{session_id}' has been revoked",
            {"session_id": session_id}
        )
        self.session_id = session_id


class SessionNotFoundError(SessionError):
    """
    Raised when a session ID is not found in the session registry.
    """

    def __init__(self, session_id: str):
        super().__init__(
            f"Session '{session_id}' not found",
            {"session_id": session_id}
        )
        self.session_id = session_id


# =============================================================================
# Rate Limit Errors
# =============================================================================

class RateLimitError(APEError):
    """
    Base error for rate limiting and quota enforcement.

    Rate limits prevent agent DDoS scenarios such as infinite
    API call loops, runaway file operations, or email spam.
    """
    pass


class RateLimitExceededError(RateLimitError):
    """
    Raised when a rate limit has been exceeded.

    Contains details about which limit was hit and when
    it will reset.
    """

    def __init__(
        self,
        message: str,
        action_id: str = None,
        limit_type: str = None,
        current_count: int = None,
        max_allowed: int = None,
        reset_seconds: float = None,
    ):
        details = {}
        if action_id:
            details["action_id"] = action_id
        if limit_type:
            details["limit_type"] = limit_type
        if current_count is not None:
            details["current_count"] = current_count
        if max_allowed is not None:
            details["max_allowed"] = max_allowed
        if reset_seconds is not None:
            details["reset_seconds"] = reset_seconds
        super().__init__(message, details)
        self.action_id = action_id
        self.limit_type = limit_type
        self.current_count = current_count
        self.max_allowed = max_allowed
        self.reset_seconds = reset_seconds


class QuotaExhaustedError(RateLimitError):
    """
    Raised when a session or global quota has been exhausted.

    Quotas are hard limits on total actions within a session
    or time window. Unlike rate limits, quotas do not reset
    automatically within the same session.
    """

    def __init__(
        self,
        message: str,
        quota_type: str = None,
        current_value: float = None,
        max_value: float = None,
    ):
        details = {}
        if quota_type:
            details["quota_type"] = quota_type
        if current_value is not None:
            details["current_value"] = current_value
        if max_value is not None:
            details["max_value"] = max_value
        super().__init__(message, details)
        self.quota_type = quota_type
        self.current_value = current_value
        self.max_value = max_value


# =============================================================================
# Policy Condition Errors
# =============================================================================

class PolicyConditionError(PolicyError):
    """
    Raised when a parameterized policy condition check fails.

    Policy conditions allow fine-grained control such as
    "allow write_file only to /tmp/" or "allow http_get
    only to api.github.com". This error is raised when
    the action is allowed by the base rule but the parameters
    violate the condition constraints.
    """

    def __init__(
        self,
        action_id: str,
        condition_field: str,
        message: str,
    ):
        super().__init__(
            f"Condition failed for '{action_id}' on field '{condition_field}': {message}",
            {
                "action_id": action_id,
                "condition_field": condition_field,
            }
        )
        self.action_id = action_id
        self.condition_field = condition_field


# =============================================================================
# Policy Adapter Errors
# =============================================================================

class PolicyAdapterError(APEError):
    """
    Base error for external policy adapter operations.

    Policy adapters integrate APE with enterprise policy engines
    such as OPA/Rego, AWS Cedar, and XACML.
    """
    pass


class AdapterConnectionError(PolicyAdapterError):
    """
    Raised when APE cannot connect to an external policy engine.
    """

    def __init__(self, adapter_type: str, endpoint: str, reason: str = ""):
        super().__init__(
            f"Failed to connect to {adapter_type} at '{endpoint}': {reason}",
            {"adapter_type": adapter_type, "endpoint": endpoint}
        )
        self.adapter_type = adapter_type
        self.endpoint = endpoint


class AdapterEvaluationError(PolicyAdapterError):
    """
    Raised when an external policy engine returns an error
    during evaluation.
    """

    def __init__(self, adapter_type: str, message: str, raw_response: Any = None):
        super().__init__(
            f"{adapter_type} evaluation error: {message}",
            {"adapter_type": adapter_type, "raw_response": str(raw_response)[:200] if raw_response else None}
        )
        self.adapter_type = adapter_type
        self.raw_response = raw_response


class AdapterConfigurationError(PolicyAdapterError):
    """
    Raised when a policy adapter is misconfigured.
    """

    def __init__(self, adapter_type: str, message: str):
        super().__init__(
            f"{adapter_type} configuration error: {message}",
            {"adapter_type": adapter_type}
        )
        self.adapter_type = adapter_type
