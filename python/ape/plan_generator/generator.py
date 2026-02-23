"""
APE Plan Generator

Plan Generator:
- The Plan Generator creates and validates execution plans
- Plans are explicit, ordered lists of intended actions
- Plans must be validated against Intent and Policy before execution
- LLM proposals must be parsed and validated before use

The Plan Generator bridges the gap between LLM reasoning and APE's structured
Plan objects. It provides mechanisms for:
1. LLMs to propose plans within APE constraints
2. Validating proposed plans against intent and policy
3. Converting LLM output to APE-compatible plans
4. Generating plans programmatically from intent

Without this, developers would:
- Manually construct plans (error-prone)
- Let LLMs output arbitrary plans (security risk)
- Skip plan validation (bypassing APE protections)

Failure behavior: reject invalid plans, reject policy violations
"""

import json
import re
import hashlib
from typing import Any, Optional, Callable
from dataclasses import dataclass, field

from ape.action_repository import ActionRepository
from ape.intent_compiler import CompiledIntent
from ape.errors import (
    PlanGenerationError,
    PlanValidationError,
    PlanParseError,
    PlanIntentViolationError,
    PlanPolicyViolationError,
)


@dataclass
class GeneratedPlanStep:
    """
    A single step in a generated plan.
    
    Each step binds an action to a tool with specific parameters.
    
    Attributes:
        action_id: The action to perform (from ActionRepository)
        tool_id: The tool that implements this action
        parameters: Parameters to pass to the tool
        description: Human-readable description of what this step does
    """
    action_id: str
    tool_id: str
    parameters: dict[str, Any] = field(default_factory=dict)
    description: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to APE-compatible dictionary."""
        result = {
            "action_id": self.action_id,
            "tool_id": self.tool_id,
        }
        if self.parameters:
            result["parameters"] = self.parameters
        if self.description:
            result["description"] = self.description
        return result
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GeneratedPlanStep":
        """Create from dictionary."""
        return cls(
            action_id=data["action_id"],
            tool_id=data["tool_id"],
            parameters=data.get("parameters", {}),
            description=data.get("description"),
        )


@dataclass
class GeneratedPlan:
    """
    A plan that has passed all validation checks.
    
    This is ready to be submitted to APE's PlanManager.
    
    Attributes:
        steps: Ordered list of plan steps
        description: Human-readable description of the overall plan
        metadata: Additional metadata about the plan
        intent_version: Version of the intent this plan was generated from
        validation_log: Log of validation decisions
    """
    steps: list[GeneratedPlanStep]
    description: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    intent_version: Optional[str] = None
    validation_log: list[str] = field(default_factory=list)
    
    def __len__(self) -> int:
        return len(self.steps)
    
    def __iter__(self):
        return iter(self.steps)
    
    def to_ape_plan(self) -> dict[str, Any]:
        """
        Convert to APE PlanManager-compatible dictionary.
        
        This is what you pass to plan_manager.submit()
        """
        result = {
            "steps": [step.to_dict() for step in self.steps],
        }
        if self.description:
            result["description"] = self.description
        if self.metadata:
            result["metadata"] = self.metadata
        return result
    
    def get_action_ids(self) -> list[str]:
        """Get all action IDs in the plan."""
        return [step.action_id for step in self.steps]
    
    def compute_hash(self) -> str:
        """Compute a hash of the plan for integrity checking."""
        canonical = json.dumps(self.to_ape_plan(), sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class PlanProposal:
    """
    A plan proposal from an LLM before validation.
    
    This represents what the LLM wants to do, which must be
    validated against intent, policy, and the Action Repository.
    
    Attributes:
        raw_output: The raw LLM output string
        parsed_steps: Steps parsed from the output
        confidence: Parse confidence (0.0 to 1.0)
        parse_warnings: Warnings generated during parsing
    """
    raw_output: str
    parsed_steps: list[dict[str, Any]]
    confidence: float = 0.0
    parse_warnings: list[str] = field(default_factory=list)


class PlanGenerator:
    """
    Engine for generating, parsing, and validating plans.
    
    The PlanGenerator ensures that plans submitted to APE are valid
    and compliant with both intent and policy.
    
    Usage:
        from ape.plan_generator import PlanGenerator
        from ape.action_repository import create_standard_repository
        
        repository = create_standard_repository()
        generator = PlanGenerator(repository)
        
        # Generate a plan from intent
        plan = generator.generate(intent, tool_registry)
        
        # Or parse an LLM proposal
        plan = generator.parse_and_validate(
            llm_output,
            intent=intent,
            policy_check=policy.evaluate,
        )
        
        # Use with APE
        plan_manager.submit(plan.to_ape_plan(), Provenance.USER_TRUSTED)
    
    Security Principles:
    - Plans must be validated before use
    - Only actions in the ActionRepository can appear in plans
    - Policy compliance is checked before execution
    - LLM output is never trusted directly
    
    Thread Safety:
        This class is thread-safe for concurrent operations.
    """
    
    def __init__(
        self,
        repository: ActionRepository,
        default_tool_resolver: Optional[Callable[[str], str]] = None,
    ) -> None:
        """
        Initialize the Plan Generator.
        
        Args:
            repository: The ActionRepository defining known actions
            default_tool_resolver: Function to resolve action_id -> tool_id
        """
        self._repository = repository
        self._default_tool_resolver = default_tool_resolver or self._identity_resolver
    
    def _identity_resolver(self, action_id: str) -> str:
        """Default resolver that uses action_id as tool_id."""
        return action_id
    
    def generate(
        self,
        intent: CompiledIntent,
        tool_registry: Optional[dict[str, Callable]] = None,
        tool_resolver: Optional[Callable[[str], str]] = None,
        include_escalation: bool = False,
    ) -> GeneratedPlan:
        """
        Generate a plan from a compiled intent.
        
        This creates a simple linear plan with one step per allowed action.
        For more complex planning, use parse_and_validate with LLM output.
        
        Args:
            intent: The compiled intent from IntentCompiler
            tool_registry: Dictionary mapping tool_ids to functions
            tool_resolver: Function to resolve action_id -> tool_id
            include_escalation: Include escalation_required actions
            
        Returns:
            GeneratedPlan ready for APE
        """
        resolver = tool_resolver or self._default_tool_resolver
        validation_log = []
        
        # Gather actions to include
        actions_to_plan = list(intent.allowed_actions)
        if include_escalation:
            actions_to_plan.extend(intent.escalation_required)
        
        steps = []
        for action_id in actions_to_plan:
            # Resolve tool
            tool_id = resolver(action_id)
            
            # Verify tool exists if registry provided
            if tool_registry and tool_id not in tool_registry:
                validation_log.append(
                    f"Warning: tool '{tool_id}' for action '{action_id}' not in registry"
                )
            
            # Get action definition for description
            defn = self._repository.get(action_id)
            
            steps.append(GeneratedPlanStep(
                action_id=action_id,
                tool_id=tool_id,
                parameters={},  # Empty params - to be filled at execution
                description=defn.description,
            ))
        
        validation_log.append(f"Generated plan with {len(steps)} steps from intent")
        
        return GeneratedPlan(
            steps=steps,
            description=intent.description,
            intent_version=None,  # Will be set when intent is registered with APE
            validation_log=validation_log,
        )
    
    def parse_proposal(self, llm_output: str) -> PlanProposal:
        """
        Parse an LLM's plan proposal from text output.
        
        Supports multiple formats:
        - JSON array of steps
        - Markdown numbered list
        - Natural language with action keywords
        
        Args:
            llm_output: Raw LLM output containing a plan
            
        Returns:
            PlanProposal with parsed steps
            
        Raises:
            PlanParseError: If output cannot be parsed
        """
        warnings = []
        parsed_steps = []
        
        # Try JSON parsing first
        try:
            data = json.loads(llm_output)
            if isinstance(data, list):
                parsed_steps = data
            elif isinstance(data, dict) and "steps" in data:
                parsed_steps = data["steps"]
            elif isinstance(data, dict) and "plan" in data:
                parsed_steps = data["plan"]
            
            if parsed_steps:
                return PlanProposal(
                    raw_output=llm_output,
                    parsed_steps=parsed_steps,
                    confidence=0.95,
                )
        except json.JSONDecodeError:
            pass
        
        # Try extracting JSON from markdown code block
        json_match = re.search(r'```(?:json)?\s*(\[[\s\S]*?\]|\{[\s\S]*?\})\s*```', llm_output)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if isinstance(data, list):
                    parsed_steps = data
                elif isinstance(data, dict) and "steps" in data:
                    parsed_steps = data["steps"]
                
                if parsed_steps:
                    return PlanProposal(
                        raw_output=llm_output,
                        parsed_steps=parsed_steps,
                        confidence=0.9,
                        parse_warnings=["Extracted JSON from code block"],
                    )
            except json.JSONDecodeError:
                warnings.append("Found code block but JSON parse failed")
        
        # Try parsing numbered list format
        list_pattern = r'(\d+)\.\s*(\w+)(?:\s*:\s*(.+))?'
        matches = re.findall(list_pattern, llm_output)
        
        if matches:
            for num, action_id, description in matches:
                if self._repository.exists(action_id):
                    parsed_steps.append({
                        "action_id": action_id,
                        "tool_id": self._default_tool_resolver(action_id),
                        "description": description.strip() if description else None,
                    })
                else:
                    warnings.append(f"Unknown action in list: {action_id}")
            
            if parsed_steps:
                return PlanProposal(
                    raw_output=llm_output,
                    parsed_steps=parsed_steps,
                    confidence=0.7,
                    parse_warnings=warnings,
                )
        
        # Try extracting actions from natural language
        action_ids = self._repository.action_ids
        found_actions = []
        
        for action_id in action_ids:
            pattern = rf'\b{re.escape(action_id)}\b'
            if re.search(pattern, llm_output, re.IGNORECASE):
                found_actions.append(action_id)
        
        if found_actions:
            parsed_steps = [
                {
                    "action_id": aid,
                    "tool_id": self._default_tool_resolver(aid),
                }
                for aid in found_actions
            ]
            warnings.append("Extracted actions from natural language (low confidence)")
            
            return PlanProposal(
                raw_output=llm_output,
                parsed_steps=parsed_steps,
                confidence=0.5,
                parse_warnings=warnings,
            )
        
        raise PlanParseError(
            f"Could not parse plan from LLM output. "
            f"Expected JSON array or numbered list.",
            raw_output=llm_output[:200]
        )
    
    def validate(
        self,
        proposal: PlanProposal,
        intent: CompiledIntent,
        policy_check: Optional[Callable[[str], Any]] = None,
        strict: bool = True,
    ) -> GeneratedPlan:
        """
        Validate a plan proposal against intent and policy.
        
        Args:
            proposal: The parsed plan proposal
            intent: The compiled intent to validate against
            policy_check: Optional function that raises on policy violation
            strict: If True, fail on any error; if False, skip invalid steps
            
        Returns:
            GeneratedPlan if validation passes
            
        Raises:
            PlanValidationError: If validation fails (in strict mode)
        """
        validation_log = []
        validation_log.extend(proposal.parse_warnings)
        errors = []
        valid_steps = []
        
        allowed_set = set(intent.allowed_actions)
        escalation_set = set(intent.escalation_required)
        forbidden_set = set(intent.forbidden_actions)
        
        for i, step_data in enumerate(proposal.parsed_steps):
            step_errors = []
            
            if "action_id" not in step_data:
                step_errors.append(f"Step {i}: missing action_id")
                errors.append(step_errors[-1])
                continue
            
            action_id = step_data["action_id"]
            
            # Check action exists in repository
            if not self._repository.exists(action_id):
                step_errors.append(f"Step {i}: unknown action '{action_id}'")
                errors.append(step_errors[-1])
                if strict:
                    continue
            
            # Check intent compliance
            if action_id in forbidden_set:
                step_errors.append(f"Step {i}: action '{action_id}' is forbidden by intent")
                errors.append(step_errors[-1])
                if strict:
                    continue
            
            if action_id not in allowed_set and action_id not in escalation_set:
                step_errors.append(
                    f"Step {i}: action '{action_id}' not in intent allowed_actions "
                    f"or escalation_required"
                )
                errors.append(step_errors[-1])
                if strict:
                    continue
            
            # Validate parameters
            parameters = step_data.get("parameters", {})
            if self._repository.exists(action_id):
                defn = self._repository.get(action_id)
                param_errors = defn.validate_parameters(parameters)
                if param_errors:
                    for pe in param_errors:
                        step_errors.append(f"Step {i}: {pe}")
                        errors.append(step_errors[-1])
                    if strict:
                        continue
            
            # Check policy
            if policy_check:
                try:
                    policy_check(action_id)
                except Exception as e:
                    step_errors.append(f"Step {i}: policy check failed: {e}")
                    errors.append(step_errors[-1])
                    if strict:
                        continue
            
            # Check tool compatibility
            tool_id = step_data.get("tool_id", self._default_tool_resolver(action_id))
            if self._repository.exists(action_id):
                defn = self._repository.get(action_id)
                if not defn.is_tool_compatible(tool_id):
                    step_errors.append(
                        f"Step {i}: tool '{tool_id}' not compatible with action '{action_id}'"
                    )
                    errors.append(step_errors[-1])
                    if strict:
                        continue
            
            if not step_errors:
                valid_steps.append(GeneratedPlanStep(
                    action_id=action_id,
                    tool_id=tool_id,
                    parameters=parameters,
                    description=step_data.get("description"),
                ))
                validation_log.append(f"Step {i}: validated '{action_id}'")
        
        if not valid_steps:
            raise PlanValidationError(
                "No valid steps in plan after validation",
                errors=errors,
            )
        
        if strict and errors:
            raise PlanValidationError(
                f"Plan validation failed with {len(errors)} errors",
                errors=errors,
            )
        
        validation_log.append(f"Validated {len(valid_steps)} of {len(proposal.parsed_steps)} steps")
        
        return GeneratedPlan(
            steps=valid_steps,
            description=intent.description,
            validation_log=validation_log,
            metadata={
                "source": "llm_proposal",
                "parse_confidence": proposal.confidence,
                "validation_errors": errors,
            },
        )
    
    def parse_and_validate(
        self,
        llm_output: str,
        intent: CompiledIntent,
        policy_check: Optional[Callable[[str], Any]] = None,
        strict: bool = True,
    ) -> GeneratedPlan:
        """
        Parse and validate an LLM plan proposal in one call.
        
        This is the recommended method for processing LLM output.
        
        Args:
            llm_output: Raw LLM output containing a plan
            intent: The compiled intent to validate against
            policy_check: Optional function that raises on policy violation
            strict: If True, fail on any error; if False, skip invalid steps
            
        Returns:
            GeneratedPlan if valid
        """
        proposal = self.parse_proposal(llm_output)
        return self.validate(proposal, intent, policy_check, strict)
    
    def repair(
        self,
        proposal: PlanProposal,
        intent: CompiledIntent,
    ) -> PlanProposal:
        """
        Attempt to repair a plan proposal with common fixes.
        
        Repairs include:
        - Removing unknown actions
        - Removing forbidden actions
        - Adding missing tool_ids
        - Fixing invalid parameters
        
        Args:
            proposal: The plan proposal to repair
            intent: The compiled intent for validation
            
        Returns:
            Repaired PlanProposal
        """
        repaired_steps = []
        warnings = list(proposal.parse_warnings)
        
        allowed_set = set(intent.allowed_actions + intent.escalation_required)
        
        for step in proposal.parsed_steps:
            if "action_id" not in step:
                warnings.append("Skipped step without action_id")
                continue
            
            action_id = step["action_id"]
            
            if not self._repository.exists(action_id):
                warnings.append(f"Removed unknown action: {action_id}")
                continue
            
            if action_id in intent.forbidden_actions:
                warnings.append(f"Removed forbidden action: {action_id}")
                continue
            
            if action_id not in allowed_set:
                warnings.append(f"Removed action not in intent: {action_id}")
                continue
            
            if "tool_id" not in step:
                step["tool_id"] = self._default_tool_resolver(action_id)
                warnings.append(f"Added tool_id for {action_id}")
            
            if "parameters" not in step:
                step["parameters"] = {}
            elif not isinstance(step["parameters"], dict):
                step["parameters"] = {}
                warnings.append(f"Reset invalid parameters for {action_id}")
            
            repaired_steps.append(step)
        
        return PlanProposal(
            raw_output=proposal.raw_output,
            parsed_steps=repaired_steps,
            confidence=proposal.confidence * 0.9,
            parse_warnings=warnings,
        )
    
    def simulate(
        self,
        plan: GeneratedPlan,
        policy_check: Callable[[str], Any],
    ) -> dict[str, Any]:
        """
        Simulate plan execution to check policy compliance.
        
        This performs a dry-run to see if the plan would succeed
        without actually executing anything.
        
        Args:
            plan: The plan to simulate
            policy_check: Function to check policy (raises on violation)
            
        Returns:
            Dictionary with simulation results
        """
        results = {
            "would_succeed": True,
            "steps": [],
            "blocked_steps": [],
        }
        
        for i, step in enumerate(plan.steps):
            step_result = {
                "index": i,
                "action_id": step.action_id,
                "allowed": False,
                "reason": None,
            }
            
            try:
                policy_check(step.action_id)
                step_result["allowed"] = True
                step_result["reason"] = "Policy allows"
            except Exception as e:
                step_result["allowed"] = False
                step_result["reason"] = str(e)
                results["would_succeed"] = False
                results["blocked_steps"].append(i)
            
            results["steps"].append(step_result)
        
        return results
    
    def to_llm_prompt(
        self,
        intent: CompiledIntent,
        include_schemas: bool = True,
    ) -> str:
        """
        Generate a prompt for an LLM to create a plan.
        
        This generates a structured prompt that tells the LLM:
        - What actions are available
        - What parameters each action accepts
        - What output format to use
        - What the user's intent is
        
        Args:
            intent: The compiled intent
            include_schemas: Whether to include parameter schemas
            
        Returns:
            Prompt string for LLM
        """
        lines = [
            "# Plan Generation Task",
            "",
            "Create a plan to accomplish the user's intent. Use ONLY the actions listed below.",
            "",
            "## Available Actions",
            ""
        ]
        
        all_actions = intent.allowed_actions + intent.escalation_required
        
        for action_id in all_actions:
            if not self._repository.exists(action_id):
                continue
            
            defn = self._repository.get(action_id)
            escalation_note = " [REQUIRES APPROVAL]" if action_id in intent.escalation_required else ""
            lines.append(f"### {action_id}{escalation_note}")
            lines.append(f"- Description: {defn.description}")
            lines.append(f"- Risk: {defn.risk_level.value}")
            
            if include_schemas and defn.parameter_schema.get("properties"):
                lines.append("- Parameters:")
                props = defn.parameter_schema.get("properties", {})
                required = set(defn.parameter_schema.get("required", []))
                for name, schema in props.items():
                    req_mark = "*" if name in required else ""
                    ptype = schema.get("type", "any")
                    pdesc = schema.get("description", "")
                    lines.append(f"  - {name}{req_mark} ({ptype}): {pdesc}")
            
            lines.append("")
        
        if intent.forbidden_actions:
            lines.extend([
                "## Forbidden Actions (DO NOT USE)",
                "",
            ])
            for action_id in intent.forbidden_actions:
                lines.append(f"- {action_id}")
            lines.append("")
        
        lines.extend([
            "## Output Format",
            "",
            "Respond with a JSON array of steps:",
            "```json",
            "[",
            '  {"action_id": "...", "tool_id": "...", "parameters": {...}, "description": "..."},',
            "  ...",
            "]",
            "```",
            "",
            "## User Intent",
            "",
            f"Scope: {intent.scope}",
            f"Original request: {intent.original_prompt}",
            "",
            "Now generate the plan:",
        ])
        
        return "\n".join(lines)
