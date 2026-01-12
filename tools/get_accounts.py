from dify_plugin.interfaces.tool import Tool
import requests

class GetAccountsTool(Tool):
    """
    Tool to fetch all accounts from Mercury.
    """
    def invoke(self, credentials: dict, parameters: dict) -> list:
        access_token = credentials.get("access_token")
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        response = requests.get("https://api.mercury.com/api/v1/accounts", headers=headers)
        response.raise_for_status()
        
        data = response.json()
        accounts = data.get("accounts", [])
        
        # Return simplified list for the workflow
        return [
            {
                "id": acc.get("id"),
                "name": acc.get("name"),
                "type": acc.get("type"),
                "balance": acc.get("availableBalance"),
                "currency": acc.get("currency")
            } for acc in accounts
        ]
