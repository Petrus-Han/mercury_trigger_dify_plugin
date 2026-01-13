import json
from collections.abc import Generator
from typing import Any

import httpx

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class GetAccountsTool(Tool):
    """Tool to fetch all accounts from Mercury Banking."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Fetch all bank accounts associated with your Mercury login."""
        access_token = self.runtime.credentials.get("access_token")
        
        if not access_token:
            yield self.create_text_message("Mercury API Access Token is required.")
            return
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        
        try:
            response = httpx.get(
                "https://api.mercury.com/api/v1/accounts",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 401:
                yield self.create_text_message("Invalid or expired Mercury API access token.")
                return
            
            response.raise_for_status()
            data = response.json()
            accounts = data.get("accounts", [])
            
            # Format accounts for output
            result = [
                {
                    "id": acc.get("id"),
                    "name": acc.get("name"),
                    "type": acc.get("type"),
                    "status": acc.get("status"),
                    "available_balance": acc.get("availableBalance"),
                    "current_balance": acc.get("currentBalance"),
                    "currency": acc.get("currency", "USD"),
                }
                for acc in accounts
            ]
            
            yield self.create_json_message(result)
            
        except httpx.RequestException as e:
            yield self.create_text_message(f"Failed to fetch Mercury accounts: {str(e)}")
