"""
APE Authority Manager

Per architecture spec (§5.5 AuthorityToken and §7.6 Authority Manager):
- AuthorityToken is a concrete, in-process runtime artifact
- Represents permission to execute exactly one action
- Properties: issued only by Authority Manager, cryptographically strong ID,
  opaque to agent, in-memory only, non-serializable, non-transferable,
  single-use, revocable
- Authority Manager issues tokens, tracks lifecycle/expiration,
  enforces single-use, prevents reuse, revokes on invalidation

AuthorityToken structure (mandatory):
- token_id: cryptographically strong unique identifier
- tenant_id: optional, if multi-tenant enabled
- intent_version: hash
- plan_hash: hash
- action_id: bound action identifier
- plan_step_index: integer
- issued_at: timestamp
- expires_at: timestamp
- consumed: boolean flag

Tokens are revoked on: intent update, plan invalidation, runtime termination,
policy violation, policy reload, escalation denial, tenant mismatch

Failure behavior: deny
"""

import secrets
import time
from typing import Any, Optional
from dataclasses import dataclass, field

from ape.errors import (
    UnauthorizedActionError,
    AuthorityExpiredError,
    TokenConsumedError,
    TokenRevokedError,
    TokenNotFoundError,
    RuntimeStateError,
)
from ape.runtime.orchestrator import RuntimeOrchestrator
from ape.action.action import Action


@dataclass
class AuthorityToken:
    """
    Authority token representing permission to execute one action.
    
    Per architecture spec:
    - In-memory only
    - Non-serializable
    - Non-transferable
    - Single-use
    - Revocable
    
    Note: This class intentionally does not implement __getstate__
    or __setstate__ to prevent serialization.
    """
    token_id: str
    tenant_id: str
    intent_version: str
    plan_hash: str
    action_id: str
    plan_step_index: int
    issued_at: float
    expires_at: float
    consumed: bool = False
    revoked: bool = False
    
    def is_valid(self) -> bool:
        """Check if token is valid (not consumed, not revoked, not expired)."""
        if self.consumed:
            return False
        if self.revoked:
            return False
        if time.time() > self.expires_at:
            return False
        return True
    
    def is_expired(self) -> bool:
        """Check if token has expired."""
        return time.time() > self.expires_at
    
    def matches_action(self, action: Action) -> bool:
        """Check if this token matches the given action."""
        return (
            self.action_id == action.action_id and
            self.intent_version == action.intent_version and
            self.plan_hash == action.plan_hash and
            self.plan_step_index == action.plan_step_index
        )
    
    def __reduce__(self):
        """Prevent pickling of authority tokens."""
        raise TypeError("AuthorityToken cannot be serialized")
    
    def __repr__(self) -> str:
        status = "valid" if self.is_valid() else "invalid"
        return f"AuthorityToken(id={self.token_id[:8]}..., action={self.action_id}, status={status})"


class AuthorityManager:
    """
    Manager for authority token lifecycle.
    
    This component:
    - Issues AuthorityTokens
    - Tracks lifecycle and expiration
    - Enforces single-use
    - Prevents reuse
    - Revokes on invalidation
    
    Failure behavior: deny
    """
    
    def __init__(
        self,
        runtime: RuntimeOrchestrator,
        token_ttl_seconds: int = 60,
        default_tenant_id: str = "default"
    ) -> None:
        """
        Initialize the authority manager.
        
        Args:
            runtime: The runtime orchestrator for state checks
            token_ttl_seconds: Time-to-live for tokens in seconds
            default_tenant_id: Default tenant ID when multi-tenant is disabled
        """
        self._runtime = runtime
        self._token_ttl = token_ttl_seconds
        self._default_tenant_id = default_tenant_id
        self._tokens: dict[str, AuthorityToken] = {}
        self._issued_count: int = 0
        self._consumed_count: int = 0
        self._revoked_count: int = 0
    
    @property
    def active_tokens(self) -> int:
        """Get count of active (valid) tokens."""
        return sum(1 for t in self._tokens.values() if t.is_valid())
    
    @property
    def issued_count(self) -> int:
        """Get total count of issued tokens."""
        return self._issued_count
    
    def issue(
        self,
        *,
        intent_version: str,
        plan_hash: str,
        action: Action,
        tenant_id: Optional[str] = None
    ) -> AuthorityToken:
        """
        Issue an authority token for an action.
        
        Per architecture spec:
        - Issued only if policy allows
        - Bound to intent, plan, and step
        - Requires EXECUTING state
        
        Args:
            intent_version: Hash of the current intent
            plan_hash: Hash of the current plan
            action: The action this token authorizes
            tenant_id: Optional tenant ID (uses default if not provided)
            
        Returns:
            AuthorityToken
            
        Raises:
            RuntimeStateError: If not in EXECUTING state
        """
        # Verify runtime state allows authority issuance
        self._runtime.assert_can_issue_authority()
        
        now = time.time()
        token = AuthorityToken(
            token_id=secrets.token_urlsafe(32),
            tenant_id=tenant_id or self._default_tenant_id,
            intent_version=intent_version,
            plan_hash=plan_hash,
            action_id=action.action_id,
            plan_step_index=action.plan_step_index,
            issued_at=now,
            expires_at=now + self._token_ttl,
        )
        
        self._tokens[token.token_id] = token
        self._issued_count += 1
        
        return token
    
    def consume(self, token: AuthorityToken) -> None:
        """
        Consume an authority token.
        
        Per architecture spec:
        - Consumed exactly once
        - Invalidated immediately after use
        - Requires EXECUTING state
        
        Args:
            token: The token to consume
            
        Raises:
            RuntimeStateError: If not in EXECUTING state
            TokenConsumedError: If token already consumed
            TokenRevokedError: If token was revoked
            AuthorityExpiredError: If token has expired
            TokenNotFoundError: If token not in registry
        """
        # Verify runtime state
        self._runtime.assert_executing()
        
        # Verify token is in our registry
        if token.token_id not in self._tokens:
            raise TokenNotFoundError(token.token_id)
        
        # Get the registered token (not the passed one, for safety)
        registered_token = self._tokens[token.token_id]
        
        # Check if already consumed
        if registered_token.consumed:
            raise TokenConsumedError(token.token_id)
        
        # Check if revoked
        if registered_token.revoked:
            raise TokenRevokedError(token.token_id)
        
        # Check if expired
        if registered_token.is_expired():
            raise AuthorityExpiredError(token.token_id)
        
        # Mark as consumed
        registered_token.consumed = True
        self._consumed_count += 1
    
    def validate(self, token: AuthorityToken, action: Action) -> None:
        """
        Validate a token matches an action without consuming it.
        
        Args:
            token: The token to validate
            action: The action to validate against
            
        Raises:
            UnauthorizedActionError: If token doesn't match action
            TokenConsumedError: If token already consumed
            TokenRevokedError: If token was revoked
            AuthorityExpiredError: If token has expired
        """
        if token.token_id not in self._tokens:
            raise TokenNotFoundError(token.token_id)
        
        registered_token = self._tokens[token.token_id]
        
        if registered_token.consumed:
            raise TokenConsumedError(token.token_id)
        
        if registered_token.revoked:
            raise TokenRevokedError(token.token_id)
        
        if registered_token.is_expired():
            raise AuthorityExpiredError(token.token_id)
        
        if not registered_token.matches_action(action):
            raise UnauthorizedActionError(
                f"Token does not match action. "
                f"Token action: {registered_token.action_id}, "
                f"Requested action: {action.action_id}"
            )
    
    def revoke(self, token_id: str) -> bool:
        """
        Revoke a specific token.
        
        Args:
            token_id: ID of the token to revoke
            
        Returns:
            True if token was found and revoked
        """
        if token_id in self._tokens:
            self._tokens[token_id].revoked = True
            self._revoked_count += 1
            return True
        return False
    
    def revoke_all(self) -> int:
        """
        Revoke all issued tokens.
        
        Per architecture spec, tokens are revoked on:
        - Intent update
        - Plan invalidation
        - Runtime termination
        - Policy violation
        - Policy reload
        
        Returns:
            Number of tokens revoked
        """
        count = 0
        for token in self._tokens.values():
            if not token.revoked:
                token.revoked = True
                count += 1
        self._revoked_count += count
        return count
    
    def revoke_for_intent(self, intent_version: str) -> int:
        """
        Revoke all tokens for a specific intent version.
        
        Args:
            intent_version: The intent version hash
            
        Returns:
            Number of tokens revoked
        """
        count = 0
        for token in self._tokens.values():
            if token.intent_version == intent_version and not token.revoked:
                token.revoked = True
                count += 1
        self._revoked_count += count
        return count
    
    def revoke_for_plan(self, plan_hash: str) -> int:
        """
        Revoke all tokens for a specific plan.
        
        Args:
            plan_hash: The plan hash
            
        Returns:
            Number of tokens revoked
        """
        count = 0
        for token in self._tokens.values():
            if token.plan_hash == plan_hash and not token.revoked:
                token.revoked = True
                count += 1
        self._revoked_count += count
        return count
    
    def revoke_for_tenant(self, tenant_id: str) -> int:
        """
        Revoke all tokens for a specific tenant.
        
        Args:
            tenant_id: The tenant ID
            
        Returns:
            Number of tokens revoked
        """
        count = 0
        for token in self._tokens.values():
            if token.tenant_id == tenant_id and not token.revoked:
                token.revoked = True
                count += 1
        self._revoked_count += count
        return count
    
    def cleanup_expired(self) -> int:
        """
        Remove expired tokens from the registry.
        
        Returns:
            Number of tokens removed
        """
        expired = [
            tid for tid, token in self._tokens.items()
            if token.is_expired()
        ]
        for tid in expired:
            del self._tokens[tid]
        return len(expired)
    
    def get_token(self, token_id: str) -> Optional[AuthorityToken]:
        """
        Get a token by ID (for inspection only).
        
        Args:
            token_id: The token ID
            
        Returns:
            AuthorityToken or None if not found
        """
        return self._tokens.get(token_id)
    
    def get_stats(self) -> dict[str, int]:
        """Get statistics about token usage."""
        return {
            "issued": self._issued_count,
            "consumed": self._consumed_count,
            "revoked": self._revoked_count,
            "active": self.active_tokens,
            "total_in_registry": len(self._tokens),
        }
    
    def __repr__(self) -> str:
        return f"AuthorityManager(active={self.active_tokens}, issued={self._issued_count})"
