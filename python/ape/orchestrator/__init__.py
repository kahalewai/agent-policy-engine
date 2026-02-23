"""
APE Orchestrator

The APE Orchestrator provides a unified API that combines all APE components
for simple, secure execution from natural language prompts.

This is one of two ways to use APE:

1. **Orchestrator Path** (This module)
   - Simple one-call or step-by-step API
   - Handles all component wiring automatically
   - Best for: Applications that want APE security with minimal code

2. **Manual Path** (Wire components yourself)
   - Full control over every component
   - Maximum flexibility for custom workflows
   - Best for: Applications with complex requirements

Usage:
    from ape.orchestrator import APEOrchestrator
    
    # Create from policy file
    orch = APEOrchestrator.from_policy("policies/read_only.yaml")
    
    # Register tools
    orch.register_tool("read_file", my_read_function)
    
    # One-call execution
    result = orch.execute("Read the config file")
    
    # Or step-by-step
    intent = orch.compile_intent("Read the config file")
    plan = orch.create_plan(intent)
    result = orch.execute_plan(plan)
"""

from ape.orchestrator.orchestrator import (
    APEOrchestrator,
    OrchestrationResult,
)


__all__ = [
    "APEOrchestrator",
    "OrchestrationResult",
]
