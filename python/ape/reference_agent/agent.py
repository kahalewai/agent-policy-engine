"""
APE Reference Agent

A reference implementation showing how to correctly integrate APE
into an agent workflow. This demonstrates:

1. Proper runtime initialization
2. Intent setting with provenance
3. Plan submission and approval
4. Action creation and execution through enforcement gate
5. Authority token lifecycle
6. Proper state transitions

This agent is for demonstration and testing purposes.
Production agents should follow the same patterns.
"""

from typing import Any, Callable, Optional
from dataclasses import dataclass

from ape.runtime.orchestrator import RuntimeOrchestrator
from ape.runtime.state import RuntimeState
from ape.intent.manager import IntentManager
from ape.plan.manager import PlanManager
from ape.policy.engine import PolicyEngine, PolicyDecision
from ape.authority.manager import AuthorityManager
from ape.enforcement.gate import EnforcementGate
from ape.action.action import Action
from ape.provenance.manager import Provenance
from ape.audit.logger import AuditLogger
from ape.config import RuntimeConfig, EnforcementMode
from ape.errors import (
    PolicyDenyError,
    EscalationRequiredError,
    RuntimeStateError,
)


@dataclass
class AgentResult:
    """Result of agent execution."""
    success: bool
    steps_completed: int
    total_steps: int
    results: list[Any]
    error: Optional[str] = None


class ReferenceAgent:
    """
    Reference agent implementation demonstrating correct APE usage.
    
    This agent shows the complete flow:
    1. Initialize runtime
    2. Set intent
    3. Submit and approve plan
    4. Execute actions through enforcement gate
    5. Handle policy decisions
    
    Key patterns demonstrated:
    - All tool execution goes through EnforcementGate
    - Authority tokens are obtained for each action
    - State machine transitions are explicit
    - Errors are handled properly
    """
    
    def __init__(
        self,
        policy_path: str,
        config: Optional[RuntimeConfig] = None,
        audit_enabled: bool = True
    ) -> None:
        """
        Initialize the reference agent.
        
        Args:
            policy_path: Path to the policy YAML file
            config: Optional runtime configuration
            audit_enabled: Whether to enable audit logging
        """
        # Create configuration
        self._config = config or RuntimeConfig(
            enforcement_mode=EnforcementMode.ENFORCE,
            audit_enabled=audit_enabled,
            policy_path=policy_path
        )
        
        # Initialize components
        self._audit = AuditLogger(enabled=audit_enabled)
        self._runtime = RuntimeOrchestrator()
        self._intent = IntentManager()
        self._plan = PlanManager(self._intent)
        self._policy = PolicyEngine(policy_path)
        self._authority = AuthorityManager(
            self._runtime,
            token_ttl_seconds=self._config.token_ttl_seconds
        )
        self._enforcement = EnforcementGate(
            self._authority,
            self._config,
            self._audit
        )
        
        # Register callbacks for token revocation
        self._intent.add_update_callback(self._on_intent_update)
        self._plan.add_update_callback(self._on_plan_update)
        
        # Tool registry
        self._tools: dict[str, Callable[..., Any]] = {}
    
    def register_tool(self, tool_id: str, tool: Callable[..., Any]) -> None:
        """
        Register a tool with the agent.
        
        Args:
            tool_id: Unique identifier for the tool
            tool: The tool function
        """
        self._tools[tool_id] = tool
    
    def register_tools(self, tools: dict[str, Callable[..., Any]]) -> None:
        """
        Register multiple tools.
        
        Args:
            tools: Dictionary mapping tool IDs to functions
        """
        self._tools.update(tools)
    
    def set_intent(
        self,
        allowed_actions: list[str],
        scope: str,
        forbidden_actions: Optional[list[str]] = None,
        provenance: Provenance = Provenance.USER_TRUSTED
    ) -> str:
        """
        Set the agent's intent.
        
        Args:
            allowed_actions: List of allowed action IDs
            scope: Intent scope description
            forbidden_actions: Optional list of forbidden actions
            provenance: Provenance of the intent (must be trusted)
            
        Returns:
            Intent version hash
        """
        intent_data = {
            "allowed_actions": allowed_actions,
            "forbidden_actions": forbidden_actions or [],
            "scope": scope
        }
        
        version = self._intent.set(intent_data, provenance)
        self._runtime.transition(RuntimeState.INTENT_SET)
        
        self._audit.log_intent_set(version, scope)
        return version
    
    def submit_plan(
        self,
        steps: list[dict[str, Any]],
        provenance: Provenance = Provenance.USER_TRUSTED
    ) -> str:
        """
        Submit a plan for approval.
        
        Args:
            steps: List of plan steps
            provenance: Provenance of the plan
            
        Returns:
            Plan hash
        """
        plan_data = {"steps": steps}
        plan_hash = self._plan.submit(plan_data, provenance)
        return plan_hash
    
    def approve_plan(self) -> None:
        """Approve the submitted plan."""
        self._plan.approve()
        self._runtime.transition(RuntimeState.PLAN_APPROVED)
        
        if self._plan.plan:
            self._audit.log_plan_approved(
                self._plan.hash or "unknown",
                len(self._plan.plan)
            )
    
    def run(self) -> AgentResult:
        """
        Execute the approved plan.
        
        Returns:
            AgentResult with execution status
        """
        if not self._plan.is_approved:
            return AgentResult(
                success=False,
                steps_completed=0,
                total_steps=0,
                results=[],
                error="No approved plan"
            )
        
        if not self._plan.plan:
            return AgentResult(
                success=False,
                steps_completed=0,
                total_steps=0,
                results=[],
                error="Plan is empty"
            )
        
        # Transition to executing
        self._runtime.transition(RuntimeState.EXECUTING)
        
        results = []
        steps_completed = 0
        total_steps = len(self._plan.plan)
        
        for idx, step in enumerate(self._plan.plan):
            try:
                result = self._execute_step(step, idx)
                results.append(result)
                steps_completed += 1
            except PolicyDenyError as e:
                return AgentResult(
                    success=False,
                    steps_completed=steps_completed,
                    total_steps=total_steps,
                    results=results,
                    error=f"Policy denied action: {e.action_id}"
                )
            except EscalationRequiredError as e:
                return AgentResult(
                    success=False,
                    steps_completed=steps_completed,
                    total_steps=total_steps,
                    results=results,
                    error=f"Escalation required for: {e.action_id}"
                )
            except Exception as e:
                return AgentResult(
                    success=False,
                    steps_completed=steps_completed,
                    total_steps=total_steps,
                    results=results,
                    error=str(e)
                )
        
        # Transition to terminated
        self._runtime.transition(RuntimeState.TERMINATED)
        
        return AgentResult(
            success=True,
            steps_completed=steps_completed,
            total_steps=total_steps,
            results=results
        )
    
    def _execute_step(self, step: Any, step_index: int) -> Any:
        """
        Execute a single plan step.
        
        Args:
            step: The plan step (PlanStep object)
            step_index: Index of the step
            
        Returns:
            Tool execution result
        """
        # Create action from step
        action = Action(
            action_id=step.action_id,
            tool_id=step.tool_id,
            parameters=step.parameters,
            intent_version=self._intent.version or "",
            plan_hash=self._plan.hash or "",
            plan_step_index=step_index,
            intent_scope=self._intent.intent.scope if self._intent.intent else None
        )
        
        # Evaluate policy
        self._policy.evaluate_or_raise(action.action_id)
        
        # Get tool
        tool = self._tools.get(action.tool_id)
        if tool is None:
            raise ValueError(f"Tool not found: {action.tool_id}")
        
        # Issue authority token
        token = self._authority.issue(
            intent_version=action.intent_version,
            plan_hash=action.plan_hash,
            action=action
        )
        
        # Execute through enforcement gate
        result = self._enforcement.execute(
            token=token,
            tool=tool,
            action=action,
            **action.parameters
        )
        
        return result
    
    def _on_intent_update(self) -> None:
        """Handle intent update by revoking tokens."""
        self._authority.revoke_all()
        self._audit.log_token_revoked(count=None, reason="intent_update")
    
    def _on_plan_update(self) -> None:
        """Handle plan update by revoking tokens."""
        self._authority.revoke_all()
        self._audit.log_token_revoked(count=None, reason="plan_update")
    
    def get_state(self) -> RuntimeState:
        """Get current runtime state."""
        return self._runtime.state
    
    def get_stats(self) -> dict[str, Any]:
        """Get agent statistics."""
        return {
            "state": self._runtime.state.value,
            "intent_set": self._intent.is_set,
            "plan_approved": self._plan.is_approved,
            "authority": self._authority.get_stats(),
            "enforcement": self._enforcement.get_stats(),
        }
    
    def reset(self) -> None:
        """Reset the agent to initial state."""
        self._authority.revoke_all()
        self._intent.clear()
        self._plan.clear()
        self._runtime.reset()
    
    def __repr__(self) -> str:
        return f"ReferenceAgent(state={self._runtime.state.value})"


def create_simple_agent(
    policy_path: str,
    tools: dict[str, Callable[..., Any]],
    allowed_actions: list[str],
    scope: str = "default"
) -> ReferenceAgent:
    """
    Create a simple agent with pre-configured intent and tools.
    
    This is a convenience function for quick agent setup.
    
    Args:
        policy_path: Path to policy file
        tools: Dictionary of tools
        allowed_actions: Actions to allow in intent
        scope: Intent scope
        
    Returns:
        Configured ReferenceAgent
    """
    agent = ReferenceAgent(policy_path)
    agent.register_tools(tools)
    agent.set_intent(allowed_actions, scope)
    return agent
