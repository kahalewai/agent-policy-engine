"""
APE MCP Scanner

Scans MCP (Model Context Protocol) configurations and generates
APE policies that match the MCP tool definitions.

This allows developers to:
1. Scan their MCP configuration file
2. Auto-generate an APE policy with all tools as allowed actions
3. Modify the generated policy as needed
4. Re-run the scan when MCP configuration changes

Usage:
    ape mcp-scan mcp_config.json -o policy.yaml
    ape mcp-info mcp_config.json
"""

import json
from pathlib import Path
from typing import Any, Optional


class MCPScanner:
    """
    Scanner for MCP configuration files.
    
    Parses MCP configuration JSON files and extracts tool definitions
    that can be converted to APE policy actions.
    
    MCP Configuration Format (typical structure):
    {
        "mcpServers": {
            "server_name": {
                "command": "...",
                "args": [...],
                "tools": ["tool1", "tool2"]  # or detected from server
            }
        }
    }
    """
    
    def __init__(self, config_path: str) -> None:
        """
        Initialize the MCP scanner.
        
        Args:
            config_path: Path to the MCP configuration JSON file
        """
        self._config_path = Path(config_path)
        self._config: dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self) -> None:
        """Load and parse the MCP configuration file."""
        if not self._config_path.exists():
            raise FileNotFoundError(f"MCP config not found: {self._config_path}")
        
        with open(self._config_path) as f:
            self._config = json.load(f)
    
    def get_servers(self) -> list[str]:
        """
        Get list of MCP server names.
        
        Returns:
            List of server names
        """
        servers = self._config.get("mcpServers", {})
        return list(servers.keys())
    
    def get_server_config(self, server_name: str) -> dict[str, Any]:
        """
        Get configuration for a specific server.
        
        Args:
            server_name: Name of the server
            
        Returns:
            Server configuration dictionary
        """
        return self._config.get("mcpServers", {}).get(server_name, {})
    
    def get_tools_for_server(self, server_name: str) -> list[str]:
        """
        Get tools defined for a specific server.
        
        This extracts tool names from the server configuration.
        Tools may be defined in various ways:
        - Explicit "tools" array
        - Inferred from server type/name
        
        Args:
            server_name: Name of the server
            
        Returns:
            List of tool names
        """
        server_config = self.get_server_config(server_name)
        
        # Check for explicit tools array
        if "tools" in server_config:
            return server_config["tools"]
        
        # Check for env-based tool detection
        env = server_config.get("env", {})
        
        # Common MCP server patterns
        tools = []
        
        # Filesystem server
        if "filesystem" in server_name.lower():
            tools.extend([
                "read_file",
                "write_file",
                "list_directory",
                "create_directory",
                "delete_file",
                "move_file",
                "copy_file",
                "get_file_info",
            ])
        
        # Git server
        if "git" in server_name.lower():
            tools.extend([
                "git_status",
                "git_diff",
                "git_log",
                "git_commit",
                "git_push",
                "git_pull",
                "git_branch",
                "git_checkout",
            ])
        
        # Database/memory server
        if "memory" in server_name.lower() or "database" in server_name.lower():
            tools.extend([
                "store",
                "retrieve",
                "delete",
                "list",
                "query",
            ])
        
        # Web/fetch server
        if "fetch" in server_name.lower() or "web" in server_name.lower():
            tools.extend([
                "fetch",
                "http_get",
                "http_post",
            ])
        
        # Shell/exec server
        if "shell" in server_name.lower() or "exec" in server_name.lower():
            tools.extend([
                "run_command",
                "execute_shell",
            ])
        
        # If no tools detected, use server name as a tool prefix
        if not tools:
            tools.append(f"{server_name}_call")
        
        return tools
    
    def get_all_tools(self) -> list[str]:
        """
        Get all tools from all servers.
        
        Returns:
            List of all tool names (deduplicated)
        """
        all_tools = set()
        for server_name in self.get_servers():
            tools = self.get_tools_for_server(server_name)
            all_tools.update(tools)
        return sorted(all_tools)
    
    def get_tools_by_server(self) -> dict[str, list[str]]:
        """
        Get tools organized by server.
        
        Returns:
            Dictionary mapping server names to tool lists
        """
        result = {}
        for server_name in self.get_servers():
            result[server_name] = self.get_tools_for_server(server_name)
        return result
    
    def generate_policy_dict(
        self,
        *,
        policy_name: str = "mcp_generated",
        default_deny: bool = True,
        forbidden_patterns: Optional[list[str]] = None,
        escalation_patterns: Optional[list[str]] = None
    ) -> dict[str, Any]:
        """
        Generate an APE policy dictionary from MCP configuration.
        
        Args:
            policy_name: Name for the generated policy
            default_deny: Whether to enable default deny
            forbidden_patterns: Patterns for forbidden actions
            escalation_patterns: Patterns for escalation-required actions
            
        Returns:
            Policy dictionary suitable for YAML output
        """
        all_tools = self.get_all_tools()
        
        # Determine forbidden and escalation actions based on patterns
        forbidden = []
        escalation = []
        allowed = []
        
        for tool in all_tools:
            tool_lower = tool.lower()
            
            # Check forbidden patterns
            is_forbidden = False
            if forbidden_patterns:
                for pattern in forbidden_patterns:
                    if pattern.lower() in tool_lower:
                        forbidden.append(tool)
                        is_forbidden = True
                        break
            
            if is_forbidden:
                continue
            
            # Check escalation patterns
            is_escalation = False
            if escalation_patterns:
                for pattern in escalation_patterns:
                    if pattern.lower() in tool_lower:
                        escalation.append(tool)
                        is_escalation = True
                        break
            
            if is_escalation:
                continue
            
            # Default: allowed
            allowed.append(tool)
        
        # Also check common dangerous patterns
        dangerous_keywords = ["delete", "remove", "drop", "destroy", "exec", "shell"]
        for tool in allowed[:]:  # Copy to avoid modification during iteration
            tool_lower = tool.lower()
            for keyword in dangerous_keywords:
                if keyword in tool_lower:
                    allowed.remove(tool)
                    escalation.append(tool)
                    break
        
        policy = {
            "name": policy_name,
            "version": "1.0.0",
            "description": f"Auto-generated policy from MCP configuration: {self._config_path.name}",
            "default_deny": default_deny,
            "allowed_actions": sorted(allowed),
            "forbidden_actions": sorted(forbidden),
            "escalation_required": sorted(escalation),
            "metadata": {
                "source": str(self._config_path),
                "servers": self.get_servers(),
                "generated_by": "ape mcp-scan"
            }
        }
        
        return policy


def generate_policy_from_mcp(
    mcp_config_path: str,
    policy_name: str = "mcp_generated",
    default_deny: bool = True,
    forbidden_patterns: Optional[list[str]] = None,
    escalation_patterns: Optional[list[str]] = None
) -> dict[str, Any]:
    """
    Generate an APE policy from an MCP configuration file.
    
    This is a convenience function that creates a scanner and
    generates the policy in one step.
    
    Args:
        mcp_config_path: Path to MCP configuration JSON
        policy_name: Name for the generated policy
        default_deny: Whether to enable default deny
        forbidden_patterns: Patterns for forbidden actions
        escalation_patterns: Patterns for escalation-required actions
        
    Returns:
        Policy dictionary
    """
    scanner = MCPScanner(mcp_config_path)
    return scanner.generate_policy_dict(
        policy_name=policy_name,
        default_deny=default_deny,
        forbidden_patterns=forbidden_patterns,
        escalation_patterns=escalation_patterns
    )
