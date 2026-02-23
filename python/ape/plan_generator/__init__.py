"""
APE Plan Generator

The Plan Generator creates and validates execution plans from compiled
intents or LLM output. It ensures plans comply with both intent constraints
and policy requirements before submission to APE.

Usage:
    from ape.plan_generator import PlanGenerator, GeneratedPlan
    from ape.action_repository import create_standard_repository
    
    repository = create_standard_repository()
    generator = PlanGenerator(repository)
    
    # Generate from intent
    plan = generator.generate(intent)
    
    # Or parse LLM output
    plan = generator.parse_and_validate(
        llm_output,
        intent=intent,
        policy_check=policy.evaluate_or_raise,
    )
    
    # Use with APE PlanManager
    plan_manager.submit(plan.to_ape_plan(), Provenance.USER_TRUSTED)
"""

from ape.plan_generator.generator import (
    PlanGenerator,
    GeneratedPlanStep,
    GeneratedPlan,
    PlanProposal,
)


__all__ = [
    "PlanGenerator",
    "GeneratedPlanStep",
    "GeneratedPlan",
    "PlanProposal",
]
