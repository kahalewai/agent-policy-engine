"""
APE Policy Adapters

Provides an adapter pattern for integrating APE with enterprise policy engines.

APE's native policy engine evaluates action allow/deny/escalate rules.
For enterprises that already use OPA/Rego, AWS Cedar, or XACML, these
adapters translate APE's evaluation requests into the external engine's
format and return standardized APE decisions.

Architecture:
    APE PolicyEngine → ExternalEvaluator (adapter) → External Engine → APE PolicyDecision

The adapter pattern allows enterprises to use their existing policy
infrastructure while APE handles agent-specific enforcement including
authority tokens, provenance tracking, and the runtime state machine.

Supported adapters:
- OPAEvaluator: Open Policy Agent (Rego)
- CedarEvaluator: AWS Cedar
- XACMLEvaluator: XACML/OASIS standard

Usage:
    from ape.policy_adapters import OPAEvaluator
    from ape.policy import PolicyEngine

    evaluator = OPAEvaluator("http://localhost:8181/v1/data/ape/allow")
    engine = PolicyEngine("policy.yaml", external_evaluator=evaluator)

    # The engine will delegate to OPA for actions that require it
    result = engine.evaluate("write_file", parameters={"path": "/tmp/data.json"})
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional
from dataclasses import dataclass

from ape.errors import (
    PolicyAdapterError,
    AdapterConnectionError,
    AdapterEvaluationError,
    AdapterConfigurationError,
)

logger = logging.getLogger("ape.policy_adapters")


# =============================================================================
# Base Adapter
# =============================================================================

@dataclass
class AdapterDecision:
    """
    Decision returned by an external policy adapter.

    Attributes:
        allowed: Whether the action is allowed
        reason: Human-readable explanation
        raw_response: The raw response from the external engine
        conditions: Any conditions attached to the decision
    """
    allowed: bool
    reason: str = ""
    raw_response: Any = None
    conditions: dict[str, Any] = None

    def __post_init__(self):
        if self.conditions is None:
            self.conditions = {}


class ExternalEvaluator(ABC):
    """
    Abstract base class for external policy engine adapters.

    All external evaluators must implement the evaluate() method,
    which receives an APE action context and returns an AdapterDecision.

    Implementations handle:
    - Formatting the request for the external engine
    - Sending the request (HTTP, SDK, etc.)
    - Parsing the response into an AdapterDecision
    - Error handling and fallback behavior
    """

    @abstractmethod
    def evaluate(
        self,
        action_id: str,
        parameters: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> AdapterDecision:
        """
        Evaluate an action against the external policy engine.

        Args:
            action_id: The action being evaluated
            parameters: Action parameters (for condition checking)
            context: Additional context (tenant_id, user_id, etc.)

        Returns:
            AdapterDecision with the external engine's verdict

        Raises:
            AdapterConnectionError: If the external engine is unreachable
            AdapterEvaluationError: If the engine returns an error
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """
        Check if the external policy engine is reachable and healthy.

        Returns:
            True if the engine is available
        """
        pass

    @property
    @abstractmethod
    def adapter_type(self) -> str:
        """Return the adapter type identifier (e.g., 'opa', 'cedar', 'xacml')."""
        pass


# =============================================================================
# OPA/Rego Adapter
# =============================================================================

class OPAEvaluator(ExternalEvaluator):
    """
    Open Policy Agent (OPA) adapter using the Rego policy language.

    OPA is the de facto standard for cloud-native policy. It is used by
    Kubernetes, Envoy, Terraform, and many other systems.

    This adapter sends APE action evaluation requests to an OPA server
    via its REST API and translates the response to APE decisions.

    OPA Input Format (sent as JSON):
    {
        "input": {
            "action": "write_file",
            "parameters": {"path": "/tmp/data.json", "content": "..."},
            "context": {"tenant_id": "acme", "user_id": "alice"}
        }
    }

    Expected OPA Output:
    {
        "result": true  // or false, or {"allowed": true, "reason": "..."}
    }

    Usage:
        evaluator = OPAEvaluator("http://localhost:8181/v1/data/ape/allow")
        decision = evaluator.evaluate("write_file", {"path": "/tmp/data.json"})
    """

    def __init__(
        self,
        endpoint: str,
        timeout_seconds: int = 5,
        headers: Optional[dict[str, str]] = None,
        fallback_deny: bool = True,
    ) -> None:
        """
        Initialize the OPA evaluator.

        Args:
            endpoint: OPA REST API endpoint (e.g., http://localhost:8181/v1/data/ape/allow)
            timeout_seconds: Request timeout in seconds
            headers: Optional HTTP headers (e.g., for authentication)
            fallback_deny: If True, deny on connection failure; if False, allow
        """
        if not endpoint:
            raise AdapterConfigurationError("OPA", "Endpoint URL is required")
        self._endpoint = endpoint
        self._timeout = timeout_seconds
        self._headers = headers or {"Content-Type": "application/json"}
        self._fallback_deny = fallback_deny

    @property
    def adapter_type(self) -> str:
        return "opa"

    def evaluate(
        self,
        action_id: str,
        parameters: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> AdapterDecision:
        """
        Evaluate an action against OPA.

        Sends a POST request to the OPA endpoint with the action context
        and interprets the response as an allow/deny decision.
        """
        payload = {
            "input": {
                "action": action_id,
                "parameters": parameters,
                "context": context or {},
            }
        }

        try:
            import urllib.request
            import urllib.error

            req = urllib.request.Request(
                self._endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers=self._headers,
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))

        except urllib.error.URLError as e:
            logger.error("OPA connection failed: %s", e)
            if self._fallback_deny:
                return AdapterDecision(
                    allowed=False,
                    reason=f"OPA unreachable (fallback deny): {e}",
                )
            raise AdapterConnectionError("OPA", self._endpoint, str(e))
        except Exception as e:
            logger.error("OPA evaluation error: %s", e)
            raise AdapterEvaluationError("OPA", str(e))

        return self._parse_opa_response(body, action_id)

    def _parse_opa_response(
        self,
        body: dict[str, Any],
        action_id: str,
    ) -> AdapterDecision:
        """
        Parse OPA's response into an AdapterDecision.

        OPA can return:
        - {"result": true/false}
        - {"result": {"allowed": true, "reason": "..."}}
        - {"result": {"allow": true}}
        """
        result = body.get("result")

        if isinstance(result, bool):
            return AdapterDecision(
                allowed=result,
                reason=f"OPA {'allowed' if result else 'denied'} action '{action_id}'",
                raw_response=body,
            )

        if isinstance(result, dict):
            allowed = result.get("allowed", result.get("allow", False))
            reason = result.get("reason", "")
            conditions = result.get("conditions", {})
            return AdapterDecision(
                allowed=bool(allowed),
                reason=reason or f"OPA decision for '{action_id}'",
                raw_response=body,
                conditions=conditions,
            )

        # Unexpected format — deny by default
        logger.warning("Unexpected OPA response format: %s", body)
        return AdapterDecision(
            allowed=False,
            reason=f"Unexpected OPA response format for '{action_id}'",
            raw_response=body,
        )

    def health_check(self) -> bool:
        """Check if OPA is reachable via its health endpoint."""
        try:
            import urllib.request
            # OPA health endpoint is at /health
            base_url = self._endpoint.split("/v1/")[0] if "/v1/" in self._endpoint else self._endpoint
            health_url = f"{base_url}/health"
            req = urllib.request.Request(health_url, method="GET")
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return resp.status == 200
        except Exception:
            return False

    def __repr__(self) -> str:
        return f"OPAEvaluator(endpoint='{self._endpoint}')"


# =============================================================================
# AWS Cedar Adapter
# =============================================================================

class CedarEvaluator(ExternalEvaluator):
    """
    AWS Cedar policy language adapter.

    Cedar is Amazon's purpose-built policy language for fine-grained
    authorization. It is used by Amazon Verified Permissions and is
    designed for expressing authorization policies concisely.

    This adapter translates APE action evaluations into Cedar
    authorization requests and processes the response.

    Cedar Request Format:
    {
        "principal": {"type": "APE::Agent", "id": "<tenant_id>"},
        "action": {"type": "APE::Action", "id": "<action_id>"},
        "resource": {"type": "APE::Resource", "id": "<resource>"},
        "context": {"parameters": {...}}
    }

    Usage:
        evaluator = CedarEvaluator("http://localhost:8180/v1/is_authorized")
        decision = evaluator.evaluate("write_file", {"path": "/tmp/data.json"})
    """

    def __init__(
        self,
        endpoint: str,
        policy_store_id: Optional[str] = None,
        timeout_seconds: int = 5,
        headers: Optional[dict[str, str]] = None,
        fallback_deny: bool = True,
    ) -> None:
        """
        Initialize the Cedar evaluator.

        Args:
            endpoint: Cedar authorization endpoint URL
            policy_store_id: Optional Cedar policy store ID
            timeout_seconds: Request timeout in seconds
            headers: Optional HTTP headers
            fallback_deny: If True, deny on connection failure
        """
        if not endpoint:
            raise AdapterConfigurationError("Cedar", "Endpoint URL is required")
        self._endpoint = endpoint
        self._policy_store_id = policy_store_id
        self._timeout = timeout_seconds
        self._headers = headers or {"Content-Type": "application/json"}
        self._fallback_deny = fallback_deny

    @property
    def adapter_type(self) -> str:
        return "cedar"

    def evaluate(
        self,
        action_id: str,
        parameters: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> AdapterDecision:
        """
        Evaluate an action against Cedar.

        Constructs a Cedar authorization request from the APE action
        context and sends it to the Cedar endpoint.
        """
        ctx = context or {}

        # Build Cedar-style authorization request
        payload = {
            "principal": {
                "type": "APE::Agent",
                "id": ctx.get("tenant_id", "default"),
            },
            "action": {
                "type": "APE::Action",
                "id": action_id,
            },
            "resource": {
                "type": "APE::Resource",
                "id": self._infer_resource(action_id, parameters),
            },
            "context": {
                "parameters": parameters,
                **{k: v for k, v in ctx.items() if k != "tenant_id"},
            },
        }

        if self._policy_store_id:
            payload["policyStoreId"] = self._policy_store_id

        try:
            import urllib.request
            import urllib.error

            req = urllib.request.Request(
                self._endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers=self._headers,
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))

        except urllib.error.URLError as e:
            logger.error("Cedar connection failed: %s", e)
            if self._fallback_deny:
                return AdapterDecision(
                    allowed=False,
                    reason=f"Cedar unreachable (fallback deny): {e}",
                )
            raise AdapterConnectionError("Cedar", self._endpoint, str(e))
        except Exception as e:
            logger.error("Cedar evaluation error: %s", e)
            raise AdapterEvaluationError("Cedar", str(e))

        return self._parse_cedar_response(body, action_id)

    def _parse_cedar_response(
        self,
        body: dict[str, Any],
        action_id: str,
    ) -> AdapterDecision:
        """
        Parse Cedar's response into an AdapterDecision.

        Cedar typically returns:
        - {"decision": "ALLOW"} or {"decision": "DENY"}
        - Or: {"isAuthorized": true/false}
        """
        decision = body.get("decision", "").upper()
        is_authorized = body.get("isAuthorized")

        if decision in ("ALLOW", "PERMIT"):
            allowed = True
        elif decision in ("DENY", "FORBID"):
            allowed = False
        elif isinstance(is_authorized, bool):
            allowed = is_authorized
        else:
            allowed = False

        reasons = body.get("determiningPolicies", body.get("reasons", []))
        reason_str = f"Cedar {'allowed' if allowed else 'denied'} '{action_id}'"
        if reasons:
            reason_str += f" (policies: {reasons})"

        return AdapterDecision(
            allowed=allowed,
            reason=reason_str,
            raw_response=body,
        )

    def _infer_resource(
        self,
        action_id: str,
        parameters: dict[str, Any],
    ) -> str:
        """Infer a Cedar resource ID from action parameters."""
        # Common parameter names that represent resources
        for key in ("path", "url", "table", "resource", "file", "database"):
            if key in parameters:
                return str(parameters[key])
        return action_id

    def health_check(self) -> bool:
        """Check if Cedar endpoint is reachable."""
        try:
            import urllib.request
            req = urllib.request.Request(self._endpoint, method="GET")
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return resp.status in (200, 405)  # 405 = method not allowed but reachable
        except Exception:
            return False

    def __repr__(self) -> str:
        return f"CedarEvaluator(endpoint='{self._endpoint}')"


# =============================================================================
# XACML Adapter
# =============================================================================

class XACMLEvaluator(ExternalEvaluator):
    """
    XACML (eXtensible Access Control Markup Language) adapter.

    XACML is the OASIS standard for attribute-based access control,
    widely used in regulated industries (banking, healthcare, government).

    This adapter translates APE action evaluations into XACML
    authorization requests (JSON profile) and processes the response.

    XACML JSON Request:
    {
        "Request": {
            "AccessSubject": [{"Attribute": [...]}],
            "Action": [{"Attribute": [...]}],
            "Resource": [{"Attribute": [...]}],
            "Environment": [{"Attribute": [...]}]
        }
    }

    Usage:
        evaluator = XACMLEvaluator("http://localhost:8080/authorize")
        decision = evaluator.evaluate("write_file", {"path": "/tmp/data.json"})
    """

    def __init__(
        self,
        endpoint: str,
        timeout_seconds: int = 5,
        headers: Optional[dict[str, str]] = None,
        fallback_deny: bool = True,
    ) -> None:
        """
        Initialize the XACML evaluator.

        Args:
            endpoint: XACML PDP (Policy Decision Point) endpoint URL
            timeout_seconds: Request timeout in seconds
            headers: Optional HTTP headers
            fallback_deny: If True, deny on connection failure
        """
        if not endpoint:
            raise AdapterConfigurationError("XACML", "Endpoint URL is required")
        self._endpoint = endpoint
        self._timeout = timeout_seconds
        self._headers = headers or {
            "Content-Type": "application/xacml+json",
            "Accept": "application/xacml+json",
        }
        self._fallback_deny = fallback_deny

    @property
    def adapter_type(self) -> str:
        return "xacml"

    def evaluate(
        self,
        action_id: str,
        parameters: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> AdapterDecision:
        """
        Evaluate an action against an XACML PDP.

        Constructs a XACML JSON profile authorization request from
        the APE action context and sends it to the PDP endpoint.
        """
        ctx = context or {}

        # Build XACML JSON profile request
        payload = {
            "Request": {
                "AccessSubject": [{
                    "Attribute": [
                        {
                            "AttributeId": "urn:ape:subject:tenant-id",
                            "Value": ctx.get("tenant_id", "default"),
                            "DataType": "http://www.w3.org/2001/XMLSchema#string",
                        },
                        {
                            "AttributeId": "urn:ape:subject:user-id",
                            "Value": ctx.get("user_id", "unknown"),
                            "DataType": "http://www.w3.org/2001/XMLSchema#string",
                        },
                    ]
                }],
                "Action": [{
                    "Attribute": [
                        {
                            "AttributeId": "urn:oasis:names:tc:xacml:1.0:action:action-id",
                            "Value": action_id,
                            "DataType": "http://www.w3.org/2001/XMLSchema#string",
                        }
                    ]
                }],
                "Resource": [{
                    "Attribute": self._build_resource_attributes(action_id, parameters)
                }],
                "Environment": [{
                    "Attribute": self._build_environment_attributes(ctx)
                }],
            }
        }

        try:
            import urllib.request
            import urllib.error

            req = urllib.request.Request(
                self._endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers=self._headers,
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))

        except urllib.error.URLError as e:
            logger.error("XACML PDP connection failed: %s", e)
            if self._fallback_deny:
                return AdapterDecision(
                    allowed=False,
                    reason=f"XACML PDP unreachable (fallback deny): {e}",
                )
            raise AdapterConnectionError("XACML", self._endpoint, str(e))
        except Exception as e:
            logger.error("XACML evaluation error: %s", e)
            raise AdapterEvaluationError("XACML", str(e))

        return self._parse_xacml_response(body, action_id)

    def _build_resource_attributes(
        self,
        action_id: str,
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Build XACML resource attributes from action parameters."""
        attributes = [
            {
                "AttributeId": "urn:oasis:names:tc:xacml:1.0:resource:resource-id",
                "Value": action_id,
                "DataType": "http://www.w3.org/2001/XMLSchema#string",
            }
        ]

        # Map common parameters to XACML attributes
        param_mapping = {
            "path": "urn:ape:resource:path",
            "url": "urn:ape:resource:url",
            "table": "urn:ape:resource:table",
            "domain": "urn:ape:resource:domain",
        }

        for param_name, attr_id in param_mapping.items():
            if param_name in parameters:
                attributes.append({
                    "AttributeId": attr_id,
                    "Value": str(parameters[param_name]),
                    "DataType": "http://www.w3.org/2001/XMLSchema#string",
                })

        return attributes

    def _build_environment_attributes(
        self,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Build XACML environment attributes from context."""
        import datetime
        attributes = [
            {
                "AttributeId": "urn:oasis:names:tc:xacml:1.0:environment:current-dateTime",
                "Value": datetime.datetime.utcnow().isoformat() + "Z",
                "DataType": "http://www.w3.org/2001/XMLSchema#dateTime",
            }
        ]
        return attributes

    def _parse_xacml_response(
        self,
        body: dict[str, Any],
        action_id: str,
    ) -> AdapterDecision:
        """
        Parse XACML response into an AdapterDecision.

        XACML JSON profile response:
        {
            "Response": [{
                "Decision": "Permit" | "Deny" | "NotApplicable" | "Indeterminate",
                "Status": {"StatusCode": {"Value": "..."}},
                "Obligations": [...],
                "AssociatedAdvice": [...]
            }]
        }
        """
        response_list = body.get("Response", [])
        if not response_list:
            return AdapterDecision(
                allowed=False,
                reason=f"Empty XACML response for '{action_id}'",
                raw_response=body,
            )

        first_response = response_list[0] if isinstance(response_list, list) else response_list
        decision = first_response.get("Decision", "Deny")

        allowed = decision.lower() in ("permit", "allow")

        # Extract obligations and advice
        obligations = first_response.get("Obligations", [])
        advice = first_response.get("AssociatedAdvice", [])

        conditions = {}
        if obligations:
            conditions["obligations"] = obligations
        if advice:
            conditions["advice"] = advice

        return AdapterDecision(
            allowed=allowed,
            reason=f"XACML decision '{decision}' for '{action_id}'",
            raw_response=body,
            conditions=conditions,
        )

    def health_check(self) -> bool:
        """Check if XACML PDP is reachable."""
        try:
            import urllib.request
            req = urllib.request.Request(self._endpoint, method="GET")
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return resp.status in (200, 405)
        except Exception:
            return False

    def __repr__(self) -> str:
        return f"XACMLEvaluator(endpoint='{self._endpoint}')"
