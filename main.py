from dify_plugin import Plugin
from tools.get_accounts import GetAccountsTool
from tools.get_transaction_detail import GetTransactionDetailTool
from endpoints.webhook import MercuryWebhookEndpoint

plugin = Plugin()

# Register Tools
plugin.register_tool('get_accounts', GetAccountsTool)
plugin.register_tool('get_transaction_detail', GetTransactionDetailTool)

# Register Endpoint
plugin.register_endpoint('mercury_webhook', MercuryWebhookEndpoint)

if __name__ == '__main__':
    plugin.run()
