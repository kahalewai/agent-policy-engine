"""
APE Enforcement Gate

Per architecture spec (§7.7 Enforcement Gate):
- Intercepts all tool calls
- Requires valid AuthorityToken
- Executes or blocks
- Emits audit events or logs
- Failure behavior: block execution

Per architecture spec (§5.5.5 Mandatory Enforcement Contract):
- No tool execution may occur without a valid AuthorityToken
- The Enforcement Gate must require an AuthorityToken for every tool invocation
- Must validate token authenticity
- Must verify token matches the action
- Must verify token is unexpired and unconsumed
- Must reject execution if any check fails
"""

from typing import Any, Callable, Optional
from dataclasses import dataclass

from ape.errors import UnauthorizedActionError
from ape.config import RuntimeConfig, EnforcementMode
from ape.authority.manager import AuthorityManager, AuthorityToken
from ape.action.action import Action
from ape.audit.logger import AuditLogger


@dataclass
class ExecutionResult:
    """Result of an enforcement gate execution."""
    success: bool
    result: Any
    action_id: str
    token_id: Optional[str]
    error: Optional[str] = None


class EnforcementGate:
    """
    Enforcement gate that intercepts all tool calls.
    
    This is the ONLY allowed path for tool execution.
    Per architecture spec: No tool execution may occur without
    a valid AuthorityToken.
    
    The enforcement gate supports three modes:
    - DISABLED: Tools execute directly (development only)
    - OBSERVE: Policy evaluated and logged, execution proceeds
    - ENFORCE: Full enforcement, execution blocked without authority
    """
    
    def __init__(
        self,
        authority: AuthorityManager,
        config: RuntimeConfig,
        audit_logger: Optional[AuditLogger] = None
    ) -> None:
        """
        Initialize the enforcement gate.
        
        Args:
            authority: The authority manager for token validation
            config: Runtime configuration
            audit_logger: Optional audit logger
        """
        self._authority = authority
        self._config = config
        self._audit = audit_logger or AuditLogger()
        self._execution_count = 0
        self._blocked_count = 0
    
    @property
    def execution_count(self) -> int:
        """Get count of successful executions."""
        return self._execution_count
    
    @property
    def blocked_count(self) -> int:
        """Get count of blocked executions."""
        return self._blocked_count
    
    def execute(
        self,
        token: Optional[AuthorityToken],
        tool: Callable[..., Any],
        action: Optional[Action] = None,
        **kwargs: Any
    ) -> Any:
        """
        Execute a tool through the enforcement gate.
        
        Per architecture spec:
        - Requires valid AuthorityToken
        - Validates token authenticity
        - Verifies token matches action
        - Verifies token is unexpired and unconsumed
        - Rejects execution if any check fails
        
        Args:
            token: The authority token (required in enforce mode)
            tool: The tool function to execute
            action: Optional action object for validation
            **kwargs: Arguments to pass to the tool
            
        Returns:
            Tool execution result
            
        Raises:
            UnauthorizedActionError: If enforcement fails
        """
        action_id = action.action_id if action else "unknown"
        
        # DISABLED mode: execute directly
        if self._config.enforcement_mode == EnforcementMode.DISABLED:
            if self._config.audit_enabled:
                self._audit.log_execution(action_id, "disabled_mode", True)
            result = tool(**kwargs)
            self._execution_count += 1
            return result
        
        # OBSERVE mode: log but proceed regardless
        if self._config.enforcement_mode == EnforcementMode.OBSERVE:
            if token is None:
                self._audit.log_warning(
                    f"No token provided for action {action_id} (observe mode)"
                )
            else:
                self._audit.log_execution(action_id, token.token_id, True)
            result = tool(**kwargs)
            self._execution_count += 1
            return result
        
        # ENFORCE mode: full enforcement
        if token is None:
            self._blocked_count += 1
            self._audit.log_denied(action_id, "missing_token")
            raise UnauthorizedActionError(
                f"Missing authority token for action: {action_id}"
            )
        
        # Validate and consume the token
        try:
            if action is not None:
                self._authority.validate(token, action)
            self._authority.consume(token)
        except Exception as e:
            self._blocked_count += 1
            self._audit.log_denied(action_id, str(e))
            raise UnauthorizedActionError(f"Token validation failed: {e}")
        
        # Execute the tool
        try:
            result = tool(**kwargs)
            self._execution_count += 1
            self._audit.log_execution(action_id, token.token_id, True)
            return result
        except Exception as e:
            self._audit.log_execution(action_id, token.token_id, False, str(e))
            raise
    
    def execute_with_result(
        self,
        token: Optional[AuthorityToken],
        tool: Callable[..., Any],
        action: Optional[Action] = None,
        **kwargs: Any
    ) -> ExecutionResult:
        """
        Execute a tool and return a structured result.
        
        This method catches exceptions and returns them in the result
        instead of raising them.
        
        Args:
            token: The authority token
            tool: The tool function to execute
            action: Optional action object for validation
            **kwargs: Arguments to pass to the tool
            
        Returns:
            ExecutionResult with success status and any error
        """
        action_id = action.action_id if action else "unknown"
        token_id = token.token_id if token else None
        
        try:
            result = self.execute(token, tool, action, **kwargs)
            return ExecutionResult(
                success=True,
                result=result,
                action_id=action_id,
                token_id=token_id
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                result=None,
                action_id=action_id,
                token_id=token_id,
                error=str(e)
            )
    
    def can_execute(self, token: Optional[AuthorityToken]) -> bool:
        """
        Check if execution would be allowed (without executing).
        
        Args:
            token: The authority token to check
            
        Returns:
            True if execution would be allowed
        """
        if self._config.enforcement_mode == EnforcementMode.DISABLED:
            return True
        
        if self._config.enforcement_mode == EnforcementMode.OBSERVE:
            return True
        
        if token is None:
            return False
        
        return token.is_valid()
    
    def get_stats(self) -> dict[str, Any]:
        """Get enforcement gate statistics."""
        return {
            "execution_count": self._execution_count,
            "blocked_count": self._blocked_count,
            "enforcement_mode": self._config.enforcement_mode.value,
        }
    
    def __repr__(self) -> str:
        return (
            f"EnforcementGate(mode={self._config.enforcement_mode.value}, "
            f"executed={self._execution_count}, blocked={self._blocked_count})"
        )
