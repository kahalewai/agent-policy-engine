"""
APE Runtime Configuration

Controls enforcement mode, audit logging, and optional features.

- Enforcement mode: disabled / observe / enforce
- Audit logging behavior
- Policy paths
- Multi-tenant mode (optional)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from pathlib import Path


class EnforcementMode(str, Enum):
    """
    Enforcement modes for APE runtime.
    
    - DISABLED: No enforcement, tools execute directly (development only)
    - OBSERVE: Policy evaluated and logged, but execution proceeds regardless
    - ENFORCE: Full enforcement, execution blocked without valid authority
    """
    DISABLED = "disabled"
    OBSERVE = "observe"
    ENFORCE = "enforce"


@dataclass(frozen=True)
class RuntimeConfig:
    """
    Immutable runtime configuration for APE.
    
    Attributes:
        enforcement_mode: How strictly to enforce policies
        audit_enabled: Whether to log audit events
        policy_path: Path to the policy file
        multi_tenant_enabled: Whether multi-tenant isolation is active
        default_tenant_id: Default tenant ID when multi-tenant is disabled
        token_ttl_seconds: Time-to-live for authority tokens (default: 60)
        strict_mode: If True, raises errors on any policy misconfiguration
    """
    enforcement_mode: EnforcementMode = EnforcementMode.ENFORCE
    audit_enabled: bool = True
    policy_path: Optional[str] = None
    multi_tenant_enabled: bool = False
    default_tenant_id: str = "default"
    token_ttl_seconds: int = 60
    strict_mode: bool = True
    
    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.token_ttl_seconds <= 0:
            raise ValueError("token_ttl_seconds must be positive")
        if self.enforcement_mode not in EnforcementMode:
            raise ValueError(f"Invalid enforcement_mode: {self.enforcement_mode}")
    
    @classmethod
    def development(cls) -> "RuntimeConfig":
        """Create a development configuration with observe mode."""
        return cls(
            enforcement_mode=EnforcementMode.OBSERVE,
            audit_enabled=True,
            strict_mode=False
        )
    
    @classmethod
    def production(cls, policy_path: str) -> "RuntimeConfig":
        """Create a production configuration with full enforcement."""
        return cls(
            enforcement_mode=EnforcementMode.ENFORCE,
            audit_enabled=True,
            policy_path=policy_path,
            strict_mode=True
        )
    
    @classmethod
    def testing(cls) -> "RuntimeConfig":
        """Create a testing configuration with enforcement disabled."""
        return cls(
            enforcement_mode=EnforcementMode.DISABLED,
            audit_enabled=False,
            strict_mode=False
        )


@dataclass
class PolicyConfig:
    """
    Configuration for policy behavior.
    
    Attributes:
        default_deny: If True, actions not in allowed list are denied
        allow_wildcards: If True, allow wildcard patterns in action matching
        case_sensitive: If True, action IDs are case-sensitive
    """
    default_deny: bool = True
    allow_wildcards: bool = False
    case_sensitive: bool = True


def load_config_from_file(path: str) -> RuntimeConfig:
    """
    Load runtime configuration from a YAML file.
    
    Args:
        path: Path to the configuration YAML file
        
    Returns:
        RuntimeConfig instance
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config file is invalid
    """
    import yaml
    
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    
    with open(config_path, 'r') as f:
        data = yaml.safe_load(f) or {}
    
    # Convert enforcement_mode string to enum
    mode_str = data.get('enforcement_mode', 'enforce')
    try:
        enforcement_mode = EnforcementMode(mode_str.lower())
    except ValueError:
        raise ValueError(f"Invalid enforcement_mode in config: {mode_str}")
    
    return RuntimeConfig(
        enforcement_mode=enforcement_mode,
        audit_enabled=data.get('audit_enabled', True),
        policy_path=data.get('policy_path'),
        multi_tenant_enabled=data.get('multi_tenant_enabled', False),
        default_tenant_id=data.get('default_tenant_id', 'default'),
        token_ttl_seconds=data.get('token_ttl_seconds', 60),
        strict_mode=data.get('strict_mode', True)
    )
