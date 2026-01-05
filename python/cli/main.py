"""
APE Command Line Interface

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
from pathlib import Path
from typing import Optional

from ape.policy.engine import PolicyEngine, PolicyDecision, validate_policy_file
from ape.errors import PolicyError, PolicyDenyError, EscalationRequiredError
from ape.mcp.scanner import MCPScanner, generate_policy_from_mcp


# Exit codes
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_POLICY_ERROR = 2
EXIT_VALIDATION_ERROR = 3
EXIT_FILE_NOT_FOUND = 4


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate a policy file."""
    errors = validate_policy_file(args.policy)
    
    if errors:
        print(f"VALIDATION FAILED: {args.policy}", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return EXIT_VALIDATION_ERROR
    
    print(f"VALID: {args.policy}")
    return EXIT_SUCCESS


def cmd_simulate(args: argparse.Namespace) -> int:
    """Simulate policy evaluation for an action."""
    try:
        engine = PolicyEngine(args.policy)
        result = engine.evaluate(args.action)
        
        print(f"Action: {args.action}")
        print(f"Decision: {result.decision.value}")
        print(f"Reason: {result.reason}")
        
        if result.decision == PolicyDecision.ALLOW:
            return EXIT_SUCCESS
        elif result.decision == PolicyDecision.ESCALATE:
            return EXIT_SUCCESS  # Escalate is not an error
        else:
            return EXIT_POLICY_ERROR
            
    except PolicyError as e:
        print(f"POLICY_ERROR: {e}", file=sys.stderr)
        return EXIT_POLICY_ERROR


def cmd_simulate_batch(args: argparse.Namespace) -> int:
    """Simulate policy evaluation for multiple actions."""
    try:
        engine = PolicyEngine(args.policy)
        
        # Read actions from file or args
        if args.actions_file:
            with open(args.actions_file) as f:
                actions = [line.strip() for line in f if line.strip()]
        else:
            actions = args.actions
        
        results = engine.simulate(actions)
        
        if args.json:
            output = [
                {
                    "action": r.action_id,
                    "decision": r.decision.value,
                    "reason": r.reason
                }
                for r in results
            ]
            print(json.dumps(output, indent=2))
        else:
            for result in results:
                status = "✓" if result.is_allowed() else "✗" if result.is_denied() else "?"
                print(f"{status} {result.action_id}: {result.decision.value}")
        
        return EXIT_SUCCESS
        
    except PolicyError as e:
        print(f"POLICY_ERROR: {e}", file=sys.stderr)
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
                "allowed_actions": policy.allowed_actions,
                "forbidden_actions": policy.forbidden_actions,
                "escalation_required": policy.escalation_required,
                "default_deny": policy.default_deny,
            }
            print(json.dumps(output, indent=2))
        else:
            print(f"Policy: {args.policy}")
            print(f"Version: {engine.version[:16]}...")
            if policy.name:
                print(f"Name: {policy.name}")
            if policy.description:
                print(f"Description: {policy.description}")
            print(f"Default Deny: {policy.default_deny}")
            print(f"Allowed Actions ({len(policy.allowed_actions)}):")
            for action in policy.allowed_actions:
                print(f"  - {action}")
            print(f"Forbidden Actions ({len(policy.forbidden_actions)}):")
            for action in policy.forbidden_actions:
                print(f"  - {action}")
            if policy.escalation_required:
                print(f"Escalation Required ({len(policy.escalation_required)}):")
                for action in policy.escalation_required:
                    print(f"  - {action}")
        
        return EXIT_SUCCESS
        
    except PolicyError as e:
        print(f"POLICY_ERROR: {e}", file=sys.stderr)
        return EXIT_POLICY_ERROR


def cmd_mcp_scan(args: argparse.Namespace) -> int:
    """Scan MCP configuration and generate a policy."""
    try:
        policy_data = generate_policy_from_mcp(
            args.mcp_config,
            policy_name=args.name,
            default_deny=not args.allow_unlisted
        )
        
        if args.output:
            import yaml
            with open(args.output, 'w') as f:
                yaml.dump(policy_data, f, default_flow_style=False, sort_keys=False)
            print(f"Policy written to: {args.output}")
        else:
            import yaml
            print(yaml.dump(policy_data, default_flow_style=False, sort_keys=False))
        
        return EXIT_SUCCESS
        
    except FileNotFoundError as e:
        print(f"FILE_NOT_FOUND: {e}", file=sys.stderr)
        return EXIT_FILE_NOT_FOUND
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return EXIT_ERROR


def cmd_mcp_info(args: argparse.Namespace) -> int:
    """Show information about an MCP configuration."""
    try:
        scanner = MCPScanner(args.mcp_config)
        tools = scanner.get_all_tools()
        
        if args.json:
            print(json.dumps(tools, indent=2))
        else:
            print(f"MCP Configuration: {args.mcp_config}")
            print(f"Servers: {len(scanner.get_servers())}")
            print(f"Total Tools: {len(tools)}")
            print("\nTools by server:")
            for server_name, server_tools in scanner.get_tools_by_server().items():
                print(f"\n  {server_name}:")
                for tool in server_tools:
                    print(f"    - {tool}")
        
        return EXIT_SUCCESS
        
    except FileNotFoundError as e:
        print(f"FILE_NOT_FOUND: {e}", file=sys.stderr)
        return EXIT_FILE_NOT_FOUND
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return EXIT_ERROR


def cmd_version(args: argparse.Namespace) -> int:
    """Show APE version."""
    print("Agent Policy Engine (APE) v1.0.0")
    return EXIT_SUCCESS


def main(argv: Optional[list[str]] = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="ape",
        description="Agent Policy Engine - Deterministic policy enforcement for AI agents"
    )
    parser.add_argument(
        "--version", "-v",
        action="store_true",
        help="Show version"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # validate command
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate a policy file"
    )
    validate_parser.add_argument("policy", help="Path to policy YAML file")
    
    # simulate command
    simulate_parser = subparsers.add_parser(
        "simulate",
        help="Simulate policy evaluation for an action"
    )
    simulate_parser.add_argument("policy", help="Path to policy YAML file")
    simulate_parser.add_argument("action", help="Action ID to evaluate")
    
    # simulate-batch command
    batch_parser = subparsers.add_parser(
        "simulate-batch",
        help="Simulate policy evaluation for multiple actions"
    )
    batch_parser.add_argument("policy", help="Path to policy YAML file")
    batch_parser.add_argument(
        "actions",
        nargs="*",
        help="Action IDs to evaluate"
    )
    batch_parser.add_argument(
        "--file", "-f",
        dest="actions_file",
        help="File containing action IDs (one per line)"
    )
    batch_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON"
    )
    
    # info command
    info_parser = subparsers.add_parser(
        "info",
        help="Show information about a policy"
    )
    info_parser.add_argument("policy", help="Path to policy YAML file")
    info_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON"
    )
    
    # mcp-scan command
    mcp_scan_parser = subparsers.add_parser(
        "mcp-scan",
        help="Scan MCP configuration and generate a policy"
    )
    mcp_scan_parser.add_argument(
        "mcp_config",
        help="Path to MCP configuration JSON file"
    )
    mcp_scan_parser.add_argument(
        "--output", "-o",
        help="Output policy file path"
    )
    mcp_scan_parser.add_argument(
        "--name", "-n",
        default="mcp_generated",
        help="Policy name"
    )
    mcp_scan_parser.add_argument(
        "--allow-unlisted",
        action="store_true",
        help="Allow actions not in the MCP config (default deny disabled)"
    )
    
    # mcp-info command
    mcp_info_parser = subparsers.add_parser(
        "mcp-info",
        help="Show information about an MCP configuration"
    )
    mcp_info_parser.add_argument(
        "mcp_config",
        help="Path to MCP configuration JSON file"
    )
    mcp_info_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON"
    )
    
    args = parser.parse_args(argv)
    
    if args.version:
        return cmd_version(args)
    
    if not args.command:
        parser.print_help()
        return EXIT_SUCCESS
    
    # Dispatch to command handler
    handlers = {
        "validate": cmd_validate,
        "simulate": cmd_simulate,
        "simulate-batch": cmd_simulate_batch,
        "info": cmd_info,
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
