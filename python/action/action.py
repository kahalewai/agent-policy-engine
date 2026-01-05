"""
APE Action Module

- An Action is the smallest unit of authority
- Actions are explicit, comparable, auditable, deterministically bound to authority
- Actions are matchable by policy

An Action consists of:
- action_id: stable identifier
- tool_id: tool to invoke
- parameters: schema-validated object
- intent_version: hash binding
- intent_scope: scope reference (optional)
- plan_hash: hash binding
- plan_step_index: integer index
"""

import json
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field, asdict
from jsonschema import validate, ValidationError

from ape.errors import ActionError, SchemaValidationError


# Load the action schema
_SCHEMA_PATH = Path(__file__).parent / "schema.json"
_SCHEMA: dict[str, Any] = json.loads(_SCHEMA_PATH.read_text())


@dataclass(frozen=True)
class Action:
    """
    Immutable action object representing a single unit of authority.
    
    Per architecture spec:
    - Actions are explicit
    - Actions are comparable
    - Actions are auditable
    - Actions are deterministically bound to authority
    - Actions are matchable by policy
    
    Each Action execution must be bound to:
    - Intent version
    - Plan hash
    - Plan step index
    """
    action_id: str
    tool_id: str
    parameters: dict[str, Any]
    intent_version: str
    plan_hash: str
    plan_step_index: int
    intent_scope: Optional[str] = None
    
    def __post_init__(self) -> None:
        """Validate the action against schema after construction."""
        self._validate()
    
    def _validate(self) -> None:
        """
        Validate this action against the JSON schema.
        
        Raises:
            ActionError: If validation fails
        """
        try:
            data = self.to_dict()
            validate(data, _SCHEMA)
        except ValidationError as e:
            raise ActionError(
                f"Action validation failed: {e.message}",
                details={"path": list(e.path), "action_id": self.action_id}
            )
    
    def to_dict(self) -> dict[str, Any]:
        """Convert action to dictionary representation."""
        result = {
            "action_id": self.action_id,
            "tool_id": self.tool_id,
            "parameters": self.parameters,
            "intent_version": self.intent_version,
            "plan_hash": self.plan_hash,
            "plan_step_index": self.plan_step_index,
        }
        if self.intent_scope is not None:
            result["intent_scope"] = self.intent_scope
        return result
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Action":
        """
        Create an Action from a dictionary.
        
        Args:
            data: Dictionary containing action fields
            
        Returns:
            Action instance
            
        Raises:
            ActionError: If data is invalid
        """
        try:
            return cls(
                action_id=data["action_id"],
                tool_id=data["tool_id"],
                parameters=data.get("parameters", {}),
                intent_version=data["intent_version"],
                plan_hash=data["plan_hash"],
                plan_step_index=data["plan_step_index"],
                intent_scope=data.get("intent_scope"),
            )
        except KeyError as e:
            raise ActionError(f"Missing required field: {e}")
        except TypeError as e:
            raise ActionError(f"Invalid action data: {e}")
    
    @classmethod
    def from_plan_step(
        cls,
        step: dict[str, Any],
        step_index: int,
        intent_version: str,
        plan_hash: str,
        intent_scope: Optional[str] = None
    ) -> "Action":
        """
        Create an Action from a plan step.
        
        This is the primary way to create actions during execution.
        
        Args:
            step: The plan step dictionary
            step_index: Index of this step in the plan
            intent_version: Hash of the current intent
            plan_hash: Hash of the current plan
            intent_scope: Optional scope from intent
            
        Returns:
            Action instance
        """
        return cls(
            action_id=step["action_id"],
            tool_id=step["tool_id"],
            parameters=step.get("parameters", {}),
            intent_version=intent_version,
            plan_hash=plan_hash,
            plan_step_index=step_index,
            intent_scope=intent_scope,
        )
    
    def matches_policy_rule(self, rule_action_id: str) -> bool:
        """
        Check if this action matches a policy rule's action ID.
        
        Args:
            rule_action_id: The action ID from a policy rule
            
        Returns:
            True if this action matches the rule
        """
        return self.action_id == rule_action_id
    
    def __repr__(self) -> str:
        return (
            f"Action(action_id={self.action_id!r}, tool_id={self.tool_id!r}, "
            f"step={self.plan_step_index})"
        )


def validate_action_data(data: dict[str, Any]) -> list[str]:
    """
    Validate action data against schema without creating an Action.
    
    Args:
        data: Dictionary to validate
        
    Returns:
        List of validation error messages (empty if valid)
    """
    try:
        validate(data, _SCHEMA)
        return []
    except ValidationError as e:
        return [e.message]
