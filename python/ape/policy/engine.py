"""
APE Policy Engine

Policy and Policy Engine:
- A Policy is a deterministic rule set defining allowed/forbidden actions,
  tool transition rules, escalation requirements, and default-deny behavior
- Policies are declarative, YAML-based, schema-validated, loaded at runtime,
  and immutable during execution
- Policy Engine loads policy files, validates against schema, evaluates rules
  deterministically, resolves conflicts via defined precedence
- Returns ALLOW, DENY, or ESCALATE
- Supports simulation mode
- Failure behavior: deny

Enhancements:
- Parameterized policy conditions (path prefix, size limits, domain allowlists)
- External evaluator adapter support (OPA/Rego, Cedar, XACML)
- Dynamic policy reload with on_update callbacks
- Rule-based policy format with per-action conditions
"""

import json
import hashlib
import time
import threading
import logging
import fnmatch
from pathlib import Path
from typing import Any, Optional, Callable
from enum import Enum
from dataclasses import dataclass, field

import yaml
from jsonschema import validate, ValidationError

from ape.errors import (
    PolicyError,
    PolicyDenyError,
    PolicyConditionError,
    EscalationRequiredError,
)

logger = logging.getLogger("ape.policy")

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
    conditions_checked: list[str] = field(default_factory=list)

    def is_allowed(self) -> bool:
        return self.decision == PolicyDecision.ALLOW

    def is_denied(self) -> bool:
        return self.decision == PolicyDecision.DENY

    def requires_escalation(self) -> bool:
        return self.decision == PolicyDecision.ESCALATE


# =============================================================================
# Policy Condition Evaluator
# =============================================================================

class ConditionEvaluator:
    """
    Evaluates parameterized conditions on action parameters.

    Supports condition types:
    - prefix: Parameter value must start with one of the given prefixes
    - suffix: Parameter value must end with one of the given suffixes
    - allowlist: Parameter value must be in the given list (supports glob)
    - denylist: Parameter value must NOT be in the given list (supports glob)
    - max: Numeric parameter must be <= the given value
    - min: Numeric parameter must be >= the given value
    - regex: Parameter value must match the given regex pattern
    - equals: Parameter value must equal the given value

    Usage in policy YAML:
        rules:
          - action: write_file
            decision: allow
            conditions:
              path:
                prefix: ["/tmp/", "/home/user/workspace/"]
              size_bytes:
                max: 10485760
    """

    @staticmethod
    def evaluate_conditions(
        action_id: str,
        parameters: dict[str, Any],
        conditions: dict[str, Any],
    ) -> list[str]:
        """
        Evaluate all conditions against the given parameters.

        Args:
            action_id: The action being checked
            parameters: The action parameters to check
            conditions: The condition rules from the policy

        Returns:
            List of failure messages (empty if all conditions pass)
        """
        failures = []

        for param_name, constraints in conditions.items():
            if not isinstance(constraints, dict):
                continue

            param_value = parameters.get(param_name)

            # If the parameter is not present, skip — schema validation handles required fields
            if param_value is None:
                continue

            for constraint_type, constraint_value in constraints.items():
                failure = ConditionEvaluator._check_constraint(
                    param_name, param_value, constraint_type, constraint_value
                )
                if failure:
                    failures.append(failure)

        return failures

    @staticmethod
    def _check_constraint(
        param_name: str,
        param_value: Any,
        constraint_type: str,
        constraint_value: Any,
    ) -> Optional[str]:
        """
        Check a single constraint against a parameter value.

        Returns failure message string, or None if constraint passes.
        """
        if constraint_type == "prefix":
            prefixes = constraint_value if isinstance(constraint_value, list) else [constraint_value]
            str_value = str(param_value)
            if not any(str_value.startswith(p) for p in prefixes):
                return (
                    f"Parameter '{param_name}' value '{str_value}' does not start with "
                    f"any allowed prefix: {prefixes}"
                )

        elif constraint_type == "suffix":
            suffixes = constraint_value if isinstance(constraint_value, list) else [constraint_value]
            str_value = str(param_value)
            if not any(str_value.endswith(s) for s in suffixes):
                return (
                    f"Parameter '{param_name}' value '{str_value}' does not end with "
                    f"any allowed suffix: {suffixes}"
                )

        elif constraint_type == "allowlist":
            items = constraint_value if isinstance(constraint_value, list) else [constraint_value]
            str_value = str(param_value)
            if not any(fnmatch.fnmatch(str_value, pattern) for pattern in items):
                return (
                    f"Parameter '{param_name}' value '{str_value}' not in allowlist: {items}"
                )

        elif constraint_type == "denylist":
            items = constraint_value if isinstance(constraint_value, list) else [constraint_value]
            str_value = str(param_value)
            if any(fnmatch.fnmatch(str_value, pattern) for pattern in items):
                return (
                    f"Parameter '{param_name}' value '{str_value}' is in denylist: {items}"
                )

        elif constraint_type == "max":
            try:
                num_value = float(param_value)
                if num_value > float(constraint_value):
                    return (
                        f"Parameter '{param_name}' value {num_value} exceeds "
                        f"maximum {constraint_value}"
                    )
            except (ValueError, TypeError):
                return (
                    f"Parameter '{param_name}' value '{param_value}' cannot be compared "
                    f"to max constraint (not numeric)"
                )

        elif constraint_type == "min":
            try:
                num_value = float(param_value)
                if num_value < float(constraint_value):
                    return (
                        f"Parameter '{param_name}' value {num_value} is below "
                        f"minimum {constraint_value}"
                    )
            except (ValueError, TypeError):
                return (
                    f"Parameter '{param_name}' value '{param_value}' cannot be compared "
                    f"to min constraint (not numeric)"
                )

        elif constraint_type == "regex":
            import re
            str_value = str(param_value)
            if not re.search(constraint_value, str_value):
                return (
                    f"Parameter '{param_name}' value '{str_value}' does not match "
                    f"pattern '{constraint_value}'"
                )

        elif constraint_type == "equals":
            if str(param_value) != str(constraint_value):
                return (
                    f"Parameter '{param_name}' value '{param_value}' does not equal "
                    f"expected value '{constraint_value}'"
                )

        return None


# =============================================================================
# Policy Rule
# =============================================================================

@dataclass
class PolicyRule:
    """
    A single policy rule with optional conditions.

    Rules extend the basic allow/deny/escalate model with
    parameter-level conditions for fine-grained control.

    Example YAML:
        - action: write_file
          decision: allow
          conditions:
            path:
              prefix: ["/tmp/"]
            size_bytes:
              max: 10485760
    """
    action: str
    decision: str  # "allow", "deny", "escalate"
    conditions: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PolicyRule":
        """Create a PolicyRule from a dictionary."""
        return cls(
            action=data["action"],
            decision=data.get("decision", "allow"),
            conditions=data.get("conditions", {}),
        )


# =============================================================================
# Policy Data
# =============================================================================

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
    - Parameterized rules with conditions
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
    rules: list[PolicyRule] = field(default_factory=list)

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
        if self.rules:
            result["rules"] = [
                {"action": r.action, "decision": r.decision, "conditions": r.conditions}
                for r in self.rules if r.conditions
            ]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Policy":
        """Create a Policy from a dictionary."""
        rules = []
        for rule_data in data.get("rules", []):
            rules.append(PolicyRule.from_dict(rule_data))

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
            rules=rules,
        )


# =============================================================================
# Policy Engine
# =============================================================================

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
    - Supports parameterized conditions
    - Supports external evaluators (OPA, Cedar, XACML)
    - Supports dynamic policy reload

    Evaluation precedence (highest to lowest):
    1. forbidden_actions → DENY
    2. escalation_required → ESCALATE
    3. rules with conditions → evaluate conditions
    4. allowed_actions → ALLOW
    5. default_deny → DENY (if true) or ALLOW (if false)

    Failure behavior: deny
    """

    def __init__(
        self,
        policy_path: Optional[str] = None,
        external_evaluator: Optional[Any] = None,
        source: Optional[str] = None,
        refresh_interval_seconds: Optional[int] = None,
        on_update: Optional[Callable] = None,
    ) -> None:
        """
        Initialize the policy engine.

        Args:
            policy_path: Optional path to policy YAML file
            external_evaluator: Optional external evaluator (OPA, Cedar, XACML)
            source: Optional URL for remote policy loading
            refresh_interval_seconds: Optional interval for auto-reload from source
            on_update: Optional callback called when policy is updated (old_ver, new_ver)
        """
        self._policy: Optional[Policy] = None
        self._version: Optional[str] = None
        self._simulation_mode: bool = False
        self._external_evaluator = external_evaluator
        self._source = source
        self._refresh_interval = refresh_interval_seconds
        self._on_update = on_update
        self._lock = threading.RLock()
        self._refresh_thread: Optional[threading.Thread] = None
        self._refresh_stop = threading.Event()
        self._policy_path: Optional[str] = None

        if policy_path:
            self.load(policy_path)

        # Start auto-refresh if configured
        if self._source and self._refresh_interval:
            self._start_auto_refresh()

    @property
    def policy(self) -> Optional[Policy]:
        """Get the current policy."""
        with self._lock:
            return self._policy

    @property
    def version(self) -> Optional[str]:
        """Get the policy version hash."""
        with self._lock:
            return self._version

    @property
    def is_loaded(self) -> bool:
        """Check if a policy is loaded."""
        with self._lock:
            return self._policy is not None

    # =========================================================================
    # Loading
    # =========================================================================

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

        # Validate against schema (rules field is allowed via additionalProperties)
        self._validate_policy_data(data)

        with self._lock:
            old_version = self._version
            self._policy = Policy.from_dict(data)
            self._version = hashlib.sha256(raw.encode()).hexdigest()
            self._policy_path = path

            if old_version and old_version != self._version and self._on_update:
                try:
                    self._on_update(old_version, self._version)
                except Exception as e:
                    logger.warning("on_update callback error: %s", e)

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
        self._validate_policy_data(data)

        with self._lock:
            old_version = self._version
            self._policy = Policy.from_dict(data)
            canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
            self._version = hashlib.sha256(canonical.encode()).hexdigest()

            if old_version and old_version != self._version and self._on_update:
                try:
                    self._on_update(old_version, self._version)
                except Exception as e:
                    logger.warning("on_update callback error: %s", e)

        return self._version

    def reload(self) -> Optional[str]:
        """
        Reload the policy from the original source.

        If loaded from a file, re-reads the file.
        If loaded from a URL source, fetches fresh content.

        Returns:
            New version hash, or None if no source is available

        Raises:
            PolicyError: If reload fails
        """
        if self._policy_path:
            return self.load(self._policy_path)

        if self._source:
            return self._load_from_url(self._source)

        logger.warning("No policy source available for reload")
        return None

    def _load_from_url(self, url: str) -> str:
        """Load policy from a URL."""
        import urllib.request
        import urllib.error

        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
                data = yaml.safe_load(raw)
        except urllib.error.URLError as e:
            raise PolicyError(f"Failed to fetch policy from URL '{url}': {e}")
        except yaml.YAMLError as e:
            raise PolicyError(f"Invalid YAML from URL '{url}': {e}")

        if data is None:
            raise PolicyError(f"Empty policy from URL: {url}")

        return self.load_from_dict(data)

    def _validate_policy_data(self, data: dict[str, Any]) -> None:
        """Validate policy data against schema and business rules."""
        # Schema validation — use a lenient approach to allow new fields like 'rules'
        try:
            # Create a copy of schema that allows additional properties
            schema_copy = dict(_SCHEMA)
            schema_copy["additionalProperties"] = True
            validate(data, schema_copy)
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

    # =========================================================================
    # Auto-Refresh
    # =========================================================================

    def _start_auto_refresh(self) -> None:
        """Start a background thread for automatic policy refresh."""
        def _refresh_loop():
            while not self._refresh_stop.is_set():
                self._refresh_stop.wait(timeout=self._refresh_interval)
                if self._refresh_stop.is_set():
                    break
                try:
                    self.reload()
                    logger.debug("Auto-refreshed policy from source")
                except Exception as e:
                    logger.error("Auto-refresh failed: %s", e)

        self._refresh_thread = threading.Thread(
            target=_refresh_loop,
            daemon=True,
            name="ape-policy-refresh",
        )
        self._refresh_thread.start()

    def stop_auto_refresh(self) -> None:
        """Stop the auto-refresh thread."""
        if self._refresh_thread:
            self._refresh_stop.set()
            self._refresh_thread.join(timeout=5)
            self._refresh_thread = None
            self._refresh_stop.clear()

    # =========================================================================
    # Evaluation
    # =========================================================================

    def evaluate(
        self,
        action_id: str,
        parameters: Optional[dict[str, Any]] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> PolicyEvaluationResult:
        """
        Evaluate an action against the policy.

        Per architecture spec:
        - Evaluates rules deterministically
        - Returns ALLOW, DENY, or ESCALATE

        Precedence (highest to lowest):
        1. forbidden_actions → DENY
        2. escalation_required → ESCALATE
        3. rules with conditions → evaluate conditions
        4. allowed_actions → ALLOW
        5. External evaluator (if configured)
        6. default_deny → DENY (if true) or ALLOW (if false)

        Args:
            action_id: The action ID to evaluate
            parameters: Optional action parameters (for condition checking)
            context: Optional context (tenant_id, user_id, etc.)

        Returns:
            PolicyEvaluationResult

        Raises:
            PolicyError: If no policy is loaded
        """
        with self._lock:
            if self._policy is None:
                raise PolicyError("No policy loaded")

            policy = self._policy
            version = self._version or "unknown"

        conditions_checked = []

        # 1. Check forbidden (highest priority)
        if action_id in policy.forbidden_actions:
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENY,
                action_id=action_id,
                reason="Action is forbidden by policy",
                policy_version=version,
            )

        # 2. Check escalation required
        if action_id in policy.escalation_required:
            return PolicyEvaluationResult(
                decision=PolicyDecision.ESCALATE,
                action_id=action_id,
                reason="Action requires escalation",
                policy_version=version,
            )

        # 3. Check rules with conditions
        if policy.rules and parameters is not None:
            for rule in policy.rules:
                if rule.action == action_id:
                    if rule.conditions:
                        failures = ConditionEvaluator.evaluate_conditions(
                            action_id, parameters, rule.conditions
                        )
                        conditions_checked.extend(list(rule.conditions.keys()))
                        if failures:
                            return PolicyEvaluationResult(
                                decision=PolicyDecision.DENY,
                                action_id=action_id,
                                reason=f"Condition check failed: {'; '.join(failures)}",
                                policy_version=version,
                                conditions_checked=conditions_checked,
                            )

                    # Rule matched and conditions passed (or no conditions)
                    decision_map = {
                        "allow": PolicyDecision.ALLOW,
                        "deny": PolicyDecision.DENY,
                        "escalate": PolicyDecision.ESCALATE,
                    }
                    decision = decision_map.get(
                        rule.decision.lower(), PolicyDecision.DENY
                    )
                    return PolicyEvaluationResult(
                        decision=decision,
                        action_id=action_id,
                        reason=f"Matched rule for '{action_id}' with decision '{rule.decision}'",
                        policy_version=version,
                        conditions_checked=conditions_checked,
                    )

        # 4. Check allowed list
        if action_id in policy.allowed_actions:
            return PolicyEvaluationResult(
                decision=PolicyDecision.ALLOW,
                action_id=action_id,
                reason="Action is allowed by policy",
                policy_version=version,
                conditions_checked=conditions_checked,
            )

        # 5. Try external evaluator (if configured)
        if self._external_evaluator and parameters is not None:
            try:
                ext_result = self._external_evaluator.evaluate(
                    action_id, parameters, context
                )
                decision = PolicyDecision.ALLOW if ext_result.allowed else PolicyDecision.DENY
                return PolicyEvaluationResult(
                    decision=decision,
                    action_id=action_id,
                    reason=ext_result.reason or f"External evaluator: {decision.value}",
                    policy_version=version,
                    conditions_checked=conditions_checked,
                )
            except Exception as e:
                logger.error("External evaluator error for '%s': %s", action_id, e)
                # Fall through to default deny on external evaluator failure

        # 6. Default deny behavior
        if policy.default_deny:
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENY,
                action_id=action_id,
                reason="Action not in allowed list (default deny)",
                policy_version=version,
                conditions_checked=conditions_checked,
            )
        else:
            return PolicyEvaluationResult(
                decision=PolicyDecision.ALLOW,
                action_id=action_id,
                reason="Action not forbidden (default allow)",
                policy_version=version,
                conditions_checked=conditions_checked,
            )

    def evaluate_or_raise(
        self,
        action_id: str,
        parameters: Optional[dict[str, Any]] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> PolicyDecision:
        """
        Evaluate an action and raise appropriate exceptions.

        This is a convenience method that raises exceptions for
        DENY and ESCALATE decisions.

        Args:
            action_id: The action ID to evaluate
            parameters: Optional action parameters
            context: Optional context

        Returns:
            PolicyDecision.ALLOW if allowed

        Raises:
            PolicyDenyError: If action is denied
            EscalationRequiredError: If action requires escalation
        """
        result = self.evaluate(action_id, parameters, context)

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
        with self._lock:
            if self._policy is None:
                return False
            return action_id in self._policy.escalation_required

    def get_all_allowed_actions(self) -> list[str]:
        """Get all explicitly allowed actions."""
        with self._lock:
            if self._policy is None:
                return []
            return self._policy.allowed_actions.copy()

    def get_all_forbidden_actions(self) -> list[str]:
        """Get all explicitly forbidden actions."""
        with self._lock:
            if self._policy is None:
                return []
            return self._policy.forbidden_actions.copy()

    def get_rules(self) -> list[PolicyRule]:
        """Get all policy rules with conditions."""
        with self._lock:
            if self._policy is None:
                return []
            return self._policy.rules.copy()

    def validate_tool_transition(
        self,
        from_tool: str,
        to_tool: str,
    ) -> bool:
        """
        Validate a tool transition is allowed.

        Args:
            from_tool: The tool transitioning from
            to_tool: The tool transitioning to

        Returns:
            True if transition is allowed
        """
        with self._lock:
            if self._policy is None:
                return True

            if not self._policy.tool_transitions:
                return True

            allowed_targets = self._policy.tool_transitions.get(from_tool, [])
            if not allowed_targets:
                return True

            return to_tool in allowed_targets

    def __repr__(self) -> str:
        with self._lock:
            if self._policy:
                name = self._policy.name or "unnamed"
                ver = self._version[:8] if self._version else "unknown"
                return f"PolicyEngine(name={name!r}, version={ver}...)"
            return "PolicyEngine(not loaded)"

    def __del__(self) -> None:
        """Cleanup auto-refresh thread on garbage collection."""
        self.stop_auto_refresh()


# =============================================================================
# Standalone Validation
# =============================================================================

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
        schema_copy = dict(_SCHEMA)
        schema_copy["additionalProperties"] = True
        validate(data, schema_copy)
    except ValidationError as e:
        errors.append(f"Schema validation failed: {e.message}")

    # Check for overlapping actions
    allowed = set(data.get("allowed_actions", []))
    forbidden = set(data.get("forbidden_actions", []))
    overlap = allowed & forbidden
    if overlap:
        errors.append(f"Actions in both allowed and forbidden: {overlap}")

    # Validate rules format if present
    for i, rule in enumerate(data.get("rules", [])):
        if not isinstance(rule, dict):
            errors.append(f"Rule {i} is not a dictionary")
            continue
        if "action" not in rule:
            errors.append(f"Rule {i} missing required 'action' field")
        if "decision" in rule:
            valid_decisions = {"allow", "deny", "escalate"}
            if rule["decision"].lower() not in valid_decisions:
                errors.append(
                    f"Rule {i} has invalid decision '{rule['decision']}'. "
                    f"Must be one of: {valid_decisions}"
                )

    return errors
