"""
APE Agent Framework Integrations

Provides SDK-level integration with popular agent frameworks:
- LangChain: Wraps APE as a tool executor with policy enforcement
- AutoGen: Provides APE-enforced tool calling for AutoGen agents
- CrewAI: Wraps APE as a CrewAI tool with policy gates

These integrations allow existing agent applications to adopt APE
security without major refactoring. Each integration wraps the
APEOrchestrator and exposes it in the framework's native API.

Usage:
    # LangChain
    from ape.integrations import APELangChainToolkit
    toolkit = APELangChainToolkit.from_policy("policies/read_only.yaml")
    tools = toolkit.get_tools()

    # AutoGen
    from ape.integrations import APEAutoGenExecutor
    executor = APEAutoGenExecutor.from_policy("policies/read_only.yaml")

    # CrewAI
    from ape.integrations import APECrewAITool
    tool = APECrewAITool.from_policy("policies/read_only.yaml")
"""

import logging
from typing import Any, Optional, Callable
from dataclasses import dataclass

from ape.orchestrator import APEOrchestrator, OrchestrationResult
from ape.action_repository import ActionRepository, create_standard_repository
from ape.policy import PolicyEngine
from ape.config import RuntimeConfig

logger = logging.getLogger("ape.integrations")


# =============================================================================
# LangChain Integration
# =============================================================================

class APELangChainToolkit:
    """
    LangChain integration for APE.

    Wraps APE as a LangChain-compatible toolkit that provides
    policy-enforced tools to LangChain agents.

    Each tool in the toolkit corresponds to an allowed action in
    the APE policy. Tool execution goes through full APE enforcement
    including policy checks, authority tokens, and audit logging.

    Usage:
        from ape.integrations import APELangChainToolkit

        toolkit = APELangChainToolkit.from_policy("policies/read_only.yaml")

        # Register actual tool implementations
        toolkit.register_tool("read_file", my_read_func)

        # Get LangChain-compatible tools
        tools = toolkit.get_tools()

        # Use with a LangChain agent
        agent = initialize_agent(tools=tools, llm=llm)
    """

    def __init__(self, orchestrator: APEOrchestrator) -> None:
        self._orch = orchestrator

    @classmethod
    def from_policy(
        cls,
        policy_path: str,
        repository: Optional[ActionRepository] = None,
    ) -> "APELangChainToolkit":
        """Create from a policy file."""
        orch = APEOrchestrator.from_policy(policy_path, repository=repository)
        return cls(orch)

    def register_tool(self, tool_id: str, tool: Callable[..., Any]) -> None:
        """Register a tool implementation."""
        self._orch.register_tool(tool_id, tool)

    def get_tools(self) -> list[dict[str, Any]]:
        """
        Get LangChain-compatible tool definitions.

        Returns a list of tool definitions that can be passed to
        LangChain's tool initialization. Each tool wraps APE enforcement.

        Returns:
            List of tool definition dicts with name, description, and func
        """
        tools = []
        repo = self._orch.repository

        for action_id in self._orch.get_available_actions():
            if not repo.exists(action_id):
                continue
            defn = repo.get(action_id)

            def make_func(aid: str):
                def func(**kwargs) -> Any:
                    return self._execute_action(aid, kwargs)
                func.__name__ = aid
                func.__doc__ = defn.description
                return func

            tools.append({
                "name": action_id,
                "description": defn.description,
                "func": make_func(action_id),
                "parameters": defn.parameter_schema,
            })

        return tools

    def _execute_action(self, action_id: str, parameters: dict) -> Any:
        """Execute a single action through APE enforcement."""
        result = self._orch.execute(
            prompt=action_id,
            parameters={action_id: parameters},
        )
        if result.success and result.results:
            return result.results[0]
        raise RuntimeError(f"APE execution failed: {result.error}")

    @property
    def orchestrator(self) -> APEOrchestrator:
        """Get the underlying orchestrator."""
        return self._orch


# =============================================================================
# AutoGen Integration
# =============================================================================

class APEAutoGenExecutor:
    """
    AutoGen integration for APE.

    Provides an APE-enforced function executor compatible with
    Microsoft AutoGen's tool calling mechanism.

    AutoGen agents can register this executor to ensure all tool
    calls go through APE policy enforcement.

    Usage:
        from ape.integrations import APEAutoGenExecutor

        executor = APEAutoGenExecutor.from_policy("policies/read_only.yaml")
        executor.register_tool("read_file", my_read_func)

        # Use as AutoGen function map
        function_map = executor.get_function_map()

        # Or execute directly
        result = executor.execute_function("read_file", path="config.json")
    """

    def __init__(self, orchestrator: APEOrchestrator) -> None:
        self._orch = orchestrator

    @classmethod
    def from_policy(
        cls,
        policy_path: str,
        repository: Optional[ActionRepository] = None,
    ) -> "APEAutoGenExecutor":
        """Create from a policy file."""
        orch = APEOrchestrator.from_policy(policy_path, repository=repository)
        return cls(orch)

    def register_tool(self, tool_id: str, tool: Callable[..., Any]) -> None:
        """Register a tool implementation."""
        self._orch.register_tool(tool_id, tool)

    def get_function_map(self) -> dict[str, Callable]:
        """
        Get AutoGen-compatible function map.

        Returns a dict mapping function names to APE-enforced callables.

        Returns:
            Dict of function_name -> callable
        """
        functions = {}
        for action_id in self._orch.get_available_actions():
            def make_func(aid: str):
                def func(**kwargs) -> Any:
                    return self.execute_function(aid, **kwargs)
                func.__name__ = aid
                return func
            functions[action_id] = make_func(action_id)
        return functions

    def execute_function(self, function_name: str, **kwargs) -> Any:
        """
        Execute a function through APE enforcement.

        This is the primary execution method for AutoGen integration.

        Args:
            function_name: The action/function to execute
            **kwargs: Function parameters

        Returns:
            Function result

        Raises:
            RuntimeError: If APE denies the execution
        """
        result = self._orch.execute(
            prompt=function_name,
            parameters={function_name: kwargs},
        )
        if result.success and result.results:
            return result.results[0]
        raise RuntimeError(f"APE denied execution of '{function_name}': {result.error}")

    def get_tool_descriptions(self) -> list[dict[str, Any]]:
        """Get tool descriptions for AutoGen agent configuration."""
        descriptions = []
        repo = self._orch.repository
        for action_id in self._orch.get_available_actions():
            if repo.exists(action_id):
                defn = repo.get(action_id)
                descriptions.append({
                    "name": action_id,
                    "description": defn.description,
                    "parameters": defn.parameter_schema,
                })
        return descriptions

    @property
    def orchestrator(self) -> APEOrchestrator:
        """Get the underlying orchestrator."""
        return self._orch


# =============================================================================
# CrewAI Integration
# =============================================================================

class APECrewAITool:
    """
    CrewAI integration for APE.

    Wraps APE as a CrewAI-compatible tool that enforces policies
    on all agent tool usage within a CrewAI crew.

    Usage:
        from ape.integrations import APECrewAITool

        ape_tool = APECrewAITool.from_policy("policies/read_only.yaml")
        ape_tool.register_tool("read_file", my_read_func)

        # Get CrewAI-compatible tools
        tools = ape_tool.get_crew_tools()

        # Use with CrewAI
        agent = Agent(role="analyst", tools=tools)
    """

    def __init__(self, orchestrator: APEOrchestrator) -> None:
        self._orch = orchestrator

    @classmethod
    def from_policy(
        cls,
        policy_path: str,
        repository: Optional[ActionRepository] = None,
    ) -> "APECrewAITool":
        """Create from a policy file."""
        orch = APEOrchestrator.from_policy(policy_path, repository=repository)
        return cls(orch)

    def register_tool(self, tool_id: str, tool: Callable[..., Any]) -> None:
        """Register a tool implementation."""
        self._orch.register_tool(tool_id, tool)

    def get_crew_tools(self) -> list[dict[str, Any]]:
        """
        Get CrewAI-compatible tool definitions.

        Returns tool definitions that can be used with CrewAI agents.
        Each tool wraps APE enforcement.

        Returns:
            List of tool definition dicts
        """
        tools = []
        repo = self._orch.repository

        for action_id in self._orch.get_available_actions():
            if not repo.exists(action_id):
                continue
            defn = repo.get(action_id)

            def make_func(aid: str):
                def func(**kwargs) -> str:
                    result = self._orch.execute(
                        prompt=aid,
                        parameters={aid: kwargs},
                    )
                    if result.success and result.results:
                        return str(result.results[0])
                    return f"Error: {result.error}"
                func.__name__ = aid
                func.__doc__ = defn.description
                return func

            tools.append({
                "name": action_id,
                "description": defn.description,
                "func": make_func(action_id),
            })

        return tools

    def run(self, action_id: str, **kwargs) -> str:
        """
        Execute an action through APE enforcement.

        This is the primary execution method for CrewAI tools.

        Args:
            action_id: The action to execute
            **kwargs: Action parameters

        Returns:
            String result (CrewAI convention)
        """
        result = self._orch.execute(
            prompt=action_id,
            parameters={action_id: kwargs},
        )
        if result.success and result.results:
            return str(result.results[0])
        return f"APE denied: {result.error}"

    @property
    def orchestrator(self) -> APEOrchestrator:
        """Get the underlying orchestrator."""
        return self._orch
