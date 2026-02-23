"""
APE Command Line Interface

CLI):
- Policy validation
- Policy simulation
- Attack test execution
- Audit inspection
- Verification export

CLI guarantees:
- Deterministic exit codes
- Typed error output
- Read-only safety (no authority issuance)

Exit codes:
- 0: Success
- 1: General error
- 2: Policy error
- 3: Validation error
- 4: File not found
"""

import argparse
import sys
import json
import textwrap
from pathlib import Path
from typing import Optional

from ape.policy.engine import PolicyEngine, PolicyDecision, validate_policy_file
from ape.errors import PolicyError, PolicyDenyError, EscalationRequiredError


# Exit codes
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_POLICY_ERROR = 2
EXIT_VALIDATION_ERROR = 3
EXIT_FILE_NOT_FOUND = 4


# =============================================================================
# Visual Formatting Helpers
# =============================================================================

# Unicode box-drawing and symbols
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
WHITE = "\033[37m"

CHECK = "✓"
CROSS = "✗"
WARN = "⚠"
ARROW = "→"
BULLET = "•"
SHIELD = "🛡"
BOX_H = "─"
BOX_V = "│"
BOX_TL = "┌"
BOX_TR = "┐"
BOX_BL = "└"
BOX_BR = "┘"
BOX_LT = "├"
BOX_RT = "┤"


def _header(title: str, width: int = 60) -> str:
    """Create a styled header box."""
    pad = width - len(title) - 4
    left_pad = pad // 2
    right_pad = pad - left_pad
    lines = [
        f"{BOX_TL}{BOX_H * (width - 2)}{BOX_TR}",
        f"{BOX_V}{' ' * left_pad} {title} {' ' * right_pad}{BOX_V}",
        f"{BOX_BL}{BOX_H * (width - 2)}{BOX_BR}",
    ]
    return "\n".join(lines)


def _section(title: str, width: int = 60) -> str:
    """Create a section divider."""
    return f"\n{BOX_LT}{BOX_H * 2} {title} {BOX_H * max(1, width - len(title) - 5)}{BOX_RT}"


def _kv(key: str, value: str, indent: int = 2) -> str:
    """Format a key-value pair."""
    return f"{' ' * indent}{DIM}{key}:{RESET} {value}"


def _status(symbol: str, color: str, text: str) -> str:
    """Format a status line."""
    return f"  {color}{symbol}{RESET} {text}"


def _next_steps(steps: list[str]) -> str:
    """Format a next-steps section."""
    lines = [f"\n{DIM}{BOX_LT}{BOX_H}{BOX_H} Next Steps {BOX_H * 44}{BOX_RT}{RESET}"]
    for i, step in enumerate(steps, 1):
        lines.append(f"  {DIM}{i}.{RESET} {step}")
    return "\n".join(lines)


def _banner() -> str:
    """Get the APE banner."""
    return f"""{BOLD}
   ╔════════════════════════════════════════════╗
   ║            Agent Policy Engine             ║
   ║   Policy Enforcement Point for AI Agents   ║
   ╚════════════════════════════════════════════╝{RESET}
"""


# =============================================================================
# Command Handlers
# =============================================================================

def cmd_validate(args: argparse.Namespace) -> int:
    """Validate a policy file."""
    print(_header("Policy Validation"))
    print(f"\n  Validating: {CYAN}{args.policy}{RESET}\n")

    errors = validate_policy_file(args.policy)

    if errors:
        print(_status(CROSS, RED, f"{RED}VALIDATION FAILED{RESET}"))
        print()
        for error in errors:
            print(f"    {RED}{BULLET}{RESET} {error}")
        print()
        print(_next_steps([
            "Fix the errors listed above",
            f"Run {CYAN}ape validate {args.policy}{RESET} again",
        ]))
        return EXIT_VALIDATION_ERROR

    # Load to get details for the report
    try:
        engine = PolicyEngine(args.policy)
        policy = engine.policy
    except PolicyError:
        policy = None

    print(_status(CHECK, GREEN, f"{GREEN}VALID{RESET} — Policy file passed all checks"))
    print()
    print(f"  {DIM}Checks performed:{RESET}")
    print(f"    {CHECK} YAML syntax is valid")
    print(f"    {CHECK} Schema structure is correct")
    print(f"    {CHECK} Required fields present (allowed_actions, forbidden_actions)")
    print(f"    {CHECK} No overlapping allowed/forbidden actions")
    if policy and policy.rules:
        print(f"    {CHECK} Rule conditions syntax validated")

    if policy:
        print(f"\n  {DIM}Policy summary:{RESET}")
        if policy.name:
            print(_kv("Name", policy.name, 4))
        print(_kv("Default Deny", str(policy.default_deny), 4))
        print(_kv("Allowed", str(len(policy.allowed_actions)), 4))
        print(_kv("Forbidden", str(len(policy.forbidden_actions)), 4))
        print(_kv("Escalation", str(len(policy.escalation_required)), 4))

    print(_next_steps([
        f"View full details: {CYAN}ape info {args.policy}{RESET}",
        f"Test actions: {CYAN}ape simulate {args.policy} <action_id>{RESET}",
        f"Test prompts: {CYAN}ape test-prompt {args.policy} \"your prompt\"{RESET}",
    ]))
    return EXIT_SUCCESS


def cmd_simulate(args: argparse.Namespace) -> int:
    """Simulate policy evaluation for an action."""
    print(_header("Policy Simulation"))
    print(f"\n  Policy: {CYAN}{args.policy}{RESET}")
    print(f"  Action: {CYAN}{args.action}{RESET}\n")

    try:
        engine = PolicyEngine(args.policy)
        result = engine.evaluate(args.action)

        if result.decision == PolicyDecision.ALLOW:
            print(_status(CHECK, GREEN, f"{args.action}: {GREEN}ALLOW{RESET}"))
            print(f"    {DIM}Reason: {result.reason}{RESET}")
        elif result.decision == PolicyDecision.ESCALATE:
            print(_status(WARN, YELLOW, f"{args.action}: {YELLOW}ESCALATE{RESET}"))
            print(f"    {DIM}Reason: {result.reason}{RESET}")
        else:
            print(_status(CROSS, RED, f"{args.action}: {RED}DENY{RESET}"))
            print(f"    {DIM}Reason: {result.reason}{RESET}")

        print(_next_steps([
            f"Test multiple: {CYAN}ape simulate-batch {args.policy} action1 action2 ...{RESET}",
            f"View policy: {CYAN}ape info {args.policy}{RESET}",
        ]))
        return EXIT_SUCCESS

    except PolicyError as e:
        print(f"  {RED}POLICY_ERROR:{RESET} {e}")
        return EXIT_POLICY_ERROR


def cmd_simulate_batch(args: argparse.Namespace) -> int:
    """Simulate policy evaluation for multiple actions."""
    print(_header("Batch Policy Simulation"))

    try:
        engine = PolicyEngine(args.policy)

        # Read actions from file or args
        if args.actions_file:
            with open(args.actions_file) as f:
                actions = [line.strip() for line in f if line.strip()]
        else:
            actions = args.actions

        if not actions:
            print(f"\n  {RED}No actions specified.{RESET}")
            print(f"  Usage: {CYAN}ape simulate-batch policy.yaml action1 action2 ...{RESET}")
            return EXIT_ERROR

        print(f"\n  Policy: {CYAN}{args.policy}{RESET}")
        print(f"  Actions: {len(actions)}\n")

        if args.json:
            output = []
            for action_id in actions:
                result = engine.evaluate(action_id)
                output.append({
                    "action": result.action_id,
                    "decision": result.decision.value,
                    "reason": result.reason,
                })
            print(json.dumps(output, indent=2))
            return EXIT_SUCCESS

        results = engine.simulate(actions)

        allowed = denied = escalated = 0
        for result in results:
            if result.is_allowed():
                print(_status(CHECK, GREEN, f"{result.action_id}: {GREEN}ALLOW{RESET}"))
                allowed += 1
            elif result.requires_escalation():
                print(_status(WARN, YELLOW, f"{result.action_id}: {YELLOW}ESCALATE{RESET}"))
                escalated += 1
            else:
                print(_status(CROSS, RED, f"{result.action_id}: {RED}DENY{RESET}"))
                denied += 1

        print(f"\n  {DIM}Summary:{RESET} "
              f"{GREEN}{allowed} allowed{RESET}, "
              f"{RED}{denied} denied{RESET}, "
              f"{YELLOW}{escalated} escalate{RESET}")

        print(_next_steps([
            f"View detailed policy: {CYAN}ape info {args.policy}{RESET}",
            f"Compare policies: {CYAN}ape diff policy1.yaml policy2.yaml{RESET}",
        ]))
        return EXIT_SUCCESS

    except PolicyError as e:
        print(f"\n  {RED}POLICY_ERROR:{RESET} {e}")
        return EXIT_POLICY_ERROR


def cmd_info(args: argparse.Namespace) -> int:
    """Show information about a policy."""
    try:
        engine = PolicyEngine(args.policy)
        policy = engine.policy

        if args.json:
            output = {
                "version": engine.version,
                "name": policy.name,
                "description": policy.description,
                "default_deny": policy.default_deny,
                "allowed_actions": sorted(policy.allowed_actions),
                "forbidden_actions": sorted(policy.forbidden_actions),
                "escalation_required": sorted(policy.escalation_required),
            }
            if policy.rules:
                output["rules"] = [
                    {"action": r.action, "decision": r.decision, "conditions": r.conditions}
                    for r in policy.rules
                ]
            print(json.dumps(output, indent=2))
            return EXIT_SUCCESS

        print(_header("Policy Information"))
        print()
        print(_kv("File", args.policy))
        print(_kv("Version", f"{engine.version[:16]}..."))
        if policy.name:
            print(_kv("Name", policy.name))
        if policy.description:
            desc = policy.description.strip()
            if len(desc) > 70:
                desc = desc[:67] + "..."
            print(_kv("Description", desc))
        print(_kv("Default Deny", f"{GREEN}Yes{RESET}" if policy.default_deny else f"{RED}No{RESET}"))

        # Allowed actions
        print(_section(f"Allowed Actions ({len(policy.allowed_actions)})"))
        for action in sorted(policy.allowed_actions):
            print(f"  {GREEN}{CHECK}{RESET} {action}")

        # Forbidden actions
        print(_section(f"Forbidden Actions ({len(policy.forbidden_actions)})"))
        for action in sorted(policy.forbidden_actions):
            print(f"  {RED}{CROSS}{RESET} {action}")

        # Escalation
        if policy.escalation_required:
            print(_section(f"Escalation Required ({len(policy.escalation_required)})"))
            for action in sorted(policy.escalation_required):
                print(f"  {YELLOW}{WARN}{RESET} {action}")

        # Rules with conditions
        if policy.rules:
            print(_section(f"Conditional Rules ({len(policy.rules)})"))
            for rule in policy.rules:
                decision_color = GREEN if rule.decision == "allow" else RED
                print(f"  {decision_color}{rule.decision.upper()}{RESET} {rule.action}")
                if rule.conditions:
                    for param, constraints in rule.conditions.items():
                        print(f"    {DIM}{param}: {constraints}{RESET}")

        # Tool transitions
        if policy.tool_transitions:
            print(_section("Tool Transitions"))
            for from_tool, to_tools in policy.tool_transitions.items():
                print(f"  {from_tool} {ARROW} {', '.join(to_tools)}")

        print(_next_steps([
            f"Test actions: {CYAN}ape simulate {args.policy} <action_id>{RESET}",
            f"Test prompts: {CYAN}ape test-prompt {args.policy} \"your prompt\"{RESET}",
            f"Compare: {CYAN}ape diff {args.policy} other_policy.yaml{RESET}",
        ]))
        return EXIT_SUCCESS

    except PolicyError as e:
        print(f"  {RED}POLICY_ERROR:{RESET} {e}")
        return EXIT_POLICY_ERROR


def cmd_diff(args: argparse.Namespace) -> int:
    """Compare two policy files."""
    print(_header("Policy Comparison"))

    try:
        engine1 = PolicyEngine(args.policy1)
        engine2 = PolicyEngine(args.policy2)
        p1 = engine1.policy
        p2 = engine2.policy

        print(f"\n  Policy A: {CYAN}{args.policy1}{RESET}")
        print(f"  Policy B: {CYAN}{args.policy2}{RESET}\n")

        # Compare allowed actions
        a1 = set(p1.allowed_actions)
        a2 = set(p2.allowed_actions)
        only_a = sorted(a1 - a2)
        only_b = sorted(a2 - a1)
        both = sorted(a1 & a2)

        print(_section("Allowed Actions"))
        if both:
            print(f"  {DIM}In both ({len(both)}): {', '.join(both[:10])}{'...' if len(both) > 10 else ''}{RESET}")
        if only_a:
            print(f"  {RED}Only in A ({len(only_a)}):{RESET}")
            for a in only_a:
                print(f"    {RED}-{RESET} {a}")
        if only_b:
            print(f"  {GREEN}Only in B ({len(only_b)}):{RESET}")
            for a in only_b:
                print(f"    {GREEN}+{RESET} {a}")

        # Compare forbidden actions
        f1 = set(p1.forbidden_actions)
        f2 = set(p2.forbidden_actions)
        only_fa = sorted(f1 - f2)
        only_fb = sorted(f2 - f1)

        print(_section("Forbidden Actions"))
        if only_fa:
            print(f"  {RED}Only in A ({len(only_fa)}):{RESET}")
            for a in only_fa:
                print(f"    {RED}-{RESET} {a}")
        if only_fb:
            print(f"  {GREEN}Only in B ({len(only_fb)}):{RESET}")
            for a in only_fb:
                print(f"    {GREEN}+{RESET} {a}")
        if not only_fa and not only_fb:
            print(f"  {DIM}No differences{RESET}")

        # Compare settings
        print(_section("Settings"))
        if p1.default_deny != p2.default_deny:
            print(f"  {YELLOW}default_deny:{RESET} A={p1.default_deny}, B={p2.default_deny}")
        else:
            print(f"  {DIM}default_deny: same ({p1.default_deny}){RESET}")

        print(_next_steps([
            f"View either policy: {CYAN}ape info <policy.yaml>{RESET}",
        ]))
        return EXIT_SUCCESS

    except PolicyError as e:
        print(f"  {RED}POLICY_ERROR:{RESET} {e}")
        return EXIT_POLICY_ERROR


def cmd_test_prompt(args: argparse.Namespace) -> int:
    """Test a prompt through the full intent compilation pipeline."""
    print(_header("Prompt Compilation Test"))
    print(f"\n  Policy: {CYAN}{args.policy}{RESET}")
    print(f"  Prompt: {CYAN}\"{args.prompt}\"{RESET}\n")

    try:
        from ape.action_repository import create_standard_repository
        from ape.intent_compiler import IntentCompiler

        engine = PolicyEngine(args.policy)
        repo = create_standard_repository()
        compiler = IntentCompiler(repo)

        intent = compiler.compile(
            prompt=args.prompt,
            policy_allowed=engine.get_all_allowed_actions(),
            policy_forbidden=engine.get_all_forbidden_actions(),
        )

        print(_status(CHECK, GREEN, f"{GREEN}COMPILED SUCCESSFULLY{RESET}"))
        print()

        # Show allowed actions
        if intent.allowed_actions:
            print(f"  {DIM}Allowed Actions:{RESET}")
            for action in intent.allowed_actions:
                print(f"    {GREEN}{CHECK}{RESET} {action}")

        # Show escalation
        if intent.escalation_required:
            print(f"  {DIM}Requires Escalation:{RESET}")
            for action in intent.escalation_required:
                print(f"    {YELLOW}{WARN}{RESET} {action}")

        # Show forbidden
        if intent.forbidden_actions:
            print(f"  {DIM}Blocked by Policy:{RESET}")
            for action in intent.forbidden_actions:
                print(f"    {RED}{CROSS}{RESET} {action}")

        print()
        print(_kv("Scope", intent.scope))
        print(_kv("Confidence", f"{intent.confidence:.0%}"))

        if intent.narrowing_log:
            print(f"\n  {DIM}Narrowing Log:{RESET}")
            for entry in intent.narrowing_log:
                print(f"    {DIM}{BULLET} {entry}{RESET}")

        print(_next_steps([
            f"Analyze without policy: {CYAN}ape analyze \"{args.prompt}\"{RESET}",
            f"View available actions: {CYAN}ape actions --by-category{RESET}",
        ]))
        return EXIT_SUCCESS

    except Exception as e:
        error_type = type(e).__name__
        if "Ambiguity" in error_type:
            print(_status(CROSS, YELLOW, f"{YELLOW}AMBIGUOUS: Could not understand prompt{RESET}"))
        elif "Narrowing" in error_type:
            print(_status(CROSS, RED, f"{RED}BLOCKED: Policy doesn't allow any requested actions{RESET}"))
        else:
            print(_status(CROSS, RED, f"{RED}ERROR: {e}{RESET}"))

        print(f"    {DIM}{e}{RESET}")
        print(_next_steps([
            f"Analyze the prompt: {CYAN}ape analyze \"{args.prompt}\"{RESET}",
            f"View policy rules: {CYAN}ape info {args.policy}{RESET}",
            f"Try more specific language (e.g., \"Read the config.json file\")",
        ]))
        return EXIT_ERROR


def cmd_analyze(args: argparse.Namespace) -> int:
    """Analyze a prompt to see extracted signals and actions."""
    print(_header("Prompt Analysis"))
    print(f"\n  Prompt: {CYAN}\"{args.prompt}\"{RESET}\n")

    try:
        from ape.action_repository import create_standard_repository
        from ape.intent_compiler import IntentCompiler

        repo = create_standard_repository()
        compiler = IntentCompiler(repo)
        result = compiler.analyze(args.prompt)

        signals_count = result["signals_extracted"]
        candidates = result["candidate_actions"]

        if not candidates:
            print(_status(CROSS, YELLOW, f"{YELLOW}No signals extracted{RESET}"))
            print(f"    The prompt doesn't match any known action patterns.")
            print(f"    Try using more specific action words like 'read', 'write',")
            print(f"    'list', 'delete', 'query', 'send', 'fetch', etc.")
            print(_next_steps([
                f"View all known actions: {CYAN}ape actions{RESET}",
                f"View actions by category: {CYAN}ape actions --by-category{RESET}",
            ]))
            return EXIT_SUCCESS

        print(f"  {DIM}Signals extracted:{RESET} {signals_count}")
        print(f"  {DIM}Candidate actions:{RESET} {len(candidates)}")
        print(f"  {DIM}Inferred scope:{RESET} {result['inferred_scope']}")

        print(_section(f"Candidate Actions ({len(candidates)})"))
        for action in sorted(candidates, key=lambda a: a["max_confidence"], reverse=True):
            conf_pct = f"{action['max_confidence']:.0%}"
            risk_color = GREEN if action["risk_level"] in ("minimal", "low") else YELLOW if action["risk_level"] == "moderate" else RED
            print(f"  {CYAN}{action['action_id']}{RESET} "
                  f"({risk_color}{action['risk_level']}{RESET}) "
                  f"— confidence: {conf_pct}")
            print(f"    {DIM}{action['description']}{RESET}")
            triggers = action.get("triggers", [])
            if triggers:
                print(f"    {DIM}Matched: \"{triggers[0]}\"{RESET}")

        print(_next_steps([
            f"Test with policy: {CYAN}ape test-prompt policy.yaml \"{args.prompt}\"{RESET}",
            f"View all actions: {CYAN}ape actions --by-category{RESET}",
        ]))
        return EXIT_SUCCESS

    except Exception as e:
        print(f"  {RED}ERROR:{RESET} {e}")
        return EXIT_ERROR


def cmd_actions(args: argparse.Namespace) -> int:
    """List actions in the Action Repository."""
    print(_header("Action Repository"))

    try:
        from ape.action_repository import create_standard_repository, ActionCategory

        repo = create_standard_repository()
        print(f"\n  {DIM}Total actions:{RESET} {repo.count}\n")

        if args.by_category:
            for category in ActionCategory:
                actions = repo.get_by_category(category)
                if not actions:
                    continue
                cat_color = {
                    "file_read": GREEN,
                    "file_write": YELLOW,
                    "file_delete": RED,
                    "network": CYAN,
                    "database_read": BLUE,
                    "database_write": MAGENTA,
                    "system": RED,
                    "communication": CYAN,
                    "compute": MAGENTA,
                }.get(category.value, WHITE)

                print(f"  {cat_color}{BOLD}{category.value.upper()}{RESET} ({len(actions)})")
                for defn in sorted(actions, key=lambda d: d.action_id):
                    risk_color = GREEN if defn.risk_level.value in ("minimal", "low") else YELLOW if defn.risk_level.value == "moderate" else RED
                    print(f"    {risk_color}{BULLET}{RESET} {defn.action_id} "
                          f"{DIM}[{defn.risk_level.value}]{RESET} — {defn.description}")
                print()
        else:
            # BUG FIX: was using repo.all_actions which doesn't exist — use action_ids
            for action_id in sorted(repo.action_ids):
                defn = repo.get(action_id)
                risk_color = GREEN if defn.risk_level.value in ("minimal", "low") else YELLOW if defn.risk_level.value == "moderate" else RED
                print(f"  {risk_color}{BULLET}{RESET} {action_id} "
                      f"{DIM}[{defn.category.value} / {defn.risk_level.value}]{RESET}")
                print(f"    {DIM}{defn.description}{RESET}")

        print(_next_steps([
            f"Group by category: {CYAN}ape actions --by-category{RESET}",
            f"Analyze a prompt: {CYAN}ape analyze \"your prompt here\"{RESET}",
            "Register custom actions in your code with ActionRepository.register()",
        ]))
        return EXIT_SUCCESS

    except Exception as e:
        print(f"  {RED}ERROR:{RESET} {e}")
        return EXIT_ERROR


def cmd_generate_mocks(args: argparse.Namespace) -> int:
    """Generate mock tool implementations for testing."""
    print(_header("Mock Tool Generator"))
    print()
    print(f"  {DIM}Purpose:{RESET} Generates Python mock implementations for all actions")
    print(f"  {DIM}         in the Action Repository, useful for testing your APE{RESET}")
    print(f"  {DIM}         policies without real tool implementations.{RESET}\n")

    try:
        from ape.action_repository import create_standard_repository

        repo = create_standard_repository()
        lines = [
            '"""',
            'Auto-generated mock tools for APE testing.',
            '',
            'These mocks simulate tool behavior without performing real operations.',
            'Use them to test policies, intents, and plans safely.',
            '',
            'Usage:',
            '    from mock_tools import register_all_mocks',
            '    register_all_mocks(orchestrator)',
            '"""',
            '',
            '',
        ]

        # BUG FIX: was using repo.all_actions — use action_ids + get()
        for action_id in sorted(repo.action_ids):
            defn = repo.get(action_id)
            lines.append(f'def mock_{action_id}(**kwargs):')
            lines.append(f'    """Mock implementation of {action_id}: {defn.description}"""')
            lines.append(f'    return {{"status": "mock", "action": "{action_id}", "params": kwargs}}')
            lines.append('')
            lines.append('')

        # Registration helper
        lines.append('def register_all_mocks(orchestrator):')
        lines.append('    """Register all mock tools with an APE orchestrator."""')
        for action_id in sorted(repo.action_ids):
            lines.append(f'    orchestrator.register_tool("{action_id}", mock_{action_id})')
        lines.append('')

        content = '\n'.join(lines)

        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content)
            print(_status(CHECK, GREEN, f"Mock tools written to: {CYAN}{args.output}{RESET}"))
            print(f"\n  {DIM}Generated {repo.count} mock functions{RESET}")
        else:
            print(content)

        print(_next_steps([
            "Import the mocks in your test files",
            f"Test with: {CYAN}ape test-prompt policy.yaml \"your prompt\"{RESET}",
            "Register mocks: register_all_mocks(orchestrator)",
        ]))
        return EXIT_SUCCESS

    except Exception as e:
        print(f"  {RED}ERROR:{RESET} {e}")
        return EXIT_ERROR


def cmd_mcp_scan(args: argparse.Namespace) -> int:
    """Scan MCP configuration and generate a policy."""
    print(_header("MCP Policy Generator"))
    print()
    print(f"  {DIM}Purpose:{RESET} Scans your MCP (Model Context Protocol) configuration")
    print(f"  {DIM}         and auto-generates an APE policy file matching your tools.{RESET}\n")

    try:
        from ape.mcp.scanner import generate_policy_from_mcp

        policy_data = generate_policy_from_mcp(
            args.mcp_config,
            policy_name=args.name,
            default_deny=not args.allow_unlisted,
        )

        if args.output:
            import yaml
            with open(args.output, 'w') as f:
                yaml.dump(policy_data, f, default_flow_style=False, sort_keys=False)
            print(_status(CHECK, GREEN, f"Policy written to: {CYAN}{args.output}{RESET}"))
        else:
            import yaml
            print(yaml.dump(policy_data, default_flow_style=False, sort_keys=False))

        print(_next_steps([
            f"Validate: {CYAN}ape validate {args.output or 'generated_policy.yaml'}{RESET}",
            f"Review: {CYAN}ape info {args.output or 'generated_policy.yaml'}{RESET}",
            "Edit the generated policy to adjust permissions as needed",
        ]))
        return EXIT_SUCCESS

    except FileNotFoundError as e:
        print(_status(CROSS, RED, f"{RED}FILE_NOT_FOUND:{RESET} MCP config not found: {args.mcp_config}"))
        print(_next_steps([
            "Ensure the MCP config file exists at the specified path",
            "MCP config is typically a JSON file (e.g., mcp_config.json)",
            f"Example: {CYAN}ape mcp-scan ~/.config/mcp/config.json -o policy.yaml{RESET}",
        ]))
        return EXIT_FILE_NOT_FOUND
    except Exception as e:
        print(f"  {RED}ERROR:{RESET} {e}")
        return EXIT_ERROR


def cmd_mcp_info(args: argparse.Namespace) -> int:
    """Show information about an MCP configuration."""
    print(_header("MCP Configuration Info"))
    print()
    print(f"  {DIM}Purpose:{RESET} Shows servers and tools defined in your MCP config,")
    print(f"  {DIM}         which can be used to auto-generate APE policies.{RESET}\n")

    try:
        from ape.mcp.scanner import MCPScanner

        scanner = MCPScanner(args.mcp_config)
        tools = scanner.get_all_tools()

        if args.json:
            print(json.dumps(tools, indent=2))
            return EXIT_SUCCESS

        print(_kv("File", args.mcp_config))
        print(_kv("Servers", str(len(scanner.get_servers()))))
        print(_kv("Total Tools", str(len(tools))))

        for server_name, server_tools in scanner.get_tools_by_server().items():
            print(f"\n  {CYAN}{BOLD}{server_name}{RESET} ({len(server_tools)} tools)")
            for tool in server_tools:
                print(f"    {BULLET} {tool}")

        print(_next_steps([
            f"Generate policy: {CYAN}ape mcp-scan {args.mcp_config} -o policy.yaml{RESET}",
            f"Validate policy: {CYAN}ape validate policy.yaml{RESET}",
        ]))
        return EXIT_SUCCESS

    except FileNotFoundError:
        print(_status(CROSS, RED, f"{RED}FILE_NOT_FOUND:{RESET} {args.mcp_config}"))
        print(_next_steps([
            "Ensure the MCP config file exists at the specified path",
            "MCP config is typically a JSON file",
            f"Example: {CYAN}ape mcp-info ~/.config/mcp/config.json{RESET}",
        ]))
        return EXIT_FILE_NOT_FOUND
    except Exception as e:
        print(f"  {RED}ERROR:{RESET} {e}")
        return EXIT_ERROR


# =============================================================================
# Main Entry Point
# =============================================================================

def main(argv: Optional[list[str]] = None) -> int:
    """Main CLI entry point."""

    parser = argparse.ArgumentParser(
        prog="ape",
        description="Agent Policy Engine — Deterministic policy enforcement for AI agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(f"""\
        Examples:
          ape validate policies/read_only.yaml        Validate a policy file
          ape info policies/read_only.yaml             View policy details
          ape simulate policies/read_only.yaml read_file   Test an action
          ape simulate-batch policies/read_only.yaml read_file write_file
          ape test-prompt policies/read_only.yaml "Read the config file"
          ape analyze "Read config.json and delete temp files"
          ape actions --by-category                    List all known actions
          ape diff policy1.yaml policy2.yaml           Compare two policies
          ape generate-mocks -o tests/mock_tools.py    Generate test mocks
          ape mcp-scan config.json -o policy.yaml      Generate from MCP
        """),
    )
    parser.add_argument(
        "--version", "-v",
        action="store_true",
        help="Show version",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # validate
    p = subparsers.add_parser("validate", help="Validate a policy file")
    p.add_argument("policy", help="Path to policy YAML file")

    # simulate
    p = subparsers.add_parser("simulate", help="Simulate policy evaluation for an action")
    p.add_argument("policy", help="Path to policy YAML file")
    p.add_argument("action", help="Action ID to evaluate")

    # simulate-batch
    p = subparsers.add_parser("simulate-batch", help="Simulate policy for multiple actions")
    p.add_argument("policy", help="Path to policy YAML file")
    p.add_argument("actions", nargs="*", help="Action IDs to evaluate")
    p.add_argument("--file", "-f", dest="actions_file", help="File with action IDs (one per line)")
    p.add_argument("--json", "-j", action="store_true", help="Output as JSON")

    # info
    p = subparsers.add_parser("info", help="Show information about a policy")
    p.add_argument("policy", help="Path to policy YAML file")
    p.add_argument("--json", "-j", action="store_true", help="Output as JSON")

    # diff
    p = subparsers.add_parser("diff", help="Compare two policy files")
    p.add_argument("policy1", help="First policy file")
    p.add_argument("policy2", help="Second policy file")

    # test-prompt
    p = subparsers.add_parser("test-prompt", help="Test a prompt through intent compilation")
    p.add_argument("policy", help="Path to policy YAML file")
    p.add_argument("prompt", help="Natural language prompt to test")

    # analyze
    p = subparsers.add_parser("analyze", help="Analyze a prompt to see extracted signals")
    p.add_argument("prompt", help="Natural language prompt to analyze")

    # actions
    p = subparsers.add_parser("actions", help="List actions in the Action Repository")
    p.add_argument("--by-category", action="store_true", help="Group by category")

    # generate-mocks
    p = subparsers.add_parser("generate-mocks", help="Generate mock tool implementations for testing")
    p.add_argument("--output", "-o", help="Output file path")

    # mcp-scan
    p = subparsers.add_parser("mcp-scan", help="Scan MCP config and generate a policy")
    p.add_argument("mcp_config", help="Path to MCP configuration JSON file (e.g., ~/.config/mcp/config.json)")
    p.add_argument("--output", "-o", help="Output policy file path")
    p.add_argument("--name", "-n", default="mcp_generated", help="Policy name")
    p.add_argument("--allow-unlisted", action="store_true", help="Allow unlisted actions (disable default deny)")

    # mcp-info
    p = subparsers.add_parser("mcp-info", help="Show MCP configuration details")
    p.add_argument("mcp_config", help="Path to MCP configuration JSON file")
    p.add_argument("--json", "-j", action="store_true", help="Output as JSON")

    args = parser.parse_args(argv)

    if args.version:
        from ape import __version__
        print(f"Agent Policy Engine (APE) v{__version__}")
        return EXIT_SUCCESS

    if not args.command:
        print(_banner())
        parser.print_help()
        return EXIT_SUCCESS

    handlers = {
        "validate": cmd_validate,
        "simulate": cmd_simulate,
        "simulate-batch": cmd_simulate_batch,
        "info": cmd_info,
        "diff": cmd_diff,
        "test-prompt": cmd_test_prompt,
        "analyze": cmd_analyze,
        "actions": cmd_actions,
        "generate-mocks": cmd_generate_mocks,
        "mcp-scan": cmd_mcp_scan,
        "mcp-info": cmd_mcp_info,
    }

    handler = handlers.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
