"""
APE Rate Limiter

Provides quota and velocity limit enforcement to prevent agent DDoS
scenarios. Supports global limits, per-action limits, per-target limits,
and cumulative risk scoring.

Usage:
    from ape.rate_limiter import RateLimiter, RateLimitConfig

    config = RateLimitConfig.from_dict({
        "global": {"max_actions_per_minute": 60},
        "per_action": {"http_get": {"max_per_minute": 20}},
    })
    limiter = RateLimiter(config)

    limiter.check_allowed("http_get")
    limiter.record_action("http_get", risk_score=0.1)
"""

from ape.rate_limiter.limiter import (
    RateLimiter,
    RateLimitConfig,
    GlobalLimits,
    ActionLimits,
    TargetLimits,
    SlidingWindowCounter,
)

__all__ = [
    "RateLimiter",
    "RateLimitConfig",
    "GlobalLimits",
    "ActionLimits",
    "TargetLimits",
    "SlidingWindowCounter",
]
