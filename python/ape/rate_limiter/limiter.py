"""
APE Rate Limiter

Provides quota and velocity limit enforcement to prevent agent DDoS scenarios.

AI agents can cause serious damage through:
- Infinite loops calling APIs
- Runaway file operations
- Database query storms
- Email/notification spam

The rate limiter operates at three levels:

1. **Global Limits**: Total actions per minute/session, cumulative risk budget
2. **Per-Action Limits**: Individual action quotas (e.g., max 20 http_get per minute)
3. **Per-Target Limits**: Target-specific limits (e.g., max 10 requests/min to api.openai.com)

Rate limits are configured via YAML and enforced at the Enforcement Gate level.
Exceeding a limit raises RateLimitExceededError or QuotaExhaustedError.

Usage:
    from ape.rate_limiter import RateLimiter, RateLimitConfig

    config = RateLimitConfig.from_dict({
        "global": {"max_actions_per_minute": 60, "max_actions_per_session": 500},
        "per_action": {"http_get": {"max_per_minute": 20}},
    })
    limiter = RateLimiter(config)

    # Check before executing
    limiter.check_allowed("http_get")  # Raises if limit exceeded

    # Record after executing
    limiter.record_action("http_get", risk_score=0.1)
"""

import time
import threading
import fnmatch
from typing import Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict

from ape.errors import (
    RateLimitExceededError,
    QuotaExhaustedError,
)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class GlobalLimits:
    """
    Global rate limits applied across all actions.

    Attributes:
        max_actions_per_minute: Maximum total actions per minute across all types
        max_actions_per_session: Maximum total actions in a session lifetime
        max_cumulative_risk_score: Maximum cumulative risk budget for a session
    """
    max_actions_per_minute: Optional[int] = None
    max_actions_per_session: Optional[int] = None
    max_cumulative_risk_score: Optional[float] = None


@dataclass
class ActionLimits:
    """
    Rate limits for a specific action type.

    Attributes:
        max_per_minute: Maximum invocations per minute
        max_per_hour: Maximum invocations per hour
        max_per_day: Maximum invocations per day
    """
    max_per_minute: Optional[int] = None
    max_per_hour: Optional[int] = None
    max_per_day: Optional[int] = None


@dataclass
class TargetLimits:
    """
    Rate limits for a specific target (e.g., domain, database).

    Attributes:
        max_per_minute: Maximum requests per minute to this target
        max_per_hour: Maximum requests per hour to this target
    """
    max_per_minute: Optional[int] = None
    max_per_hour: Optional[int] = None


@dataclass
class RateLimitConfig:
    """
    Complete rate limit configuration.

    Combines global, per-action, and per-target limits into a
    unified configuration that can be loaded from YAML.
    """
    global_limits: GlobalLimits = field(default_factory=GlobalLimits)
    per_action: dict[str, ActionLimits] = field(default_factory=dict)
    per_target: dict[str, dict[str, TargetLimits]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RateLimitConfig":
        """
        Create a RateLimitConfig from a dictionary (e.g., parsed from YAML).

        Expected structure:
        {
            "global": {"max_actions_per_minute": 60, ...},
            "per_action": {"http_get": {"max_per_minute": 20, ...}},
            "per_target": {"domain": {"api.openai.com": {"max_per_minute": 10}}}
        }
        """
        global_data = data.get("global", {})
        global_limits = GlobalLimits(
            max_actions_per_minute=global_data.get("max_actions_per_minute"),
            max_actions_per_session=global_data.get("max_actions_per_session"),
            max_cumulative_risk_score=global_data.get("max_cumulative_risk_score"),
        )

        per_action = {}
        for action_id, limits_data in data.get("per_action", {}).items():
            per_action[action_id] = ActionLimits(
                max_per_minute=limits_data.get("max_per_minute"),
                max_per_hour=limits_data.get("max_per_hour"),
                max_per_day=limits_data.get("max_per_day"),
            )

        per_target = {}
        for target_type, targets in data.get("per_target", {}).items():
            per_target[target_type] = {}
            for target_name, limits_data in targets.items():
                per_target[target_type][target_name] = TargetLimits(
                    max_per_minute=limits_data.get("max_per_minute"),
                    max_per_hour=limits_data.get("max_per_hour"),
                )

        return cls(
            global_limits=global_limits,
            per_action=per_action,
            per_target=per_target,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: dict[str, Any] = {}

        global_data = {}
        if self.global_limits.max_actions_per_minute is not None:
            global_data["max_actions_per_minute"] = self.global_limits.max_actions_per_minute
        if self.global_limits.max_actions_per_session is not None:
            global_data["max_actions_per_session"] = self.global_limits.max_actions_per_session
        if self.global_limits.max_cumulative_risk_score is not None:
            global_data["max_cumulative_risk_score"] = self.global_limits.max_cumulative_risk_score
        if global_data:
            result["global"] = global_data

        if self.per_action:
            pa = {}
            for action_id, limits in self.per_action.items():
                al = {}
                if limits.max_per_minute is not None:
                    al["max_per_minute"] = limits.max_per_minute
                if limits.max_per_hour is not None:
                    al["max_per_hour"] = limits.max_per_hour
                if limits.max_per_day is not None:
                    al["max_per_day"] = limits.max_per_day
                pa[action_id] = al
            result["per_action"] = pa

        if self.per_target:
            pt = {}
            for target_type, targets in self.per_target.items():
                pt[target_type] = {}
                for target_name, limits in targets.items():
                    tl = {}
                    if limits.max_per_minute is not None:
                        tl["max_per_minute"] = limits.max_per_minute
                    if limits.max_per_hour is not None:
                        tl["max_per_hour"] = limits.max_per_hour
                    pt[target_type][target_name] = tl
            result["per_target"] = pt

        return result


# =============================================================================
# Sliding Window Counter
# =============================================================================

class SlidingWindowCounter:
    """
    A sliding window counter for rate limit tracking.

    Efficiently tracks event counts over configurable time windows
    using a list of timestamps. Old timestamps are pruned on each
    access to keep memory usage bounded.
    """

    def __init__(self) -> None:
        self._timestamps: list[float] = []
        self._lock = threading.Lock()

    def record(self, timestamp: Optional[float] = None) -> None:
        """Record an event at the given timestamp (defaults to now)."""
        ts = timestamp or time.time()
        with self._lock:
            self._timestamps.append(ts)

    def count_in_window(self, window_seconds: float) -> int:
        """
        Count events within the last window_seconds.

        Also prunes timestamps older than the largest window we might
        need (24 hours) to prevent unbounded growth.
        """
        now = time.time()
        cutoff = now - window_seconds
        # Prune entries older than 24 hours
        max_retention = now - 86400
        with self._lock:
            self._timestamps = [
                ts for ts in self._timestamps
                if ts > max_retention
            ]
            return sum(1 for ts in self._timestamps if ts > cutoff)

    def count_per_minute(self) -> int:
        """Count events in the last 60 seconds."""
        return self.count_in_window(60.0)

    def count_per_hour(self) -> int:
        """Count events in the last 3600 seconds."""
        return self.count_in_window(3600.0)

    def count_per_day(self) -> int:
        """Count events in the last 86400 seconds."""
        return self.count_in_window(86400.0)

    @property
    def total(self) -> int:
        """Total number of tracked events (including expired)."""
        with self._lock:
            return len(self._timestamps)

    def reset(self) -> None:
        """Clear all recorded events."""
        with self._lock:
            self._timestamps.clear()


# =============================================================================
# Rate Limiter
# =============================================================================

class RateLimiter:
    """
    Enforces rate limits and quotas on agent actions.

    The RateLimiter is consulted before each action execution to ensure
    the agent has not exceeded any configured limits. It operates at
    three levels:

    1. **Global**: Total actions across all types
    2. **Per-Action**: Limits for specific action types
    3. **Per-Target**: Limits for specific targets (domains, databases, etc.)

    The limiter tracks:
    - Action counts per sliding time window (minute, hour, day)
    - Total actions in the session
    - Cumulative risk score across all actions

    Thread Safety:
        This class uses internal locks and is safe for concurrent use.

    Usage:
        limiter = RateLimiter(config)

        # Before executing an action:
        limiter.check_allowed("http_get", target="api.github.com")

        # After successful execution:
        limiter.record_action("http_get", risk_score=0.1, target="api.github.com")

        # Get current usage:
        summary = limiter.get_usage_summary()
    """

    def __init__(self, config: Optional[RateLimitConfig] = None) -> None:
        """
        Initialize the rate limiter.

        Args:
            config: Rate limit configuration. If None, no limits are enforced.
        """
        self._config = config or RateLimitConfig()
        self._lock = threading.Lock()

        # Global counters
        self._global_counter = SlidingWindowCounter()
        self._total_actions: int = 0
        self._cumulative_risk: float = 0.0

        # Per-action counters
        self._action_counters: dict[str, SlidingWindowCounter] = defaultdict(SlidingWindowCounter)

        # Per-target counters: target_type -> target_name -> counter
        self._target_counters: dict[str, dict[str, SlidingWindowCounter]] = defaultdict(
            lambda: defaultdict(SlidingWindowCounter)
        )

    @property
    def total_actions(self) -> int:
        """Total actions recorded in this limiter's lifetime."""
        return self._total_actions

    @property
    def cumulative_risk(self) -> float:
        """Cumulative risk score across all recorded actions."""
        return self._cumulative_risk

    def check_allowed(
        self,
        action_id: str,
        target: Optional[str] = None,
        target_type: str = "domain",
        risk_score: float = 0.0,
    ) -> None:
        """
        Check if an action is allowed under current rate limits.

        This should be called BEFORE executing the action. It raises
        an exception if any limit would be exceeded.

        Args:
            action_id: The action being attempted
            target: Optional target identifier (e.g., domain name)
            target_type: Type of target (e.g., "domain", "database")
            risk_score: Risk score of the action (for cumulative risk budget)

        Raises:
            RateLimitExceededError: If a rate limit would be exceeded
            QuotaExhaustedError: If a session quota would be exceeded
        """
        gl = self._config.global_limits

        # Check global actions per minute
        if gl.max_actions_per_minute is not None:
            current = self._global_counter.count_per_minute()
            if current >= gl.max_actions_per_minute:
                raise RateLimitExceededError(
                    f"Global rate limit exceeded: {current}/{gl.max_actions_per_minute} actions per minute",
                    action_id=action_id,
                    limit_type="global_per_minute",
                    current_count=current,
                    max_allowed=gl.max_actions_per_minute,
                    reset_seconds=60.0,
                )

        # Check global actions per session
        if gl.max_actions_per_session is not None:
            if self._total_actions >= gl.max_actions_per_session:
                raise QuotaExhaustedError(
                    f"Session quota exhausted: {self._total_actions}/{gl.max_actions_per_session} actions",
                    quota_type="actions_per_session",
                    current_value=float(self._total_actions),
                    max_value=float(gl.max_actions_per_session),
                )

        # Check cumulative risk
        if gl.max_cumulative_risk_score is not None:
            projected = self._cumulative_risk + risk_score
            if projected > gl.max_cumulative_risk_score:
                raise QuotaExhaustedError(
                    f"Risk budget exceeded: {projected:.2f}/{gl.max_cumulative_risk_score} cumulative risk",
                    quota_type="cumulative_risk",
                    current_value=projected,
                    max_value=gl.max_cumulative_risk_score,
                )

        # Check per-action limits
        if action_id in self._config.per_action:
            limits = self._config.per_action[action_id]
            counter = self._action_counters[action_id]

            if limits.max_per_minute is not None:
                current = counter.count_per_minute()
                if current >= limits.max_per_minute:
                    raise RateLimitExceededError(
                        f"Action '{action_id}' rate limit exceeded: {current}/{limits.max_per_minute} per minute",
                        action_id=action_id,
                        limit_type="action_per_minute",
                        current_count=current,
                        max_allowed=limits.max_per_minute,
                        reset_seconds=60.0,
                    )

            if limits.max_per_hour is not None:
                current = counter.count_per_hour()
                if current >= limits.max_per_hour:
                    raise RateLimitExceededError(
                        f"Action '{action_id}' rate limit exceeded: {current}/{limits.max_per_hour} per hour",
                        action_id=action_id,
                        limit_type="action_per_hour",
                        current_count=current,
                        max_allowed=limits.max_per_hour,
                        reset_seconds=3600.0,
                    )

            if limits.max_per_day is not None:
                current = counter.count_per_day()
                if current >= limits.max_per_day:
                    raise RateLimitExceededError(
                        f"Action '{action_id}' rate limit exceeded: {current}/{limits.max_per_day} per day",
                        action_id=action_id,
                        limit_type="action_per_day",
                        current_count=current,
                        max_allowed=limits.max_per_day,
                        reset_seconds=86400.0,
                    )

        # Check per-target limits
        if target and target_type in self._config.per_target:
            target_limits = self._config.per_target[target_type]
            matched_limits = self._match_target(target, target_limits)
            if matched_limits:
                counter = self._target_counters[target_type][target]

                if matched_limits.max_per_minute is not None:
                    current = counter.count_per_minute()
                    if current >= matched_limits.max_per_minute:
                        raise RateLimitExceededError(
                            f"Target '{target}' rate limit exceeded: "
                            f"{current}/{matched_limits.max_per_minute} per minute",
                            action_id=action_id,
                            limit_type="target_per_minute",
                            current_count=current,
                            max_allowed=matched_limits.max_per_minute,
                            reset_seconds=60.0,
                        )

                if matched_limits.max_per_hour is not None:
                    current = counter.count_per_hour()
                    if current >= matched_limits.max_per_hour:
                        raise RateLimitExceededError(
                            f"Target '{target}' rate limit exceeded: "
                            f"{current}/{matched_limits.max_per_hour} per hour",
                            action_id=action_id,
                            limit_type="target_per_hour",
                            current_count=current,
                            max_allowed=matched_limits.max_per_hour,
                            reset_seconds=3600.0,
                        )

    def record_action(
        self,
        action_id: str,
        risk_score: float = 0.0,
        target: Optional[str] = None,
        target_type: str = "domain",
    ) -> None:
        """
        Record that an action was executed.

        This should be called AFTER successful execution to update
        all relevant counters.

        Args:
            action_id: The action that was executed
            risk_score: Risk score of the action
            target: Optional target identifier
            target_type: Type of target
        """
        now = time.time()
        with self._lock:
            self._global_counter.record(now)
            self._total_actions += 1
            self._cumulative_risk += risk_score
            self._action_counters[action_id].record(now)

            if target:
                self._target_counters[target_type][target].record(now)

    def _match_target(
        self,
        target: str,
        target_limits: dict[str, TargetLimits],
    ) -> Optional[TargetLimits]:
        """
        Match a target against configured target limits.

        Supports glob patterns (e.g., "*.internal.corp").
        Exact matches take precedence over glob matches.

        Args:
            target: The target to match
            target_limits: Dictionary of target patterns to limits

        Returns:
            Matched TargetLimits or None if no match
        """
        # Exact match first
        if target in target_limits:
            return target_limits[target]

        # Glob pattern match
        for pattern, limits in target_limits.items():
            if fnmatch.fnmatch(target, pattern):
                return limits

        return None

    def get_usage_summary(self) -> dict[str, Any]:
        """
        Get a summary of current rate limit usage.

        Returns:
            Dictionary with current counters and limit status
        """
        gl = self._config.global_limits
        summary: dict[str, Any] = {
            "total_actions": self._total_actions,
            "cumulative_risk": round(self._cumulative_risk, 4),
            "global_actions_per_minute": self._global_counter.count_per_minute(),
        }

        if gl.max_actions_per_minute is not None:
            summary["global_limit_per_minute"] = gl.max_actions_per_minute
        if gl.max_actions_per_session is not None:
            summary["session_limit"] = gl.max_actions_per_session
        if gl.max_cumulative_risk_score is not None:
            summary["risk_budget"] = gl.max_cumulative_risk_score
            summary["risk_remaining"] = round(
                gl.max_cumulative_risk_score - self._cumulative_risk, 4
            )

        # Per-action usage
        action_usage = {}
        for action_id, counter in self._action_counters.items():
            action_usage[action_id] = {
                "per_minute": counter.count_per_minute(),
                "per_hour": counter.count_per_hour(),
            }
            if action_id in self._config.per_action:
                limits = self._config.per_action[action_id]
                if limits.max_per_minute is not None:
                    action_usage[action_id]["limit_per_minute"] = limits.max_per_minute
                if limits.max_per_hour is not None:
                    action_usage[action_id]["limit_per_hour"] = limits.max_per_hour
        if action_usage:
            summary["per_action"] = action_usage

        return summary

    def reset(self) -> None:
        """Reset all counters. Used when creating a new session."""
        with self._lock:
            self._global_counter.reset()
            self._total_actions = 0
            self._cumulative_risk = 0.0
            self._action_counters.clear()
            self._target_counters.clear()

    def update_config(self, config: RateLimitConfig) -> None:
        """
        Update the rate limit configuration.

        This allows dynamic policy updates to change limits
        without resetting counters.

        Args:
            config: New rate limit configuration
        """
        with self._lock:
            self._config = config

    def __repr__(self) -> str:
        return (
            f"RateLimiter(total={self._total_actions}, "
            f"risk={self._cumulative_risk:.2f}, "
            f"actions_tracked={len(self._action_counters)})"
        )
