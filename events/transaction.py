from __future__ import annotations

from typing import Any, Mapping

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event


class TransactionEvent(Event):
    """Mercury transaction event handler.
    
    Processes incoming transaction webhooks and normalizes the payload
    for downstream workflow consumption.
    """

    def _on_event(
        self, 
        request: Request, 
        parameters: Mapping[str, Any], 
        payload: Mapping[str, Any]
    ) -> Variables:
        """Process transaction event and return normalized variables.
        
        Expected payload format (from external poller or Mercury):
        {
            "id": "evt_xxx",
            "resourceType": "transaction",
            "operationType": "created" | "updated",
            "resourceId": "txn_xxx",
            "mergePatch": {
                "accountId": "acc_xxx",
                "amount": -150.00,
                "status": "posted",
                "postedAt": "2025-12-19T10:30:00Z",
                "counterpartyName": "Staples",
                "bankDescription": "DEBIT CARD PURCHASE",
                "note": "",
                "category": "",
                "type": "debit"
            }
        }
        """
        # Get the raw payload from request
        raw_payload = request.get_json(force=True) or {}
        
        # Extract fields from Mercury's JSON Merge Patch format
        merge_patch = raw_payload.get("mergePatch", {})
        
        # Normalize the transaction data
        return Variables(variables={
            "event_id": raw_payload.get("id", ""),
            "transaction_id": raw_payload.get("resourceId", ""),
            "operation_type": raw_payload.get("operationType", ""),
            "account_id": merge_patch.get("accountId", ""),
            "amount": merge_patch.get("amount"),
            "status": merge_patch.get("status", ""),
            "posted_at": merge_patch.get("postedAt", ""),
            "counterparty_name": merge_patch.get("counterpartyName", ""),
            "bank_description": merge_patch.get("bankDescription", ""),
            "note": merge_patch.get("note", ""),
            "category": merge_patch.get("category", ""),
            "transaction_type": merge_patch.get("type", ""),
        })
