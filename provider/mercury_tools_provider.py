import httpx
from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class MercuryToolsProvider(ToolProvider):
    """Mercury Banking Tools Provider.
    
    Validates Mercury API credentials for the tools.
    """

    def _validate_credentials(self, credentials: dict) -> None:
        """Validate Mercury API access token by fetching accounts."""
        access_token = credentials.get("access_token")
        
        if not access_token:
            raise ToolProviderCredentialValidationError(
                "Mercury API Access Token is required."
            )

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
                raise ToolProviderCredentialValidationError(
                    "Invalid or expired Mercury API access token."
                )
            
            if response.status_code >= 400:
                raise ToolProviderCredentialValidationError(
                    f"Mercury API error: {response.text}"
                )
                
        except httpx.RequestException as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to connect to Mercury API: {str(e)}"
            )
