# Changelog

All notable changes to APE (Agent Policy Engine) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.2] - 2025-02-07

### Added

#### Parameterized Policy Conditions (`ape.policy`)
- **ConditionEvaluator**: Evaluates parameter-level conditions at execution time
- **PolicyRule**: Dataclass for rules with conditions (action, decision, conditions)
- Supported condition types: `prefix`, `suffix`, `allowlist`, `denylist`, `max`, `min`, `regex`, `equals`
- Glob pattern matching in allowlists and denylists (e.g., `*.internal.corp`)
- Conditions are validated against action parameters during policy evaluation

#### External Policy Adapters (`ape.policy_adapters`)
- **ExternalEvaluator**: Abstract base class for external policy engines
- **OPAEvaluator**: Open Policy Agent (OPA/Rego) adapter via REST API
- **CedarEvaluator**: AWS Cedar authorization adapter
- **XACMLEvaluator**: XACML JSON profile adapter
- All adapters support: `evaluate()`, `health_check()`, configurable timeout, fallback deny, custom headers
- Evaluation precedence: forbidden → escalate → conditions → allowed → external evaluator → default deny

#### Session Management (`ape.session`)
- **SessionManager**: Creates, retrieves, revokes, and cleans up sessions
- **Session**: Tracks multi-turn conversation state including actions executed, cumulative risk, tokens issued, and time remaining
- **SessionUsageSummary**: Structured summary of session activity
- `APEOrchestrator.create_session(user_id, ttl_minutes)` — unified API entry point
- Session timeout with automatic expiry
- Administrative session revocation
- `cleanup_expired()` for memory management in long-running processes

#### Rate Limiting (`ape.rate_limiter`)
- **RateLimiter**: Sliding window rate limiting with thread-safe counters
- **RateLimitConfig**: Declarative configuration with `from_dict()` factory
- **GlobalLimits**: `max_actions_per_minute`, `max_actions_per_session`, `max_cumulative_risk_score`
- **ActionLimits**: Per-action limits with `max_per_minute`, `max_per_hour`, `max_per_day`
- **TargetLimits**: Per-target limits with glob pattern matching (e.g., `*.internal.corp`)
- Cumulative risk scoring across session lifetime
- Integration with SessionManager and APEOrchestrator

#### Dynamic Policy Reload (`ape.policy`)
- **PolicyEngine** now accepts `source` (URL), `refresh_interval_seconds`, and `on_update` callback
- `PolicyEngine.reload()` — manual reload from file or URL
- `PolicyEngine.stop_auto_refresh()` — stop background polling thread
- Background daemon thread for auto-refresh from remote policy sources
- Thread-safe policy swapping with RLock

#### Framework Integrations (`ape.integrations`)
- **APELangChainToolkit**: LangChain SDK integration adapter
- **APEAutoGenExecutor**: AutoGen SDK integration adapter
- **APECrewAITool**: CrewAI SDK integration adapter
- All adapters accept an APEOrchestrator instance

#### New Error Types (`ape.errors`)
- **SessionError**, **SessionExpiredError**, **SessionRevokedError**, **SessionNotFoundError**
- **RateLimitError**, **RateLimitExceededError**, **QuotaExhaustedError**
- **PolicyConditionError** — parameterized condition violation
- **PolicyAdapterError**, **AdapterConnectionError**, **AdapterEvaluationError**, **AdapterConfigurationError**

#### CLI Enhancements (`ape.cli`)
- `ape diff` — compare two policy files side by side
- Professional visual formatting with ANSI colors, Unicode box-drawing characters
- Every command now explains its purpose and suggests next steps
- `ape validate` shows detailed checks performed
- `ape generate-mocks` explains mock tool usage

### Fixed
- `ape actions` and `ape generate-mocks` crashed with `'ActionRepository' object has no attribute 'all_actions'` — corrected to use `action_ids`
- `ape analyze "Read config.json and delete temp files"` crashed with `object of type 'int' has no len()` — fixed type handling in CLI analyze command
- `ape test-prompt` failed to recognize `"Read the config file"` and `"Read"` — added fallback semantic patterns for bare verbs and intermediate phrasings
- Intent compiler now recognizes bare action verbs (read, write, list, delete, etc.) with appropriate confidence levels

### Changed
- **PolicyEngine** constructor extended with optional `external_evaluator`, `source`, `refresh_interval_seconds`, and `on_update` parameters
- **PolicyEngine.evaluate()** now accepts optional `parameters` argument for condition evaluation
- **APEOrchestrator.from_policy()** extended with `rate_limit_config`, `external_evaluator`, `source`, `refresh_interval_seconds`, and `on_update` parameters
- **APEOrchestrator** now has `create_session()` method and integrated `SessionManager`
- Updated `ape/__init__.py` to export all new modules and classes
- Updated `pyproject.toml` with new version
- CLI visual overhaul for all 11 commands

### Security
- Parameter-level enforcement prevents path traversal, domain abuse, and resource exhaustion
- Rate limiting prevents agent-driven DDoS (LLM DDoS prevention)
- Session tracking enables cumulative risk monitoring across multi-turn conversations
- External policy adapters enable integration with enterprise policy infrastructure (OPA, Cedar, XACML)

## [1.0.1] - 2025-01-08

### Added

#### Action Repository (`ape.action_repository`)
- **ActionRepository**: Canonical registry of all valid actions that APE can authorize
- **ActionDefinition**: Complete definition of an action including schema, risk level, and tool bindings
- **ActionCategory**: Categories for grouping actions (FILE_READ, FILE_WRITE, NETWORK, DATABASE_READ, etc.)
- **ActionRiskLevel**: Risk classifications (MINIMAL, LOW, MODERATE, HIGH, CRITICAL)
- **create_standard_repository()**: Factory function providing 18 standard actions out of the box
- Standard actions include: read_file, write_file, list_directory, delete_file, http_get, http_post, query_data, send_email, execute_code, and more

#### Intent Compiler (`ape.intent_compiler`)
- **IntentCompiler**: Transforms natural language prompts into structured APE Intent objects
- **CompiledIntent**: Validated intent ready for plan generation and APE enforcement
- **IntentSignal**: Semantic signals extracted from user prompts
- 60+ semantic patterns for natural language understanding
- Policy-constrained narrowing (only allowed actions pass through)
- Risk-based filtering with escalation support
- Scope inference (single_file, directory, project, system, database)
- Complete audit trail of compilation decisions

#### Plan Generator (`ape.plan_generator`)
- **PlanGenerator**: Creates and validates execution plans from intents or LLM output
- **GeneratedPlan**: Validated plan ready for APE PlanManager
- **GeneratedPlanStep**: Individual step in a generated plan
- **PlanProposal**: Parsed but unvalidated plan proposal from LLM
- Multiple parsing formats: JSON, markdown lists, natural language
- Plan repair for common LLM errors
- Plan simulation for dry-run policy checks
- LLM prompt generation for plan creation

#### APE Orchestrator (`ape.orchestrator`)
- **APEOrchestrator**: Unified API combining all APE components
- **OrchestrationResult**: Complete execution result with audit information
- One-call API: `orch.execute("Read config.json")` 
- Step-by-step API: `compile_intent()` → `create_plan()` → `execute_plan()`
- Automatic tool registration and binding
- Policy analysis and suggestion tools
- Full APE enforcement on every execution

#### New Error Types
- ActionRepositoryError, ActionNotFoundError, ActionAlreadyExistsError, ActionParameterError, RepositoryFrozenError
- IntentCompilationError, IntentNarrowingError, IntentAmbiguityError
- PlanGenerationError, PlanValidationError, PlanParseError, PlanIntentViolationError, PlanPolicyViolationError
- AgentError, ToolNotRegisteredError, ExecutionError

### Changed
- Updated main `ape/__init__.py` to export all new components
- Updated `pyproject.toml` with new version and keywords
- Documentation now covers both Orchestrator and Manual integration paths

### Security
- Core principle enforced: "Prompts guide intent, but never are intent"
- All prompt-to-action transformation goes through validated compilation
- Policy narrowing ensures only allowed actions can be in intents
- Risk-based filtering with mandatory escalation for high-risk actions
- Complete audit trail from prompt to execution

## [1.0.0] - 2025-01-05

### Added

#### Core Runtime (`ape.runtime`)
- **RuntimeOrchestrator**: State machine enforcing valid execution flow
- **RuntimeState**: Enumeration of valid states (UNINITIALIZED, INTENT_SET, PLAN_APPROVED, EXECUTING, TERMINATED, FAILED)
- Illegal state transitions are security violations, not warnings

#### Provenance System (`ape.provenance`)
- **Provenance**: Labels for data origin (USER_TRUSTED, AGENT_GENERATED, TOOL_OUTPUT, EXTERNAL_UNTRUSTED)
- **ProvenanceManager**: Tracks and validates data provenance
- EXTERNAL_UNTRUSTED data cannot participate in authority creation

#### Intent Management (`ape.intent`)
- **Intent**: Immutable intent specification with allowed/forbidden actions
- **IntentManager**: Manages intent lifecycle with version tracking
- Intent updates trigger automatic token revocation

#### Plan Management (`ape.plan`)
- **Plan**: Ordered list of steps with cryptographic hash
- **PlanStep**: Individual action binding in a plan
- **PlanManager**: Plan submission, approval, and validation
- Plan mutations after approval invalidate all tokens

#### Policy Engine (`ape.policy`)
- **PolicyEngine**: YAML-based policy loading and evaluation
- **PolicyDecision**: ALLOW, DENY, or ESCALATE decisions
- Default-deny: unspecified actions are denied

#### Authority System (`ape.authority`)
- **AuthorityToken**: Single-use, time-limited execution authority
- **AuthorityManager**: Token lifecycle management
- Tokens are cryptographically bound to intent and plan

#### Enforcement Gate (`ape.enforcement`)
- **EnforcementGate**: Mandatory checkpoint for all tool execution
- No tool execution without valid AuthorityToken

#### Escalation Handling (`ape.escalation`)
- **EscalationHandler**: Routes escalation requests to resolvers
- **EscalationResolver**: Interface for custom approval logic
- **DefaultDenyResolver**: Safe default that denies all escalations

#### Audit Logging (`ape.audit`)
- **AuditLogger**: Structured logging of all APE events
- **AuditEvent**: Typed audit events with timestamps
- Complete execution history for compliance

#### MCP Integration (`ape.mcp`)
- **MCPScanner**: Scans MCP configuration files
- **generate_policy_from_mcp()**: Auto-generates policies from MCP tools

#### Reference Implementation (`ape.reference_agent`)
- **ReferenceAgent**: Complete working example of APE integration
- **create_simple_agent()**: Quick-start factory function

#### CLI Tools (`ape.cli`)
- `ape validate` — Validate policy files
- `ape simulate` — Simulate policy evaluation
- `ape simulate-batch` — Batch policy simulation
- `ape info` — Show policy information
- `ape mcp-scan` — Scan MCP configurations
- `ape mcp-info` — Show MCP configuration details
- `ape test-prompt` — Test prompt compilation
- `ape analyze` — Analyze prompt signals
- `ape actions` — List available actions
- `ape generate-mocks` — Generate mock tools

#### Example Policies
- `minimal_safe.yaml` — Minimal read-only policy
- `read_only.yaml` — File reading only
- `development.yaml` — Broader development permissions
- `filesystem_scoped.yaml` — Path-constrained access
- `human_in_loop.yaml` — Escalation-required policy

### Security
- Deterministic, non-probabilistic enforcement
- Cryptographic binding of tokens to intent/plan
- Mandatory schema validation
- Complete audit trail
- Default-deny policy model
