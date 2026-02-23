"""
APE Intent Compiler

The Intent Compiler transforms natural language prompts into structured
APE Intent objects, enforcing the core principle:

    "Prompts guide intent, but never are intent."

Usage:
    from ape.intent_compiler import IntentCompiler, CompiledIntent
    from ape.action_repository import create_standard_repository
    
    repository = create_standard_repository()
    compiler = IntentCompiler(repository)
    
    intent = compiler.compile(
        prompt="Read the config file and list the directory",
        policy_allowed=["read_file", "list_directory"],
    )
    
    # Use with APE IntentManager
    intent_manager.set(intent.to_ape_intent(), Provenance.USER_TRUSTED)
"""

from ape.intent_compiler.compiler import (
    IntentCompiler,
    IntentSignal,
    CompiledIntent,
    SEMANTIC_PATTERNS,
    SCOPE_PATTERNS,
)


__all__ = [
    "IntentCompiler",
    "IntentSignal",
    "CompiledIntent",
    "SEMANTIC_PATTERNS",
    "SCOPE_PATTERNS",
]
