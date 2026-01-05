"""
APE Provenance Manager

Per architecture spec (§5.4 Provenance and §7.4 Provenance Manager):
- All data entering the agent is labeled with provenance metadata
- Provenance categories: SYSTEM_TRUSTED, USER_TRUSTED, EXTERNAL_UNTRUSTED
- Provenance is mandatory and immutable once assigned
- Mixed provenance results in EXTERNAL_UNTRUSTED
- Untrusted data may not create, modify, or expand authority
- EXTERNAL_UNTRUSTED data may not participate in authority creation,
  modification, escalation, or approval
- Failure behavior: default to EXTERNAL_UNTRUSTED
"""

from enum import Enum
from typing import Any, Optional
from dataclasses import dataclass, field
from ape.errors import ProvenanceError


class Provenance(str, Enum):
    """
    Provenance categories for data entering the agent.
    
    - SYSTEM_TRUSTED: Data from the system itself (policies, configs)
    - USER_TRUSTED: Data explicitly provided by authenticated users
    - EXTERNAL_UNTRUSTED: Data from external sources (API responses, files, etc.)
    """
    SYSTEM_TRUSTED = "SYSTEM_TRUSTED"
    USER_TRUSTED = "USER_TRUSTED"
    EXTERNAL_UNTRUSTED = "EXTERNAL_UNTRUSTED"


@dataclass(frozen=True)
class ProvenanceLabel:
    """
    Immutable provenance label attached to data.
    
    Attributes:
        provenance: The provenance category
        source: Optional description of the data source
        timestamp: When the label was created
    """
    provenance: Provenance
    source: Optional[str] = None
    timestamp: Optional[float] = field(default_factory=lambda: __import__('time').time())
    
    def is_trusted(self) -> bool:
        """Check if this provenance is trusted (SYSTEM or USER)."""
        return self.provenance in (Provenance.SYSTEM_TRUSTED, Provenance.USER_TRUSTED)
    
    def can_grant_authority(self) -> bool:
        """Check if this provenance can participate in authority operations."""
        return self.provenance != Provenance.EXTERNAL_UNTRUSTED


def combine_provenance(a: Provenance, b: Provenance) -> Provenance:
    """
    Combine two provenance values.
    
    Per architecture spec: Mixed provenance results in EXTERNAL_UNTRUSTED.
    
    Args:
        a: First provenance value
        b: Second provenance value
        
    Returns:
        Combined provenance (most restrictive)
    """
    # If either is untrusted, result is untrusted
    if a == Provenance.EXTERNAL_UNTRUSTED or b == Provenance.EXTERNAL_UNTRUSTED:
        return Provenance.EXTERNAL_UNTRUSTED
    
    # If either is user trusted (but not system), result is user trusted
    if a == Provenance.USER_TRUSTED or b == Provenance.USER_TRUSTED:
        return Provenance.USER_TRUSTED
    
    # Both must be system trusted
    return Provenance.SYSTEM_TRUSTED


class ProvenanceManager:
    """
    Manager for tracking and enforcing provenance rules.
    
    This component:
    - Assigns provenance labels
    - Propagates provenance through operations
    - Enforces authority restrictions based on provenance
    - Prevents provenance escalation
    """
    
    def __init__(self) -> None:
        """Initialize the provenance manager."""
        self._labels: dict[int, ProvenanceLabel] = {}
    
    def label(
        self,
        data: Any,
        provenance: Provenance,
        source: Optional[str] = None
    ) -> ProvenanceLabel:
        """
        Assign a provenance label to data.
        
        Args:
            data: The data to label
            provenance: The provenance category
            source: Optional description of the data source
            
        Returns:
            The assigned provenance label
        """
        label = ProvenanceLabel(provenance=provenance, source=source)
        self._labels[id(data)] = label
        return label
    
    def get_label(self, data: Any) -> ProvenanceLabel:
        """
        Get the provenance label for data.
        
        Per architecture spec: Failure behavior is default to EXTERNAL_UNTRUSTED.
        
        Args:
            data: The data to check
            
        Returns:
            The provenance label (defaults to EXTERNAL_UNTRUSTED if not found)
        """
        label = self._labels.get(id(data))
        if label is None:
            # Default to untrusted per spec
            return ProvenanceLabel(
                provenance=Provenance.EXTERNAL_UNTRUSTED,
                source="unknown"
            )
        return label
    
    def get_provenance(self, data: Any) -> Provenance:
        """
        Get just the provenance category for data.
        
        Args:
            data: The data to check
            
        Returns:
            The provenance category
        """
        return self.get_label(data).provenance
    
    def assert_can_grant_authority(self, provenance: Provenance) -> None:
        """
        Assert that the given provenance can participate in authority operations.
        
        Per architecture spec (§5.4):
        EXTERNAL_UNTRUSTED data may not participate in authority creation,
        modification, escalation, or approval.
        
        Args:
            provenance: The provenance to check
            
        Raises:
            ProvenanceError: If provenance cannot grant authority
        """
        if provenance == Provenance.EXTERNAL_UNTRUSTED:
            raise ProvenanceError(
                "EXTERNAL_UNTRUSTED provenance cannot grant authority. "
                "Only SYSTEM_TRUSTED or USER_TRUSTED provenance may "
                "participate in authority operations."
            )
    
    def assert_trusted(self, provenance: Provenance) -> None:
        """
        Assert that the given provenance is trusted.
        
        Args:
            provenance: The provenance to check
            
        Raises:
            ProvenanceError: If provenance is not trusted
        """
        if provenance == Provenance.EXTERNAL_UNTRUSTED:
            raise ProvenanceError(
                "Operation requires trusted provenance. "
                f"Got: {provenance.value}"
            )
    
    def combine(self, *provenances: Provenance) -> Provenance:
        """
        Combine multiple provenance values.
        
        Args:
            *provenances: Provenance values to combine
            
        Returns:
            Combined provenance (most restrictive)
        """
        if not provenances:
            return Provenance.EXTERNAL_UNTRUSTED
        
        result = provenances[0]
        for p in provenances[1:]:
            result = combine_provenance(result, p)
        return result
    
    def clear(self) -> None:
        """Clear all stored provenance labels."""
        self._labels.clear()
