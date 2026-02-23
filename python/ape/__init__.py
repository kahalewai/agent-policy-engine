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
- Integrated escalation handling
- Mandatory schema validation
- Production-grade tooling
- Enforced provenance controls
- Runtime state machine
- Optional multi-tenant isolation

Enhancements:
- ActionRepository: Canonical registry of known actions
- IntentCompiler: Transform prompts to structured intents
- PlanGenerator: Generate and validate execution plans
- APEOrchestrator: Unified one-call API from prompt to execution
- SessionManager: Multi-turn conversation continuity
- RateLimiter: Quota and velocity limit enforcement (LLM DDoS prevention)
- PolicyAdapters: OPA/Rego, AWS Cedar, XACML integration
- ConditionEvaluator: Parameterized policy conditions
- Dynamic policy reload with on_update callbacks

Three Ways to Use APE:

1. **Orchestrator Path** (Simple)
    from ape import APEOrchestrator

    orch = APEOrchestrator.from_policy("policies/read_only.yaml")
    orch.register_tool("read_file", my_read_func)
    result = orch.execute("Read config.json")

2. **Session Path** (Multi-turn)
    orch = APEOrchestrator.from_policy("policies/read_only.yaml")
    session = orch.create_session(user_id="user_123", ttl_minutes=30)
    result = session.execute("Read config.json")

3. **Manual Path** (Full Control)
    from ape import (
        PolicyEngine, IntentManager, PlanManager,
        RuntimeOrchestrator, AuthorityManager, EnforcementGate,
        ActionRepository, IntentCompiler, PlanGenerator,
    )

    # Wire components yourself for maximum flexibility
    # See IMPLEMENTATION_GUIDE.md for details

License: Apache-2.0
"""

__version__ = "1.0.2"

# =============================================================================
# Core Errors
# =============================================================================
from ape.errors import (
    # Base error
    APEError,

    # Core errors
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

    # Action Repository errors
    ActionRepositoryError,
    ActionNotFoundError,
    ActionAlreadyExistsError,
    ActionParameterError,
    RepositoryFrozenError,

    # Intent Compilation errors
    IntentCompilationError,
    IntentNarrowingError,
    IntentAmbiguityError,

    # Plan Generation errors
    PlanGenerationError,
    PlanValidationError,
    PlanParseError,
    PlanIntentViolationError,
    PlanPolicyViolationError,

    # Agent errors
    AgentError,
    ToolNotRegisteredError,
    ExecutionError,

    # Session errors
    SessionError,
    SessionExpiredError,
    SessionRevokedError,
    SessionNotFoundError,

    # Rate Limit errors
    RateLimitError,
    RateLimitExceededError,
    QuotaExhaustedError,

    # Policy Condition errors
    PolicyConditionError,

    # Policy Adapter errors
    PolicyAdapterError,
    AdapterConnectionError,
    AdapterEvaluationError,
    AdapterConfigurationError,
)

# =============================================================================
# Core Components (v1.0)
# =============================================================================
from ape.action import Action, validate_action_data
from ape.provenance import Provenance
from ape.intent import IntentManager
from ape.plan import PlanManager
from ape.policy import (
    PolicyEngine,
    PolicyDecision,
    Policy,
    PolicyEvaluationResult,
    PolicyRule,
    ConditionEvaluator,
    validate_policy_file,
)
from ape.authority import AuthorityManager, AuthorityToken
from ape.enforcement import EnforcementGate, ExecutionResult
from ape.escalation import EscalationHandler, DefaultDenyResolver
from ape.audit import AuditLogger, AuditEvent
from ape.runtime import RuntimeOrchestrator, RuntimeState
from ape.config import RuntimeConfig, EnforcementMode

# =============================================================================
# Extended Components
# =============================================================================
from ape.action_repository import (
    ActionRepository,
    ActionDefinition,
    ActionCategory,
    ActionRiskLevel,
    create_standard_repository,
)
from ape.intent_compiler import IntentCompiler, CompiledIntent, IntentSignal
from ape.plan_generator import PlanGenerator, GeneratedPlan, GeneratedPlanStep
from ape.orchestrator import APEOrchestrator, OrchestrationResult
from ape.mcp import MCPScanner

# =============================================================================
# New Modules
# =============================================================================
from ape.session import SessionManager, Session, SessionUsageSummary
from ape.rate_limiter import (
    RateLimiter,
    RateLimitConfig,
    GlobalLimits,
    ActionLimits,
    TargetLimits,
)
from ape.policy_adapters import (
    ExternalEvaluator,
    AdapterDecision,
    OPAEvaluator,
    CedarEvaluator,
    XACMLEvaluator,
)

# =============================================================================
# Public API
# =============================================================================
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
    "PolicyConditionError",
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
    "ActionRepositoryError",
    "ActionNotFoundError",
    "ActionAlreadyExistsError",
    "ActionParameterError",
    "RepositoryFrozenError",
    "IntentCompilationError",
    "IntentNarrowingError",
    "IntentAmbiguityError",
    "PlanGenerationError",
    "PlanValidationError",
    "PlanParseError",
    "PlanIntentViolationError",
    "PlanPolicyViolationError",
    "AgentError",
    "ToolNotRegisteredError",
    "ExecutionError",
    "SessionError",
    "SessionExpiredError",
    "SessionRevokedError",
    "SessionNotFoundError",
    "RateLimitError",
    "RateLimitExceededError",
    "QuotaExhaustedError",
    "PolicyAdapterError",
    "AdapterConnectionError",
    "AdapterEvaluationError",
    "AdapterConfigurationError",

    # Core
    "Action",
    "Provenance",
    "IntentManager",
    "PlanManager",
    "PolicyEngine",
    "PolicyDecision",
    "Policy",
    "PolicyEvaluationResult",
    "PolicyRule",
    "ConditionEvaluator",
    "validate_policy_file",
    "AuthorityManager",
    "AuthorityToken",
    "EnforcementGate",
    "ExecutionResult",
    "EscalationHandler",
    "DefaultDenyResolver",
    "AuditLogger",
    "AuditEvent",
    "RuntimeOrchestrator",
    "RuntimeState",
    "RuntimeConfig",
    "EnforcementMode",

    # Extended
    "ActionRepository",
    "ActionDefinition",
    "ActionCategory",
    "ActionRiskLevel",
    "create_standard_repository",
    "IntentCompiler",
    "CompiledIntent",
    "IntentSignal",
    "PlanGenerator",
    "GeneratedPlan",
    "GeneratedPlanStep",
    "APEOrchestrator",
    "OrchestrationResult",
    "MCPScanner",

    # New Modules
    "SessionManager",
    "Session",
    "SessionUsageSummary",
    "RateLimiter",
    "RateLimitConfig",
    "GlobalLimits",
    "ActionLimits",
    "TargetLimits",
    "ExternalEvaluator",
    "AdapterDecision",
    "OPAEvaluator",
    "CedarEvaluator",
    "XACMLEvaluator",
]
