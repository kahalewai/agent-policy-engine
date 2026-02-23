"""
APE Action Repository

Action Repository:
- The Action Repository is the canonical registry of all valid actions
- It provides a bounded, enumerable set of known actions
- Actions are defined with schemas, risk levels, and tool bindings
- Only actions in the repository can appear in intents and plans

The Action Repository solves a fundamental problem: APE policies reference
action_ids, but without a source of truth for what actions exist, developers
either invent IDs ad-hoc or bypass the abstraction entirely.

Core Principle:
    "Prompts guide intent, but never are intent."
    
The Action Repository enables this by providing:
1. A bounded action space that LLMs and intent compilers can reference
2. Schema validation for action parameters
3. Risk-based classifications for escalation decisions
4. Tool compatibility bindings

Failure behavior: reject unknown actions
"""

import re
import json
import hashlib
from pathlib import Path
from typing import Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

from jsonschema import validate, ValidationError

from ape.errors import (
    ActionRepositoryError,
    ActionNotFoundError,
    ActionAlreadyExistsError,
    ActionParameterError,
    RepositoryFrozenError,
)


class ActionRiskLevel(str, Enum):
    """
    Risk classification for actions.
    
    Risk levels inform escalation decisions and policy configuration.
    Higher risk actions may require human approval or additional controls.
    """
    MINIMAL = "minimal"      # Read-only, no side effects
    LOW = "low"              # Reversible side effects
    MODERATE = "moderate"    # Irreversible but recoverable
    HIGH = "high"            # Potentially destructive
    CRITICAL = "critical"    # Requires explicit human approval


class ActionCategory(str, Enum):
    """
    Categories for grouping related actions.
    
    Categories enable policy grouping and help organize
    the action space for easier management.
    """
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    NETWORK = "network"
    DATABASE_READ = "database_read"
    DATABASE_WRITE = "database_write"
    SYSTEM = "system"
    COMMUNICATION = "communication"
    COMPUTE = "compute"
    CUSTOM = "custom"


@dataclass
class ActionDefinition:
    """
    Definition of a single action in the Action Repository.
    
    An ActionDefinition specifies everything APE needs to know about
    an action: what it does, what parameters it accepts, how risky it is,
    and which tools can implement it.
    
    Attributes:
        action_id: Stable identifier matching pattern ^[a-zA-Z_][a-zA-Z0-9_]*$
        description: Human-readable description of the action
        category: ActionCategory for grouping
        risk_level: ActionRiskLevel for escalation decisions
        parameter_schema: JSON Schema for parameter validation
        compatible_tools: List of tool_ids that can implement this action
        requires_human_review: Whether this action always needs approval
        max_scope_breadth: Scope constraint (e.g., "single_file", "directory")
        tags: Additional tags for filtering/searching
        examples: Example parameter sets for documentation
        constraints: Additional constraints for the action
    """
    action_id: str
    description: str
    category: ActionCategory
    risk_level: ActionRiskLevel
    parameter_schema: dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    compatible_tools: list[str] = field(default_factory=list)
    requires_human_review: bool = False
    max_scope_breadth: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate the action_id format."""
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', self.action_id):
            raise ActionRepositoryError(
                f"Invalid action_id format: '{self.action_id}'. "
                "Must start with letter/underscore, contain only alphanumeric/underscore."
            )
    
    def validate_parameters(self, parameters: dict[str, Any]) -> list[str]:
        """
        Validate parameters against the schema.
        
        Args:
            parameters: Dictionary of parameters to validate
            
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        try:
            validate(parameters, self.parameter_schema)
        except ValidationError as e:
            errors.append(e.message)
        return errors
    
    def is_tool_compatible(self, tool_id: str) -> bool:
        """
        Check if a tool can implement this action.
        
        Args:
            tool_id: The tool identifier to check
            
        Returns:
            True if tool is compatible (or no restrictions set)
        """
        if not self.compatible_tools:
            return True  # No restrictions
        return tool_id in self.compatible_tools
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "action_id": self.action_id,
            "description": self.description,
            "category": self.category.value,
            "risk_level": self.risk_level.value,
            "parameter_schema": self.parameter_schema,
            "compatible_tools": self.compatible_tools,
            "requires_human_review": self.requires_human_review,
            "max_scope_breadth": self.max_scope_breadth,
            "tags": self.tags,
            "examples": self.examples,
            "constraints": self.constraints,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActionDefinition":
        """Create from dictionary."""
        return cls(
            action_id=data["action_id"],
            description=data["description"],
            category=ActionCategory(data["category"]),
            risk_level=ActionRiskLevel(data["risk_level"]),
            parameter_schema=data.get("parameter_schema", {"type": "object"}),
            compatible_tools=data.get("compatible_tools", []),
            requires_human_review=data.get("requires_human_review", False),
            max_scope_breadth=data.get("max_scope_breadth"),
            tags=data.get("tags", []),
            examples=data.get("examples", []),
            constraints=data.get("constraints", {}),
        )


class ActionRepository:
    """
    The canonical registry of all known actions.
    
    The Action Repository is the source of truth for:
    - What actions exist (action_ids)
    - What they do (descriptions, categories)
    - What parameters they accept (schemas)
    - How risky they are (risk levels)
    - Which tools implement them (bindings)
    
    This enables:
    - Policy narrowing: Only registered actions can be proposed
    - Intent compilation: Natural language maps to known actions
    - Parameter validation: Schemas enforce correct usage
    - Risk assessment: Risk levels inform escalation
    
    Usage:
        repository = ActionRepository()
        repository.register(ActionDefinition(...))
        
        # Or load from file
        repository = ActionRepository.load("actions.yaml")
        
        # Check if action exists
        if repository.exists("read_file"):
            defn = repository.get("read_file")
    
    Thread Safety:
        This class is NOT thread-safe. Each runtime should have
        its own ActionRepository instance.
    """
    
    def __init__(self) -> None:
        """Initialize an empty Action Repository."""
        self._actions: dict[str, ActionDefinition] = {}
        self._tool_bindings: dict[str, Callable] = {}
        self._frozen: bool = False
        self._version: Optional[str] = None
    
    @property
    def action_ids(self) -> list[str]:
        """Get all registered action IDs."""
        return list(self._actions.keys())
    
    @property
    def count(self) -> int:
        """Get the number of registered actions."""
        return len(self._actions)
    
    @property
    def is_frozen(self) -> bool:
        """Check if repository is frozen."""
        return self._frozen
    
    @property
    def version(self) -> Optional[str]:
        """Get the repository version hash."""
        return self._version
    
    def register(self, definition: ActionDefinition) -> None:
        """
        Register an action definition.
        
        Args:
            definition: The action definition to register
            
        Raises:
            RepositoryFrozenError: If repository is frozen
            ActionAlreadyExistsError: If action already registered
        """
        if self._frozen:
            raise RepositoryFrozenError()
        
        if definition.action_id in self._actions:
            raise ActionAlreadyExistsError(definition.action_id)
        
        self._actions[definition.action_id] = definition
        self._version = None  # Invalidate cached version
    
    def register_many(self, definitions: list[ActionDefinition]) -> None:
        """
        Register multiple action definitions.
        
        Args:
            definitions: List of action definitions to register
        """
        for defn in definitions:
            self.register(defn)
    
    def get(self, action_id: str) -> ActionDefinition:
        """
        Get an action definition by ID.
        
        Args:
            action_id: The action ID to look up
            
        Returns:
            ActionDefinition
            
        Raises:
            ActionNotFoundError: If action doesn't exist
        """
        if action_id not in self._actions:
            raise ActionNotFoundError(action_id)
        return self._actions[action_id]
    
    def exists(self, action_id: str) -> bool:
        """Check if an action exists in the repository."""
        return action_id in self._actions
    
    def validate_action(
        self,
        action_id: str,
        parameters: dict[str, Any],
        tool_id: Optional[str] = None
    ) -> list[str]:
        """
        Validate an action and its parameters.
        
        Args:
            action_id: The action ID
            parameters: The action parameters
            tool_id: Optional tool ID to check compatibility
            
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        # Check action exists
        if not self.exists(action_id):
            errors.append(f"Unknown action: {action_id}")
            return errors
        
        defn = self._actions[action_id]
        
        # Validate parameters
        param_errors = defn.validate_parameters(parameters)
        errors.extend(param_errors)
        
        # Check tool compatibility
        if tool_id and not defn.is_tool_compatible(tool_id):
            errors.append(
                f"Tool '{tool_id}' is not compatible with action '{action_id}'. "
                f"Compatible tools: {defn.compatible_tools}"
            )
        
        return errors
    
    def get_by_category(self, category: ActionCategory) -> list[ActionDefinition]:
        """Get all actions in a category."""
        return [
            defn for defn in self._actions.values()
            if defn.category == category
        ]
    
    def get_by_risk_level(
        self,
        max_level: ActionRiskLevel
    ) -> list[ActionDefinition]:
        """Get all actions at or below a risk level."""
        level_order = [
            ActionRiskLevel.MINIMAL,
            ActionRiskLevel.LOW,
            ActionRiskLevel.MODERATE,
            ActionRiskLevel.HIGH,
            ActionRiskLevel.CRITICAL,
        ]
        max_idx = level_order.index(max_level)
        return [
            defn for defn in self._actions.values()
            if level_order.index(defn.risk_level) <= max_idx
        ]
    
    def get_by_tag(self, tag: str) -> list[ActionDefinition]:
        """Get all actions with a specific tag."""
        return [
            defn for defn in self._actions.values()
            if tag in defn.tags
        ]
    
    def get_requiring_human_review(self) -> list[ActionDefinition]:
        """Get all actions that require human review."""
        return [
            defn for defn in self._actions.values()
            if defn.requires_human_review
        ]
    
    def bind_tool(self, action_id: str, tool: Callable) -> None:
        """
        Bind a tool implementation to an action.
        
        Args:
            action_id: The action ID
            tool: The tool function
            
        Raises:
            ActionNotFoundError: If action doesn't exist
        """
        if not self.exists(action_id):
            raise ActionNotFoundError(action_id)
        self._tool_bindings[action_id] = tool
    
    def get_tool(self, action_id: str) -> Optional[Callable]:
        """Get the bound tool for an action."""
        return self._tool_bindings.get(action_id)
    
    def freeze(self) -> str:
        """
        Freeze the Action Repository (no more registrations).
        
        Call this after all actions are registered to prevent
        accidental modification.
        
        Returns:
            The repository version hash
        """
        self._frozen = True
        self._compute_version()
        return self._version
    
    def _compute_version(self) -> None:
        """Compute a version hash for the repository state."""
        if self._version is None:
            data = json.dumps(
                [self._actions[k].to_dict() for k in sorted(self._actions.keys())],
                sort_keys=True,
                separators=(',', ':')
            )
            self._version = hashlib.sha256(data.encode()).hexdigest()
    
    def to_dict(self) -> dict[str, Any]:
        """Convert the entire repository to a dictionary."""
        return {
            "actions": [defn.to_dict() for defn in self._actions.values()],
            "frozen": self._frozen,
        }
    
    def save(self, path: str) -> None:
        """
        Save the Action Repository to a YAML file.
        
        Args:
            path: Path to save the file
        """
        import yaml
        data = self.to_dict()
        with open(path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    @classmethod
    def load(cls, path: str) -> "ActionRepository":
        """
        Load an Action Repository from a YAML file.
        
        Args:
            path: Path to the YAML file
            
        Returns:
            ActionRepository instance
        """
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f)
        
        repository = cls()
        for action_data in data.get("actions", []):
            repository.register(ActionDefinition.from_dict(action_data))
        
        if data.get("frozen", False):
            repository.freeze()
        
        return repository
    
    def to_prompt_context(self, include_schemas: bool = False) -> str:
        """
        Generate a prompt fragment describing available actions for an LLM.
        
        This is used by the Intent Compiler to help LLMs understand
        what actions are available.
        
        Args:
            include_schemas: Whether to include parameter schemas
            
        Returns:
            Formatted string for LLM prompt context
        """
        lines = ["Available Actions:"]
        
        # Group by category
        by_category: dict[ActionCategory, list[ActionDefinition]] = {}
        for defn in self._actions.values():
            by_category.setdefault(defn.category, []).append(defn)
        
        for category in ActionCategory:
            actions = by_category.get(category, [])
            if not actions:
                continue
            
            lines.append(f"\n## {category.value}")
            for defn in sorted(actions, key=lambda d: d.action_id):
                risk = f"[{defn.risk_level.value}]"
                lines.append(f"- {defn.action_id} {risk}: {defn.description}")
                
                if include_schemas and defn.parameter_schema.get("properties"):
                    props = defn.parameter_schema["properties"]
                    required = set(defn.parameter_schema.get("required", []))
                    params = []
                    for name, schema in props.items():
                        req = "*" if name in required else ""
                        ptype = schema.get("type", "any")
                        params.append(f"{name}{req}: {ptype}")
                    lines.append(f"  Parameters: {', '.join(params)}")
        
        return "\n".join(lines)
    
    def __repr__(self) -> str:
        status = "frozen" if self._frozen else "mutable"
        return f"ActionRepository(actions={self.count}, {status})"
