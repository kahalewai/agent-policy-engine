"""
APE Runtime Orchestrator (Controller)

Per architecture spec (§7.1 Runtime Controller):
- Owns runtime state
- Enforces legal transitions
- Blocks illegal execution paths
- Failure behavior: hard reject execution with RuntimeStateError
"""

from typing import Optional, Callable, Any
from ape.runtime.state import (
    RuntimeState,
    VALID_TRANSITIONS,
    is_valid_transition,
    can_execute,
    can_issue_authority,
    is_terminal_state
)
from ape.errors import RuntimeStateError


class RuntimeOrchestrator:
    """
    The authoritative runtime controller for APE.
    
    This component owns the runtime state machine and enforces
    all state transitions. No execution-capable component may
    progress without consulting the RuntimeOrchestrator.
    
    Thread Safety: This class is NOT thread-safe. Each agent
    instance should have its own RuntimeOrchestrator.
    """
    
    def __init__(self) -> None:
        """Initialize the orchestrator in INITIALIZED state."""
        self._state: RuntimeState = RuntimeState.INITIALIZED
        self._transition_hooks: list[Callable[[RuntimeState, RuntimeState], None]] = []
        self._state_history: list[RuntimeState] = [RuntimeState.INITIALIZED]
    
    @property
    def state(self) -> RuntimeState:
        """Get the current runtime state."""
        return self._state
    
    @property
    def state_history(self) -> list[RuntimeState]:
        """Get the history of state transitions."""
        return self._state_history.copy()
    
    def transition(self, new_state: RuntimeState) -> None:
        """
        Transition to a new state.
        
        Per architecture spec (§8.2):
        Illegal transitions are security violations, not warnings.
        
        Args:
            new_state: The target state
            
        Raises:
            RuntimeStateError: If transition is illegal
        """
        if not is_valid_transition(self._state, new_state):
            raise RuntimeStateError(self._state.value, new_state.value)
        
        old_state = self._state
        self._state = new_state
        self._state_history.append(new_state)
        
        # Invoke transition hooks
        for hook in self._transition_hooks:
            hook(old_state, new_state)
    
    def assert_state(self, expected: RuntimeState) -> None:
        """
        Assert the runtime is in an expected state.
        
        Args:
            expected: The expected state
            
        Raises:
            RuntimeStateError: If not in expected state
        """
        if self._state != expected:
            raise RuntimeStateError(self._state.value, expected.value)
    
    def assert_executing(self) -> None:
        """
        Assert the runtime is in EXECUTING state.
        
        Per architecture spec: Execution must not proceed unless
        state is EXECUTING.
        
        Raises:
            RuntimeStateError: If not in EXECUTING state
        """
        if not can_execute(self._state):
            raise RuntimeStateError(
                self._state.value,
                RuntimeState.EXECUTING.value
            )
    
    def assert_can_issue_authority(self) -> None:
        """
        Assert that authority tokens can be issued.
        
        Per architecture spec: No authority issuance during
        ESCALATION_REQUIRED.
        
        Raises:
            RuntimeStateError: If authority cannot be issued
        """
        if not can_issue_authority(self._state):
            raise RuntimeStateError(
                self._state.value,
                f"Authority issuance not allowed in {self._state.value}"
            )
    
    def is_terminated(self) -> bool:
        """Check if the runtime has terminated."""
        return is_terminal_state(self._state)
    
    def terminate(self) -> None:
        """
        Terminate the runtime.
        
        This transitions to TERMINATED state from any state
        that allows it.
        """
        self.transition(RuntimeState.TERMINATED)
    
    def reset(self) -> None:
        """
        Reset the runtime to INITIALIZED state.
        
        This is a hard reset that clears all state history.
        Use with caution - this should typically only be used
        in testing scenarios.
        """
        self._state = RuntimeState.INITIALIZED
        self._state_history = [RuntimeState.INITIALIZED]
    
    def add_transition_hook(
        self,
        hook: Callable[[RuntimeState, RuntimeState], None]
    ) -> None:
        """
        Add a hook to be called on state transitions.
        
        Hooks are called after the transition completes with
        (old_state, new_state) arguments.
        
        Args:
            hook: Callable to invoke on transitions
        """
        self._transition_hooks.append(hook)
    
    def remove_transition_hook(
        self,
        hook: Callable[[RuntimeState, RuntimeState], None]
    ) -> None:
        """
        Remove a previously added transition hook.
        
        Args:
            hook: The hook to remove
        """
        if hook in self._transition_hooks:
            self._transition_hooks.remove(hook)
    
    def get_valid_transitions(self) -> set[RuntimeState]:
        """
        Get valid transitions from current state.
        
        Returns:
            Set of states that can be transitioned to
        """
        return VALID_TRANSITIONS.get(self._state, set()).copy()
    
    def __repr__(self) -> str:
        return f"RuntimeOrchestrator(state={self._state.value})"
