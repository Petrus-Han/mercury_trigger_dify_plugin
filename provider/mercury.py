from __future__ import annotations

import base64
import hmac
import hashlib
import json
import logging
import sys
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

# 配置日志输出到 stdout
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


def log_info(msg: str):
    """强制输出日志"""
    print(f"[MERCURY] INFO: {msg}", flush=True)
    logger.info(msg)


def log_error(msg: str):
    """强制输出错误日志"""
    print(f"[MERCURY] ERROR: {msg}", flush=True)
    logger.error(msg)


def log_debug(msg: str):
    """强制输出调试日志"""
    print(f"[MERCURY] DEBUG: {msg}", flush=True)
    logger.debug(msg)


class MercuryTrigger(Trigger):
    """Handle Mercury transaction webhook event dispatch."""

    def _dispatch_event(self, subscription: Subscription, request: Request) -> EventDispatch:
        """Process incoming webhook request and dispatch to appropriate event handlers."""
        log_info("=== _dispatch_event called ===")
        log_info(f"Request method: {request.method}")
        log_info(f"Request headers: {dict(request.headers)}")
        
        # Validate webhook signature
        webhook_secret = subscription.properties.get("webhook_secret")
        log_info(f"Webhook secret configured: {bool(webhook_secret)}")
        
        if webhook_secret:
            self._validate_signature(request, webhook_secret)
        
        # Parse and validate payload
        payload = self._parse_payload(request)
        log_info(f"Parsed payload: {json.dumps(payload, indent=2)}")
        
        # Determine event type based on operation type
        event_types = self._resolve_event_types(payload)
        log_info(f"Resolved event types: {event_types}")
        
        # Return success response
        response = Response(
            response='{"status": "ok"}',
            status=200,
            mimetype="application/json"
        )
        
        log_info("=== _dispatch_event completed ===")
        return EventDispatch(events=event_types, response=response)

    def _validate_signature(self, request: Request, secret: str) -> None:
        """Verify Mercury webhook signature."""
        log_info("Validating webhook signature...")
        sig_header = request.headers.get("Mercury-Signature")
        
        if not sig_header:
            log_error("Missing Mercury-Signature header")
            raise TriggerValidationError("Missing Mercury-Signature header")
        
        log_debug(f"Mercury-Signature header: {sig_header}")
        
        try:
            parts = dict(p.split("=", 1) for p in sig_header.split(","))
            timestamp = parts.get("t")
            signature = parts.get("v1")
            
            if not timestamp or not signature:
                log_error("Invalid Mercury-Signature format")
                raise TriggerValidationError("Invalid Mercury-Signature format")

            body = request.get_data(as_text=True)
            signed_payload = f"{timestamp}.{body}"
            
            try:
                secret_bytes = base64.b64decode(secret)
            except Exception:
                secret_bytes = secret.encode()
            
            expected = hmac.new(
                secret_bytes,
                signed_payload.encode(),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected):
                log_error("Invalid webhook signature")
                raise TriggerValidationError("Invalid webhook signature")
            
            log_info("Webhook signature validated successfully")
                
        except TriggerValidationError:
            raise
        except Exception as exc:
            log_error(f"Signature verification failed: {exc}")
            raise TriggerValidationError(f"Signature verification failed: {exc}") from exc

    def _parse_payload(self, request: Request) -> Mapping[str, Any]:
        """Parse and validate the webhook payload."""
        log_info("Parsing webhook payload...")
        try:
            payload = request.get_json(force=True)
            
            if not isinstance(payload, dict) or not payload:
                log_error("Empty or invalid JSON payload")
                raise TriggerDispatchError("Empty or invalid JSON payload")
            
            log_info(f"Payload parsed successfully, keys: {list(payload.keys())}")
            return payload
        except TriggerDispatchError:
            raise
        except Exception as exc:
            log_error(f"Failed to parse payload: {exc}")
            raise TriggerDispatchError(f"Failed to parse payload: {exc}") from exc

    def _resolve_event_types(self, payload: Mapping[str, Any]) -> list[str]:
        """Determine which event handlers to dispatch to based on payload content."""
        resource_type = payload.get("resourceType", "").lower()
        operation_type = payload.get("operationType", "")
        
        log_info(f"Resource type: {resource_type}, Operation type: {operation_type}")
        
        if resource_type == "transaction":
            return ["transaction"]
        
        return ["transaction"]


class MercurySubscriptionConstructor(TriggerSubscriptionConstructor):
    """Manage Mercury webhook subscriptions."""

    _API_BASE_URLS = {
        "production": "https://api.mercury.com/api/v1",
        "sandbox": "https://api-sandbox.mercury.com/api/v1",
    }
    _REQUEST_TIMEOUT = 15

    def _get_api_base_url(self, credentials: Mapping[str, Any]) -> str:
        """Get the API base URL based on environment setting."""
        # Get environment from credentials (default to sandbox)
        api_environment = credentials.get("api_environment", "sandbox")

        # Determine URL based on environment
        # Sandbox URL: https://api-sandbox.mercury.com/api/v1/
        # Production URL: https://api.mercury.com/api/v1/
        url = self._API_BASE_URLS.get(api_environment, self._API_BASE_URLS["sandbox"])
        log_info(f"Using API base URL: {url} (environment: {api_environment})")
        return url

    def _validate_api_key(self, credentials: Mapping[str, Any]) -> None:
        """Validate Mercury API access token."""
        log_info("=== _validate_api_key called ===")
        
        access_token = credentials.get("access_token")
        
        if not access_token:
            log_error("Mercury API Access Token is required.")
            raise TriggerProviderCredentialValidationError(
                "Mercury API Access Token is required."
            )
        
        log_info(f"Access token: {access_token[:10]}...{access_token[-4:]}")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json;charset=utf-8",
        }
        
        api_base_url = self._get_api_base_url(credentials)
        url = f"{api_base_url}/accounts"
        log_info(f"Validating token by calling: GET {url}")
        
        try:
            response = httpx.get(
                url,
                headers=headers,
                timeout=self._REQUEST_TIMEOUT
            )
            log_info(f"Response status: {response.status_code}")
            log_debug(f"Response body: {response.text[:500]}")
        except httpx.HTTPError as exc:
            log_error(f"Network error: {exc}")
            raise TriggerProviderCredentialValidationError(
                f"Error while validating credentials: {exc}"
            ) from exc
        
        if response.status_code == 401:
            log_error("Invalid or expired Mercury API access token.")
            raise TriggerProviderCredentialValidationError(
                "Invalid or expired Mercury API access token."
            )
        
        if response.status_code >= 400:
            try:
                details = response.json()
            except json.JSONDecodeError:
                details = {"message": response.text}
            log_error(f"Mercury API validation failed: {details}")
            raise TriggerProviderCredentialValidationError(
                f"Mercury API validation failed: {details.get('message', response.text)}"
            )
        
        log_info("=== _validate_api_key completed successfully ===")

    def _create_subscription(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:
        """Create a webhook on Mercury to receive transaction events."""
        log_info("=== _create_subscription called ===")
        log_info(f"Endpoint: {endpoint}")
        log_info(f"Parameters: {parameters}")
        log_info(f"Credential type: {credential_type}")
        
        access_token = credentials.get("access_token")
        if not access_token:
            log_error("Mercury API access token is required.")
            raise SubscriptionError(
                "Mercury API access token is required.",
                error_code="MISSING_CREDENTIALS",
            )

        event_types: list[str] = parameters.get("event_types", [])
        filter_paths_str: str = parameters.get("filter_paths", "")

        webhook_data: dict[str, Any] = {
            "url": endpoint,
        }

        if event_types:
            webhook_data["eventTypes"] = event_types

        if filter_paths_str and filter_paths_str.strip():
            filter_paths = [p.strip() for p in filter_paths_str.split(",") if p.strip()]
            if filter_paths:
                webhook_data["filterPaths"] = filter_paths

        api_base_url = self._get_api_base_url(credentials)
        url = f"{api_base_url}/webhooks"
        
        log_info(f"Creating webhook at: POST {url}")
        log_info(f"Webhook data: {json.dumps(webhook_data, indent=2)}")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json;charset=utf-8",
            "Content-Type": "application/json;charset=utf-8",
        }

        try:
            response = httpx.post(
                url,
                json=webhook_data,
                headers=headers,
                timeout=self._REQUEST_TIMEOUT
            )
            log_info(f"Response status: {response.status_code}")
            log_info(f"Response body: {response.text}")
        except httpx.HTTPError as exc:
            log_error(f"Network error creating webhook: {exc}")
            raise SubscriptionError(
                f"Network error while creating webhook: {exc}",
                error_code="NETWORK_ERROR"
            ) from exc

        if response.status_code in (200, 201):
            webhook_response = response.json()
            webhook_id = webhook_response.get("id")
            webhook_secret = webhook_response.get("secret")
            
            log_info(f"Webhook created successfully! ID: {webhook_id}")
            
            return Subscription(
                endpoint=endpoint,
                parameters=parameters,
                properties={
                    "external_id": webhook_id,
                    "webhook_secret": webhook_secret,
                    "status": webhook_response.get("status", "active"),
                },
            )

        response_data: dict[str, Any] = {}
        try:
            response_data = response.json() if response.content else {}
        except json.JSONDecodeError:
            response_data = {"message": response.text}
            
        error_msg = response_data.get("message", json.dumps(response_data))
        log_error(f"Failed to create Mercury webhook: {error_msg}")

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
        """Delete the webhook from Mercury when user unsubscribes."""
        log_info("=== _delete_subscription called ===")
        
        external_id = subscription.properties.get("external_id")
        log_info(f"Deleting webhook ID: {external_id}")
        
        if not external_id:
            log_error("Missing webhook ID information")
            raise UnsubscribeError(
                message="Missing webhook ID information",
                error_code="MISSING_PROPERTIES",
                external_response=None,
            )

        access_token = credentials.get("access_token")
        if not access_token:
            log_error("Mercury API access token is required.")
            raise UnsubscribeError(
                message="Mercury API access token is required.",
                error_code="MISSING_CREDENTIALS",
                external_response=None,
            )

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json;charset=utf-8",
        }

        api_base_url = self._get_api_base_url(credentials)
        url = f"{api_base_url}/webhooks/{external_id}"
        log_info(f"Deleting webhook at: DELETE {url}")

        try:
            response = httpx.delete(
                url,
                headers=headers,
                timeout=self._REQUEST_TIMEOUT
            )
            log_info(f"Response status: {response.status_code}")
        except httpx.HTTPError as exc:
            log_error(f"Network error while deleting webhook: {exc}")
            raise UnsubscribeError(
                message=f"Network error while deleting webhook: {exc}",
                error_code="NETWORK_ERROR",
                external_response=None,
            ) from exc

        if response.status_code in (200, 204):
            log_info(f"Successfully removed webhook {external_id}")
            return UnsubscribeResult(
                success=True,
                message=f"Successfully removed webhook {external_id} from Mercury"
            )

        if response.status_code == 404:
            log_info(f"Webhook {external_id} not found (already deleted)")
            return UnsubscribeResult(
                success=True,
                message=f"Webhook {external_id} not found in Mercury (already deleted)"
            )

        response_data = None
        try:
            response_data = response.json() if response.content else None
        except json.JSONDecodeError:
            pass

        log_error(f"Failed to delete webhook: {response.text}")
        raise UnsubscribeError(
            message=f"Failed to delete webhook: {response.text}",
            error_code="WEBHOOK_DELETION_FAILED",
            external_response=response_data,
        )

    def _refresh_subscription(
        self,
        subscription: Subscription,
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:
        """Refresh the webhook subscription."""
        log_info("=== _refresh_subscription called ===")
        
        external_id = subscription.properties.get("external_id")
        log_info(f"Refreshing webhook ID: {external_id}")
        
        if not external_id:
            log_error("Missing webhook ID for refresh")
            raise SubscriptionError(
                "Missing webhook ID for refresh",
                error_code="MISSING_PROPERTIES",
            )

        access_token = credentials.get("access_token")
        if not access_token:
            log_error("Mercury API access token is required.")
            raise SubscriptionError(
                "Mercury API access token is required.",
                error_code="MISSING_CREDENTIALS",
            )

        api_base_url = self._get_api_base_url(credentials)
        url = f"{api_base_url}/webhooks/{external_id}"
        log_info(f"Getting webhook status at: GET {url}")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json;charset=utf-8",
        }

        try:
            response = httpx.get(
                url,
                headers=headers,
                timeout=self._REQUEST_TIMEOUT
            )
            log_info(f"Response status: {response.status_code}")
        except httpx.HTTPError as exc:
            log_error(f"Network error while refreshing webhook: {exc}")
            raise SubscriptionError(
                f"Network error while refreshing webhook: {exc}",
                error_code="NETWORK_ERROR"
            ) from exc

        if response.status_code == 200:
            webhook_data = response.json()
            updated_properties = dict(subscription.properties)
            updated_properties["status"] = webhook_data.get("status", "active")
            
            log_info(f"Webhook refreshed successfully, status: {updated_properties['status']}")
            
            return Subscription(
                endpoint=subscription.endpoint,
                parameters=subscription.parameters,
                properties=updated_properties,
            )

        if response.status_code == 404:
            log_error(f"Webhook {external_id} no longer exists on Mercury")
            raise SubscriptionError(
                f"Webhook {external_id} no longer exists on Mercury",
                error_code="WEBHOOK_NOT_FOUND",
            )

        log_error(f"Failed to refresh webhook: {response.text}")
        raise SubscriptionError(
            f"Failed to refresh webhook: {response.text}",
            error_code="WEBHOOK_REFRESH_FAILED",
        )
