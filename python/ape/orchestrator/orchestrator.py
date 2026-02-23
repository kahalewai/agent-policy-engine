"""
APE Orchestrator - Unified API from Prompt to Execution

APE Orchestrator:
- The APE Orchestrator is the complete integration layer combining all APE components
- It provides both one-call and step-by-step APIs for secure execution
- All execution goes through APE enforcement (policy, authority tokens, audit)
- Prompts are compiled, never executed directly

Core Principle:
    "Prompts guide intent, but never are intent."

The APE Orchestrator is one of two ways to use APE:

1. **Orchestrator Path** (This module)
   - Simple API with minimal boilerplate
   - Handles all component wiring automatically
   - Best for: Applications that want APE security with minimal code

2. **Manual Path** (Wire components yourself)
   - Full control over every component
   - Maximum flexibility for custom workflows
   - Best for: Applications with complex requirements

The Orchestrator combines:
- ActionRepository: Registry of known actions
- IntentCompiler: Prompt → structured intent
- PlanGenerator: Intent → execution plan
- APE Core: Policy enforcement and execution
- SessionManager: Multi-turn conversation continuity
- RateLimiter: Quota and velocity limit enforcement

Usage:
    from ape.orchestrator import APEOrchestrator

    # Create orchestrator with policy
    orch = APEOrchestrator.from_policy("policies/my_policy.yaml")

    # Register tools
    orch.register_tool("read_file", my_read_file_function)
    orch.register_tool("write_file", my_write_file_function)

    # Execute a prompt (one-call API)
    result = orch.execute("Read the config.json file and show me the contents")

    # Or with session for multi-turn conversations
    session = orch.create_session(user_id="user_123", ttl_minutes=30)
    result1 = session.execute("Read config.json")
    result2 = session.execute("Now update it")
    print(session.actions_executed)
"""

from typing import Any, Optional, Callable
from dataclasses import dataclass, field

# APE Core imports
from ape.runtime import RuntimeOrchestrator as RuntimeStateMachine, RuntimeState
from ape.intent import IntentManager
from ape.plan import PlanManager
from ape.policy import PolicyEngine
from ape.authority import AuthorityManager
from ape.enforcement import EnforcementGate
from ape.action import Action
from ape.provenance import Provenance
from ape.audit import AuditLogger
from ape.config import RuntimeConfig, EnforcementMode
from ape.errors import (
    APEError,
    PolicyDenyError,
    EscalationRequiredError,
    AgentError,
    ToolNotRegisteredError,
    ExecutionError,
    IntentCompilationError,
    IntentNarrowingError,
    IntentAmbiguityError,
    PlanValidationError,
)

# APE component imports
from ape.action_repository import (
    ActionRepository,
    ActionRiskLevel,
    create_standard_repository,
)
from ape.intent_compiler import IntentCompiler, CompiledIntent
from ape.plan_generator import PlanGenerator, GeneratedPlan
from ape.session import SessionManager, Session
from ape.rate_limiter import RateLimiter, RateLimitConfig


@dataclass
class OrchestrationResult:
    """
    Result of executing a prompt or plan through the APE Orchestrator.

    Attributes:
        success: Whether execution completed successfully
        results: List of results from each step
        steps_completed: Number of steps that completed
        total_steps: Total number of steps in the plan
        error: Error message if failed
        error_step: Index of the step that failed
        intent: The compiled intent (for audit)
        plan: The generated plan (for audit)
        execution_log: Log of execution events
    """
    success: bool
    results: list[Any] = field(default_factory=list)
    steps_completed: int = 0
    total_steps: int = 0
    error: Optional[str] = None
    error_step: Optional[int] = None

    # Audit information
    intent: Optional[CompiledIntent] = None
    plan: Optional[GeneratedPlan] = None
    execution_log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "results": self.results,
            "steps_completed": self.steps_completed,
            "total_steps": self.total_steps,
            "error": self.error,
            "error_step": self.error_step,
            "execution_log": self.execution_log,
        }


class APEOrchestrator:
    """
    Complete APE integration providing unified API from prompt to execution.

    The APEOrchestrator combines all APE components into a simple,
    secure interface. It provides three usage patterns:

    **One-Call API** - Execute a prompt in a single call:
        result = orch.execute("Read config.json")

    **Step-by-Step API** - More control over each phase:
        intent = orch.compile_intent("Read config.json")
        plan = orch.create_plan(intent)
        result = orch.execute_plan(plan)

    **Session API** - Multi-turn conversations:
        session = orch.create_session(user_id="user_123", ttl_minutes=30)
        result1 = session.execute("Read config.json")
        result2 = session.execute("Now update it")

    Components Orchestrated:
    - ActionRepository: Canonical registry of known actions
    - IntentCompiler: Transforms prompts to structured intents
    - PlanGenerator: Creates validated execution plans
    - APE Core: Policy enforcement, authority tokens, execution gates
    - SessionManager: Multi-turn conversation continuity
    - RateLimiter: Quota and velocity limit enforcement

    Security Guarantees:
    - All execution goes through APE enforcement
    - Prompts are compiled, never executed directly
    - Policy compliance is mandatory
    - High-risk actions require escalation
    - All decisions are audited

    Thread Safety:
        Each APEOrchestrator instance should be used by a single thread.
        Create separate instances for concurrent execution.
        Sessions are individually thread-safe.

    Example:
        orch = APEOrchestrator.from_policy("policies/read_only.yaml")
        orch.register_tool("read_file", lambda path: open(path).read())

        result = orch.execute("Read config.json")
        if result.success:
            print(result.results[0])
    """

    def __init__(
        self,
        repository: ActionRepository,
        policy: PolicyEngine,
        config: Optional[RuntimeConfig] = None,
        llm_analyzer: Optional[Callable[[dict], dict]] = None,
        rate_limit_config: Optional[RateLimitConfig] = None,
    ) -> None:
        """
        Initialize the APE Orchestrator.

        For most use cases, use the `from_policy()` class method instead.

        Args:
            repository: ActionRepository defining known actions
            policy: PolicyEngine with loaded policy
            config: Optional runtime configuration
            llm_analyzer: Optional LLM for enhanced semantic analysis
            rate_limit_config: Optional rate limit configuration
        """
        self._repository = repository
        self._policy = policy
        self._config = config or RuntimeConfig(
            enforcement_mode=EnforcementMode.ENFORCE,
            audit_enabled=True,
        )

        # Initialize components
        self._intent_compiler = IntentCompiler(
            repository=repository,
            llm_analyzer=llm_analyzer,
        )
        self._plan_generator = PlanGenerator(
            repository=repository,
        )

        # Tool registry
        self._tools: dict[str, Callable[..., Any]] = {}

        # Audit logger
        self._audit = AuditLogger(enabled=self._config.audit_enabled)

        # Rate limiting
        self._rate_limit_config = rate_limit_config

        # Session management
        self._session_manager = SessionManager(
            rate_limit_config=rate_limit_config,
            audit_logger=self._audit,
        )

        # Cache policy data for compiler/generator
        self._policy_allowed = policy.get_all_allowed_actions()
        self._policy_forbidden = policy.get_all_forbidden_actions()

    @classmethod
    def from_policy(
        cls,
        policy_path: str,
        repository: Optional[ActionRepository] = None,
        config: Optional[RuntimeConfig] = None,
        llm_analyzer: Optional[Callable[[dict], dict]] = None,
        rate_limit_config: Optional[RateLimitConfig] = None,
        external_evaluator: Optional[Any] = None,
        source: Optional[str] = None,
        refresh_interval_seconds: Optional[int] = None,
        on_update: Optional[Callable] = None,
    ) -> "APEOrchestrator":
        """
        Create an APEOrchestrator from a policy file.

        This is the recommended way to create an APEOrchestrator.

        Args:
            policy_path: Path to policy YAML file
            repository: Optional custom ActionRepository (uses standard if None)
            config: Optional runtime configuration
            llm_analyzer: Optional LLM for enhanced semantic analysis
            rate_limit_config: Optional rate limit configuration
            external_evaluator: Optional external policy evaluator (OPA, Cedar, XACML)
            source: Optional URL for remote policy loading
            refresh_interval_seconds: Optional interval for auto-reload
            on_update: Optional callback on policy update

        Returns:
            Configured APEOrchestrator ready for tool registration

        Example:
            orch = APEOrchestrator.from_policy("policies/development.yaml")
        """
        # Load policy with optional extensions
        policy = PolicyEngine(
            policy_path,
            external_evaluator=external_evaluator,
            source=source,
            refresh_interval_seconds=refresh_interval_seconds,
            on_update=on_update,
        )

        # Use standard repository if not provided
        if repository is None:
            repository = create_standard_repository()

        return cls(
            repository=repository,
            policy=policy,
            config=config,
            llm_analyzer=llm_analyzer,
            rate_limit_config=rate_limit_config,
        )

    # =========================================================================
    # Tool Registration
    # =========================================================================

    def register_tool(
        self,
        tool_id: str,
        tool: Callable[..., Any],
        action_id: Optional[str] = None,
    ) -> None:
        """
        Register a tool implementation.

        Tools are the actual functions that perform actions. Each tool
        is identified by a tool_id and optionally bound to an action_id
        in the repository.

        Args:
            tool_id: Unique identifier for the tool
            tool: The tool function to execute
            action_id: Optional action_id this tool implements
        """
        self._tools[tool_id] = tool

        # Optionally bind to repository
        if action_id and self._repository.exists(action_id):
            self._repository.bind_tool(action_id, tool)

    def register_tools(self, tools: dict[str, Callable[..., Any]]) -> None:
        """
        Register multiple tools at once.

        Args:
            tools: Dictionary mapping tool_id to tool function
        """
        for tool_id, tool in tools.items():
            self.register_tool(tool_id, tool)

    def get_tool(self, tool_id: str) -> Optional[Callable]:
        """Get a registered tool by ID."""
        return self._tools.get(tool_id)

    def has_tool(self, tool_id: str) -> bool:
        """Check if a tool is registered."""
        return tool_id in self._tools

    # =========================================================================
    # Session API
    # =========================================================================

    def create_session(
        self,
        user_id: str,
        ttl_minutes: int = 30,
        rate_limit_config: Optional[RateLimitConfig] = None,
    ) -> Session:
        """
        Create a new session for multi-turn conversation continuity.

        Sessions track cumulative behavior across multiple execute() calls
        within a conversation. They provide:
        - actions_executed: List of actions performed
        - cumulative_risk: Running risk total
        - tokens_issued: Count of authority tokens issued
        - time_remaining: Seconds until session expires
        - get_usage_summary(): Full usage report

        Args:
            user_id: User identifier for audit and tracking
            ttl_minutes: Session time-to-live in minutes (default: 30)
            rate_limit_config: Optional per-session rate limits

        Returns:
            Session instance with execute() method

        Example:
            session = orch.create_session(user_id="user_123", ttl_minutes=30)
            result1 = session.execute("Read config.json")
            result2 = session.execute("Now update it")
            print(session.actions_executed)
            print(session.cumulative_risk)
        """
        session = self._session_manager.create(
            user_id=user_id,
            ttl_minutes=ttl_minutes,
            rate_limit_config=rate_limit_config,
            execute_fn=self.execute,
        )
        return session

    @property
    def session_manager(self) -> SessionManager:
        """Get the session manager for advanced session operations."""
        return self._session_manager

    # =========================================================================
    # One-Call API
    # =========================================================================

    def execute(
        self,
        prompt: str,
        max_risk_level: ActionRiskLevel = ActionRiskLevel.MODERATE,
        parameters: Optional[dict[str, dict]] = None,
    ) -> OrchestrationResult:
        """
        Execute a prompt through the complete APE pipeline.

        This is the primary one-call API. It automatically:
        1. Compiles the prompt to a structured intent
        2. Generates a validated plan from the intent
        3. Executes the plan through APE enforcement

        Args:
            prompt: Natural language prompt from user
            max_risk_level: Maximum risk level without requiring escalation
            parameters: Optional dict mapping action_id -> parameters

        Returns:
            OrchestrationResult with success status and results
        """
        execution_log = []

        try:
            # Step 1: Compile intent
            execution_log.append("Compiling intent from prompt...")
            intent = self.compile_intent(prompt, max_risk_level)
            execution_log.append(
                f"Intent compiled: {len(intent.allowed_actions)} allowed, "
                f"{len(intent.escalation_required)} require escalation"
            )

            # Step 2: Create plan
            execution_log.append("Creating execution plan...")
            plan = self.create_plan(intent, parameters)
            execution_log.append(f"Plan created: {len(plan)} steps")

            # Step 3: Execute plan
            execution_log.append("Executing plan through APE enforcement...")
            result = self.execute_plan(plan)

            # Update result with intent/plan for audit
            result.intent = intent
            result.plan = plan
            result.execution_log = execution_log + result.execution_log

            return result

        except IntentAmbiguityError as e:
            execution_log.append("Failed: Could not understand prompt")
            return OrchestrationResult(
                success=False,
                error=f"Could not understand prompt: {e}",
                execution_log=execution_log,
            )
        except IntentNarrowingError as e:
            execution_log.append("Failed: Policy doesn't allow requested actions")
            return OrchestrationResult(
                success=False,
                error=f"Policy doesn't allow any requested actions: {e}",
                execution_log=execution_log,
            )
        except IntentCompilationError as e:
            execution_log.append("Failed: Intent compilation error")
            return OrchestrationResult(
                success=False,
                error=f"Intent compilation failed: {e}",
                execution_log=execution_log,
            )
        except PlanValidationError as e:
            execution_log.append("Failed: Plan validation error")
            return OrchestrationResult(
                success=False,
                error=f"Plan validation failed: {e}",
                execution_log=execution_log,
            )
        except AgentError as e:
            execution_log.append(f"Failed: {e}")
            return OrchestrationResult(
                success=False,
                error=str(e),
                execution_log=execution_log,
            )

    # =========================================================================
    # Step-by-Step API
    # =========================================================================

    def compile_intent(
        self,
        prompt: str,
        max_risk_level: ActionRiskLevel = ActionRiskLevel.MODERATE,
    ) -> CompiledIntent:
        """
        Compile a prompt into a structured intent.

        Use this for step-by-step control over the execution pipeline.

        Args:
            prompt: Natural language prompt
            max_risk_level: Maximum risk without escalation

        Returns:
            CompiledIntent ready for plan creation

        Raises:
            IntentCompilationError: If compilation fails
            IntentAmbiguityError: If prompt is too ambiguous
            IntentNarrowingError: If no actions allowed by policy
        """
        # Refresh policy cache in case of dynamic updates
        self._policy_allowed = self._policy.get_all_allowed_actions()
        self._policy_forbidden = self._policy.get_all_forbidden_actions()

        return self._intent_compiler.compile(
            prompt=prompt,
            policy_allowed=self._policy_allowed,
            policy_forbidden=self._policy_forbidden,
            max_risk_level=max_risk_level,
        )

    def create_plan(
        self,
        intent: CompiledIntent,
        parameters: Optional[dict[str, dict]] = None,
    ) -> GeneratedPlan:
        """
        Create a validated plan from an intent.

        Args:
            intent: Compiled intent from compile_intent()
            parameters: Optional dict mapping action_id -> parameters

        Returns:
            GeneratedPlan ready for execution
        """
        # Generate plan from intent
        plan = self._plan_generator.generate(
            intent=intent,
            tool_registry=self._tools,
            include_escalation=False,  # Only include allowed actions
        )

        # Fill in parameters if provided
        if parameters:
            for step in plan.steps:
                if step.action_id in parameters:
                    step.parameters.update(parameters[step.action_id])

        return plan

    def create_plan_from_llm(
        self,
        llm_output: str,
        intent: CompiledIntent,
    ) -> GeneratedPlan:
        """
        Create a validated plan from LLM output.

        Use this when an LLM has generated a plan proposal that needs
        to be validated before execution.

        Args:
            llm_output: Raw LLM output containing a plan
            intent: The intent to validate against

        Returns:
            GeneratedPlan if validation passes

        Raises:
            PlanParseError: If LLM output cannot be parsed
            PlanValidationError: If plan fails validation
        """
        return self._plan_generator.parse_and_validate(
            llm_output=llm_output,
            intent=intent,
            policy_check=self._policy.evaluate_or_raise,
        )

    def execute_plan(
        self,
        plan: GeneratedPlan,
    ) -> OrchestrationResult:
        """
        Execute a validated plan through APE enforcement.

        This creates a fresh APE runtime and executes each step
        through the full enforcement pipeline.

        Args:
            plan: The validated plan to execute

        Returns:
            OrchestrationResult with execution results
        """
        execution_log = []
        results = []

        # Create fresh APE runtime components for this execution
        runtime = RuntimeStateMachine()
        intent_manager = IntentManager()
        plan_manager = PlanManager(intent_manager)
        authority = AuthorityManager(
            runtime,
            token_ttl_seconds=self._config.token_ttl_seconds,
        )
        enforcement = EnforcementGate(
            authority,
            self._config,
            self._audit,
        )

        # Register callbacks to revoke tokens on any changes
        intent_manager.add_update_callback(lambda: authority.revoke_all())
        plan_manager.add_update_callback(lambda: authority.revoke_all())

        try:
            # Set intent in APE
            intent_data = {
                "allowed_actions": plan.get_action_ids(),
                "forbidden_actions": [],
                "scope": plan.description or "execution",
            }
            intent_version = intent_manager.set(intent_data, Provenance.USER_TRUSTED)
            runtime.transition(RuntimeState.INTENT_SET)
            execution_log.append(f"Intent registered (version: {intent_version[:8]}...)")

            # Submit and approve plan in APE
            plan_hash = plan_manager.submit(plan.to_ape_plan(), Provenance.USER_TRUSTED)
            plan_manager.approve()
            runtime.transition(RuntimeState.PLAN_APPROVED)
            execution_log.append(f"Plan approved (hash: {plan_hash[:8]}...)")

            # Begin execution
            runtime.transition(RuntimeState.EXECUTING)
            execution_log.append("Execution started")

            # Execute each step
            for idx, step in enumerate(plan.steps):
                execution_log.append(f"Step {idx}: executing {step.action_id}")

                # Get the registered tool
                tool = self._tools.get(step.tool_id)
                if tool is None:
                    raise ToolNotRegisteredError(step.tool_id)

                # Create APE action object
                action = Action(
                    action_id=step.action_id,
                    tool_id=step.tool_id,
                    parameters=step.parameters,
                    intent_version=intent_version,
                    plan_hash=plan_hash,
                    plan_step_index=idx,
                )

                # Evaluate against policy (with parameters for condition checking)
                self._policy.evaluate_or_raise(action.action_id, parameters=step.parameters)

                # Issue authority token
                token = authority.issue(
                    intent_version=intent_version,
                    plan_hash=plan_hash,
                    action=action,
                )

                # Execute through enforcement gate
                result = enforcement.execute(
                    token=token,
                    tool=tool,
                    action=action,
                    **step.parameters,
                )
                results.append(result)
                execution_log.append(f"Step {idx}: completed successfully")

            # Terminate runtime
            runtime.transition(RuntimeState.TERMINATED)
            execution_log.append("Execution completed successfully")

            return OrchestrationResult(
                success=True,
                results=results,
                steps_completed=len(plan.steps),
                total_steps=len(plan.steps),
                execution_log=execution_log,
            )

        except PolicyDenyError as e:
            execution_log.append(f"Policy denied action: {e.action_id}")
            return OrchestrationResult(
                success=False,
                results=results,
                steps_completed=len(results),
                total_steps=len(plan.steps),
                error=f"Policy denied action: {e.action_id}",
                error_step=len(results),
                execution_log=execution_log,
            )
        except EscalationRequiredError as e:
            execution_log.append(f"Escalation required for: {e.action_id}")
            return OrchestrationResult(
                success=False,
                results=results,
                steps_completed=len(results),
                total_steps=len(plan.steps),
                error=f"Escalation required for: {e.action_id}",
                error_step=len(results),
                execution_log=execution_log,
            )
        except ToolNotRegisteredError as e:
            execution_log.append(f"Tool not registered: {e.tool_id}")
            return OrchestrationResult(
                success=False,
                results=results,
                steps_completed=len(results),
                total_steps=len(plan.steps),
                error=str(e),
                error_step=len(results),
                execution_log=execution_log,
            )
        except Exception as e:
            execution_log.append(f"Execution error: {e}")
            return OrchestrationResult(
                success=False,
                results=results,
                steps_completed=len(results),
                total_steps=len(plan.steps),
                error=str(e),
                error_step=len(results),
                execution_log=execution_log,
            )

    # =========================================================================
    # Analysis & Debugging
    # =========================================================================

    def analyze_prompt(self, prompt: str) -> dict[str, Any]:
        """
        Analyze a prompt without executing (for debugging/preview).

        Returns analysis including extracted signals, candidate actions,
        policy compliance check, and risk assessment.
        """
        analysis = self._intent_compiler.analyze(prompt)

        # Add policy compliance check
        compliant_actions = []
        blocked_actions = []

        for action in analysis.get("candidate_actions", []):
            action_id = action["action_id"]
            try:
                self._policy.evaluate_or_raise(action_id)
                compliant_actions.append(action_id)
            except (PolicyDenyError, EscalationRequiredError) as e:
                blocked_actions.append({
                    "action_id": action_id,
                    "reason": str(e),
                })

        analysis["policy_compliant"] = compliant_actions
        analysis["policy_blocked"] = blocked_actions

        return analysis

    def suggest_policy(
        self,
        prompt: str,
        risk_tolerance: ActionRiskLevel = ActionRiskLevel.MODERATE,
    ) -> dict[str, Any]:
        """Suggest a policy configuration that would allow the given prompt."""
        return self._intent_compiler.suggest_policy(prompt, risk_tolerance)

    def get_llm_prompt_for_plan(
        self,
        intent: CompiledIntent,
        include_schemas: bool = True,
    ) -> str:
        """Get a prompt to send to an LLM for plan generation."""
        return self._plan_generator.to_llm_prompt(intent, include_schemas)

    # =========================================================================
    # Policy Management
    # =========================================================================

    def reload_policy(self) -> Optional[str]:
        """
        Reload the policy from its original source.

        Useful for dynamic policy updates without restarting.

        Returns:
            New policy version hash, or None if no source available
        """
        new_version = self._policy.reload()
        if new_version:
            # Refresh cached lists
            self._policy_allowed = self._policy.get_all_allowed_actions()
            self._policy_forbidden = self._policy.get_all_forbidden_actions()
        return new_version

    # =========================================================================
    # Introspection
    # =========================================================================

    @property
    def repository(self) -> ActionRepository:
        """Get the ActionRepository."""
        return self._repository

    @property
    def policy(self) -> PolicyEngine:
        """Get the PolicyEngine."""
        return self._policy

    @property
    def registered_tools(self) -> list[str]:
        """Get list of registered tool IDs."""
        return list(self._tools.keys())

    def get_available_actions(self) -> list[str]:
        """Get actions that are both in the repository and allowed by policy."""
        return [
            aid for aid in self._repository.action_ids
            if self._policy.is_action_allowed(aid)
        ]

    def __repr__(self) -> str:
        policy_name = self._policy.policy.name if self._policy.policy else "none"
        return (
            f"APEOrchestrator(actions={self._repository.count}, "
            f"tools={len(self._tools)}, policy='{policy_name}')"
        )
