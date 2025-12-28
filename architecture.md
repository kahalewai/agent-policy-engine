# Agent Policy Engine (APE)

**Software Architecture & Implementation Specification
(Normative, Codegen-Ready, Security-Enforced)**

**Version:** 1.0

**Status:** Normative

**Audience:** Security engineers, platform architects, AI system developers, code generators

---

## 1. Document Purpose

This document defines the **software architecture, operational semantics, and implementation blueprint** of the **Agent Policy Engine (APE)**.

Its goals are to:

* Precisely define system boundaries
* Specify components, responsibilities, and interfaces
* Explicitly define all runtime artifacts
* Enable deterministic implementation
* Serve as a long-term reference for humans and AI
* Be usable as a **single-prompt input to generate code**
* Avoid ambiguity around agent behavior, authority, and enforcement
* Define packaging, installation, configuration, and usage patterns

This document is **normative**.
Any implementation that deviates from this specification is **non-compliant**.

---

## 2. Architectural Overview

### 2.1 System Role

APE is a **policy enforcement runtime** that governs how an AI agent:

* Interprets user intent
* Plans actions
* Consumes external data
* Executes tool calls

APE enforces **authority boundaries independently of the language model**.

### 2.2 Architectural Positioning

APE sits **inside the agent runtime**, between reasoning and execution, and **owns the authoritative runtime state machine**.

```
User Input
→ Intent Construction
→ APE Runtime Controller
→ LLM Reasoning
→ Plan Proposal
→ APE Plan Validation
→ APE Policy Evaluation
→ APE Authority Issuance
→ APE Enforcement Gate
→ Tool Execution
```

APE is:

* In-process
* Synchronous
* Deterministic
* Library-first (not a service)

All execution-capable components **must consult the Runtime Controller** before progressing.

### 2.3 Architectural Style

* Layered architecture
* Deterministic control flow
* Explicit state transitions
* Fail-safe by default
* Configuration-driven policy
* Code-enforced authority
* Capability-based security model
* Explicit state machine enforcement
* Hash-based immutability
* Schema-validated inputs
* Zero-trust data handling
* Deterministic failure modes

---

## 3. Threat Model

APE mitigates the following agent-layer threats:

### 3.1 Indirect Prompt Injection

Untrusted content contains instructions that alter agent behavior.

### 3.2 Confused Deputy Attacks

The agent performs actions on behalf of an attacker using user-granted authority.

### 3.3 Cross-Tool Escalation

Data read from one tool leads to actions in another without user intent.

### 3.4 Instruction Smuggling

Operational commands embedded in natural language content.

### 3.5 Authority Reuse & Replay Attacks

Attempting to reuse authority across actions, plans, intents, or tenants.

**Mitigations:**

* Single-use AuthorityTokens
* Token binding to:
  * tenant (if enabled)
  * intent version hash
  * plan hash
  * action ID
  * plan step index
* Central token registry
* Explicit revocation rules

### 3.6 Runtime Confusion Attacks

Executing actions in invalid lifecycle states.

**Mitigations:**

* Enforced runtime state machine
* Illegal transitions rejected deterministically

---

## 4. Core Design Principles

### 4.1 Reasoning Is Probabilistic, Authority Is Deterministic

LLMs may suggest actions; policy engines decide.

### 4.2 Data Is Never Authority

External content may inform reasoning but may not control actions.

### 4.3 Explicit Intent Is Mandatory

Agents operate only within machine-readable intent boundaries.

### 4.4 Default Deny

Any action not explicitly allowed is denied or escalated.

### 4.5 Enforcement Over Guidance

Policies are enforced in code, not suggested via prompts.

### 4.6 Capability-Based Authority

Authority is represented as a **non-forgeable, in-process capability**.
Possession of a valid AuthorityToken is the **only** way to execute an action.

### 4.7 Immutability via Hashing

Intent and plans are immutable via:

* Canonical serialization
* Cryptographic hashing
* Token binding to hashes

---

## 5. Core Runtime Concepts (Normative)

### 5.1 Intent

Intent is a **structured, machine-readable declaration of user intent**.

Intent defines:

* Allowed actions
* Forbidden actions
* Escalation requirements
* Scope boundaries

Properties:

* Intent must be created from user input
* Intent must be validated against a mandatory JSON Schema
* Intent must be Canonically serialized
* Intent must be Immutable after set
* Intent must be Immutable during execution
* Intent must be explicitly versioned via cryptographic hash (`intent_version`)
* Intent must produce a stable intent_version hash
* Intent must be stored in runtime state

Intent update rules:

* Any intent update requires explicit user action
* Any intent update invalidates the current plan
* Any intent update revokes all issued AuthorityTokens
* Any intent update resets runtime state to `INTENT_SET`

### 5.2 Plan

A Plan is an **explicit, ordered list of intended actions**.

Plan properties:

* Plan must be proposed by the agent
* Plan must be validated against intent
* Plan must be validated against a mandatory JSON Schema
* Plan must be frozen upon approval
* Plan must be canonically serialized
* Plan must have a stable cryptographic hash (`plan_hash`)
* Plan must be linear (no branching or looping)
* Plan must be immutable once approved

Plan mutation rules:

* Any plan change invalidates the plan
* Any plan change invalidates plan hash
* Any plan change invalidates runtime execution state
* Any plan change revokes all issued AuthorityTokens
* Any plan change requires re-submission and approval

### 5.3 Action

An **Action** is the smallest unit of authority.

An Action consists of:

* `action_id` – stable identifier
* `tool_id` – tool to invoke
* `parameters` – schema-validated object
* `intent_version` – hash binding
* `intent_scope` – scope reference
* `plan_hash` – hash binding
* `plan_step_index` – integer index

Actions are:

* Explicit
* Comparable
* Auditable
* Deterministically bound to authority
* Matchable by policy

Each Action execution must be bound to:

* Intent version
* Plan hash
* Plan step index

### 5.4 Provenance

All data entering the agent is labeled with provenance metadata.

Provenance categories:

* `SYSTEM_TRUSTED`
* `USER_TRUSTED`
* `EXTERNAL_UNTRUSTED`

Rules:

* Provenance is mandatory
* Provenance is immutable once assigned
* Mixed provenance results in `EXTERNAL_UNTRUSTED`
* Untrusted data may inform reasoning
* Untrusted data may not create, modify, or expand authority
* EXTERNAL_UNTRUSTED data may not participate in authority creation, modification, escalation, or approval

Provenance enforcement is **code-level**, not advisory.

### 5.5 AuthorityToken (Normative)

AuthorityToken is a **concrete, in-process runtime artifact**.

It represents permission to execute **exactly one action**.

#### 5.5.1 AuthorityToken Properties

* Issued only by the Authority Manager
* Cryptographically strong opaque identifier
* Opaque to the agent
* In-memory only
* Non-serializable
* Non-transferable
* Single-use
* Revocable

#### 5.5.2 AuthorityToken Structure

An AuthorityToken **must** contain:

* `token_id` - cryptographically strong, unique opaque identifier
* `tenant_id` - optional, if multi-tenant mode enabled
* `intent_version` - hash
* `plan_hash` - hash
* `action_id` - bound action identifier
* `plan_step_index`
* `issued_at` - timestamp
* `expires_at` - timestamp
* `consumed` - boolean flag

#### 5.5.3 AuthorityToken Lifecycle

1. Requested for a specific action
2. Issued only if policy allows
3. Bound to intent, plan, and step
4. Presented to Enforcement Gate
5. Consumed exactly once
6. Invalidated immediately after use
7. Automatically invalid on expiration

AuthorityTokens are revoked on:

* Intent update
* Plan invalidation
* Runtime termination
* Policy violation
* Policy reload
* Escalation denial
* Tenant mismatch (if tenant mode enabled)

Tokens are:

* In-memory only
* Non-serializable
* Non-transferable
* Non-reusable

#### 5.5.4 Cryptography Clarification

AuthorityTokens are **not encrypted**.

Rationale:

* Tokens are never transmitted
* Tokens are never persisted
* Security derives from unforgeability and containment, not secrecy

#### 5.5.5 Mandatory Enforcement Contract

Normative Rule:

No tool execution may occur without a valid AuthorityToken.

The Enforcement Gate must:

* Require an AuthorityToken for every tool invocation
* Validate token authenticity
* Verify token matches the action
* Verify token is unexpired and unconsumed
* Reject execution if any check fails

Any tool execution without a valid AuthorityToken is a security violation.

### 5.6 Policy

A Policy is a deterministic rule set defining:

* Allowed actions
* Forbidden actions
* Tool transition rules
* Escalation requirements
* Default-deny behavior

Policies are:

* Declarative
* YAML-based
* Schema-validated against mandatory JSON Schema
* Loaded at runtime
* Immutable during execution

### 5.7 Required Invariants

Add explicit invariants, including:

* No authority without intent + plan binding
* No authority reuse
* No execution without EXECUTING state
* No authority issuance during ESCALATION_REQUIRED
* No EXTERNAL_UNTRUSTED provenance in authority paths

---

## 6. High-Level Component Architecture

### 6.1 Core Components

* Runtime Controller (state machine)
* Intent Manager
* Plan Manager
* Provenance Manager
* Policy Engine
* Authority Manager
* Enforcement Gate
* Escalation Handler (integration hook)
* Audit Logger
* Schema Validators
* Formal Verification Exporter

Each component has a **single, explicit responsibility**.

---

## 7. Component Specifications

### 7.1 Runtime Controller

* Owns runtime state
* Enforces legal transitions
* Blocks illegal execution paths

Failure behavior: hard reject execution with `RuntimeStateError`.

### 7.2 Intent Manager

* Constructs intent objects
* Validates intent schema against mandatory JSON Schema
* Computes intent hash
* Enforces immutability
* Triggers revocation on update
* Handles intent updates and resets

Failure behavior: reject malformed intent.

### 7.3 Plan Manager

* Accepts plan proposals
* Validates plan schema against mandatory JSON Schema
* Validates against intent
* Computes plan hash
* Detects mutation
* Freezes approved plans

Failure behavior: deny execution

### 7.4 Provenance Manager

* Assigns provenance labels
* Propagates provenance
* Enforces authority restrictions
* Prevents provenance escalation

Failure behavior: default to EXTERNAL_UNTRUSTED

### 7.5 Policy Engine

* Loads policy files
* Validates policy schema against mandatory JSON Schema
* Evaluates rules deterministically
* Resolves conflicts via defined precedence
* Returns `ALLOW`, `DENY`, or `ESCALATE`
* Supports simulation mode

Failure behavior: deny.

### 7.6 Authority Manager

* Issues AuthorityTokens
* Tracks lifecycle
* Tracks expiration
* Enforces single-use
* Prevents reuse
* Revokes on invalidation
* Revokes tokens on violations

Failure behavior: deny

### 7.7 Enforcement Gate

* Intercepts all tool calls
* Requires valid AuthorityToken
* Executes or blocks
* Emits audit events or logs

Failure behavior: block execution.

### 7.8 Escalation Handler

* Is an Integration hook only
* Does not implement UI or approval logic
* Must be provided by the host application
  
Default behavior: deny escalation

### 7.9 Schema Validators

Schemas are mandatory for:

  * Intent
  * Plan
  * Policy

Schema must be validated against mandatory JSON Schema

Failure behavior: hard reject

### 7.10 Formal Verification Exporter

* Exports policy models for:

  * TLA+
  * Alloy
  * Z3
  * Dafny

Purpose:

  * independent verification of invariants
  * Machine-checkable invariants
  * Independent security review

Explicit verification model schema

Required exported fields:

  * ACTIONS
  * ALLOW
  * DENY
  * ESCALATE
  * INVARIANTS

---

## 8. Runtime State Machine

### 8.1 Valid states

* `INITIALIZED`
* `INTENT_SET`
* `PLAN_APPROVED`
* `EXECUTING`
* `ESCALATION_REQUIRED`
* `TERMINATED`

### 8.2 State transition Rules

* Illegal transitions are rejected
* Illegal transitions are security violations, not warnings.
* Execution requires `EXECUTING`
* Execution must not proceed unless state is EXECUTING.
* Escalation pauses authority issuance

---

## 9. Control Flow

### 9.1 Normal Flow

1. Initialize runtime
2. Set intent
3. Agent Proposes plan
4. Plan is approved
5. Agent requests action
6. Transition to EXECUTING
7. Evaluate policy
8. Issue AuthorityToken
9. Tool executed via Enforcement gate
10. Result tagged with provenance
11. Audit result
12. Loop continues

### 9.2 Escalation Flow

1. Policy returns `ESCALATE`
2. Runtime enters `ESCALATION_REQUIRED`
3. Authority issuance halts
4. Application requests user confirmation
5. Escalation handler invoked
6. Approval resumes execution
7. Denial terminates runtime

---

## 10. Error Model

Typed, deterministic errors:

* `IntentError`
* `PlanError`
* `PolicyDenyError`
* `EscalationRequiredError`
* `AuthorityExpiredError`
* `UnauthorizedActionError`
* `RuntimeStateError`
* `ProvenanceError`
* `VerificationError`
* `PlanMutationError` (or PlanError subtype)

Errors are:

* deterministic and explicit
* Typed
* Non-recoverable unless explicitly handled

---

## 11. Installation & Packaging

### 11.1 Language Target

* Python ≥ 3.10

### 11.2 Distribution

* Installable via `pip`

### 11.3 Dependencies

* No external services
* No network dependencies
* Core runtime has zero optional runtime dependencies

### 11.2 Optional Components

* CLI tools are included but optional to use
* Multi-tenant mode is included but optional to use

---

## 12. Repository Structure

ape/
├── pyproject.toml
├── ape/
│   ├── runtime/
│   ├── intent/
│   ├── plan/
│   ├── policy/
│   ├── provenance/
│   ├── authority/
│   ├── enforcement/
│   ├── escalation/
│   ├── cli/
│   ├── audit/
│   └── reference_agent/
├── policies/
├── tests/
└── docs/

---

## 13. Configuration Model

### 13.1 Policy Files

Policies are defined in YAML:

* Allowed actions
* Forbidden actions
* Tool transitions
* Escalation mode

### 13.1 Runtime Configuration

Controls:

* Enforcement mode (disabled / observe / enforce)
* Audit logging / logging behavior
* Policy Paths
* Multi-tenant mode (optional)

### 13.1 Multi-Tenant Mode

Multi-tenant isolation:

* Optional
* Explicitly configured
* Enforced at token, intent, plan, and runtime levels

---

## 14. CLI

CLI supports:

* Policy validation
* Policy simulation
* Attack test execution
* Audit inspection
* Verification export

CLI guarantees:

* Deterministic exit codes
* Typed error output
* Read-only safety (no authority issuance)

`verify-policy` output compatibility with:

* TLA+
* Alloy
* Z3
* Dafny

State that exported models are machine-consumable and deterministic.

CLI command is 'ape'
CLI is read-only and cannot issue authority.
CLI is optional in production.

---

## 15. Developer Usage Model

Developers **must**:

1. Install APE
2. Load policy configuration
3. Initialize APE runtime
4. Set/construct intent
5. Submit agent plan
6. Route all actions through APE
7. Execute tools only with AuthorityToken
8. Execute tools only via Enforcement Gate
9. Handle escalation explicitly
10. Use schema-validated inputs
11. Respect runtime state transitions
12. Route escalation through handler
13. Never execute tools outside Enforcement Gate

---

## 16. Testing Architecture

* Unit tests
* Integration tests
* Threat simulations
* Regression tests
* State machine tests
* Authority lifecycle tests
* Tenant isolation tests
* Verification tests

---

## 17. Non-Goals

APE does not:

* Interpret natural language
* Modify prompts
* Enforce ethics or values
* Control model internals

APE enforces authority, not cognition.

---

## 18. Open Source Strategy

* Apache 2.0 license
* SECURITY.md required
* Formal verification artifacts encouraged
* Security-first contribution policy

APE is open source to:

* Enable review
* Encourage standardization
* Prevent fragmented solutions
* Improve ecosystem security

---

## 19. Summary

The Agent Policy Engine provides:

* Explicit intent and plans with cryptographic immutability
* Deterministic runtime state enforcement
* Deterministic policy enforcement
* Capability-based authority via secure tokens
* Enforced authority via AuthorityToken
* Auditable execution
* A missing security layer for agent systems
* Integrated escalation handling
* Mandatory schema validation against mandatory JSON Schema
* Production-grade tooling
* Enforced provenance controls
* Runtime state machine
* Escalation integration
* Optional multi-tenant isolation
* Formal verification compatibility

APE restores the fundamental boundary between reasoning and power.

**APE defines a new execution-security standard for AI agents:**

> *Authority is explicit, finite, revocable, and never inferred.*
