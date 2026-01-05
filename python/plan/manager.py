"""
APE Plan Manager

Per architecture spec (§5.2 Plan and §7.3 Plan Manager):
- A Plan is an explicit, ordered list of intended actions
- Plan must be proposed by the agent
- Plan must be validated against intent
- Plan must be validated against mandatory JSON Schema
- Plan must be frozen upon approval
- Plan must be canonically serialized with stable cryptographic hash (plan_hash)
- Plan must be linear (no branching or looping)
- Plan must be immutable once approved

Plan mutation rules:
- Any plan change invalidates the plan, plan hash, runtime execution state
- Any plan change revokes all issued AuthorityTokens
- Any plan change requires re-submission and approval

Failure behavior: deny execution
"""

import json
import hashlib
from pathlib import Path
from typing import Any, Optional, Iterator
from dataclasses import dataclass, field
from jsonschema import validate, ValidationError

from ape.errors import PlanError, PlanMutationError
from ape.provenance.manager import Provenance, ProvenanceManager
from ape.intent.manager import IntentManager


# Load the plan schema
_SCHEMA_PATH = Path(__file__).parent / "schema.json"
_SCHEMA: dict[str, Any] = json.loads(_SCHEMA_PATH.read_text())


@dataclass
class PlanStep:
    """A single step in a plan."""
    action_id: str
    tool_id: str
    parameters: dict[str, Any] = field(default_factory=dict)
    description: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert step to dictionary."""
        result: dict[str, Any] = {
            "action_id": self.action_id,
            "tool_id": self.tool_id,
        }
        if self.parameters:
            result["parameters"] = self.parameters
        if self.description:
            result["description"] = self.description
        return result
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlanStep":
        """Create a PlanStep from a dictionary."""
        return cls(
            action_id=data["action_id"],
            tool_id=data["tool_id"],
            parameters=data.get("parameters", {}),
            description=data.get("description"),
        )


@dataclass
class Plan:
    """
    Immutable plan object after approval.
    
    A Plan is an explicit, ordered list of intended actions.
    Plans are linear (no branching or looping).
    """
    steps: list[PlanStep]
    description: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def __len__(self) -> int:
        return len(self.steps)
    
    def __iter__(self) -> Iterator[PlanStep]:
        return iter(self.steps)
    
    def __getitem__(self, index: int) -> PlanStep:
        return self.steps[index]
    
    def to_dict(self) -> dict[str, Any]:
        """Convert plan to dictionary."""
        result: dict[str, Any] = {
            "steps": [step.to_dict() for step in self.steps],
        }
        if self.description:
            result["description"] = self.description
        if self.metadata:
            result["metadata"] = self.metadata
        return result
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Plan":
        """Create a Plan from a dictionary."""
        steps = [PlanStep.from_dict(s) for s in data.get("steps", [])]
        return cls(
            steps=steps,
            description=data.get("description"),
            metadata=data.get("metadata", {}),
        )
    
    def get_action_ids(self) -> list[str]:
        """Get all action IDs in the plan."""
        return [step.action_id for step in self.steps]


class PlanManager:
    """
    Manager for plan lifecycle.
    
    This component:
    - Accepts plan proposals
    - Validates plan schema
    - Validates against intent
    - Computes plan hash
    - Detects mutation
    - Freezes approved plans
    
    Failure behavior: deny execution
    """
    
    def __init__(self, intent_manager: Optional[IntentManager] = None) -> None:
        """
        Initialize the plan manager.
        
        Args:
            intent_manager: Optional IntentManager for intent validation
        """
        self._plan: Optional[Plan] = None
        self._hash: Optional[str] = None
        self._approved: bool = False
        self._intent_manager = intent_manager
        self._provenance_manager = ProvenanceManager()
        self._update_callbacks: list[callable] = []
        self._original_hash: Optional[str] = None  # For mutation detection
    
    @property
    def plan(self) -> Optional[Plan]:
        """Get the current plan."""
        return self._plan
    
    @property
    def hash(self) -> Optional[str]:
        """Get the current plan hash."""
        return self._hash
    
    @property
    def is_approved(self) -> bool:
        """Check if plan has been approved."""
        return self._approved
    
    @property
    def is_submitted(self) -> bool:
        """Check if a plan has been submitted."""
        return self._plan is not None
    
    def submit(
        self,
        plan_data: dict[str, Any],
        provenance: Provenance
    ) -> str:
        """
        Submit a plan proposal.
        
        Per architecture spec:
        - Plan must be proposed by the agent
        - Plan must be validated against mandatory JSON Schema
        - EXTERNAL_UNTRUSTED provenance cannot submit plans
        
        Args:
            plan_data: Dictionary containing plan data
            provenance: Provenance of the plan data
            
        Returns:
            The plan hash
            
        Raises:
            PlanError: If validation fails
            ProvenanceError: If provenance is untrusted
        """
        # Verify provenance
        self._provenance_manager.assert_can_grant_authority(provenance)
        
        # If plan was already approved, this is a re-submission
        if self._approved:
            self._notify_update()
            self._approved = False
        
        # Validate against schema
        try:
            validate(plan_data, _SCHEMA)
        except ValidationError as e:
            raise PlanError(
                f"Plan schema validation failed: {e.message}",
                details={"path": list(e.path)}
            )
        
        # Create plan object
        self._plan = Plan.from_dict(plan_data)
        
        # Compute hash from canonical serialization
        canonical = json.dumps(plan_data, sort_keys=True, separators=(',', ':'))
        self._hash = hashlib.sha256(canonical.encode()).hexdigest()
        
        return self._hash
    
    def validate_against_intent(self) -> list[str]:
        """
        Validate the plan against the current intent.
        
        Per architecture spec: Plan must be validated against intent.
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        if self._plan is None:
            errors.append("No plan submitted")
            return errors
        
        if self._intent_manager is None or not self._intent_manager.is_set:
            errors.append("No intent set")
            return errors
        
        intent = self._intent_manager.intent
        
        for step in self._plan.steps:
            # Check if action is forbidden
            if intent.is_action_forbidden(step.action_id):
                errors.append(f"Action {step.action_id} is forbidden by intent")
            
            # Check if action is allowed
            if not intent.is_action_allowed(step.action_id):
                errors.append(f"Action {step.action_id} is not allowed by intent")
        
        return errors
    
    def approve(self) -> None:
        """
        Approve and freeze the current plan.
        
        Per architecture spec:
        - Plan must be frozen upon approval
        - Plan must be immutable once approved
        
        Raises:
            PlanError: If no plan is submitted or validation fails
        """
        if self._plan is None:
            raise PlanError("No plan submitted")
        
        # Validate against intent if intent manager is available
        if self._intent_manager is not None:
            errors = self.validate_against_intent()
            if errors:
                raise PlanError(
                    "Plan validation against intent failed",
                    details={"errors": errors}
                )
        
        self._approved = True
        self._original_hash = self._hash
    
    def detect_mutation(self) -> bool:
        """
        Detect if the plan has been mutated after approval.
        
        Returns:
            True if mutation detected
        """
        if not self._approved or self._plan is None:
            return False
        
        # Recompute hash and compare
        current = json.dumps(self._plan.to_dict(), sort_keys=True, separators=(',', ':'))
        current_hash = hashlib.sha256(current.encode()).hexdigest()
        
        return current_hash != self._original_hash
    
    def assert_not_mutated(self) -> None:
        """
        Assert the plan has not been mutated.
        
        Raises:
            PlanMutationError: If mutation detected
        """
        if self.detect_mutation():
            raise PlanMutationError()
    
    def clear(self) -> None:
        """
        Clear the current plan.
        
        This triggers update callbacks for token revocation.
        """
        if self._plan is not None:
            self._notify_update()
        self._plan = None
        self._hash = None
        self._approved = False
        self._original_hash = None
    
    def add_update_callback(self, callback: callable) -> None:
        """Add a callback to be invoked when plan is updated."""
        self._update_callbacks.append(callback)
    
    def remove_update_callback(self, callback: callable) -> None:
        """Remove an update callback."""
        if callback in self._update_callbacks:
            self._update_callbacks.remove(callback)
    
    def _notify_update(self) -> None:
        """Notify all callbacks that plan has been updated."""
        for callback in self._update_callbacks:
            callback()
    
    def get_step(self, index: int) -> Optional[PlanStep]:
        """
        Get a plan step by index.
        
        Args:
            index: Step index
            
        Returns:
            PlanStep or None if out of bounds
        """
        if self._plan is None or index < 0 or index >= len(self._plan):
            return None
        return self._plan[index]
    
    def __repr__(self) -> str:
        if self._plan:
            status = "approved" if self._approved else "pending"
            return f"PlanManager(steps={len(self._plan)}, status={status}, hash={self._hash[:8]}...)"
        return "PlanManager(not submitted)"
