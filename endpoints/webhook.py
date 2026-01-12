import json
import hmac
import hashlib
from typing import Mapping
from werkzeug import Request, Response
from dify_plugin import Endpoint

class MercuryWebhookEndpoint(Endpoint):
    """
    Receives transaction events directly from Mercury's native webhook system.
    """
    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        if r.method != "POST":
            return Response(status=405, response="Method Not Allowed")

        # 1. Signature Verification (Required for production)
        secret = settings.get("webhook_secret")
        if secret:
            if not self._verify_signature(r, secret):
                return Response(status=401, response="Invalid Signature")

        # 2. Parse Payload
        try:
            payload = r.get_json()
            if not payload:
                return Response(status=400, response="Missing Payload")
        except Exception:
            return Response(status=400, response="Invalid JSON")

        # 3. Extract event details (using Mercury's JSON Merge Patch format)
        resource_type = payload.get("resourceType")
        operation_type = payload.get("operationType")
        resource_id = payload.get("resourceId")
        merge_patch = payload.get("mergePatch", {})

        # Only process transaction events
        if resource_type != "transaction":
            return Response(status=200, response=json.dumps({"status": "ignored", "reason": "not a transaction"}))

        # 4. Trigger Dify Workflow/App
        app_config = settings.get("app")
        if not app_config:
            return Response(status=500, response="Target App Not Configured")

        try:
            result = self.session.app.workflow.run(
                workflow_id=app_config["app_id"],
                inputs={
                    "event_id": payload.get("id"),
                    "transaction_id": resource_id,
                    "operation_type": operation_type,  # "created" or "updated"
                    "status": merge_patch.get("status"),
                    "amount": merge_patch.get("amount"),
                    "posted_at": merge_patch.get("postedAt"),
                    "counterparty": merge_patch.get("counterpartyName"),
                    "note": merge_patch.get("note"),
                }
            )
            
            return Response(
                response=json.dumps({"status": "success", "workflow_run_id": result.get("workflow_run_id")}),
                status=200,
                content_type="application/json"
            )
        except Exception as e:
            return Response(
                response=json.dumps({"status": "error", "message": str(e)}),
                status=500,
                content_type="application/json"
            )

    def _verify_signature(self, r: Request, secret: str) -> bool:
        """
        Verifies the Mercury-Signature header.
        Format: t=<timestamp>,v1=<hex_signature>
        Message: <timestamp>.<request_body>
        """
        sig_header = r.headers.get("Mercury-Signature")
        if not sig_header:
            return False
        
        try:
            # Parse header: t=...,v1=...
            parts = dict(p.split("=", 1) for p in sig_header.split(","))
            timestamp = parts.get("t")
            signature = parts.get("v1")
            
            if not timestamp or not signature:
                return False

            # Construct signed payload
            signed_payload = f"{timestamp}.{r.get_data(as_text=True)}"
            
            # Compute expected signature
            expected = hmac.new(
                secret.encode(),
                signed_payload.encode(),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(signature, expected)
        except Exception:
            return False
