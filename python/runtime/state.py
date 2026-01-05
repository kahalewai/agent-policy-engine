"""
APE Runtime State Machine

- Valid states: INITIALIZED, INTENT_SET, PLAN_APPROVED, EXECUTING, ESCALATION_REQUIRED, TERMINATED
- Illegal transitions are rejected as security violations
- Execution requires EXECUTING state
- Escalation pauses authority issuance
"""

from enum import Enum


class RuntimeState(str, Enum):
    """
    Valid runtime states for APE.
    
    State flow:
    INITIALIZED → INTENT_SET → PLAN_APPROVED → EXECUTING → TERMINATED
                                                    ↓
                                          ESCALATION_REQUIRED
                                                    ↓
                                          EXECUTING or TERMINATED
    """
    INITIALIZED = "INITIALIZED"
    INTENT_SET = "INTENT_SET"
    PLAN_APPROVED = "PLAN_APPROVED"
    EXECUTING = "EXECUTING"
    ESCALATION_REQUIRED = "ESCALATION_REQUIRED"
    TERMINATED = "TERMINATED"


# Define valid state transitions
# Key: current state, Value: set of valid next states
VALID_TRANSITIONS: dict[RuntimeState, set[RuntimeState]] = {
    RuntimeState.INITIALIZED: {RuntimeState.INTENT_SET, RuntimeState.TERMINATED},
    RuntimeState.INTENT_SET: {RuntimeState.PLAN_APPROVED, RuntimeState.INTENT_SET, RuntimeState.TERMINATED},
    RuntimeState.PLAN_APPROVED: {RuntimeState.EXECUTING, RuntimeState.TERMINATED},
    RuntimeState.EXECUTING: {RuntimeState.EXECUTING, RuntimeState.ESCALATION_REQUIRED, RuntimeState.TERMINATED},
    RuntimeState.ESCALATION_REQUIRED: {RuntimeState.EXECUTING, RuntimeState.TERMINATED},
    RuntimeState.TERMINATED: set(),  # Terminal state, no transitions allowed
}


def is_valid_transition(current: RuntimeState, target: RuntimeState) -> bool:
    """
    Check if a state transition is valid.
    
    Args:
        current: Current runtime state
        target: Target runtime state
        
    Returns:
        True if transition is valid, False otherwise
    """
    return target in VALID_TRANSITIONS.get(current, set())


def get_valid_transitions(state: RuntimeState) -> set[RuntimeState]:
    """
    Get all valid transitions from a given state.
    
    Args:
        state: Current runtime state
        
    Returns:
        Set of valid target states
    """
    return VALID_TRANSITIONS.get(state, set()).copy()


def is_terminal_state(state: RuntimeState) -> bool:
    """
    Check if a state is terminal (no further transitions possible).
    
    Args:
        state: Runtime state to check
        
    Returns:
        True if state is terminal
    """
    return state == RuntimeState.TERMINATED


def can_execute(state: RuntimeState) -> bool:
    """
    Check if execution is allowed in the current state.
    
    Per architecture spec: Execution must not proceed unless state is EXECUTING.
    
    Args:
        state: Current runtime state
        
    Returns:
        True if execution is allowed
    """
    return state == RuntimeState.EXECUTING


def can_issue_authority(state: RuntimeState) -> bool:
    """
    Check if authority tokens can be issued in the current state.
    
    Per architecture spec: No authority issuance during ESCALATION_REQUIRED.
    
    Args:
        state: Current runtime state
        
    Returns:
        True if authority can be issued
    """
    return state == RuntimeState.EXECUTING
