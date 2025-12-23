# OWASP Risk Coverage — Agent Policy Engine (APE)  — OWASP Top 10 for LLM Applications

### **LLM01: Prompt Injection**

**Status:** ✅ **Strongly Mitigated**

**Risk**
Untrusted input manipulates the model into executing unintended actions.

**How APE Mitigates**

* Explicit intent (machine-readable)
* Data is never authority
* Provenance labeling
* Default-deny execution
* Enforcement gate blocks unauthorized actions

**Why This Matters**
Prompt injection becomes **non-fatal** when language cannot grant authority.

---

### **LLM02: Insecure Output Handling**

**Status:** ✅ **Mitigated**

**Risk**
LLM outputs are trusted blindly and fed into tools or systems.

**How APE Mitigates**

* Outputs do not directly trigger actions
* Actions must be pre-declared in a plan
* AuthorityTokens required for execution
* Schema validation prevents malformed actions

---

### **LLM03: Training Data Poisoning**

**Status:** ⚠️ **Partially Mitigated (Scope-Limited)**

**Risk**
Model behavior influenced by poisoned training data.

**APE Position**

* APE does **not** control model training
* APE prevents poisoned behavior from gaining authority

**Net Effect**
Even if the model is poisoned, **damage is contained**.

---

### **LLM04: Model Denial of Service**

**Status:** ❌ **Out of Scope**

**Risk**
Excessive or malicious usage exhausts model resources.

**APE Position**

* Not a rate-limiting or infra tool
* Should be handled at platform level

---

### **LLM05: Supply Chain Vulnerabilities**

**Status:** ⚠️ **Indirectly Mitigated**

**Risk**
Compromised dependencies or tools return malicious data.

**How APE Helps**

* External tool output marked untrusted
* Data cannot expand authority
* Tool calls still require explicit authorization

---

### **LLM06: Sensitive Information Disclosure**

**Status:** ⚠️ **Partially Mitigated**

**Risk**
Agents leak secrets or sensitive data.

**How APE Helps**

* Explicit action control (e.g., forbid exfiltration tools)
* Policy can block data-export actions
* Audit logging provides traceability

**Note**
APE enforces *authority*, not data classification.

---

### **LLM07: Insecure Plugin / Tool Design**

**Status:** ✅ **Strongly Mitigated**

**Risk**
Tools/plugins expose dangerous capabilities.

**How APE Mitigates**

* Tools cannot be called directly
* Enforcement gate requires AuthorityToken
* Policy restricts tool usage
* Immutable plans prevent hidden calls

---

### **LLM08: Excessive Agency**

**Status:** ✅ **Directly Solved**

**Risk**
Agents act beyond intended autonomy.

**How APE Solves This**

* Explicit intent
* Immutable plans
* Escalation requirements
* Single-use authority tokens

**This is one of APE’s primary design goals.**

---

### **LLM09: Overreliance on LLMs**

**Status:** ⚠️ **Partially Mitigated**

**Risk**
Critical decisions delegated entirely to models.

**How APE Helps**

* Separates reasoning from authority
* Enforcement is deterministic
* Model decisions are advisory only

---

### **LLM10: Improper Access Control**

**Status:** ✅ **Directly Solved**

**Risk**
LLMs lack traditional access control enforcement.

**How APE Solves This**

* Action-level authorization
* Policy-driven enforcement
* Tenant isolation
* Mandatory execution gates

---

### ✅ Summary — OWASP LLM Top 10

| Risk                   | Coverage       |
| ---------------------- | -------------- |
| LLM01 Prompt Injection | ✅ Strong       |
| LLM02 Insecure Output  | ✅ Strong       |
| LLM03 Data Poisoning   | ⚠️ Containment |
| LLM04 DoS              | ❌ Out of scope |
| LLM05 Supply Chain     | ⚠️ Partial     |
| LLM06 Data Disclosure  | ⚠️ Partial     |
| LLM07 Insecure Tools   | ✅ Strong       |
| LLM08 Excessive Agency | ✅ Strong       |
| LLM09 Overreliance     | ⚠️ Partial     |
| LLM10 Access Control   | ✅ Strong       |

---

> **APE does not try to solve every security problem.**
> It solves the *agent-specific* ones that traditional security models miss.

APE is best described as:

> **An access control and authority enforcement layer for AI agents**

It **directly addresses** the most dangerous OWASP LLM risks:

* Prompt injection
* Excessive agency
* Insecure tool usage
* Broken access control

And it **contains** the blast radius of others.

---
