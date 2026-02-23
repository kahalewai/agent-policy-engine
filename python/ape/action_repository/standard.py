"""
APE Standard Action Definitions

This module provides a standard set of commonly-used action definitions
that most agents will need. Applications can use these as a baseline
and extend with custom actions.

The standard actions cover:
- File operations (read, write, delete)
- Network operations (HTTP requests)
- Database operations (query, insert, update, delete)
- Communication (email, notifications)
- Compute (code execution, shell commands)

Usage:
    from ape.action_repository import create_standard_repository
    
    repository = create_standard_repository()
    # Add custom actions if needed
    repository.register(my_custom_action)
    repository.freeze()
"""

from ape.action_repository.repository import (
    ActionRepository,
    ActionDefinition,
    ActionCategory,
    ActionRiskLevel,
)


def create_standard_repository() -> ActionRepository:
    """
    Create an Action Repository with standard, commonly-used actions.
    
    This provides a baseline set of actions that most agents will need.
    Applications can extend this with custom actions before freezing.
    
    Returns:
        ActionRepository with standard actions (not frozen)
    """
    repository = ActionRepository()
    
    # =========================================================================
    # File Read Actions
    # =========================================================================
    
    repository.register(ActionDefinition(
        action_id="read_file",
        description="Read the contents of a single file",
        category=ActionCategory.FILE_READ,
        risk_level=ActionRiskLevel.MINIMAL,
        parameter_schema={
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read",
                    "minLength": 1,
                },
                "encoding": {
                    "type": "string",
                    "description": "File encoding (default: utf-8)",
                    "default": "utf-8",
                },
            },
            "additionalProperties": False,
        },
        max_scope_breadth="single_file",
        tags=["filesystem", "read"],
        examples=[
            {"path": "config.json"},
            {"path": "/etc/hosts", "encoding": "ascii"},
        ],
    ))
    
    repository.register(ActionDefinition(
        action_id="list_directory",
        description="List contents of a directory",
        category=ActionCategory.FILE_READ,
        risk_level=ActionRiskLevel.MINIMAL,
        parameter_schema={
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the directory",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "List recursively",
                    "default": False,
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum recursion depth",
                    "minimum": 1,
                    "default": 3,
                },
            },
            "additionalProperties": False,
        },
        max_scope_breadth="directory",
        tags=["filesystem", "read"],
    ))
    
    repository.register(ActionDefinition(
        action_id="search_files",
        description="Search for files matching a pattern",
        category=ActionCategory.FILE_READ,
        risk_level=ActionRiskLevel.LOW,
        parameter_schema={
            "type": "object",
            "required": ["pattern"],
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g., '*.py')",
                },
                "directory": {
                    "type": "string",
                    "description": "Root directory to search",
                    "default": ".",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "minimum": 1,
                    "maximum": 1000,
                    "default": 100,
                },
            },
            "additionalProperties": False,
        },
        max_scope_breadth="directory",
        tags=["filesystem", "read", "search"],
    ))
    
    # =========================================================================
    # File Write Actions
    # =========================================================================
    
    repository.register(ActionDefinition(
        action_id="write_file",
        description="Write content to a file (creates or overwrites)",
        category=ActionCategory.FILE_WRITE,
        risk_level=ActionRiskLevel.MODERATE,
        parameter_schema={
            "type": "object",
            "required": ["path", "content"],
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write",
                },
                "encoding": {
                    "type": "string",
                    "default": "utf-8",
                },
                "create_directories": {
                    "type": "boolean",
                    "description": "Create parent directories if needed",
                    "default": False,
                },
            },
            "additionalProperties": False,
        },
        requires_human_review=False,
        max_scope_breadth="single_file",
        tags=["filesystem", "write"],
    ))
    
    repository.register(ActionDefinition(
        action_id="append_file",
        description="Append content to an existing file",
        category=ActionCategory.FILE_WRITE,
        risk_level=ActionRiskLevel.LOW,
        parameter_schema={
            "type": "object",
            "required": ["path", "content"],
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "additionalProperties": False,
        },
        max_scope_breadth="single_file",
        tags=["filesystem", "write"],
    ))
    
    repository.register(ActionDefinition(
        action_id="create_directory",
        description="Create a new directory",
        category=ActionCategory.FILE_WRITE,
        risk_level=ActionRiskLevel.LOW,
        parameter_schema={
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {"type": "string"},
                "parents": {
                    "type": "boolean",
                    "description": "Create parent directories",
                    "default": True,
                },
            },
            "additionalProperties": False,
        },
        max_scope_breadth="directory",
        tags=["filesystem", "write"],
    ))
    
    # =========================================================================
    # File Delete Actions
    # =========================================================================
    
    repository.register(ActionDefinition(
        action_id="delete_file",
        description="Delete a single file",
        category=ActionCategory.FILE_DELETE,
        risk_level=ActionRiskLevel.HIGH,
        parameter_schema={
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {"type": "string"},
            },
            "additionalProperties": False,
        },
        requires_human_review=True,
        max_scope_breadth="single_file",
        tags=["filesystem", "delete", "destructive"],
    ))
    
    repository.register(ActionDefinition(
        action_id="delete_directory",
        description="Delete a directory and all its contents",
        category=ActionCategory.FILE_DELETE,
        risk_level=ActionRiskLevel.CRITICAL,
        parameter_schema={
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {"type": "string"},
                "recursive": {
                    "type": "boolean",
                    "description": "Delete contents recursively",
                    "default": False,
                },
            },
            "additionalProperties": False,
        },
        requires_human_review=True,
        max_scope_breadth="directory",
        tags=["filesystem", "delete", "destructive"],
    ))
    
    # =========================================================================
    # Network Actions
    # =========================================================================
    
    repository.register(ActionDefinition(
        action_id="http_get",
        description="Make an HTTP GET request",
        category=ActionCategory.NETWORK,
        risk_level=ActionRiskLevel.LOW,
        parameter_schema={
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {
                    "type": "string",
                    "format": "uri",
                },
                "headers": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
                "timeout": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 300,
                    "default": 30,
                },
            },
            "additionalProperties": False,
        },
        tags=["network", "http", "read"],
    ))
    
    repository.register(ActionDefinition(
        action_id="http_post",
        description="Make an HTTP POST request",
        category=ActionCategory.NETWORK,
        risk_level=ActionRiskLevel.MODERATE,
        parameter_schema={
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {"type": "string", "format": "uri"},
                "body": {"type": "string"},
                "json": {"type": "object"},
                "headers": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
                "timeout": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 300,
                    "default": 30,
                },
            },
            "additionalProperties": False,
        },
        tags=["network", "http", "write"],
    ))
    
    # =========================================================================
    # Database Actions
    # =========================================================================
    
    repository.register(ActionDefinition(
        action_id="query_data",
        description="Execute a read-only database query",
        category=ActionCategory.DATABASE_READ,
        risk_level=ActionRiskLevel.LOW,
        parameter_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The query to execute",
                },
                "parameters": {
                    "type": "array",
                    "description": "Query parameters",
                    "items": {},
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10000,
                    "default": 1000,
                },
            },
            "additionalProperties": False,
        },
        tags=["database", "read"],
        constraints={
            "query_must_be_select": True,
        },
    ))
    
    repository.register(ActionDefinition(
        action_id="insert_data",
        description="Insert data into a database",
        category=ActionCategory.DATABASE_WRITE,
        risk_level=ActionRiskLevel.MODERATE,
        parameter_schema={
            "type": "object",
            "required": ["table", "data"],
            "properties": {
                "table": {"type": "string"},
                "data": {
                    "type": "object",
                    "description": "Key-value pairs to insert",
                },
            },
            "additionalProperties": False,
        },
        tags=["database", "write"],
    ))
    
    repository.register(ActionDefinition(
        action_id="update_data",
        description="Update existing database records",
        category=ActionCategory.DATABASE_WRITE,
        risk_level=ActionRiskLevel.MODERATE,
        parameter_schema={
            "type": "object",
            "required": ["table", "data", "where"],
            "properties": {
                "table": {"type": "string"},
                "data": {"type": "object"},
                "where": {
                    "type": "object",
                    "description": "Conditions to match",
                },
            },
            "additionalProperties": False,
        },
        tags=["database", "write"],
    ))
    
    repository.register(ActionDefinition(
        action_id="delete_data",
        description="Delete database records",
        category=ActionCategory.DATABASE_WRITE,
        risk_level=ActionRiskLevel.HIGH,
        parameter_schema={
            "type": "object",
            "required": ["table", "where"],
            "properties": {
                "table": {"type": "string"},
                "where": {
                    "type": "object",
                    "description": "Conditions to match",
                    "minProperties": 1,
                },
            },
            "additionalProperties": False,
        },
        requires_human_review=True,
        tags=["database", "delete", "destructive"],
    ))
    
    # =========================================================================
    # Communication Actions
    # =========================================================================
    
    repository.register(ActionDefinition(
        action_id="send_email",
        description="Send an email message",
        category=ActionCategory.COMMUNICATION,
        risk_level=ActionRiskLevel.MODERATE,
        parameter_schema={
            "type": "object",
            "required": ["to", "subject", "body"],
            "properties": {
                "to": {
                    "type": "array",
                    "items": {"type": "string", "format": "email"},
                    "minItems": 1,
                },
                "cc": {
                    "type": "array",
                    "items": {"type": "string", "format": "email"},
                },
                "subject": {"type": "string", "maxLength": 998},
                "body": {"type": "string"},
                "html": {"type": "boolean", "default": False},
            },
            "additionalProperties": False,
        },
        requires_human_review=True,
        tags=["communication", "email"],
    ))
    
    repository.register(ActionDefinition(
        action_id="send_notification",
        description="Send a notification (e.g., Slack, webhook)",
        category=ActionCategory.COMMUNICATION,
        risk_level=ActionRiskLevel.LOW,
        parameter_schema={
            "type": "object",
            "required": ["channel", "message"],
            "properties": {
                "channel": {"type": "string"},
                "message": {"type": "string", "maxLength": 4000},
            },
            "additionalProperties": False,
        },
        tags=["communication", "notification"],
    ))
    
    # =========================================================================
    # Compute Actions
    # =========================================================================
    
    repository.register(ActionDefinition(
        action_id="execute_code",
        description="Execute code in a sandboxed environment",
        category=ActionCategory.COMPUTE,
        risk_level=ActionRiskLevel.HIGH,
        parameter_schema={
            "type": "object",
            "required": ["language", "code"],
            "properties": {
                "language": {
                    "type": "string",
                    "enum": ["python", "javascript", "bash"],
                },
                "code": {"type": "string"},
                "timeout": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 300,
                    "default": 60,
                },
            },
            "additionalProperties": False,
        },
        requires_human_review=True,
        tags=["compute", "execute"],
    ))
    
    repository.register(ActionDefinition(
        action_id="run_shell_command",
        description="Execute a shell command",
        category=ActionCategory.SYSTEM,
        risk_level=ActionRiskLevel.CRITICAL,
        parameter_schema={
            "type": "object",
            "required": ["command"],
            "properties": {
                "command": {"type": "string"},
                "working_directory": {"type": "string"},
                "timeout": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 3600,
                    "default": 60,
                },
                "capture_output": {
                    "type": "boolean",
                    "default": True,
                },
            },
            "additionalProperties": False,
        },
        requires_human_review=True,
        tags=["system", "shell", "execute"],
    ))
    
    return repository


# Convenience function for backward compatibility
def get_standard_actions() -> list[ActionDefinition]:
    """
    Get a list of all standard action definitions.
    
    Returns:
        List of ActionDefinition objects
    """
    repository = create_standard_repository()
    return [repository.get(aid) for aid in repository.action_ids]
