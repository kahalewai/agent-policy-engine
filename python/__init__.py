"""
Agent Policy Engine (APE)

Deterministic, capability-based policy enforcement runtime for AI agents.

APE provides:
- Explicit intent and plans with cryptographic immutability
- Deterministic runtime state enforcement
- Deterministic policy enforcement
- Capability-based authority via secure tokens
- Enforced authority via AuthorityToken
- Auditable execution
- Integrated escalation handling (v2.0+)
- Mandatory schema validation
- Production-grade tooling
- Enforced provenance controls
- Runtime state machine
- Optional multi-tenant isolation

Quick Start:
    from ape import PolicyEngine, RuntimeConfig, EnforcementMode
    
    # Load a policy
    policy = PolicyEngine("policies/read_only.yaml")
    
    # Check if an action is allowed
    result = policy.evaluate("read_file")
    print(result.decision)  # ALLOW, DENY, or ESCALATE

For full integration, see ReferenceAgent for a complete example.

Version: 1.0.0
License: Apache-2.0
"""

__version__ = "1.0.0"

# Core errors
from ape.errors import (
    APEError,
    IntentError,
    PlanError,
    PlanMutationError,
    ActionError,
    PolicyError,
    PolicyDenyError,
    EscalationRequiredError,
    AuthorityExpiredError,
    UnauthorizedActionError,
    RuntimeStateError,
    ProvenanceError,
    VerificationError,
    SchemaValidationError,
    TokenConsumedError,
    TokenRevokedError,
    TokenNotFoundError,
    TenantMismatchError,
)

# Configuration
from ape.config import (
    RuntimeConfig,
    PolicyConfig,
    EnforcementMode,
    load_config_from_file,
)

# Runtime
from ape.runtime import (
    RuntimeState,
    RuntimeOrchestrator,
    VALID_TRANSITIONS,
    is_valid_transition,
    can_execute,
    can_issue_authority,
)

# Provenance
from ape.provenance import (
    Provenance,
    ProvenanceLabel,
    ProvenanceManager,
    combine_provenance,
)

# Action
from ape.action import Action, validate_action_data

# Intent
from ape.intent import Intent, IntentManager

# Plan
from ape.plan import Plan, PlanStep, PlanManager

# Policy
from ape.policy import (
    Policy,
    PolicyDecision,
    PolicyEngine,
    PolicyEvaluationResult,
    validate_policy_file,
)

# Authority
from ape.authority import AuthorityToken, AuthorityManager

# Enforcement
from ape.enforcement import EnforcementGate, ExecutionResult

# Escalation
from ape.escalation import (
    EscalationHandler,
    EscalationResolver,
    EscalationRequest,
    EscalationResult,
    EscalationDecision,
    DefaultDenyResolver,
)

# Audit
from ape.audit import AuditLogger, AuditEvent, AuditEventType

# MCP
from ape.mcp import MCPScanner, generate_policy_from_mcp

# Reference Agent
from ape.reference_agent import ReferenceAgent, AgentResult, create_simple_agent


__all__ = [
    # Version
    "__version__",
    
    # Errors
    "APEError",
    "IntentError",
    "PlanError",
    "PlanMutationError",
    "ActionError",
    "PolicyError",
    "PolicyDenyError",
    "EscalationRequiredError",
    "AuthorityExpiredError",
    "UnauthorizedActionError",
    "RuntimeStateError",
    "ProvenanceError",
    "VerificationError",
    "SchemaValidationError",
    "TokenConsumedError",
    "TokenRevokedError",
    "TokenNotFoundError",
    "TenantMismatchError",
    
    # Configuration
    "RuntimeConfig",
    "PolicyConfig",
    "EnforcementMode",
    "load_config_from_file",
    
    # Runtime
    "RuntimeState",
    "RuntimeOrchestrator",
    "VALID_TRANSITIONS",
    "is_valid_transition",
    "can_execute",
    "can_issue_authority",
    
    # Provenance
    "Provenance",
    "ProvenanceLabel",
    "ProvenanceManager",
    "combine_provenance",
    
    # Action
    "Action",
    "validate_action_data",
    
    # Intent
    "Intent",
    "IntentManager",
    
    # Plan
    "Plan",
    "PlanStep",
    "PlanManager",
    
    # Policy
    "Policy",
    "PolicyDecision",
    "PolicyEngine",
    "PolicyEvaluationResult",
    "validate_policy_file",
    
    # Authority
    "AuthorityToken",
    "AuthorityManager",
    
    # Enforcement
    "EnforcementGate",
    "ExecutionResult",
    
    # Escalation
    "EscalationHandler",
    "EscalationResolver",
    "EscalationRequest",
    "EscalationResult",
    "EscalationDecision",
    "DefaultDenyResolver",
    
    # Audit
    "AuditLogger",
    "AuditEvent",
    "AuditEventType",
    
    # MCP
    "MCPScanner",
    "generate_policy_from_mcp",
    
    # Reference Agent
    "ReferenceAgent",
    "AgentResult",
    "create_simple_agent",
]
