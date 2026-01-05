# Agent Policy Engine (APE) - Implementation Guide

**Version 1.0.0**

This guide explains how to install, configure, integrate, and troubleshoot the Agent Policy Engine (APE) in your AI agent applications.

<br>

## Table of Contents

1. [Installation](#installation)
2. [Core Concepts](#core-concepts)
3. [Quick Start](#quick-start)
4. [Policy Configuration](#policy-configuration)
5. [Integration Patterns](#integration-patterns)
6. [CLI Reference](#cli-reference)
7. [MCP Integration](#mcp-integration)
8. [Troubleshooting](#troubleshooting)
9. [Security Checklist](#security-checklist)
10. [API Reference](#api-reference)

<br>

## Installation

### Requirements

- Python 3.10 or higher
- No external services required
- No network dependencies at runtime

### Install from Source

```bash
git clone https://github.com/kahalewai/agent-policy-engine/python.git
cd python
pip install -e .
```

### Install with Development Dependencies

```bash
pip install -e ".[dev]"
```

### Verify Installation

```bash
# Check CLI is available
ape --version

# Validate included policies
ape validate policies/minimal_safe.yaml
```

<br>

## Core Concepts

### The APE Execution Model

```
User Input
    ↓
Intent Construction (what the user wants)
    ↓
APE Runtime Controller (state machine)
    ↓
LLM Reasoning (agent proposes plan)
    ↓
Plan Proposal
    ↓
APE Plan Validation (validates against intent)
    ↓
APE Policy Evaluation (ALLOW/DENY/ESCALATE)
    ↓
APE Authority Issuance (single-use token)
    ↓
APE Enforcement Gate (validates and executes)
    ↓
Tool Execution
```

### Key Principles

| Principle | Description |
|-----------|-------------|
| **Default Deny** | Actions not explicitly allowed are denied |
| **Capability-Based Authority** | AuthorityTokens are the only way to execute |
| **Single-Use Tokens** | Each token can only be used once |
| **Immutable Plans** | Plans cannot be modified after approval |
| **Provenance Tracking** | All data is labeled with trust level |


<br>

### Runtime States

```
INITIALIZED → INTENT_SET → PLAN_APPROVED → EXECUTING → TERMINATED
                                              ↓
                                    ESCALATION_REQUIRED
                                              ↓
                                    EXECUTING or TERMINATED
```

<br>

## Quick Start

### 1. Create a Policy File

```yaml
# my_policy.yaml
name: my_agent_policy
version: "1.0.0"
default_deny: true

allowed_actions:
  - read_file
  - list_directory
  - query_data

forbidden_actions:
  - delete_file
  - drop_database

escalation_required:
  - write_file
  - send_email
```

### 2. Basic Policy Evaluation

```python
from ape import PolicyEngine

# Load policy
policy = PolicyEngine("my_policy.yaml")

# Evaluate actions
result = policy.evaluate("read_file")
if result.is_allowed():
    print("Action allowed")

result = policy.evaluate("delete_file")
if result.is_denied():
    print("Action denied")
```

### 3. Full Agent Integration

```python
from ape import (
    RuntimeOrchestrator,
    IntentManager,
    PlanManager,
    PolicyEngine,
    AuthorityManager,
    EnforcementGate,
    RuntimeConfig,
    RuntimeState,
    Action,
    Provenance,
    EnforcementMode,
)

# Define your tools
def read_file(path: str) -> str:
    with open(path) as f:
        return f.read()

TOOLS = {"file_reader": read_file}

# Initialize APE components
runtime = RuntimeOrchestrator()
intent_manager = IntentManager()
plan_manager = PlanManager(intent_manager)
policy = PolicyEngine("my_policy.yaml")
config = RuntimeConfig(enforcement_mode=EnforcementMode.ENFORCE)
authority = AuthorityManager(runtime, token_ttl_seconds=60)
enforcement = EnforcementGate(authority, config)

# Step 1: Set Intent (from trusted user input)
intent_manager.set({
    "allowed_actions": ["read_file"],
    "forbidden_actions": [],
    "scope": "read_operations"
}, Provenance.USER_TRUSTED)
runtime.transition(RuntimeState.INTENT_SET)

# Step 2: Submit Plan
plan_manager.submit({
    "steps": [
        {
            "action_id": "read_file",
            "tool_id": "file_reader",
            "parameters": {"path": "config.txt"}
        }
    ]
}, Provenance.USER_TRUSTED)

# Step 3: Approve Plan
plan_manager.approve()
runtime.transition(RuntimeState.PLAN_APPROVED)

# Step 4: Execute Plan
runtime.transition(RuntimeState.EXECUTING)

for idx, step in enumerate(plan_manager.plan):
    # Create action
    action = Action(
        action_id=step.action_id,
        tool_id=step.tool_id,
        parameters=step.parameters,
        intent_version=intent_manager.version,
        plan_hash=plan_manager.hash,
        plan_step_index=idx
    )
    
    # Evaluate policy
    policy.evaluate_or_raise(action.action_id)
    
    # Get authority token
    token = authority.issue(
        intent_version=intent_manager.version,
        plan_hash=plan_manager.hash,
        action=action
    )
    
    # Execute through enforcement gate
    tool = TOOLS[action.tool_id]
    result = enforcement.execute(token, tool, action, **action.parameters)
    print(f"Result: {result}")

runtime.transition(RuntimeState.TERMINATED)
```

<br>

## Policy Configuration

### Policy Schema

```yaml
# Required fields
allowed_actions: []      # Actions explicitly allowed
forbidden_actions: []    # Actions explicitly forbidden

# Optional fields
name: string             # Human-readable name
version: string          # Policy version
description: string      # Description
default_deny: boolean    # Deny unlisted actions (default: true)
escalation_required: []  # Actions requiring escalation
tool_transitions: {}     # Allowed tool sequences
metadata: {}             # Custom metadata
```

<br>

### Policy Evaluation Precedence

1. **forbidden_actions** → DENY (highest priority)
2. **escalation_required** → ESCALATE
3. **allowed_actions** → ALLOW
4. **default_deny** → DENY (if true) or ALLOW (if false)

<br>

### Example Policies

#### Minimal Safe (Recommended Starting Point)

```yaml
name: minimal_safe
default_deny: true

allowed_actions:
  - read_file
  - list_directory
  - query_data

forbidden_actions:
  - delete_file
  - rm_rf

escalation_required:
  - write_file
  - create_directory
```

#### Read-Only

```yaml
name: read_only
default_deny: true

allowed_actions:
  - read_file
  - list_directory
  - get_status
  - query_data

forbidden_actions:
  - write_file
  - delete_file
  - update_data
  - insert_data
```

<br>

## Integration Patterns

### Pattern 1: Tool Wrapping (Recommended)

**Never expose tools directly to the agent. Always wrap them.**

```python
# WRONG - Agent can bypass APE
tools = {
    "read_file": read_file,
    "write_file": write_file
}

# CORRECT - All tools wrapped
def execute_action(action_id, token, **params):
    return enforcement.execute(
        token=token,
        tool=TOOLS[action_id],
        action=action,
        **params
    )
```

### Pattern 2: Central Action Dispatcher

```python
class ActionExecutor:
    def __init__(self, policy, authority, enforcement):
        self.policy = policy
        self.authority = authority
        self.enforcement = enforcement
    
    def run(self, intent_version, plan_hash, step, action_id, tool, **kwargs):
        # 1. Evaluate policy
        self.policy.evaluate_or_raise(action_id)
        
        # 2. Issue authority token
        action = Action(
            action_id=action_id,
            tool_id=tool.__name__,
            parameters=kwargs,
            intent_version=intent_version,
            plan_hash=plan_hash,
            plan_step_index=step
        )
        token = self.authority.issue(
            intent_version=intent_version,
            plan_hash=plan_hash,
            action=action
        )
        
        # 3. Execute through enforcement gate
        return self.enforcement.execute(token, tool, action, **kwargs)
```

### Pattern 3: LangChain Integration

```python
from langchain.agents import Tool, initialize_agent

# Create APE-protected tools
def ape_protected_tool(action_id: str, original_func):
    def wrapper(**kwargs):
        action = create_action(action_id, kwargs)
        policy.evaluate_or_raise(action_id)
        token = authority.issue(...)
        return enforcement.execute(token, original_func, action, **kwargs)
    return wrapper

# Wrap all tools
protected_tools = [
    Tool(
        name="ReadFile",
        func=ape_protected_tool("read_file", read_file),
        description="Reads a file safely"
    )
]

agent = initialize_agent(protected_tools, llm)
```

<br>

## CLI Reference

### Commands

```bash
# Validate a policy file
ape validate <policy_file>

# Simulate policy evaluation
ape simulate <policy_file> <action_id>

# Batch simulation
ape simulate-batch <policy_file> action1 action2 action3
ape simulate-batch <policy_file> --file actions.txt --json

# Show policy information
ape info <policy_file>
ape info <policy_file> --json

# MCP configuration scanning
ape mcp-scan <mcp_config.json> -o output_policy.yaml
ape mcp-info <mcp_config.json>

# Version
ape --version
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Policy error |
| 3 | Validation error |
| 4 | File not found |

<br>

## MCP Integration

APE can scan MCP (Model Context Protocol) configurations and automatically generate matching policies. This allows you to easily create APE policies to match your MCP server configuration. 

<br>

### Scan MCP Configuration

```bash
# Generate policy from MCP config
ape mcp-scan mcp_config.json -o my_policy.yaml

# Preview without saving
ape mcp-scan mcp_config.json

# Show MCP tools
ape mcp-info mcp_config.json
```
<br>

### Programmatic Usage

```python
from ape import MCPScanner, generate_policy_from_mcp

# Generate policy
policy_data = generate_policy_from_mcp(
    "mcp_config.json",
    policy_name="mcp_generated",
    default_deny=True
)

# Save to file
import yaml
with open("generated_policy.yaml", "w") as f:
    yaml.dump(policy_data, f)
```

<br>

## Troubleshooting

### Common Errors

<br>

#### PolicyDenyError

```
PolicyDenyError: Action denied by policy
```

**Cause**: The action is not in `allowed_actions` or is in `forbidden_actions`.

**Solution**: Add the action to `allowed_actions` in your policy, or check if it's incorrectly forbidden.

<br>

#### EscalationRequiredError

```
EscalationRequiredError: Action requires escalation
```

**Cause**: The action is in `escalation_required`.

**Solution**: In v1.0, escalation must be handled by your application. Either:
1. Remove from `escalation_required` and add to `allowed_actions`
2. Implement escalation handling in your application

<br>

#### RuntimeStateError

```
RuntimeStateError: Illegal state transition: INITIALIZED → EXECUTING
```

**Cause**: Attempting to execute without going through required states.

**Solution**: Follow the state machine:
```python
runtime.transition(RuntimeState.INTENT_SET)    # After setting intent
runtime.transition(RuntimeState.PLAN_APPROVED)  # After approving plan
runtime.transition(RuntimeState.EXECUTING)      # Before executing
```

<br>

#### UnauthorizedActionError

```
UnauthorizedActionError: Missing authority token
```

**Cause**: Attempting to execute without a valid token.

**Solution**: Always obtain a token before execution:
```python
token = authority.issue(
    intent_version=intent_manager.version,
    plan_hash=plan_manager.hash,
    action=action
)
result = enforcement.execute(token, tool, action, **params)
```

<br>

#### ProvenanceError

```
ProvenanceError: EXTERNAL_UNTRUSTED provenance cannot grant authority
```

**Cause**: Attempting to set intent or plan with untrusted data.

**Solution**: Only use `Provenance.USER_TRUSTED` or `Provenance.SYSTEM_TRUSTED`:
```python
intent_manager.set(data, Provenance.USER_TRUSTED)
```

<br>

### Debug Mode

```python
from ape import AuditLogger

# Enable verbose audit logging
audit = AuditLogger(
    enabled=True,
    store_events=True  # Keep events in memory for debugging
)

# After execution, inspect events
for event in audit.events:
    print(f"{event.event_type}: {event.to_json()}")
```

<br>

## Security Checklist

Before deploying an agent using APE, verify:

- [ ] No tool is callable outside `EnforcementGate`
- [ ] All actions require `AuthorityToken`
- [ ] Authority tokens are single-use
- [ ] Policies are `default_deny: true`
- [ ] Escalation paths are handled (or actions moved to allowed/forbidden)
- [ ] No tool references exist in LLM prompts
- [ ] Runtime state machine is enforced
- [ ] All intent/plan data uses trusted provenance

<br>

### Inline Enforcement Requirement

**APE must be inline with execution.** This means:

- APE runs in the same process as the agent
- All tool execution passes through `EnforcementGate`
- No tool may be called directly
- No authority may be cached or reused
- No bypass paths may exist

**Non-compliant architectures** (APE does NOT protect):

- Tools called directly
- Tools passed into the LLM
- APE used only for logging
- Enforcement that's optional
- Authority tokens that are reused or serialized

<br>

## API Reference

### Core Classes

#### PolicyEngine

```python
class PolicyEngine:
    def __init__(self, policy_path: str = None)
    def load(self, path: str) -> str  # Returns policy hash
    def evaluate(self, action_id: str) -> PolicyEvaluationResult
    def evaluate_or_raise(self, action_id: str) -> PolicyDecision
    def simulate(self, action_ids: list[str]) -> list[PolicyEvaluationResult]
```

#### RuntimeOrchestrator

```python
class RuntimeOrchestrator:
    def transition(self, new_state: RuntimeState) -> None
    def assert_executing(self) -> None
    def assert_can_issue_authority(self) -> None
```

#### IntentManager

```python
class IntentManager:
    def set(self, intent_data: dict, provenance: Provenance) -> str  # Returns version hash
    def clear(self) -> None
```

#### PlanManager

```python
class PlanManager:
    def submit(self, plan_data: dict, provenance: Provenance) -> str  # Returns plan hash
    def approve(self) -> None
    def validate_against_intent(self) -> list[str]
```

#### AuthorityManager

```python
class AuthorityManager:
    def issue(self, *, intent_version: str, plan_hash: str, action: Action) -> AuthorityToken
    def consume(self, token: AuthorityToken) -> None
    def revoke_all(self) -> int
```

#### EnforcementGate

```python
class EnforcementGate:
    def execute(self, token: AuthorityToken, tool: Callable, action: Action = None, **kwargs) -> Any
```

### Enums

```python
class RuntimeState(Enum):
    INITIALIZED = "INITIALIZED"
    INTENT_SET = "INTENT_SET"
    PLAN_APPROVED = "PLAN_APPROVED"
    EXECUTING = "EXECUTING"
    ESCALATION_REQUIRED = "ESCALATION_REQUIRED"
    TERMINATED = "TERMINATED"

class PolicyDecision(Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    ESCALATE = "ESCALATE"

class Provenance(Enum):
    SYSTEM_TRUSTED = "SYSTEM_TRUSTED"
    USER_TRUSTED = "USER_TRUSTED"
    EXTERNAL_UNTRUSTED = "EXTERNAL_UNTRUSTED"

class EnforcementMode(Enum):
    DISABLED = "disabled"
    OBSERVE = "observe"
    ENFORCE = "enforce"
```

<br>

## Version History

v1.0.0

- Initial release
- Core policy enforcement
- Runtime state machine
- Authority token lifecycle
- Provenance tracking
- MCP configuration scanning
- 5 example policies
- CLI tools

Future (v2.0+)

- Full escalation resolver implementation
- Async escalation support
- Risk-based escalation
- Pre-approval capability leasing

<br>
<br>
<br>
<br>
<br>
<br>
<p align="center">
▁ ▂ ▄ ▅ ▆ ▇ █   Built with Aloha by Kahalewai - 2026  █ ▇ ▆ ▅ ▄ ▂ ▁
</p>
<br>

