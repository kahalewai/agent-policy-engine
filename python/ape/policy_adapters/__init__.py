"""
APE Policy Adapters

Provides adapter integrations for enterprise policy engines:
- OPA/Rego: Open Policy Agent (cloud-native standard)
- AWS Cedar: Amazon's fine-grained authorization language
- XACML: OASIS enterprise standard for attribute-based access control

Usage:
    from ape.policy_adapters import OPAEvaluator, CedarEvaluator, XACMLEvaluator

    # Use OPA for policy evaluation
    evaluator = OPAEvaluator("http://localhost:8181/v1/data/ape/allow")

    # Pass to PolicyEngine
    from ape.policy import PolicyEngine
    engine = PolicyEngine("policy.yaml", external_evaluator=evaluator)
"""

from ape.policy_adapters.adapters import (
    ExternalEvaluator,
    AdapterDecision,
    OPAEvaluator,
    CedarEvaluator,
    XACMLEvaluator,
)

__all__ = [
    "ExternalEvaluator",
    "AdapterDecision",
    "OPAEvaluator",
    "CedarEvaluator",
    "XACMLEvaluator",
]
