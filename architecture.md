# Agent Policy Engine (APE)

**Software Architecture & Implementation Specification
(Single-Prompt, Codegen-Ready, Normative)**

---

## 1. Document Purpose

This document defines the **software architecture, operational semantics, and implementation blueprint** of the Agent Policy Engine (APE).

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

---

### 2.2 Architectural Positioning

APE sits **inside the agent runtime**, between reasoning and execution.

```
User Input
→ Intent Construction
→ Agent Policy Engine (APE)
→ LLM Reasoning
→ APE Enforcement
→ Tool Execution
```

APE is:

* In-process
* Synchronous
* Deterministic
* Library-first (not a service)

---

### 2.3 Architectural Style

* Layered architecture
* Deterministic control flow
* Explicit state transitions
* Fail-safe by default
* Configuration-driven policy
* Code-enforced authority

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

* Created from user input
* Validated against schema
* Immutable during execution
* Stored in runtime state
* Explicitly versioned

Intent update rules:

* Requires explicit user action
* Invalidates the current plan
* Revokes all issued authority tokens
* Resets runtime state to `INTENT_SET`

---

### 5.2 Plan

A Plan is an **explicit, ordered list of intended actions**.

Plan properties:

* Proposed by the agent
* Validated against intent
* Frozen upon approval
* Linear (v1 – no branching or looping)
* Immutable once approved

Plan mutation rules:

* Any change invalidates the plan
* Requires re-submission and approval
* Revokes all issued authority tokens

---

### 5.3 Action (Explicit Definition)

An **Action** is the smallest unit of authority.

An Action consists of:

* `action_id` – stable string identifier
* `tool_id` – tool to be invoked
* `parameters` – validated parameter object
* `intent_scope` – scope reference
* `plan_step_index` – index in approved plan

Actions are:

* Explicit
* Comparable
* Matchable by policy
* Auditable

---

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

---

## 5.5 Authority Token (Normative, Explicit)

**AuthorityToken** is a concrete, in-process runtime artifact.

It represents **permission to execute exactly one action**.

### 5.5.1 AuthorityToken Definition

AuthorityToken is:

* Issued only by the Authority Manager
* Opaque to the agent
* Non-serializable
* In-memory only

### 5.5.2 AuthorityToken Structure

An AuthorityToken **must** contain:

* `token_id` – unique opaque identifier
* `action_id` – bound action identifier
* `issued_at` – timestamp
* `expires_at` – timestamp
* `consumed` – boolean flag

### 5.5.3 AuthorityToken Lifecycle

1. Requested for a specific action
2. Issued only if policy allows
3. Presented to Enforcement Gate
4. Consumed exactly once
5. Invalidated immediately after use
6. Automatically invalid on expiration

AuthorityTokens are revoked on:

* Intent update
* Plan invalidation
* Policy violation
* Runtime termination

---

### 5.5.4 Mandatory Enforcement Contract

**Normative Rule:**

> No tool execution may occur without a valid AuthorityToken.

The Enforcement Gate **must**:

* Require an AuthorityToken for every tool invocation
* Validate token authenticity
* Verify token matches the action
* Verify token is unexpired and unconsumed
* Reject execution if any check fails

Any tool execution without a valid AuthorityToken is a **security violation**.

---

### 5.6 Policy

A Policy is a deterministic rule set defining:

* Allowed actions
* Forbidden actions
* Tool transition rules
* Escalation requirements
* Default-deny behavior

Policies are:

* Declarative
* Human-readable (YAML)
* Loaded at runtime
* Immutable during execution

---

## 6. High-Level Component Architecture

### 6.1 Core Components

* Intent Manager
* Plan Manager
* Provenance Manager
* Policy Engine
* Authority Manager
* Enforcement Gate
* Runtime State Machine
* Audit Logger

Each component has a **single, explicit responsibility**.

---

## 7. Component Specifications

### 7.1 Intent Manager

* Constructs intent objects
* Validates schema
* Enforces immutability
* Handles intent updates and resets

Failure behavior: reject malformed intent.

---

### 7.2 Plan Manager

* Accepts plan proposals
* Validates against intent
* Freezes approved plans
* Detects mutation

Failure behavior: deny execution.

---

### 7.3 Provenance Manager

* Assigns provenance labels
* Propagates provenance
* Prevents provenance escalation

Failure behavior: default to `EXTERNAL_UNTRUSTED`.

---

### 7.4 Policy Engine

* Loads policy files
* Evaluates rules deterministically
* Resolves conflicts via defined precedence
* Returns `ALLOW`, `DENY`, or `ESCALATE`

Failure behavior: deny.

---

### 7.5 Authority Manager

* Issues AuthorityTokens
* Tracks expiration
* Prevents reuse
* Revokes tokens on violations

Failure behavior: deny.

---

### 7.6 Enforcement Gate

* Intercepts all tool calls
* Requires AuthorityToken
* Executes or blocks
* Emits audit logs

Failure behavior: block execution.

---

## 8. Runtime State Machine (Explicit)

Valid states:

* `INITIALIZED`
* `INTENT_SET`
* `PLAN_APPROVED`
* `EXECUTING`
* `ESCALATION_REQUIRED`
* `TERMINATED`

Illegal transitions are rejected.

---

## 9. Control Flow

### 9.1 Normal Flow

1. Initialize runtime
2. Set intent
3. Agent proposes plan
4. Plan approved
5. Agent requests action
6. Policy evaluated
7. AuthorityToken issued
8. Tool executed via Enforcement Gate
9. Result tagged with provenance
10. Loop continues

---

### 9.2 Escalation Flow

* Policy returns `ESCALATE`
* Runtime enters `ESCALATION_REQUIRED`
* Application requests user confirmation
* Approval resumes execution
* Denial terminates session

---

## 10. Error Model (Normative)

Typed errors:

* `IntentError`
* `PlanError`
* `PolicyDenyError`
* `EscalationRequiredError`
* `AuthorityExpiredError`
* `UnauthorizedActionError`

Errors are deterministic and explicit.

---

## 11. Installation & Packaging

### 11.1 Initial Language Target

* Python (v1)

---

### 11.2 Distribution

* Installable via `pip`
* No external services
* No network dependencies

---

## 12. Repository Structure (Required)

```
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
│   ├── cli/
│   ├── audit/
│   └── reference_agent/
├── policies/
├── tests/
└── docs/
```

---

## 13. Configuration Model

### 13.1 Policy Files

Policies are defined in YAML:

* Allowed actions
* Forbidden actions
* Tool transitions
* Escalation rules

---

### 13.2 Runtime Configuration

Controls:

* Enforcement mode (disabled / observe / enforce)
* Policy paths
* Logging behavior

---

## 14. CLI (Optional)

CLI supports:

* Policy validation
* Policy simulation
* Attack test execution
* Audit inspection

CLI is optional in production.

---

## 15. Developer Usage Model (Normative)

Developers must:

1. Install APE
2. Load policy configuration
3. Initialize APE runtime
4. Construct intent
5. Submit agent plan
6. Route all actions through APE
7. Execute tools **only** with AuthorityToken

---

## 16. Testing Architecture

### 16.1 Test Categories

* Unit tests
* Integration tests
* Threat simulations
* Regression tests

---

## 17. Non-Goals

APE does not:

* Interpret natural language
* Modify prompts
* Enforce ethics or values
* Control model internals

APE enforces **authority, not cognition**.

---

## 18. Open Source Strategy

APE is open source to:

* Enable review
* Encourage standardization
* Prevent fragmented solutions
* Improve ecosystem security

---

## 19. Summary

The Agent Policy Engine provides:

* Explicit intent
* Deterministic policy
* Enforced authority via AuthorityToken
* Auditable execution
* A missing security layer for agent systems

APE restores the fundamental boundary between **reasoning** and **power**.

---
