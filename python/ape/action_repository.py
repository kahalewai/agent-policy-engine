"""
APE Action Repository

The Action Repository is the canonical registry of all valid actions
that APE can authorize. It provides a bounded, enumerable set of known
actions with schemas, risk levels, and tool bindings.

Core Principle:
    "Prompts guide intent, but never are intent."
    
The Action Repository enables this by constraining what actions can
exist in intents and plans.

Usage:
    from ape.action_repository import (
        ActionRepository,
        ActionDefinition,
        ActionCategory,
        ActionRiskLevel,
        create_standard_repository,
    )
    
    # Use the standard repository
    repository = create_standard_repository()
    
    # Or create custom
    repository = ActionRepository()
    repository.register(ActionDefinition(
        action_id="my_action",
        description="My custom action",
        category=ActionCategory.CUSTOM,
        risk_level=ActionRiskLevel.LOW,
        parameter_schema={...},
    ))
    
    # Freeze when done
    repository.freeze()
"""

from ape.action_repository.repository import (
    ActionRepository,
    ActionDefinition,
    ActionCategory,
    ActionRiskLevel,
)

from ape.action_repository.standard import (
    create_standard_repository,
    get_standard_actions,
)


__all__ = [
    # Core classes
    "ActionRepository",
    "ActionDefinition",
    "ActionCategory",
    "ActionRiskLevel",
    
    # Standard repository
    "create_standard_repository",
    "get_standard_actions",
]
