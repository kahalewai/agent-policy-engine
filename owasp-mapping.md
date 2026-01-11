# **Agent Policy Engine (APE) mapped to OWASP Top 10 LLM Risks**

This document analyzes the security coverage of the **Agent Policy Engine (APE)** against the OWASP Top 10 LLM 2025 risks. It focuses on how APE components interact deterministically to enforce authority, policy, and state integrity.

<br>

| Risk Category                     | Mitigation Status     |
| --------------------------------- | --------------------- |
| LLM01 Prompt Injection            | ✅ Strong              |
| LLM02 Sensitive Info Disclosure   | ⚠️ Partial            |
| LLM03 Supply Chain                | ⚠️ Partial / indirect |
| LLM04 Data/Model Poisoning        | ⚠️ Partial            |
| LLM05 Improper Output Handling    | ⚠️ Partial            |
| LLM06 Excessive Agency            | ✅ Strong              |
| LLM07 System Prompt Leakage       | ⚠️ Partial            |
| LLM08 Vector/Embedding Weaknesses | ⚠️ Minimal            |
| LLM09 Misinformation              | ⚠️ Indirect           |
| LLM10 Unbounded Consumption       | ✅ Strong              |

<br>

* **APE excels at operational enforcement:** Authority, deterministic execution, token lifecycle, policy evaluation, and state-machine governance.
* **Risks outside the execution layer remain partially or fully outside scope:** LLM outputs, embeddings, model poisoning, prompt confidentiality, and supply chain integrity.
* **Indirect protection:** Even for out-of-scope risks, APE **prevents unsafe execution**—meaning malicious instructions, poisoned vectors, or misinformation cannot trigger harmful actions.

<br>

APE strongly mitigates 3 of the 10 OWASP Top 10 LLM Risks, providing a **robust, deterministic enforcement layer** for LLM agents, turning probabilistic reasoning into safe, auditable, and capability-bound actions. While not a substitute for output validation, model vetting, or content filtering, APE is a **foundational security layer** that enforces the “execution-only” principle for AI agents.

<br>

## **LLM01: Prompt Injection**

**Risk Overview:**
Malicious or unexpected inputs instruct the LLM to perform unintended actions, including leaking secrets, executing unauthorized plans, or bypassing policies.

**APE Mitigation:**

APE enforces **deterministic authority separation**:

1. **Runtime Controller:** Ensures that no action can execute unless explicitly authorized by AuthorityToken. Any plan proposed by the LLM is blocked unless it matches intent and passes validation.
2. **Intent Manager & Plan Manager:** Canonically serialize and hash intents and plans. Any deviation introduced by injected prompts breaks hash bindings, invalidating AuthorityTokens.
3. **Policy Engine:** Evaluates proposed actions against allowed rules. Any plan step influenced by a malicious prompt that violates policy results in `DENY` or `ESCALATE`.
4. **Enforcement Gate:** Intercepts all tool calls; without a valid AuthorityToken, execution cannot proceed. Even if the LLM suggests malicious actions, they are blocked deterministically.
5. **Provenance Manager:** Labels all user/external content. `EXTERNAL_UNTRUSTED` content can inform reasoning but **cannot influence authority issuance**.

**Effectiveness:** ✅ Strong mitigation. APE’s deterministic bindings ensure that injected instructions cannot bypass policy or gain authority.

<br>

## **LLM02: Sensitive Information Disclosure**

**Risk Overview:**
LLMs may expose sensitive information through outputs or logs.

**APE Mitigation:**

* **Scope Enforcement:** AuthorityTokens are **never serialized or transmitted**. They cannot be exfiltrated, even if an LLM suggests leaking them.
* **Provenance Manager:** Prevents EXTERNAL_UNTRUSTED content from gaining authority that could result in sensitive data operations.
* **Audit Logger:** Provides traceable records of actions, aiding detection of attempts to access sensitive operations.

**Limitations / Out of Scope:**
APE does not sanitize LLM outputs; disclosure of sensitive content from the LLM itself remains possible. However, **APE ensures that sensitive operations cannot be executed or escalated without proper authority**, reducing risk of system-level leakage.

**Effectiveness:** ✅ Partial mitigation; operational leaks prevented, output leakage outside APE’s scope.

<br>

## **LLM03: Supply Chain Vulnerabilities**

**Risk Overview:**
External models, datasets, plugins, or libraries may introduce hidden risks (e.g., backdoors, compromised logic).

**APE Mitigation:**

* **Policy Engine & Enforcement Gate:** Any action originating from compromised components must still pass authority checks. Unauthorized plans cannot execute.
* **Schema Validation:** Ensures that data and plans from external sources conform to expected formats, limiting malformed data abuse.
* **Formal Verification Exporter:** Enables static security review of policies and rules, which can catch unsafe interactions with third-party components.

**Limitations / Out of Scope:**
APE does not vet external models or runtime dependencies; supply chain integrity is primarily outside its design. Mitigation is **indirect**, via deterministic enforcement and validation of any attempted action.

**Effectiveness:** ⚠️ Partial / indirect mitigation; execution enforcement reduces impact, but supply chain risk itself is external.

<br>

## **LLM04: Data and Model Poisoning**

**Risk Overview:**
Malicious training or fine-tuning data may compromise reasoning or output quality.

**APE Mitigation:**

* **Authority Binding:** Actions, plans, and intents are cryptographically hashed. Poisoned input cannot generate valid AuthorityTokens unless aligned with policy.
* **Provenance Manager:** EXTERNAL_UNTRUSTED data cannot create, modify, or escalate authority.
* **Runtime Controller:** Prevents execution if plan hash or intent hash does not match approved state.

**Limitations / Out of Scope:**
APE cannot detect reasoning bias or poisoned model outputs; it only prevents poisoned content from directly triggering unauthorized actions.

**Effectiveness:** ⚠️ Partial mitigation; prevents operational consequences, but reasoning bias is outside APE’s scope.

<br>

## **LLM05: Improper Output Handling**

**Risk Overview:**
Model outputs used without validation may lead to exploits, unsafe behavior, or security violations.

**APE Mitigation:**

* **Schema Validators:** Ensure that all plan and intent objects conform to required formats before execution.
* **Enforcement Gate & AuthorityTokens:** Prevent any action derived from malformed outputs from executing.
* **Audit Logger:** Tracks execution and tool usage, enabling detection of misuse.

**Limitations / Out of Scope:**
APE does not filter or validate outputs delivered to end users. Output handling beyond authority control remains the responsibility of surrounding application logic.

**Effectiveness:** ⚠️ Partial mitigation; execution enforcement ensures outputs cannot cause unauthorized action, but user-facing output risks remain.

<br>

## **LLM06: Excessive Agency**

**Risk Overview:**
LLMs acting with unchecked autonomy can perform harmful actions without oversight.

**APE Mitigation:**

* **Capability-Based Authority:** Only a valid, single-use AuthorityToken allows tool execution.
* **Runtime State Machine:** Execution is allowed only in `EXECUTING` state; all other states block action.
* **Policy Engine & Enforcement Gate:** Policies define allowed transitions and escalation requirements, preventing autonomous execution.
* **AuthorityManager:** Ensures tokens cannot be reused or forged, preventing unintended chaining of autonomous actions.

**Effectiveness:** ✅ Strong mitigation; LLM autonomy is fully constrained by deterministic authority enforcement.

<br>

## **LLM07: System Prompt Leakage**

**Risk Overview:**
Internal system prompts or instructions may be exposed to users or attackers.

**APE Mitigation:**

* **Provenance Enforcement:** EXTERNAL_UNTRUSTED content cannot gain authority from prompt data.
* **AuthorityTokens & Enforcement Gate:** Even if prompts are leaked, no execution path can be triggered without token validation.
* **Audit Logger:** Helps detect abnormal access patterns related to prompt use.

**Limitations / Out of Scope:**
APE does not actively prevent prompts from being output by the LLM. Leakage is technically possible, but **impact is minimized** as leaked prompts cannot control execution.

**Effectiveness:** ⚠️ Partial mitigation; operational security preserved, source confidentiality outside APE scope.

<br>

## **LLM08: Vector and Embedding Weaknesses**

**Risk Overview:**
Manipulation of embeddings or vector stores may bias context retrieval or action selection.

**APE Mitigation:**

* **Policy Engine & AuthorityTokens:** Even if retrieved vectors suggest unsafe actions, execution is blocked unless plan + intent validation passes.
* **Provenance Manager:** Flags external sources; untrusted vectors cannot grant authority.

**Limitations / Out of Scope:**
APE does not inspect or sanitize embeddings. Reasoning layer vulnerabilities are outside its design. APE mitigates only **operational execution** impact.

**Effectiveness:** ⚠️ Minimal mitigation; prevents misuse of authority but cannot prevent reasoning-level manipulation.

<br>

## **LLM09: Misinformation**

**Risk Overview:**
LLMs may produce incorrect or misleading content that appears authoritative.

**APE Mitigation:**

* **Authority Binding:** Only actions conforming to validated intent and plan can execute.
* **Policy Engine:** Any plan suggesting dangerous operations based on misinformation will be denied unless explicitly allowed.
* **Audit Logger:** Provides traceability, supporting detection of repeated anomalous patterns.

**Limitations / Out of Scope:**
APE cannot prevent the LLM from generating false content. Only **operational misuse** is controlled.

**Effectiveness:** ⚠️ Indirect mitigation; ensures false outputs do not translate into unauthorized actions.

<br>

## **LLM10: Unbounded Consumption**

**Risk Overview:**
Excessive token use, API calls, or action execution may cause resource exhaustion or denial-of-service.

**APE Mitigation:**

* **AuthorityTokens:** Single-use, bound to plan step; prevents repeated or infinite execution loops.
* **Runtime State Machine:** Execution only allowed in `EXECUTING`; illegal transitions rejected deterministically.
* **Policy Engine:** Can limit allowed actions and enforce default-deny.
* **Multi-Tenant Mode:** Optional isolation prevents one tenant from affecting another’s resource usage.

**Effectiveness:** ✅ Strong mitigation; deterministic enforcement ensures controlled consumption of actions and prevents runaway execution.

<br>

Back to https://github.com/kahalewai/agent-policy-engine
