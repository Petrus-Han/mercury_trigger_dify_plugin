# Mercury Banking Trigger Plugin

Mercury Banking Trigger plugin for Dify - Receive real-time transaction events via webhooks.

## Overview

This plugin enables your Dify workflows to react to Mercury Banking events in real-time. When transactions occur in your Mercury accounts, webhooks are automatically triggered to start your workflows.

## Features

- **Real-time Events**: Receive instant notifications when transactions are created or updated
- **Automatic Webhook Management**: Plugin handles webhook subscription lifecycle automatically
- **Signature Verification**: Secure HMAC-SHA256 signature validation for all incoming webhooks
- **Event Filtering**: Configure which event types and field changes trigger workflows
- **Environment Support**: Works with both Sandbox (testing) and Production Mercury accounts

## Event Types

### Transaction Event

Triggered when Mercury transactions are created or updated.

**Output Variables:**
- `event_id`: Unique event identifier
- `transaction_id`: Transaction ID
- `operation_type`: Event operation (`created` or `updated`)
- `account_id`: Mercury account ID
- `amount`: Transaction amount (negative for debits, positive for credits)
- `status`: Transaction status (`posted`, `pending`, etc.)
- `posted_at`: Transaction posting timestamp (ISO 8601)
- `counterparty_name`: Name of the other party
- `bank_description`: Bank's description of the transaction
- `note`: User-added note
- `category`: Transaction category
- `transaction_type`: Type of transaction (`debit`, `credit`)

## Setup

### 1. Get Mercury API Access Token

1. Log in to your Mercury account
2. Go to **Settings** → **API Tokens**
3. Create a new token with the following permission:
   - `webhooks:write` - Required to create and manage webhooks
4. Copy the access token

**Important**: Mercury API keys are environment-specific. Sandbox keys only work with the Sandbox environment, and Production keys only work with Production.

### 2. Configure Webhook in Mercury (Manual Setup Required)

**Note**: Mercury does not support automatic webhook creation via API for security reasons. You must manually configure the webhook in Mercury:

1. Log in to Mercury Dashboard
2. Go to **Settings** → **Webhooks**
3. Click **Create Webhook**
4. Use the webhook URL provided by Dify when you create the trigger
5. Select event types: `transaction.created`, `transaction.updated`
6. (Optional) Add filter paths to only trigger on specific field changes
7. Save the webhook and copy the **Webhook Secret**

### 3. Install Plugin in Dify

1. Upload the `mercury_trigger_plugin.difypkg` to your Dify instance
2. Or use remote debugging during development (see below)

### 4. Configure Trigger in Workflow

1. Create a new workflow in Dify
2. Add **Mercury Transaction Trigger** as the trigger
3. Configure credentials:
   - **Mercury API Access Token**: Your API token from step 1
   - **API Environment**: Select `Sandbox` or `Production`
4. Configure subscription parameters (optional):
   - **Event Types**: Select which events to receive (default: all transaction events)
   - **Filter Paths**: Comma-separated field names to filter events (e.g., `status,amount`)
5. Save the workflow

The plugin will automatically create a webhook subscription in Mercury when you save the workflow.

## Usage Examples

### Example 1: Log All Transactions

```yaml
Trigger: Mercury Transaction Trigger
  Event Types: [transaction.created, transaction.updated]

Step 1: Code Node
  Input Variables:
    - transaction_id
    - amount
    - counterparty_name
  Code:
    print(f"Transaction {transaction_id}: {counterparty_name} - ${amount}")
```

### Example 2: Sync Large Expenses to QuickBooks

```yaml
Trigger: Mercury Transaction Trigger
  Event Types: [transaction.created]
  Filter Paths: status

Step 1: Condition
  IF: amount < -500.00 AND status == "posted"

Step 2: QuickBooks Tool - Create Purchase
  Parameters:
    - amount: abs(amount)
    - description: bank_description
    - note: note
    - txn_date: posted_at
```

### Example 3: Alert on Large Deposits

```yaml
Trigger: Mercury Transaction Trigger
  Event Types: [transaction.created]

Step 1: Condition
  IF: amount > 10000 AND transaction_type == "credit"

Step 2: Send Notification
  Message: "Large deposit received: ${amount} from ${counterparty_name}"
```

### Example 4: Integration with Mercury Tools

Combine the trigger with Mercury Tools plugin for additional context:

```yaml
Trigger: Mercury Transaction Trigger
  → Receives transaction event

Step 1: Mercury Tools - Get Account
  Parameters:
    account_id: {from trigger}
  → Fetch full account details

Step 2: Mercury Tools - Get Transactions
  Parameters:
    account_id: {from trigger}
    limit: 10
  → Get recent transactions for context

Step 3: LLM Analysis
  → Analyze transaction patterns and generate insights
```

## Event Filtering

### Event Types

Filter which operations trigger your workflow:
- `transaction.created` - New transactions only
- `transaction.updated` - Transaction updates only
- (Leave empty for all events)

### Filter Paths

Only trigger when specific fields change:
- `status` - Trigger when transaction status changes
- `amount` - Trigger when amount is modified
- `status,amount` - Trigger when either field changes

## Security

### Webhook Signature Verification

All incoming webhooks are verified using HMAC-SHA256 signatures:

1. Mercury includes a `Mercury-Signature` header with each webhook
2. Format: `t=<timestamp>,v1=<signature>`
3. The plugin verifies the signature using the webhook secret
4. Requests with invalid signatures are rejected

This ensures that only authentic Mercury webhooks can trigger your workflows.

## Webhook Lifecycle

### Creation
When you save a workflow with this trigger, the plugin:
1. Validates your Mercury API token
2. Creates a webhook subscription in Mercury
3. Stores the webhook ID and secret for future use

### Updates
Dify periodically refreshes webhook status to ensure it's still active.

### Deletion
When you delete the trigger or workflow, the plugin:
1. Deletes the webhook subscription from Mercury
2. Cleans up stored credentials

## Development & Testing

### Local Development

```bash
# Navigate to plugin directory
cd mercury_trigger_plugin

# Create virtual environment
uv venv
source .venv/bin/activate  # or .venv/Scripts/activate on Windows

# Install dependencies
uv pip install -r requirements.txt
```

### Remote Debugging

Configure `.env` file:
```env
INSTALL_METHOD=remote
REMOTE_INSTALL_HOST=debug.dify.ai
REMOTE_INSTALL_PORT=5003
REMOTE_INSTALL_KEY=your-debug-key
```

Run the plugin:
```bash
python main.py
```

### Testing with Sandbox

1. Create a Mercury Sandbox account at https://mercury.com/developers
2. Get sandbox API credentials
3. Create test transactions in the sandbox
4. Verify your workflow triggers correctly

### Package Plugin

```bash
dify plugin package ./mercury_trigger_plugin
```

## Troubleshooting

### Webhook Not Triggering

1. **Check API Environment**: Ensure your API token matches the selected environment (Sandbox vs Production)
2. **Verify Webhook Status**: Check Mercury Dashboard → Webhooks to see if webhook is active
3. **Check Event Types**: Ensure your transaction matches the selected event types
4. **Check Filter Paths**: If using filter paths, ensure the fields you're monitoring are actually changing

### Signature Verification Failed

1. **Webhook Secret Mismatch**: Ensure the webhook secret stored in Dify matches the one in Mercury
2. **Time Skew**: Verify system clocks are synchronized
3. **Replay Attack**: Mercury signatures include timestamps to prevent replay attacks

### Authentication Errors

1. **Token Expired**: Mercury tokens expire after 1 hour (for OAuth). Recreate the trigger with a fresh token
2. **Wrong Environment**: Sandbox tokens don't work with Production and vice versa
3. **Insufficient Permissions**: Ensure token has `webhooks:write` permission

## API Reference

See [Mercury API Documentation](https://docs.mercury.com) for full API details.

### Endpoints Used

- `GET /accounts` - Validate API token
- `POST /webhooks` - Create webhook subscription
- `GET /webhooks/{id}` - Refresh webhook status
- `DELETE /webhooks/{id}` - Delete webhook subscription

## Related Plugins

- **Mercury Tools Plugin** (`mercury_tools_plugin`): Query accounts, transactions, and financial data
- **QuickBooks Plugin** (`quickbooks_plugin`): Sync transactions to QuickBooks for accounting

## Environment Support

| Environment | Base URL | Use Case |
|-------------|----------|----------|
| **Sandbox** | `https://api-sandbox.mercury.com/api/v1` | Testing and development |
| Production | `https://api.mercury.com/api/v1` | Live data and real transactions |

## Version History

See [FLOW.md](FLOW.md) for detailed technical documentation.

## License

Copyright (c) 2026

## Support

For issues or questions, please refer to the Dify plugin documentation.
