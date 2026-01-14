# Mercury Trigger Plugin 流程文档

## 概述

Mercury Trigger Plugin 是一个 Dify Trigger 插件，用于接收 Mercury 银行的实时交易事件。通过 Webhook 机制实现事件驱动的工作流触发。

---

## 整体架构

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Mercury Bank   │     │   Dify Plugin   │     │  Dify Workflow  │
│    (Sandbox)    │────▶│    Runtime      │────▶│                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                      │
         │ Webhook POST         │ Subscription
         │ (Transaction Event)  │ Management
         ▼                      ▼
  api-sandbox.mercury.com   MercuryTrigger
                            MercurySubscriptionConstructor
```

---

## 核心组件

| 组件 | 类名 | 职责 |
|------|------|------|
| Trigger 分发器 | `MercuryTrigger` | 接收 Webhook 请求，验证签名，分发事件 |
| 订阅构造器 | `MercurySubscriptionConstructor` | 管理 Webhook 的创建、删除、刷新 |
| 事件处理器 | `TransactionEvent` | 解析交易数据，规范化输出变量 |

---

## 完整生命周期流程

```
┌──────────────────────────────────────────────────────────────────┐
│                    SUBSCRIPTION LIFECYCLE                        │
└──────────────────────────────────────────────────────────────────┘

用户在 Dify 创建触发器
        │
        ▼
┌───────────────────┐
│ 1. 验证 API Key   │  ──▶  GET /accounts
│ _validate_api_key │       验证 Token 有效性
└───────────────────┘
        │ ✓ 成功
        ▼
┌───────────────────┐
│ 2. 创建订阅       │  ──▶  POST /webhooks
│ _create_subscription     创建 Webhook
└───────────────────┘
        │ ✓ 返回 webhook_id + secret
        ▼
┌───────────────────┐
│ 3. 存储订阅信息   │  ──▶  Dify 平台存储
│ Subscription      │       properties: {external_id, webhook_secret, status}
└───────────────────┘
        │
        ▼
    [订阅激活，等待事件]
        │
        │ Mercury 发送交易事件
        ▼
┌───────────────────┐
│ 4. 接收 Webhook   │  ◀──  Mercury POST 请求
│ _dispatch_event   │       Headers: Mercury-Signature
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 5. 验证签名       │
│ _validate_signature      HMAC-SHA256 验证
└───────────────────┘
        │ ✓ 签名有效
        ▼
┌───────────────────┐
│ 6. 解析事件       │  ──▶  transaction event
│ _resolve_event_types
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 7. 处理交易数据   │  ──▶  规范化 Variables
│ TransactionEvent._on_event
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 8. 触发 Workflow  │  ──▶  Dify Workflow 执行
│                   │       传入交易变量
└───────────────────┘


用户删除触发器
        │
        ▼
┌───────────────────┐
│ 9. 删除订阅       │  ──▶  DELETE /webhooks/{id}
│ _delete_subscription
└───────────────────┘
```

---

## Mercury API 调用详情

### API 基础配置

| 环境 | Base URL |
|------|----------|
| **Sandbox** | `https://api-sandbox.mercury.com/api/v1` |
| Production | `https://api.mercury.com/api/v1` |

### 认证方式

```http
Authorization: Bearer {access_token}
Accept: application/json;charset=utf-8
```

### 调用的 API 列表

#### 1. 验证 Token（`_validate_api_key`）

```http
GET /accounts
```

**目的**：验证用户提供的 Access Token 是否有效

**响应处理**：
- `200 OK` → Token 有效
- `401 Unauthorized` → Token 无效或过期
- `4xx/5xx` → 其他错误

---

#### 2. 创建 Webhook（`_create_subscription`）

```http
POST /webhooks
Content-Type: application/json;charset=utf-8

{
  "url": "https://dify.example.com/webhook/xxx",
  "eventTypes": ["transaction.created", "transaction.updated"],
  "filterPaths": ["status", "amount"]  // 可选
}
```

**参数说明**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| url | string | ✓ | Dify 生成的 Webhook 回调地址 |
| eventTypes | array | ✗ | 事件类型过滤，不填则接收全部 |
| filterPaths | array | ✗ | 字段过滤，只在这些字段变化时触发 |

**成功响应** (`200/201`):

```json
{
  "id": "whk_xxx",
  "secret": "base64_encoded_secret",
  "status": "active",
  "url": "https://dify.example.com/webhook/xxx",
  "eventTypes": ["transaction.created", "transaction.updated"]
}
```

---

#### 3. 删除 Webhook（`_delete_subscription`）

```http
DELETE /webhooks/{webhook_id}
```

**响应处理**：
- `200/204` → 删除成功
- `404` → Webhook 不存在（视为成功）
- 其他 → 抛出 `UnsubscribeError`

---

#### 4. 刷新/获取 Webhook 状态（`_refresh_subscription`）

```http
GET /webhooks/{webhook_id}
```

**成功响应**：

```json
{
  "id": "whk_xxx",
  "status": "active",
  "url": "https://...",
  ...
}
```

---

## 数据存储

### Subscription 对象

当 Webhook 创建成功后，Dify 会存储以下信息：

```python
Subscription(
    endpoint="https://dify.example.com/webhook/xxx",  # Dify 回调地址
    parameters={
        "event_types": ["transaction.created", "transaction.updated"],
        "filter_paths": "status,amount"
    },
    properties={
        "external_id": "whk_xxx",        # Mercury Webhook ID
        "webhook_secret": "base64...",   # 签名验证密钥
        "status": "active"               # 状态
    }
)
```

### 存储位置

| 信息 | 存储位置 | 用途 |
|------|----------|------|
| `external_id` | Dify 数据库 (Subscription.properties) | 删除/刷新 Webhook 时使用 |
| `webhook_secret` | Dify 数据库 (Subscription.properties) | 验证 Webhook 签名 |
| `access_token` | Dify 数据库 (Credentials) | 调用 Mercury API |

---

## Webhook 签名验证机制

### Mercury 签名格式

```
Mercury-Signature: t=1705123456,v1=abc123...
```

### 验证流程

```python
# 1. 解析 Header
sig_header = "t=1705123456,v1=abc123..."
parts = {"t": "1705123456", "v1": "abc123..."}

# 2. 构造签名载荷
timestamp = parts["t"]
body = request.get_data(as_text=True)
signed_payload = f"{timestamp}.{body}"

# 3. 计算预期签名
secret_bytes = base64.b64decode(webhook_secret)
expected = hmac.new(secret_bytes, signed_payload.encode(), hashlib.sha256).hexdigest()

# 4. 比较签名
hmac.compare_digest(parts["v1"], expected)  # 必须匹配
```

---

## 事件处理流程

### Mercury Webhook Payload 格式

```json
{
  "id": "evt_xxx",
  "resourceType": "transaction",
  "operationType": "created",
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
```

### TransactionEvent 输出变量

```python
Variables(variables={
    "event_id": "evt_xxx",              # 事件 ID
    "transaction_id": "txn_xxx",        # 交易 ID
    "operation_type": "created",        # 操作类型
    "account_id": "acc_xxx",            # 账户 ID
    "amount": -150.00,                  # 金额（负数为支出）
    "status": "posted",                 # 状态
    "posted_at": "2025-12-19T10:30:00Z",# 入账时间
    "counterparty_name": "Staples",     # 对方名称
    "bank_description": "DEBIT CARD...",# 银行描述
    "note": "",                         # 备注
    "category": "",                     # 分类
    "transaction_type": "debit",        # 交易类型
})
```

---

## 刷新机制

### 触发时机

刷新由 Dify 平台自动调用，通常在以下情况：
1. 订阅长时间未接收事件
2. 平台定期健康检查
3. 用户手动刷新

### 流程

```
_refresh_subscription()
        │
        ▼
  GET /webhooks/{external_id}
        │
        ├── 200 OK ──▶ 更新 status，返回更新后的 Subscription
        │
        ├── 404 Not Found ──▶ 抛出 SubscriptionError (WEBHOOK_NOT_FOUND)
        │                     需要用户重新创建订阅
        │
        └── 其他错误 ──▶ 抛出 SubscriptionError (WEBHOOK_REFRESH_FAILED)
```

---

## 配置项说明

### Provider 配置 (`provider/mercury.yaml`)

```yaml
# 订阅属性（创建后自动填充）
subscription_schema:
  - name: webhook_secret    # Webhook 签名密钥

# 订阅参数（用户配置）
subscription_constructor:
  parameters:
    - name: event_types     # 事件类型选择
    - name: filter_paths    # 字段过滤

  # 凭证配置
  credentials_schema:
    access_token:           # Mercury API Token
```

### Event 配置 (`events/transaction.yaml`)

```yaml
parameters:
  - name: operation_filter  # 事件级过滤（all/created/updated）

output_schema:              # 输出到 Workflow 的变量定义
  properties:
    event_id, transaction_id, operation_type, ...
```

---

## 错误处理

| 错误类型 | 触发条件 | 错误码 |
|----------|----------|--------|
| `TriggerProviderCredentialValidationError` | Token 验证失败 | - |
| `SubscriptionError` | Webhook 创建/刷新失败 | `MISSING_CREDENTIALS`, `NETWORK_ERROR`, `WEBHOOK_CREATION_FAILED`, `WEBHOOK_NOT_FOUND` |
| `UnsubscribeError` | Webhook 删除失败 | `MISSING_PROPERTIES`, `WEBHOOK_DELETION_FAILED` |
| `TriggerValidationError` | 签名验证失败 | - |
| `TriggerDispatchError` | Payload 解析失败 | - |

---

## 序列图

```
┌────────┐      ┌─────────┐      ┌────────────────────┐      ┌───────────┐
│  User  │      │  Dify   │      │  MercuryTrigger    │      │  Mercury  │
└───┬────┘      └────┬────┘      │  Plugin            │      │  API      │
    │                │           └─────────┬──────────┘      └─────┬─────┘
    │                │                     │                       │
    │ Create Trigger │                     │                       │
    │───────────────▶│                     │                       │
    │                │ _validate_api_key() │                       │
    │                │────────────────────▶│                       │
    │                │                     │ GET /accounts         │
    │                │                     │──────────────────────▶│
    │                │                     │    200 OK             │
    │                │                     │◀──────────────────────│
    │                │                     │                       │
    │                │ _create_subscription│                       │
    │                │────────────────────▶│                       │
    │                │                     │ POST /webhooks        │
    │                │                     │──────────────────────▶│
    │                │                     │    {id, secret}       │
    │                │                     │◀──────────────────────│
    │                │  Subscription saved │                       │
    │                │◀────────────────────│                       │
    │  Success       │                     │                       │
    │◀───────────────│                     │                       │
    │                │                     │                       │
    │                │                     │    ... 等待事件 ...    │
    │                │                     │                       │
    │                │                     │  POST (Transaction)   │
    │                │                     │◀──────────────────────│
    │                │                     │                       │
    │                │ _dispatch_event()   │                       │
    │                │◀────────────────────│                       │
    │                │                     │                       │
    │                │ TransactionEvent    │                       │
    │                │   ._on_event()      │                       │
    │                │◀────────────────────│                       │
    │                │                     │                       │
    │ Workflow Run   │                     │                       │
    │◀───────────────│                     │                       │
```

---

## 文件结构

```
mercury_trigger_plugin/
├── manifest.yaml           # 插件清单
├── main.py                 # 入口文件
├── requirements.txt        # 依赖
├── _assets/
│   └── icon.svg           # 图标
├── provider/
│   ├── mercury.yaml       # Provider 配置
│   └── mercury.py         # MercuryTrigger + MercurySubscriptionConstructor
└── events/
    ├── transaction.yaml   # 事件配置
    └── transaction.py     # TransactionEvent 处理器
```
