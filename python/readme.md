# APE Implementation Guide

<br>

This guide provides step-by-step instructions for integrating APE (Agent Policy Engine) into your AI agent system. APE offers two integration paths:

<br>

1. **Orchestrator Path** Simple API with minimal boilerplate
2. **Manual Path** Full control over every component

<br>

Choose the path that best fits your needs. Lets GOOOOOO!!

<br>

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Understanding APE Architecture](#understanding-ape-architecture)
4. [Path 1: Orchestrator Integration](#path-1-orchestrator-integration)
5. [Path 2: Manual Integration](#path-2-manual-integration)
6. [Policy Configuration](#policy-configuration)
7. [Parameterized Conditions](#parameterized-conditions)
8. [Action Repository](#action-repository)
9. [Intent Compilation](#intent-compilation)
10. [Plan Generation](#plan-generation)
11. [Session Management](#session-management)
12. [Rate Limiting](#rate-limiting)
13. [External Policy Adapters](#external-policy-adapters)
14. [Dynamic Policy Reload](#dynamic-policy-reload)
15. [Escalation Handling](#escalation-handling)
16. [Framework Integrations](#framework-integrations)
17. [CLI Reference](#cli-reference)
18. [Error Handling](#error-handling)
19. [Production Deployment](#production-deployment)
20. [Troubleshooting](#troubleshooting)

<br>

## Prerequisites

- Python 3.10 or higher
- Basic understanding of AI agent systems
- Your existing tools/functions that the agent will execute

<br>

## Installation

```bash
# From PyPI
pip install agent-policy-engine

# From source
git clone https://github.com/kahalewai/agent-policy-engine/python.git
cd ape
pip install -e .

# Verify installation
python -c "import ape; print(ape.__version__)"
```

<br>

## Understanding APE Architecture

Before implementing, understand APE's core principle:

> **"Prompts guide intent, but never are intent."**

User prompts are never executed directly. They are transformed through a validated pipeline:

```
User Prompt
    │
    ▼
┌─────────────────┐
│ Intent Compiler │  ← Extracts actions, applies policy narrowing
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Plan Generator  │  ← Creates validated execution plan
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ APE Core        │  ← Policy check, authority tokens, enforcement
│ (+ Conditions)  │  ← Parameter-level validation
│ (+ Rate Limits) │  ← Quota and velocity enforcement
└────────┬────────┘
         │
         ▼
    Tool Execution (with audit)
```

<br>

### Key Components

| Component | Purpose |
|-----------|---------|
| **ActionRepository** | Canonical registry of known actions |
| **IntentCompiler** | Transforms prompts to structured intents |
| **PlanGenerator** | Creates validated execution plans |
| **PolicyEngine** | Evaluates actions against policy rules with parameterized conditions |
| **IntentManager** | Manages intent lifecycle and versioning |
| **PlanManager** | Manages plan submission and approval |
| **AuthorityManager** | Issues single-use execution tokens |
| **EnforcementGate** | Mandatory checkpoint for tool execution |
| **SessionManager** | Multi-turn conversation continuity and cumulative tracking |
| **RateLimiter** | Global, per-action, and per-target quota enforcement |
| **APEOrchestrator** | Combines all components into unified API |

<br>

## Path 1: Orchestrator Integration

The Orchestrator path is recommended for most use cases. It handles all component wiring automatically.

### Step 1: Create a Policy File

Create `policies/my_policy.yaml`:

```yaml
name: my_agent_policy
version: "1.0"
description: "Policy for my AI agent"

default_decision: deny

rules:
  - action: read_file
    decision: allow
    
  - action: list_directory
    decision: allow
    
  - action: write_file
    decision: allow
    conditions:
      path:
        prefix: ["/tmp/", "/home/user/workspace/"]

  - action: delete_file
    decision: escalate
    
  - action: run_shell_command
    decision: deny
```

### Step 2: Create the Orchestrator

```python
from ape import APEOrchestrator

# Basic usage
orch = APEOrchestrator.from_policy("policies/my_policy.yaml")

# With rate limiting
from ape import RateLimitConfig

rate_config = RateLimitConfig.from_dict({
    "global": {"max_actions_per_minute": 60, "max_actions_per_session": 500},
    "per_action": {"http_get": {"max_per_minute": 20}},
})
orch = APEOrchestrator.from_policy(
    "policies/my_policy.yaml",
    rate_limit_config=rate_config,
)

# With external policy evaluator
from ape import OPAEvaluator

orch = APEOrchestrator.from_policy(
    "policies/my_policy.yaml",
    external_evaluator=OPAEvaluator("http://localhost:8181/v1/data/ape/allow"),
)

# With dynamic policy reload
orch = APEOrchestrator.from_policy(
    "policies/my_policy.yaml",
    source="https://policy-server.corp/ape/production",
    refresh_interval_seconds=60,
    on_update=lambda old, new: print(f"Policy updated: {old} → {new}"),
)
```

### Step 3: Implement and Register Tools

```python
import os

def read_file(path: str, encoding: str = "utf-8") -> str:
    """Read file contents."""
    with open(path, encoding=encoding) as f:
        return f.read()

def write_file(path: str, content: str) -> bool:
    """Write content to file."""
    with open(path, "w") as f:
        f.write(content)
    return True

def list_directory(path: str) -> list[str]:
    """List directory contents."""
    return os.listdir(path)

# Register all tools
orch.register_tools({
    "read_file": read_file,
    "write_file": write_file,
    "list_directory": list_directory,
})
```

### Step 4: Execute Prompts

```python
# One-call execution
result = orch.execute("Read the config.json file")

if result.success:
    print("Success!")
    print(f"Results: {result.results}")
else:
    print(f"Failed: {result.error}")

# With explicit parameters
result = orch.execute(
    prompt="Read config.json",
    parameters={"read_file": {"path": "config.json"}},
)

# Analyze without executing
analysis = orch.analyze_prompt("Delete all temp files")
print(f"Would be blocked: {analysis['policy_blocked']}")
```

### Step 5: Use Sessions for Multi-Turn Conversations

```python
# Create a session for a user
session = orch.create_session(user_id="user_123", ttl_minutes=30)

# Execute through the session — actions are tracked
result1 = session.execute("Read config.json")
result2 = session.execute("Now update it")

# Monitor session state
print(session.actions_executed)   # ["read_file", "write_file"]
print(session.cumulative_risk)    # 0.4
print(session.tokens_issued)      # 2
print(session.time_remaining)     # 1740 seconds
print(session.is_active)          # True

# Get full usage summary
summary = session.get_usage_summary()
```

### Complete Orchestrator Example

```python
"""Complete example using APE Orchestrator with sessions and rate limiting."""
import os
from ape import APEOrchestrator, RateLimitConfig, ActionRiskLevel

# 1. Configure rate limits
rate_config = RateLimitConfig.from_dict({
    "global": {
        "max_actions_per_minute": 60,
        "max_actions_per_session": 500,
        "max_cumulative_risk_score": 100,
    },
    "per_action": {
        "http_get": {"max_per_minute": 20, "max_per_hour": 200},
        "send_email": {"max_per_hour": 10, "max_per_day": 50},
    },
})

# 2. Create orchestrator
orch = APEOrchestrator.from_policy(
    "policies/my_policy.yaml",
    rate_limit_config=rate_config,
)

# 3. Register tools
orch.register_tools({
    "read_file": lambda path: open(path).read(),
    "list_directory": lambda path: os.listdir(path),
    "write_file": lambda path, content: open(path, "w").write(content) or True,
})

# 4. Process user requests through a session
def process_conversation(user_id: str, prompts: list[str]):
    session = orch.create_session(user_id=user_id, ttl_minutes=30)
    
    for prompt in prompts:
        result = session.execute(prompt, max_risk_level=ActionRiskLevel.MODERATE)
        
        if result.success:
            print(f"✓ {prompt}: {result.results}")
        else:
            print(f"✗ {prompt}: {result.error}")
    
    print(f"\nSession summary: {session.get_usage_summary()}")

# Example usage
process_conversation("user_123", [
    "Read the README.md file",
    "List files in the current directory",
])
```

<br>

## Path 2: Manual Integration

The Manual path gives you full control over every component.

### Step 1: Setup Core Components

```python
from ape import (
    # Configuration
    RuntimeConfig, EnforcementMode,
    
    # Core components
    PolicyEngine,
    RuntimeOrchestrator, RuntimeState,
    IntentManager,
    PlanManager,
    AuthorityManager,
    EnforcementGate,
    Action,
    Provenance,
    
    # Compilation and planning
    IntentCompiler, CompiledIntent,
    PlanGenerator, GeneratedPlan,
    
    # Session and rate limiting
    SessionManager, RateLimiter, RateLimitConfig,
    
    # Utilities
    AuditLogger,
    create_standard_repository,
)

# Create configuration
config = RuntimeConfig(
    enforcement_mode=EnforcementMode.ENFORCE,
    audit_enabled=True,
    token_ttl_seconds=300,
)

# Load policy with parameterized conditions
policy = PolicyEngine("policies/my_policy.yaml")

# Create action repository
repository = create_standard_repository()

# Create intent compiler and plan generator
compiler = IntentCompiler(repository)
generator = PlanGenerator(repository)
```

### Step 2: Define Your Tools

```python
TOOLS = {}

def register_tool(tool_id):
    def decorator(func):
        TOOLS[tool_id] = func
        return func
    return decorator

@register_tool("read_file")
def read_file(path: str) -> str:
    with open(path) as f:
        return f.read()

@register_tool("list_directory")
def list_directory(path: str) -> list:
    import os
    return os.listdir(path)
```

### Step 3: Compile Intent from Prompt

```python
def compile_prompt(prompt: str) -> CompiledIntent:
    """Compile a user prompt into a structured intent."""
    
    intent = compiler.compile(
        prompt=prompt,
        policy_allowed=policy.get_all_allowed_actions(),
        policy_forbidden=policy.get_all_forbidden_actions(),
    )
    
    print(f"Allowed actions: {intent.allowed_actions}")
    print(f"Escalation required: {intent.escalation_required}")
    
    return intent
```

### Step 4: Generate Execution Plan

```python
def create_plan(intent: CompiledIntent, parameters: dict = None) -> GeneratedPlan:
    """Generate an execution plan from intent."""
    
    plan = generator.generate(intent, tool_registry=TOOLS)
    
    if parameters:
        for step in plan.steps:
            if step.action_id in parameters:
                step.parameters.update(parameters[step.action_id])
    
    return plan
```

### Step 5: Execute Through APE Core

```python
def execute_plan(plan: GeneratedPlan) -> list:
    """Execute a plan through APE enforcement."""
    
    # Create fresh runtime components
    runtime = RuntimeOrchestrator()
    intent_manager = IntentManager()
    plan_manager = PlanManager(intent_manager)
    authority = AuthorityManager(runtime, token_ttl_seconds=config.token_ttl_seconds)
    enforcement = EnforcementGate(authority, config)
    
    # Setup callbacks — intent/plan changes revoke all tokens
    intent_manager.add_update_callback(lambda: authority.revoke_all())
    plan_manager.add_update_callback(lambda: authority.revoke_all())
    
    results = []
    
    # 1. Set intent
    intent_data = {
        "allowed_actions": plan.get_action_ids(),
        "forbidden_actions": [],
        "scope": plan.description or "execution",
    }
    intent_version = intent_manager.set(intent_data, Provenance.USER_TRUSTED)
    runtime.transition(RuntimeState.INTENT_SET)
    
    # 2. Submit and approve plan
    plan_hash = plan_manager.submit(plan.to_ape_plan(), Provenance.USER_TRUSTED)
    plan_manager.approve()
    runtime.transition(RuntimeState.PLAN_APPROVED)
    
    # 3. Execute
    runtime.transition(RuntimeState.EXECUTING)
    
    for idx, step in enumerate(plan.steps):
        tool = TOOLS[step.tool_id]
        
        action = Action(
            action_id=step.action_id,
            tool_id=step.tool_id,
            parameters=step.parameters,
            intent_version=intent_version,
            plan_hash=plan_hash,
            plan_step_index=idx,
        )
        
        # Policy check includes parameterized conditions
        policy.evaluate_or_raise(action.action_id, parameters=step.parameters)
        token = authority.issue(intent_version, plan_hash, action)
        result = enforcement.execute(token, tool, action, **step.parameters)
        results.append(result)
    
    # 4. Terminate
    runtime.transition(RuntimeState.TERMINATED)
    
    return results
```

### Step 6: Complete Manual Integration

```python
def process_request_manual(prompt: str, parameters: dict = None) -> list:
    """Process a user request using manual integration."""
    
    # Step 1: Compile intent
    intent = compile_prompt(prompt)
    
    # Step 2: Generate plan
    plan = create_plan(intent, parameters)
    
    # Step 3: Execute
    results = execute_plan(plan)
    
    return results

# Usage
results = process_request_manual(
    "Read config.json and list the data directory",
    parameters={
        "read_file": {"path": "config.json"},
        "list_directory": {"path": "data/"},
    },
)
```

<br>

## Policy Configuration

### Policy Structure

```yaml
name: policy_name
version: "1.0"
description: "Description"

default_decision: deny  # deny, allow, or escalate

rules:
  - action: action_id
    decision: allow|deny|escalate
    conditions:      # Optional: parameter-level constraints
      parameter_name:
        constraint_type: constraint_value
```

### Validating Policies

```python
from ape import validate_policy_file

errors = validate_policy_file("policy.yaml")
if errors:
    for error in errors:
        print(f"Error: {error}")
```

Or via CLI:

```bash
ape validate policies/my_policy.yaml
```

<br>

## Parameterized Conditions

Policy rules can include conditions that constrain action parameters at execution time. This provides fine-grained control beyond simple allow/deny.

### Condition Types

| Condition | Description | Example |
|-----------|-------------|---------|
| `prefix` | Value must start with one of the listed prefixes | `prefix: ["/tmp/", "/home/"]` |
| `suffix` | Value must end with one of the listed suffixes | `suffix: [".txt", ".json"]` |
| `allowlist` | Value must match one entry (supports glob `*`) | `allowlist: ["api.github.com", "*.corp"]` |
| `denylist` | Value must not match any entry (supports glob `*`) | `denylist: ["*.evil.com"]` |
| `max` | Numeric value must be ≤ this limit | `max: 10485760` |
| `min` | Numeric value must be ≥ this limit | `min: 0` |
| `regex` | Value must match the regular expression | `regex: "^[a-zA-Z0-9_]+$"` |
| `equals` | Value must exactly equal the specified value | `equals: "production"` |

### Example: Scoped File Access

```yaml
rules:
  - action: write_file
    decision: allow
    conditions:
      path:
        prefix: ["/tmp/", "/home/user/workspace/"]
      size_bytes:
        max: 10485760  # 10 MB limit
```

### Example: Domain-Restricted HTTP

```yaml
rules:
  - action: http_get
    decision: allow
    conditions:
      domain:
        allowlist: ["api.github.com", "*.internal.corp"]
        denylist: ["*.evil.com"]

  - action: http_post
    decision: allow
    conditions:
      domain:
        allowlist: ["api.internal.corp"]
```

### Example: Database Access Control

```yaml
rules:
  - action: query_data
    decision: allow
    conditions:
      tables:
        allowlist: ["public.*"]
      operations:
        allowlist: ["SELECT"]  # No INSERT/UPDATE/DELETE
```

### Evaluating Conditions Programmatically

```python
from ape import ConditionEvaluator

# Check if parameters satisfy conditions
failures = ConditionEvaluator.evaluate_conditions(
    action_id="write_file",
    parameters={"path": "/tmp/output.txt"},
    conditions={"path": {"prefix": ["/tmp/", "/home/"]}},
)

if failures:
    print(f"Condition violations: {failures}")
else:
    print("All conditions satisfied")
```

<br>

## Action Repository

### Using Standard Repository

```python
from ape import create_standard_repository

repository = create_standard_repository()
print(repository.action_ids)
# ['read_file', 'write_file', 'list_directory', 'delete_file', ...]
```

### Creating Custom Actions

```python
from ape import ActionRepository, ActionDefinition, ActionCategory, ActionRiskLevel

repository = ActionRepository()

repository.register(ActionDefinition(
    action_id="my_action",
    description="My custom action",
    category=ActionCategory.CUSTOM,
    risk_level=ActionRiskLevel.LOW,
    parameter_schema={
        "type": "object",
        "required": ["param1"],
        "properties": {
            "param1": {"type": "string"},
        },
    },
))

repository.freeze()  # Prevent further modifications
```

<br>

## Intent Compilation

### Basic Compilation

```python
from ape import IntentCompiler, ActionRiskLevel

intent = compiler.compile(
    prompt="Read config.json and list the data directory",
    policy_allowed=["read_file", "list_directory"],
    max_risk_level=ActionRiskLevel.MODERATE,
)

print(intent.allowed_actions)   # ['read_file', 'list_directory']
print(intent.scope)             # 'directory'
```

### Analysis Mode

Use analysis mode to debug prompt understanding without executing:

```python
analysis = compiler.analyze("Read config.json and send email")
print(analysis["signals_extracted"])     # Number of signals found
print(analysis["candidate_actions"])     # All matched actions
print(analysis["scope"])                 # Inferred scope
```

<br>

## Plan Generation

### From Intent

```python
plan = generator.generate(intent, tool_registry=TOOLS)

for step in plan.steps:
    print(f"{step.action_id}: {step.parameters}")
```

### From LLM Output

```python
llm_output = '[{"action_id": "read_file", "parameters": {"path": "config.json"}}]'

plan = generator.parse_and_validate(
    llm_output=llm_output,
    intent=intent,
    policy_check=policy.evaluate_or_raise,
)
```

<br>

## Session Management

Sessions provide multi-turn conversation continuity, tracking cumulative behavior across a series of agent actions.

### Creating and Using Sessions

```python
from ape import APEOrchestrator

orch = APEOrchestrator.from_policy("policies/my_policy.yaml")
orch.register_tools({...})

# Create a session
session = orch.create_session(user_id="user_123", ttl_minutes=30)

# Execute through the session
result1 = session.execute("Read config.json")
result2 = session.execute("Now update the config")

# Session properties
session.session_id           # Unique session identifier
session.user_id              # "user_123"
session.is_active            # True while not expired/revoked
session.actions_executed     # ["read_file", "write_file"]
session.cumulative_risk      # 0.4
session.tokens_issued        # 2
session.time_remaining       # Seconds until expiry
```

### Session Usage Summary

```python
summary = session.get_usage_summary()
# Returns: {
#   "session_id": "...",
#   "user_id": "user_123",
#   "actions_executed": 2,
#   "cumulative_risk": 0.4,
#   "tokens_issued": 2,
#   "is_active": True,
#   "time_remaining": 1740,
# }
```

### Managing Sessions

```python
from ape import SessionManager

manager = SessionManager()

# Create a session
session = manager.create(user_id="user_123", ttl_minutes=30)

# Retrieve by ID
session = manager.get(session.session_id)

# Revoke a session (admin action)
manager.revoke(session.session_id)

# Clean up expired sessions (call periodically)
cleaned = manager.cleanup_expired()
print(f"Removed {cleaned} expired sessions")

# List active sessions
active = manager.list_active()
```

<br>

## Rate Limiting

Rate limiting prevents agent-driven denial of service — runaway API calls, database query storms, email spam, and resource exhaustion.

### Configuration

```yaml
# Rate limits can be defined in YAML or Python
quotas:
  global:
    max_actions_per_minute: 60
    max_actions_per_session: 500
    max_cumulative_risk_score: 100
  
  per_action:
    http_get:
      max_per_minute: 20
      max_per_hour: 200
    http_post:
      max_per_minute: 5
      max_per_hour: 50
    send_email:
      max_per_hour: 10
      max_per_day: 50
    
  per_target:
    domain:
      "api.openai.com":
        max_per_minute: 10
      "*.internal.corp":
        max_per_minute: 100
```

### Python Configuration

```python
from ape import RateLimiter, RateLimitConfig

config = RateLimitConfig.from_dict({
    "global": {
        "max_actions_per_minute": 60,
        "max_actions_per_session": 500,
        "max_cumulative_risk_score": 100,
    },
    "per_action": {
        "http_get": {"max_per_minute": 20, "max_per_hour": 200},
        "send_email": {"max_per_hour": 10, "max_per_day": 50},
    },
    "per_target": {
        "domain": {
            "api.openai.com": {"max_per_minute": 10},
        },
    },
})

limiter = RateLimiter(config)

# Check before executing
limiter.check_allowed("http_get", target="api.openai.com")  # Raises if exceeded
limiter.record_action("http_get", risk_score=0.1, target="api.openai.com")

# Get usage summary
summary = limiter.get_usage_summary()
```

### Rate Limits with Orchestrator

```python
orch = APEOrchestrator.from_policy(
    "policies/my_policy.yaml",
    rate_limit_config=config,
)

# Rate limits are automatically enforced on every execute()
```

### Rate Limit Errors

```python
from ape import RateLimitExceededError, QuotaExhaustedError

try:
    limiter.check_allowed("http_get")
except RateLimitExceededError as e:
    print(f"Rate limit hit: {e}")
    # Wait and retry
except QuotaExhaustedError as e:
    print(f"Session quota exhausted: {e}")
    # Session is done
```

<br>

## External Policy Adapters

APE can delegate policy decisions to external enterprise policy engines using adapters. This lets organizations use their existing policy infrastructure while APE handles agent-specific enforcement.

### OPA (Open Policy Agent)

```python
from ape import PolicyEngine, OPAEvaluator

# Create OPA adapter
opa = OPAEvaluator(
    endpoint="http://localhost:8181/v1/data/ape/allow",
    timeout_seconds=5,
    fallback_deny=True,  # Deny if OPA is unreachable
)

# Use with PolicyEngine
policy = PolicyEngine(
    "policy.yaml",
    external_evaluator=opa,
)

# Or with Orchestrator
orch = APEOrchestrator.from_policy(
    "policy.yaml",
    external_evaluator=opa,
)

# Health check
if opa.health_check():
    print("OPA is reachable")
```

### AWS Cedar

```python
from ape import CedarEvaluator

cedar = CedarEvaluator(
    endpoint="https://verifiedpermissions.us-east-1.amazonaws.com",
    policy_store_id="ps-abc123",
    timeout_seconds=5,
    headers={"Authorization": "Bearer ..."},
)

policy = PolicyEngine("policy.yaml", external_evaluator=cedar)
```

### XACML

```python
from ape import XACMLEvaluator

xacml = XACMLEvaluator(
    endpoint="https://pdp.enterprise.com/authorize",
    timeout_seconds=5,
    headers={"Authorization": "Bearer ..."},
)

policy = PolicyEngine("policy.yaml", external_evaluator=xacml)
```

### Evaluation Flow

When an external evaluator is configured, APE's evaluation precedence is:

1. **Forbidden rules** — Always deny (external evaluator cannot override)
2. **Escalation rules** — Always escalate
3. **Rules with conditions** — Evaluate conditions on parameters
4. **Allowed rules** — Allow if explicitly listed
5. **External evaluator** — Delegate to OPA/Cedar/XACML
6. **Default deny** — Deny if nothing matches

<br>

## Dynamic Policy Reload

Policies can be updated at runtime without restarting the application.

### URL-Based Auto-Refresh

```python
policy = PolicyEngine(
    "policy.yaml",                              # Initial policy
    source="https://policy-server.corp/ape/production",  # Remote source
    refresh_interval_seconds=60,                # Poll every 60 seconds
    on_update=lambda old, new: audit.log("policy_updated", old, new),
)

# Stop auto-refresh when shutting down
policy.stop_auto_refresh()
```

### Webhook-Triggered Reload

```python
policy = PolicyEngine("policy.yaml")

# In your webhook handler
@app.route("/webhook/policy-update", methods=["POST"])
def policy_webhook():
    new_version = policy.reload()
    return f"Reloaded: {new_version}"
```

### Manual Reload

```python
# Force immediate reload from file
new_version = policy.reload()
print(f"Policy reloaded: {new_version}")
```

<br>

## Escalation Handling

```python
from ape import ActionRiskLevel

intent = orch.compile_intent(
    "Delete temporary files",
    max_risk_level=ActionRiskLevel.LOW,
)

if intent.escalation_required:
    print(f"Needs approval: {intent.escalation_required}")
    
    # Get human approval, then retry with higher tolerance
    if get_human_approval():
        intent = orch.compile_intent(
            "Delete temporary files",
            max_risk_level=ActionRiskLevel.CRITICAL,
        )
```

<br>

## Framework Integrations

APE provides native adapters for popular agent frameworks.

### LangChain

```python
from ape import APEOrchestrator
from ape.integrations.frameworks import APELangChainToolkit

orch = APEOrchestrator.from_policy("policy.yaml")
orch.register_tools({...})

toolkit = APELangChainToolkit(orch)
# Use toolkit with your LangChain agent
```

### AutoGen

```python
from ape.integrations.frameworks import APEAutoGenExecutor

executor = APEAutoGenExecutor(orch)
# Use executor with your AutoGen agent
```

### CrewAI

```python
from ape.integrations.frameworks import APECrewAITool

tool = APECrewAITool(orch)
# Use tool with your CrewAI agent
```

<br>

## CLI Reference

APE provides a comprehensive CLI for policy management and debugging.

### Policy Validation

```bash
# Validate a policy file
ape validate policies/my_policy.yaml

# Output includes: checks performed, policy summary, next steps
```

### Policy Simulation

```bash
# Simulate a single action against policy
ape simulate policies/read_only.yaml read_file

# Simulate multiple actions
ape simulate-batch policies/read_only.yaml read_file write_file delete_file
```

### Policy Comparison

```bash
# Compare two policy files
ape diff policies/read_only.yaml policies/development.yaml
```

### Policy Information

```bash
# Show detailed policy information
ape info policies/read_only.yaml
```

### Prompt Testing

```bash
# Test a prompt through the full intent compilation pipeline
ape test-prompt policies/read_only.yaml "Read the config file"

# Analyze a prompt to see extracted signals and candidate actions
ape analyze "Read config.json and delete temp files"
```

### Action Repository

```bash
# List all actions in the Action Repository
ape actions

# List actions grouped by category
ape actions --by-category
```

### MCP Integration

```bash
# Scan MCP configuration and generate a policy
ape mcp-scan ~/.config/claude/claude_desktop_config.json -o policies/mcp.yaml

# Show information about an MCP configuration
ape mcp-info ~/.config/claude/claude_desktop_config.json
```

### Mock Generation

```bash
# Generate mock tool implementations for testing
ape generate-mocks -o tests/mock_tools.py
```

<br>

## Error Handling

APE provides a comprehensive hierarchy of typed, deterministic errors.

### Core Errors

```python
from ape import (
    # Policy errors
    PolicyDenyError,           # Action denied by policy
    EscalationRequiredError,   # Action requires human approval
    PolicyConditionError,      # Parameter failed condition check
    
    # Intent errors
    IntentAmbiguityError,      # Prompt too ambiguous to understand
    IntentCompilationError,    # General compilation failure
    IntentNarrowingError,      # No actions allowed by policy
    
    # Plan errors
    PlanValidationError,       # Plan failed validation
    PlanParseError,            # Could not parse LLM plan output
    
    # Execution errors
    ToolNotRegisteredError,    # Tool not registered
    ExecutionError,            # Runtime execution failure
    
    # Session errors
    SessionExpiredError,       # Session TTL elapsed
    SessionRevokedError,       # Session was administratively revoked
    SessionNotFoundError,      # Session ID not found
    
    # Rate limit errors
    RateLimitExceededError,    # Velocity limit hit
    QuotaExhaustedError,       # Budget/quota exhausted
    
    # Adapter errors
    PolicyAdapterError,        # External evaluator failure
    AdapterConnectionError,    # Cannot reach external evaluator
)
```

### Error Handling Patterns

```python
from ape import (
    PolicyDenyError, EscalationRequiredError,
    RateLimitExceededError, PolicyConditionError,
)

try:
    result = orch.execute("Write data to /etc/passwd")
except PolicyDenyError as e:
    print(f"Denied: {e.action_id}")
except PolicyConditionError as e:
    print(f"Parameter violation: {e}")
except EscalationRequiredError as e:
    print(f"Needs approval: {e.action_id}")
except RateLimitExceededError as e:
    print(f"Rate limited: {e}")
```

<br>

## Production Deployment

### Configuration Checklist

- [ ] Policy files validated with `ape validate`
- [ ] All tools registered
- [ ] Parameterized conditions configured for sensitive actions
- [ ] Rate limits configured to prevent agent DDoS
- [ ] Session TTLs set appropriately
- [ ] Audit logging enabled
- [ ] Escalation resolver configured for high-risk actions
- [ ] Error handling implemented for all APE error types
- [ ] External policy adapter configured (if using OPA/Cedar/XACML)
- [ ] Policy reload mechanism configured (if using dynamic policies)

### Recommended Settings

```python
from ape import RuntimeConfig, EnforcementMode, RateLimitConfig

config = RuntimeConfig(
    enforcement_mode=EnforcementMode.ENFORCE,
    audit_enabled=True,
    token_ttl_seconds=60,
)

rate_limits = RateLimitConfig.from_dict({
    "global": {
        "max_actions_per_minute": 60,
        "max_actions_per_session": 500,
        "max_cumulative_risk_score": 100,
    },
})
```

<br>

## Troubleshooting

### "Action not found in repository"

```python
print(repository.action_ids)  # Check available actions
```

### "Policy denies all actions"

```python
print(policy.get_all_allowed_actions())  # Check what's allowed
```

### "Intent compilation failed"

```python
analysis = compiler.analyze("your prompt")  # Debug mode
print(analysis)
```

### "Tool not registered"

```python
print(orch.registered_tools)  # Check registered tools
```

### "Policy condition failed"

```python
from ape import ConditionEvaluator

failures = ConditionEvaluator.evaluate_conditions(
    "write_file", {"path": "/etc/test"}, {"path": {"prefix": ["/tmp/"]}}
)
print(failures)  # Shows which condition failed and why
```

### "Rate limit exceeded"

```python
summary = limiter.get_usage_summary()
print(summary)  # Shows current counts and limits
```

### "Session expired"

```python
print(session.is_active)        # Check if still active
print(session.time_remaining)   # Check remaining TTL
```

<br>

## Summary

### Orchestrator Path

```python
from ape import APEOrchestrator

orch = APEOrchestrator.from_policy("policy.yaml")
orch.register_tool("tool_id", tool_function)
result = orch.execute("User prompt")

# With sessions
session = orch.create_session(user_id="user_123", ttl_minutes=30)
result = session.execute("User prompt")
```

### Manual Path

```python
from ape import (
    PolicyEngine, IntentCompiler, PlanGenerator,
    RuntimeOrchestrator, IntentManager, PlanManager,
    AuthorityManager, EnforcementGate, Action, Provenance,
    RuntimeState, create_standard_repository,
)

# Setup → Compile → Generate → Execute
repository = create_standard_repository()
policy = PolicyEngine("policy.yaml")
compiler = IntentCompiler(repository)
generator = PlanGenerator(repository)

intent = compiler.compile(prompt, policy_allowed=policy.get_all_allowed_actions())
plan = generator.generate(intent)

# Execute through APE core...
```
