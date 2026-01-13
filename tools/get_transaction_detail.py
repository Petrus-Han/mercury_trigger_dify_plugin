from collections.abc import Generator
from typing import Any

import httpx

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class GetTransactionDetailTool(Tool):
    """Tool to fetch full details of a specific Mercury transaction."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Fetch full details for a specific Mercury transaction."""
        access_token = self.runtime.credentials.get("access_token")
        transaction_id = tool_parameters.get("transaction_id")
        
        if not access_token:
            yield self.create_text_message("Mercury API Access Token is required.")
            return
        
        if not transaction_id:
            yield self.create_text_message("Transaction ID is required.")
            return
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        
        try:
            response = httpx.get(
                f"https://api.mercury.com/api/v1/transactions/{transaction_id}",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 401:
                yield self.create_text_message("Invalid or expired Mercury API access token.")
                return
            
            if response.status_code == 404:
                yield self.create_text_message(f"Transaction {transaction_id} not found.")
                return
            
            response.raise_for_status()
            transaction = response.json()
            
            # Format transaction for output
            result = {
                "id": transaction.get("id"),
                "amount": transaction.get("amount"),
                "status": transaction.get("status"),
                "posted_at": transaction.get("postedAt"),
                "counterparty_name": transaction.get("counterpartyName"),
                "bank_description": transaction.get("bankDescription"),
                "note": transaction.get("note"),
                "category": transaction.get("category"),
                "type": transaction.get("type"),
            }
            
            yield self.create_json_message(result)
            
        except httpx.RequestException as e:
            yield self.create_text_message(f"Failed to fetch transaction details: {str(e)}")
