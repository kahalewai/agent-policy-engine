"""
APE Agent Framework Integrations

Provides SDK-level integration with popular agent frameworks:
- LangChain: APELangChainToolkit
- AutoGen: APEAutoGenExecutor
- CrewAI: APECrewAITool

Usage:
    from ape.integrations import APELangChainToolkit
    toolkit = APELangChainToolkit.from_policy("policies/read_only.yaml")
"""

from ape.integrations.frameworks import (
    APELangChainToolkit,
    APEAutoGenExecutor,
    APECrewAITool,
)

__all__ = [
    "APELangChainToolkit",
    "APEAutoGenExecutor",
    "APECrewAITool",
]
