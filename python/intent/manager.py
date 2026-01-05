"""
APE Intent Manager

Per architecture spec (§5.1 Intent and §7.2 Intent Manager):
- Intent is a structured, machine-readable declaration of user intent
- Intent defines: allowed actions, forbidden actions, escalation requirements, scope boundaries
- Intent must be validated against mandatory JSON Schema
- Intent must be canonically serialized and immutable after set
- Intent must be explicitly versioned via cryptographic hash (intent_version)
- Intent update rules: requires explicit user action, invalidates plan, revokes tokens

Failure behavior: reject malformed intent
"""

import json
import hashlib
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field
from jsonschema import validate, ValidationError

from ape.errors import IntentError, SchemaValidationError
from ape.provenance.manager import Provenance, ProvenanceManager


# Load the intent schema
_SCHEMA_PATH = Path(__file__).parent / "schema.json"
_SCHEMA: dict[str, Any] = json.loads(_SCHEMA_PATH.read_text())


@dataclass
class Intent:
    """
    Immutable intent object after creation.
    
    Intent defines:
    - Allowed actions
    - Forbidden actions
    - Escalation requirements
    - Scope boundaries
    """
    allowed_actions: list[str]
    forbidden_actions: list[str]
    scope: str
    escalation_required: list[str] = field(default_factory=list)
    description: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert intent to dictionary representation."""
        result: dict[str, Any] = {
            "allowed_actions": self.allowed_actions,
            "forbidden_actions": self.forbidden_actions,
            "scope": self.scope,
        }
        if self.escalation_required:
            result["escalation_required"] = self.escalation_required
        if self.description:
            result["description"] = self.description
        if self.metadata:
            result["metadata"] = self.metadata
        return result
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Intent":
        """Create an Intent from a dictionary."""
        return cls(
            allowed_actions=data["allowed_actions"],
            forbidden_actions=data["forbidden_actions"],
            scope=data["scope"],
            escalation_required=data.get("escalation_required", []),
            description=data.get("description"),
            metadata=data.get("metadata", {}),
        )
    
    def is_action_allowed(self, action_id: str) -> bool:
        """Check if an action is in the allowed list."""
        return action_id in self.allowed_actions
    
    def is_action_forbidden(self, action_id: str) -> bool:
        """Check if an action is in the forbidden list."""
        return action_id in self.forbidden_actions
    
    def requires_escalation(self, action_id: str) -> bool:
        """Check if an action requires escalation."""
        return action_id in self.escalation_required


class IntentManager:
    """
    Manager for intent lifecycle.
    
    This component:
    - Constructs intent objects
    - Validates intent schema
    - Computes intent hash (version)
    - Enforces immutability
    - Triggers revocation on update
    
    Per architecture spec:
    - Intent must be created from user input
    - Intent must produce a stable intent_version hash
    - Any intent update invalidates current plan and revokes tokens
    """
    
    def __init__(self) -> None:
        """Initialize the intent manager."""
        self._intent: Optional[Intent] = None
        self._version: Optional[str] = None
        self._frozen: bool = False
        self._provenance_manager = ProvenanceManager()
        self._update_callbacks: list[callable] = []
    
    @property
    def intent(self) -> Optional[Intent]:
        """Get the current intent."""
        return self._intent
    
    @property
    def version(self) -> Optional[str]:
        """Get the current intent version hash."""
        return self._version
    
    @property
    def is_set(self) -> bool:
        """Check if intent has been set."""
        return self._intent is not None
    
    def set(
        self,
        intent_data: dict[str, Any],
        provenance: Provenance
    ) -> str:
        """
        Set the intent from user input.
        
        Per architecture spec:
        - Intent must be created from user input
        - Intent must be validated against mandatory JSON Schema
        - EXTERNAL_UNTRUSTED provenance cannot set intent
        
        Args:
            intent_data: Dictionary containing intent data
            provenance: Provenance of the intent data
            
        Returns:
            The intent version hash
            
        Raises:
            IntentError: If validation fails
            ProvenanceError: If provenance is untrusted
        """
        # Verify provenance
        self._provenance_manager.assert_can_grant_authority(provenance)
        
        # Validate against schema
        try:
            validate(intent_data, _SCHEMA)
        except ValidationError as e:
            raise IntentError(
                f"Intent schema validation failed: {e.message}",
                details={"path": list(e.path)}
            )
        
        # Check for overlapping allowed/forbidden actions
        allowed = set(intent_data.get("allowed_actions", []))
        forbidden = set(intent_data.get("forbidden_actions", []))
        overlap = allowed & forbidden
        if overlap:
            raise IntentError(
                f"Actions cannot be both allowed and forbidden: {overlap}"
            )
        
        # If intent was already set, notify callbacks (for token revocation, etc.)
        if self._intent is not None:
            self._notify_update()
        
        # Create intent object
        self._intent = Intent.from_dict(intent_data)
        
        # Compute version hash from canonical serialization
        canonical = json.dumps(intent_data, sort_keys=True, separators=(',', ':'))
        self._version = hashlib.sha256(canonical.encode()).hexdigest()
        
        return self._version
    
    def validate(self, intent_data: dict[str, Any]) -> list[str]:
        """
        Validate intent data without setting it.
        
        Args:
            intent_data: Dictionary to validate
            
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        try:
            validate(intent_data, _SCHEMA)
        except ValidationError as e:
            errors.append(e.message)
            return errors
        
        # Check for overlapping actions
        allowed = set(intent_data.get("allowed_actions", []))
        forbidden = set(intent_data.get("forbidden_actions", []))
        overlap = allowed & forbidden
        if overlap:
            errors.append(f"Actions cannot be both allowed and forbidden: {overlap}")
        
        return errors
    
    def clear(self) -> None:
        """
        Clear the current intent.
        
        This triggers update callbacks for token revocation.
        """
        if self._intent is not None:
            self._notify_update()
        self._intent = None
        self._version = None
        self._frozen = False
    
    def add_update_callback(self, callback: callable) -> None:
        """
        Add a callback to be invoked when intent is updated.
        
        Callbacks are used to trigger token revocation and plan invalidation.
        
        Args:
            callback: Function to call on intent update
        """
        self._update_callbacks.append(callback)
    
    def remove_update_callback(self, callback: callable) -> None:
        """Remove an update callback."""
        if callback in self._update_callbacks:
            self._update_callbacks.remove(callback)
    
    def _notify_update(self) -> None:
        """Notify all callbacks that intent has been updated."""
        for callback in self._update_callbacks:
            callback()
    
    def check_action_allowed(self, action_id: str) -> tuple[bool, str]:
        """
        Check if an action is allowed by the current intent.
        
        Args:
            action_id: The action ID to check
            
        Returns:
            Tuple of (is_allowed, reason)
        """
        if self._intent is None:
            return False, "No intent set"
        
        if self._intent.is_action_forbidden(action_id):
            return False, f"Action {action_id} is forbidden by intent"
        
        if not self._intent.is_action_allowed(action_id):
            return False, f"Action {action_id} is not in allowed list"
        
        return True, "Allowed by intent"
    
    def __repr__(self) -> str:
        if self._intent:
            return f"IntentManager(scope={self._intent.scope!r}, version={self._version[:8]}...)"
        return "IntentManager(not set)"
