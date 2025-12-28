Below are **5 real-world, production-useful example policies**, designed to be **safe by default**, easy to understand, and immediately usable.

Each one:

* Solves a **common agent use case**
* Demonstrates a **security pattern**
* Is conservative (default-deny)
* Is meant to be **copied and modified**, not blindly trusted

---

## 1. `example_minimal_safe.yaml`

### *“Start here” policy*

**Use case**

* First-time users
* Proof-of-concept agents
* Learning APE safely

**Security posture**

* Read-only actions allowed
* Any side effect requires escalation
* Destructive actions forbidden

```yaml
# example_minimal_safe.yaml
# Minimal, conservative starting policy

allowed_actions:
  - read_file
  - list_directory
  - fetch_url

escalation_required:
  - write_file
  - send_email
  - run_command

forbidden_actions:
  - delete_file
  - delete_directory
  - drop_database
```

**Why this is useful**

* Forces developers to *think* before adding authority
* Makes escalation a first-class concept
* Very hard to misuse accidentally

---

## 2. `example_read_only_agent.yaml`

### *Inspection, analysis, reporting*

**Use case**

* Observability agents
* Log analysis
* Compliance review
* Data exploration

**Security posture**

* Zero mutation
* Zero side effects
* Extremely safe in production

```yaml
# example_read_only_agent.yaml
# Agent may observe but not change the system

allowed_actions:
  - read_file
  - list_directory
  - fetch_url
  - query_database
  - generate_report

escalation_required: []

forbidden_actions:
  - write_file
  - delete_file
  - modify_database
  - send_email
  - run_command
```

**Why this is useful**

* Can be deployed almost anywhere
* Ideal for regulated environments
* Demonstrates how powerful agents can be *without* write access

---

## 3. `example_filesystem_scoped.yaml`

### *Config editors, refactoring agents*

**Use case**

* Code modification agents
* Configuration management
* Build or CI assistants

**Security posture**

* Controlled mutation
* Destructive actions forbidden
* Explicit escalation for risky operations

```yaml
# example_filesystem_scoped.yaml
# Controlled file-system modification policy

allowed_actions:
  - read_file
  - write_file
  - list_directory

escalation_required:
  - overwrite_file
  - move_file
  - run_command

forbidden_actions:
  - delete_file
  - delete_directory
  - format_disk
```

**Why this is useful**

* Matches real-world developer workflows
* Prevents catastrophic mistakes
* Encourages fine-grained action design

---

## 4. `example_human_in_the_loop.yaml`

### *Approval-driven enterprise agents*

**Use case**

* Enterprise workflows
* Customer communication
* Change management
* Risk-sensitive automation

**Security posture**

* Most actions require approval
* Clear separation of autonomy vs authority

```yaml
# example_human_in_the_loop.yaml
# Designed for explicit human approval

allowed_actions:
  - propose_plan
  - simulate_action
  - generate_summary

escalation_required:
  - send_email
  - write_file
  - modify_database
  - call_external_api

forbidden_actions:
  - delete_database
  - delete_file
  - run_unrestricted_command
```

**Why this is useful**

* Very easy to explain to auditors
* Aligns with real enterprise controls
* Demonstrates escalation as a *feature*, not a failure

---

## 5. `example_network_restricted.yaml`

### *Agents with strict outbound controls*

**Use case**

* Security-sensitive environments
* Air-gapped or semi-gapped systems
* Data exfiltration prevention

**Security posture**

* Explicit network allow-listing
* Everything else denied

```yaml
# example_network_restricted.yaml
# Strict network access policy

allowed_actions:
  - fetch_internal_api
  - read_file
  - write_file

escalation_required:
  - fetch_external_api
  - send_email

forbidden_actions:
  - open_socket
  - start_server
  - upload_data
```

**Why this is useful**

* Prevents silent data leaks
* Clear boundary between internal and external systems
* Extremely relevant for regulated industries

---

# How These Examples Fit APE’s Philosophy

These examples:

* Do **not** weaken security
* Do **not** bypass enforcement
* Do **not** assume trust in the agent
* Make policy intent *obvious*
* Encourage least privilege by default

They also serve as:

* Templates
* Teaching tools
* Shared vocabulary across teams

---

# Strong Recommendation

Ship **3–5 example policies** exactly like this in:

```
policies/
  example_minimal_safe.yaml
  example_read_only_agent.yaml
  example_filesystem_scoped.yaml
  example_human_in_the_loop.yaml
  example_network_restricted.yaml
```

Document them as:

> “Safe starting points — copy, modify, tighten.”

This dramatically improves:

* Developer onboarding
* Correct usage
* Real-world adoption
* Long-term security outcomes

