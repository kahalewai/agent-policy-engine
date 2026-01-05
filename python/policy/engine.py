"""
APE Policy Engine

Per architecture spec (§5.6 Policy and §7.5 Policy Engine):
- A Policy is a deterministic rule set defining allowed/forbidden actions,
  tool transition rules, escalation requirements, and default-deny behavior
- Policies are declarative, YAML-based, schema-validated, loaded at runtime,
  and immutable during execution
- Policy Engine loads policy files, validates against schema, evaluates rules
  deterministically, resolves conflicts via defined precedence
- Returns ALLOW, DENY, or ESCALATE
- Supports simulation mode
- Failure behavior: deny
"""

import json
import hashlib
from pathlib import Path
from typing import Any, Optional
from enum import Enum
from dataclasses import dataclass, field

import yaml
from jsonschema import validate, ValidationError

from ape.errors import PolicyError, PolicyDenyError, EscalationRequiredError


# Load the policy schema
_SCHEMA_PATH = Path(__file__).parent / "schema.json"
_SCHEMA: dict[str, Any] = json.loads(_SCHEMA_PATH.read_text())


class PolicyDecision(str, Enum):
    """Possible policy evaluation outcomes."""
    ALLOW = "ALLOW"
    DENY = "DENY"
    ESCALATE = "ESCALATE"


@dataclass
class PolicyEvaluationResult:
    """Result of a policy evaluation."""
    decision: PolicyDecision
    action_id: str
    reason: str
    policy_version: str
    
    def is_allowed(self) -> bool:
        return self.decision == PolicyDecision.ALLOW
    
    def is_denied(self) -> bool:
        return self.decision == PolicyDecision.DENY
    
    def requires_escalation(self) -> bool:
        return self.decision == PolicyDecision.ESCALATE


@dataclass
class Policy:
    """
    Immutable policy object.
    
    Policies define:
    - Allowed actions
    - Forbidden actions
    - Escalation requirements
    - Tool transition rules
    - Default-deny behavior
    """
    allowed_actions: list[str]
    forbidden_actions: list[str]
    escalation_required: list[str] = field(default_factory=list)
    default_deny: bool = True
    name: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    tool_transitions: dict[str, list[str]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert policy to dictionary."""
        result: dict[str, Any] = {
            "allowed_actions": self.allowed_actions,
            "forbidden_actions": self.forbidden_actions,
        }
        if self.escalation_required:
            result["escalation_required"] = self.escalation_required
        if not self.default_deny:
            result["default_deny"] = self.default_deny
        if self.name:
            result["name"] = self.name
        if self.version:
            result["version"] = self.version
        if self.description:
            result["description"] = self.description
        if self.tool_transitions:
            result["tool_transitions"] = self.tool_transitions
        if self.metadata:
            result["metadata"] = self.metadata
        return result
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Policy":
        """Create a Policy from a dictionary."""
        return cls(
            allowed_actions=data.get("allowed_actions", []),
            forbidden_actions=data.get("forbidden_actions", []),
            escalation_required=data.get("escalation_required", []),
            default_deny=data.get("default_deny", True),
            name=data.get("name"),
            version=data.get("version"),
            description=data.get("description"),
            tool_transitions=data.get("tool_transitions", {}),
            metadata=data.get("metadata", {}),
        )


class PolicyEngine:
    """
    Policy evaluation engine.
    
    This component:
    - Loads policy files
    - Validates policy schema
    - Evaluates rules deterministically
    - Resolves conflicts via defined precedence
    - Returns ALLOW, DENY, or ESCALATE
    - Supports simulation mode
    
    Evaluation precedence (highest to lowest):
    1. forbidden_actions → DENY
    2. escalation_required → ESCALATE
    3. allowed_actions → ALLOW
    4. default_deny → DENY (if true) or ALLOW (if false)
    
    Failure behavior: deny
    """
    
    def __init__(self, policy_path: Optional[str] = None) -> None:
        """
        Initialize the policy engine.
        
        Args:
            policy_path: Optional path to policy YAML file
        """
        self._policy: Optional[Policy] = None
        self._version: Optional[str] = None
        self._simulation_mode: bool = False
        
        if policy_path:
            self.load(policy_path)
    
    @property
    def policy(self) -> Optional[Policy]:
        """Get the current policy."""
        return self._policy
    
    @property
    def version(self) -> Optional[str]:
        """Get the policy version hash."""
        return self._version
    
    @property
    def is_loaded(self) -> bool:
        """Check if a policy is loaded."""
        return self._policy is not None
    
    def load(self, path: str) -> str:
        """
        Load a policy from a YAML file.
        
        Args:
            path: Path to the policy YAML file
            
        Returns:
            Policy version hash
            
        Raises:
            PolicyError: If loading or validation fails
        """
        policy_path = Path(path)
        if not policy_path.exists():
            raise PolicyError(f"Policy file not found: {path}")
        
        try:
            raw = policy_path.read_text()
            data = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            raise PolicyError(f"Invalid YAML in policy file: {e}")
        
        if data is None:
            raise PolicyError("Policy file is empty")
        
        # Validate against schema
        try:
            validate(data, _SCHEMA)
        except ValidationError as e:
            raise PolicyError(
                f"Policy schema validation failed: {e.message}",
                details={"path": list(e.path)}
            )
        
        # Check for overlapping allowed/forbidden actions
        allowed = set(data.get("allowed_actions", []))
        forbidden = set(data.get("forbidden_actions", []))
        overlap = allowed & forbidden
        if overlap:
            raise PolicyError(
                f"Actions cannot be both allowed and forbidden: {overlap}"
            )
        
        # Create policy object
        self._policy = Policy.from_dict(data)
        
        # Compute version hash
        self._version = hashlib.sha256(raw.encode()).hexdigest()
        
        return self._version
    
    def load_from_dict(self, data: dict[str, Any]) -> str:
        """
        Load a policy from a dictionary.
        
        Args:
            data: Policy data dictionary
            
        Returns:
            Policy version hash
            
        Raises:
            PolicyError: If validation fails
        """
        # Validate against schema
        try:
            validate(data, _SCHEMA)
        except ValidationError as e:
            raise PolicyError(
                f"Policy schema validation failed: {e.message}",
                details={"path": list(e.path)}
            )
        
        # Check for overlapping allowed/forbidden actions
        allowed = set(data.get("allowed_actions", []))
        forbidden = set(data.get("forbidden_actions", []))
        overlap = allowed & forbidden
        if overlap:
            raise PolicyError(
                f"Actions cannot be both allowed and forbidden: {overlap}"
            )
        
        # Create policy object
        self._policy = Policy.from_dict(data)
        
        # Compute version hash
        canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
        self._version = hashlib.sha256(canonical.encode()).hexdigest()
        
        return self._version
    
    def evaluate(self, action_id: str) -> PolicyEvaluationResult:
        """
        Evaluate an action against the policy.
        
        Per architecture spec:
        - Evaluates rules deterministically
        - Returns ALLOW, DENY, or ESCALATE
        
        Precedence (highest to lowest):
        1. forbidden_actions → DENY
        2. escalation_required → ESCALATE
        3. allowed_actions → ALLOW
        4. default_deny → DENY (if true) or ALLOW (if false)
        
        Args:
            action_id: The action ID to evaluate
            
        Returns:
            PolicyEvaluationResult
            
        Raises:
            PolicyError: If no policy is loaded
        """
        if self._policy is None:
            raise PolicyError("No policy loaded")
        
        version = self._version or "unknown"
        
        # 1. Check forbidden (highest priority)
        if action_id in self._policy.forbidden_actions:
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENY,
                action_id=action_id,
                reason="Action is forbidden by policy",
                policy_version=version
            )
        
        # 2. Check escalation required
        if action_id in self._policy.escalation_required:
            return PolicyEvaluationResult(
                decision=PolicyDecision.ESCALATE,
                action_id=action_id,
                reason="Action requires escalation",
                policy_version=version
            )
        
        # 3. Check allowed
        if action_id in self._policy.allowed_actions:
            return PolicyEvaluationResult(
                decision=PolicyDecision.ALLOW,
                action_id=action_id,
                reason="Action is allowed by policy",
                policy_version=version
            )
        
        # 4. Default deny behavior
        if self._policy.default_deny:
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENY,
                action_id=action_id,
                reason="Action not in allowed list (default deny)",
                policy_version=version
            )
        else:
            return PolicyEvaluationResult(
                decision=PolicyDecision.ALLOW,
                action_id=action_id,
                reason="Action not forbidden (default allow)",
                policy_version=version
            )
    
    def evaluate_or_raise(self, action_id: str) -> PolicyDecision:
        """
        Evaluate an action and raise appropriate exceptions.
        
        This is a convenience method that raises exceptions for
        DENY and ESCALATE decisions.
        
        Args:
            action_id: The action ID to evaluate
            
        Returns:
            PolicyDecision.ALLOW if allowed
            
        Raises:
            PolicyDenyError: If action is denied
            EscalationRequiredError: If action requires escalation
        """
        result = self.evaluate(action_id)
        
        if result.decision == PolicyDecision.DENY:
            raise PolicyDenyError(action_id, result.reason)
        
        if result.decision == PolicyDecision.ESCALATE:
            raise EscalationRequiredError(action_id, result.reason)
        
        return result.decision
    
    def simulate(self, action_ids: list[str]) -> list[PolicyEvaluationResult]:
        """
        Simulate policy evaluation for multiple actions.
        
        This is a read-only operation that doesn't affect state.
        
        Args:
            action_ids: List of action IDs to evaluate
            
        Returns:
            List of evaluation results
        """
        return [self.evaluate(action_id) for action_id in action_ids]
    
    def set_simulation_mode(self, enabled: bool) -> None:
        """Enable or disable simulation mode."""
        self._simulation_mode = enabled
    
    def is_action_allowed(self, action_id: str) -> bool:
        """
        Quick check if an action would be allowed.
        
        Args:
            action_id: The action ID to check
            
        Returns:
            True if action would be allowed
        """
        try:
            result = self.evaluate(action_id)
            return result.is_allowed()
        except PolicyError:
            return False
    
    def requires_escalation(self, action_id: str) -> bool:
        """
        Check if an action requires escalation.
        
        Args:
            action_id: The action ID to check
            
        Returns:
            True if action requires escalation
        """
        if self._policy is None:
            return False
        return action_id in self._policy.escalation_required
    
    def get_all_allowed_actions(self) -> list[str]:
        """Get all explicitly allowed actions."""
        if self._policy is None:
            return []
        return self._policy.allowed_actions.copy()
    
    def get_all_forbidden_actions(self) -> list[str]:
        """Get all explicitly forbidden actions."""
        if self._policy is None:
            return []
        return self._policy.forbidden_actions.copy()
    
    def validate_tool_transition(
        self,
        from_tool: str,
        to_tool: str
    ) -> bool:
        """
        Validate a tool transition is allowed.
        
        Args:
            from_tool: The tool transitioning from
            to_tool: The tool transitioning to
            
        Returns:
            True if transition is allowed
        """
        if self._policy is None:
            return True
        
        if not self._policy.tool_transitions:
            return True
        
        allowed_targets = self._policy.tool_transitions.get(from_tool, [])
        if not allowed_targets:
            return True
        
        return to_tool in allowed_targets
    
    def __repr__(self) -> str:
        if self._policy:
            name = self._policy.name or "unnamed"
            return f"PolicyEngine(name={name!r}, version={self._version[:8]}...)"
        return "PolicyEngine(not loaded)"


def validate_policy_file(path: str) -> list[str]:
    """
    Validate a policy file without loading it.
    
    Args:
        path: Path to the policy file
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    policy_path = Path(path)
    if not policy_path.exists():
        errors.append(f"Policy file not found: {path}")
        return errors
    
    try:
        raw = policy_path.read_text()
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        errors.append(f"Invalid YAML: {e}")
        return errors
    
    if data is None:
        errors.append("Policy file is empty")
        return errors
    
    try:
        validate(data, _SCHEMA)
    except ValidationError as e:
        errors.append(f"Schema validation failed: {e.message}")
    
    # Check for overlapping actions
    allowed = set(data.get("allowed_actions", []))
    forbidden = set(data.get("forbidden_actions", []))
    overlap = allowed & forbidden
    if overlap:
        errors.append(f"Actions in both allowed and forbidden: {overlap}")
    
    return errors
