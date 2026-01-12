from __future__ import annotations

import base64
import hmac
import hashlib
import json
from typing import Any, Mapping

import httpx
from werkzeug import Request, Response

from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.trigger import EventDispatch, Subscription, UnsubscribeResult
from dify_plugin.errors.trigger import (
    SubscriptionError,
    TriggerDispatchError,
    TriggerProviderCredentialValidationError,
    TriggerValidationError,
    UnsubscribeError,
)
from dify_plugin.interfaces.trigger import Trigger, TriggerSubscriptionConstructor


class MercuryTrigger(Trigger):
    """Handle Mercury transaction webhook event dispatch.
    
    This trigger receives real-time transaction events from Mercury Banking
    when transactions are created or updated.
    """

    def _dispatch_event(self, subscription: Subscription, request: Request) -> EventDispatch:
        """Process incoming webhook request and dispatch to appropriate event handlers."""
        
        # Validate webhook signature
        webhook_secret = subscription.properties.get("webhook_secret")
        if webhook_secret:
            self._validate_signature(request, webhook_secret)
        
        # Parse and validate payload
        payload = self._parse_payload(request)
        
        # Determine event type based on operation type
        event_types = self._resolve_event_types(payload)
        
        # Return success response
        response = Response(
            response='{"status": "ok"}',
            status=200,
            mimetype="application/json"
        )
        
        return EventDispatch(events=event_types, response=response)

    def _validate_signature(self, request: Request, secret: str) -> None:
        """Verify Mercury webhook signature.
        
        Mercury-Signature header format: t=<timestamp>,v1=<signature>
        Signed payload: <timestamp>.<request_body>
        Algorithm: HMAC-SHA256 with secret key (base64 decoded)
        """
        sig_header = request.headers.get("Mercury-Signature")
        if not sig_header:
            raise TriggerValidationError("Missing Mercury-Signature header")
        
        try:
            # Parse Mercury-Signature header: t=...,v1=...
            parts = dict(p.split("=", 1) for p in sig_header.split(","))
            timestamp = parts.get("t")
            signature = parts.get("v1")
            
            if not timestamp or not signature:
                raise TriggerValidationError("Invalid Mercury-Signature format")

            # Construct signed payload: timestamp.body
            body = request.get_data(as_text=True)
            signed_payload = f"{timestamp}.{body}"
            
            # Decode base64 secret if needed
            try:
                secret_bytes = base64.b64decode(secret)
            except Exception:
                # If not base64, use as-is
                secret_bytes = secret.encode()
            
            # Compute expected signature
            expected = hmac.new(
                secret_bytes,
                signed_payload.encode(),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected):
                raise TriggerValidationError("Invalid webhook signature")
                
        except TriggerValidationError:
            raise
        except Exception as exc:
            raise TriggerValidationError(f"Signature verification failed: {exc}") from exc

    def _parse_payload(self, request: Request) -> Mapping[str, Any]:
        """Parse and validate the webhook payload."""
        try:
            payload = request.get_json(force=True)
            
            if not isinstance(payload, dict) or not payload:
                raise TriggerDispatchError("Empty or invalid JSON payload")
            
            return payload
        except TriggerDispatchError:
            raise
        except Exception as exc:
            raise TriggerDispatchError(f"Failed to parse payload: {exc}") from exc

    def _resolve_event_types(self, payload: Mapping[str, Any]) -> list[str]:
        """Determine which event handlers to dispatch to based on payload content.
        
        Mercury sends events with operationType: "create" or "update"
        We map these to our event handlers.
        """
        resource_type = payload.get("resourceType", "").lower()
        
        # Only handle transaction events for now
        if resource_type == "transaction":
            return ["transaction"]
        
        # Default to transaction handler
        return ["transaction"]


class MercurySubscriptionConstructor(TriggerSubscriptionConstructor):
    """Manage Mercury webhook subscriptions.
    
    Handles the complete webhook lifecycle:
    - Creating webhooks on Mercury when user subscribes
    - Deleting webhooks when user unsubscribes
    - Validating API credentials
    """

    _API_BASE_URL = "https://api.mercury.com/api/v1"
    _REQUEST_TIMEOUT = 15

    def _validate_api_key(self, credentials: Mapping[str, Any]) -> None:
        """Validate Mercury API access token."""
        access_token = credentials.get("access_token")
        
        if not access_token:
            raise TriggerProviderCredentialValidationError(
                "Mercury API Access Token is required."
            )

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json;charset=utf-8",
        }
        
        try:
            # Try to fetch accounts to validate token
            response = httpx.get(
                f"{self._API_BASE_URL}/accounts",
                headers=headers,
                timeout=self._REQUEST_TIMEOUT
            )
        except httpx.RequestException as exc:
            raise TriggerProviderCredentialValidationError(
                f"Error while validating credentials: {exc}"
            ) from exc
        
        if response.status_code == 401:
            raise TriggerProviderCredentialValidationError(
                "Invalid or expired Mercury API access token."
            )
        
        if response.status_code >= 400:
            try:
                details = response.json()
            except json.JSONDecodeError:
                details = {"message": response.text}
            raise TriggerProviderCredentialValidationError(
                f"Mercury API validation failed: {details.get('message', response.text)}"
            )

    def _create_subscription(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:
        """Create a webhook on Mercury to receive transaction events.
        
        Args:
            endpoint: Dify's webhook URL that Mercury will POST to
            parameters: User-configured parameters (event_types, filter_paths)
            credentials: Mercury API credentials (access_token)
            credential_type: Type of credentials
            
        Returns:
            Subscription object containing webhook ID and secret
        """
        access_token = credentials.get("access_token")
        if not access_token:
            raise SubscriptionError(
                "Mercury API access token is required.",
                error_code="MISSING_CREDENTIALS",
            )

        # Build webhook configuration
        event_types: list[str] = parameters.get("event_types", [])
        filter_paths_str: str = parameters.get("filter_paths", "")
        
        webhook_data: dict[str, Any] = {
            "url": endpoint,
        }
        
        # Add event types if specified
        if event_types:
            webhook_data["eventTypes"] = event_types
        
        # Parse and add filter paths if specified
        if filter_paths_str and filter_paths_str.strip():
            filter_paths = [p.strip() for p in filter_paths_str.split(",") if p.strip()]
            if filter_paths:
                webhook_data["filterPaths"] = filter_paths

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json;charset=utf-8",
            "Content-Type": "application/json;charset=utf-8",
        }

        try:
            response = httpx.post(
                f"{self._API_BASE_URL}/webhooks",
                json=webhook_data,
                headers=headers,
                timeout=self._REQUEST_TIMEOUT
            )
        except httpx.RequestException as exc:
            raise SubscriptionError(
                f"Network error while creating webhook: {exc}",
                error_code="NETWORK_ERROR"
            ) from exc

        if response.status_code in (200, 201):
            webhook_response = response.json()
            webhook_id = webhook_response.get("id")
            webhook_secret = webhook_response.get("secret")
            
            return Subscription(
                endpoint=endpoint,
                parameters=parameters,
                properties={
                    "external_id": webhook_id,
                    "webhook_secret": webhook_secret,
                    "status": webhook_response.get("status", "active"),
                },
            )

        # Handle errors
        response_data: dict[str, Any] = {}
        try:
            response_data = response.json() if response.content else {}
        except json.JSONDecodeError:
            response_data = {"message": response.text}
            
        error_msg = response_data.get("message", json.dumps(response_data))

        raise SubscriptionError(
            f"Failed to create Mercury webhook: {error_msg}",
            error_code="WEBHOOK_CREATION_FAILED",
            external_response=response_data,
        )

    def _delete_subscription(
        self, 
        subscription: Subscription, 
        credentials: Mapping[str, Any], 
        credential_type: CredentialType
    ) -> UnsubscribeResult:
        """Delete the webhook from Mercury when user unsubscribes.
        
        Args:
            subscription: The subscription to delete
            credentials: Mercury API credentials
            credential_type: Type of credentials
            
        Returns:
            UnsubscribeResult indicating success or failure
        """
        external_id = subscription.properties.get("external_id")
        
        if not external_id:
            raise UnsubscribeError(
                message="Missing webhook ID information",
                error_code="MISSING_PROPERTIES",
                external_response=None,
            )

        access_token = credentials.get("access_token")
        if not access_token:
            raise UnsubscribeError(
                message="Mercury API access token is required.",
                error_code="MISSING_CREDENTIALS",
                external_response=None,
            )

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json;charset=utf-8",
        }

        try:
            response = httpx.delete(
                f"{self._API_BASE_URL}/webhooks/{external_id}",
                headers=headers,
                timeout=self._REQUEST_TIMEOUT
            )
        except httpx.RequestException as exc:
            raise UnsubscribeError(
                message=f"Network error while deleting webhook: {exc}",
                error_code="NETWORK_ERROR",
                external_response=None,
            ) from exc

        # Mercury returns 204 on successful deletion
        if response.status_code in (200, 204):
            return UnsubscribeResult(
                success=True,
                message=f"Successfully removed webhook {external_id} from Mercury"
            )

        if response.status_code == 404:
            # Webhook doesn't exist, consider it successfully removed
            return UnsubscribeResult(
                success=True,
                message=f"Webhook {external_id} not found in Mercury (already deleted)"
            )

        response_data = None
        try:
            response_data = response.json() if response.content else None
        except json.JSONDecodeError:
            pass

        raise UnsubscribeError(
            message=f"Failed to delete webhook: {response.text}",
            error_code="WEBHOOK_DELETION_FAILED",
            external_response=response_data,
        )
