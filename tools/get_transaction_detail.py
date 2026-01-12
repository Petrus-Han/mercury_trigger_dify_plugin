from dify_plugin.interfaces.tool import Tool
import requests

class GetTransactionDetailTool(Tool):
    """
    Tool to fetch full details of a specific Mercury transaction.
    """
    def invoke(self, credentials: dict, parameters: dict) -> dict:
        access_token = credentials.get("access_token")
        transaction_id = parameters.get("transaction_id")
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        url = f"https://api.mercury.com/api/v1/transactions/{transaction_id}"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        return response.json()
