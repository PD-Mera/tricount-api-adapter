# Tricount Private API – Integration Reference

> Target examined: Tricount Android `14.0.3` (`com.bunq.tricount.android`)  
> Base URL: `https://api.tricount.bunq.com`  
> Status: private / undocumented API. It may change without notice.

## 1. Integration scope

This document describes the Tricount private HTTP API discovered in the Android app and cross-checked against current reverse-engineered clients.

Recommended use: backend-to-backend integration for tricounts that you own or are explicitly authorized to access. Do not expose device credentials, session tokens, or tricount sharing tokens in browser JavaScript.

### Confidence labels

- **VERIFIED**: endpoint/path and behavior are confirmed by reverse-engineered clients and/or live tests, and the path is present in the Android app.
- **APK-OBSERVED**: path/class is present in Tricount 14.0.3, but this document does not claim that the route is currently usable.
- **BROKEN/CURRENTLY ABSENT**: path exists in the app or older references, but recent live probing reports the server route as unavailable.

---

## 2. Base URL

```text
https://api.tricount.bunq.com
```

All paths below already include `/v1` where applicable.

---

## 3. Authentication model

Tricount does not use a normal email/password login for this API. A client registers an anonymous device identity and receives:

- an authentication token;
- a Tricount API user ID.

Persist the device identity and reuse it. Do not generate a new identity for every request.

### 3.1 Persistent device credentials

Generate once and store securely:

```json
{
  "app_id": "<uuid-v4>",
  "private_key_pem": "<RSA private key>",
  "public_key_pem": "<RSA public key>"
}
```

Observed working reverse-engineered implementations use a 2048-bit RSA key pair.

### 3.2 Common request headers

The current reverse-engineered client uses these headers:

```http
User-Agent: com.bunq.tricount.android:RELEASE:7.0.7:3174:ANDROID:13:C
app-id: <persistent-app-uuid>
X-Bunq-Client-Request-Id: 049bfcdf-6ae4-4cee-af7b-45da31ea85d0
X-Bunq-Client-Authentication: <session-token>
Content-Type: application/json
```

Notes:

- `X-Bunq-Client-Authentication` is omitted for initial session installation.
- The server expects the client to identify itself as the Tricount app; a generic User-Agent may be rejected.
- The request-id value above is used by a current reverse-engineered client. Treat it as implementation detail, not an official API contract.

### 3.3 Create/register a session — VERIFIED

```http
POST /v1/session-registry-installation
```

Request:

```json
{
  "app_installation_uuid": "<app_id>",
  "client_public_key": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----",
  "device_description": "Android"
}
```

Representative response envelope:

```json
{
  "Response": [
    {
      "Token": {
        "token": "<session-token>"
      }
    },
    {
      "UserPerson": {
        "id": 12345678,
        "display_name": "tricount participant",
        "public_uuid": "..."
      }
    }
  ]
}
```

Extract and cache:

```text
Token.token   -> X-Bunq-Client-Authentication
UserPerson.id -> userId used in /v1/user/{userId}/...
```

Recommended behavior: when an authenticated API call returns `401`, create/register a new session once and retry the original request once.

### 3.4 Session-related paths found in APK 14.0.3

| Method | Path | Status |
|---|---|---|
| POST | `/v1/session-registry-installation` | VERIFIED |
| POST | `/v1/session-registry-refresh` | APK-OBSERVED |
| POST | `/v1/session-registry-request` | APK-OBSERVED |
| POST | `/v1/session-registry-social` | APK-OBSERVED |
| — | `/session-registry-confirm` | APK-OBSERVED |

For a new integration, `session-registry-installation` is sufficient for the documented flow below.

---

## 4. Response envelope

Most JSON responses use a top-level `Response` array:

```json
{
  "Response": [
    {
      "SomeObject": {
        "id": 123
      }
    }
  ]
}
```

Mutation endpoints commonly return:

```json
{
  "Response": [
    {
      "Id": {
        "id": 123456789
      }
    }
  ]
}
```

Amounts are usually decimal strings, not JSON numbers.

---

# 5. Tricount / Registry endpoints

In Tricount API terminology, one Tricount is represented as a **Registry**.

## 5.1 List/fetch tricounts — VERIFIED

```http
GET /v1/user/{userId}/registry
```

Optional query parameters:

| Parameter | Type | Description |
|---|---|---|
| `public_identifier_token` | string | Sharing token from a URL such as `tricount.com/tABC123xyz` |
| `registry_id` | integer | Internal registry ID |

Examples:

```http
GET /v1/user/12345678/registry
```

```http
GET /v1/user/12345678/registry?public_identifier_token=tABC123xyz
```

Representative response item:

```json
{
  "Registry": {
    "id": 102257091,
    "uuid": "034d1734-...",
    "title": "Japan Trip",
    "description": "Trip expenses",
    "currency": "JPY",
    "emoji": "🗾",
    "category": "TRAVEL",
    "status": "READ_WRITE",
    "created": "2026-03-01 10:57:38.087586",
    "public_identifier_token": "tABC123xyz",
    "memberships": [],
    "all_registry_entry": [],
    "all_registry_gallery_attachment": []
  }
}
```

## 5.2 Synchronize/join by sharing token — VERIFIED

```http
POST /v1/user/{userId}/registry-synchronization
```

This is the key endpoint for loading a tricount from its sharing token.

Request:

```json
{
  "all_registry_active": [
    {
      "public_identifier_token": "tABC123xyz"
    }
  ],
  "all_registry_archived": [],
  "all_registry_deleted": []
}
```

It can contain multiple tokens.

Representative response:

```json
{
  "Response": [
    {
      "RegistrySynchronization": {
        "all_registry_active": [
          {
            "id": 102257091,
            "title": "Japan Trip",
            "memberships": [],
            "all_registry_entry": []
          }
        ],
        "all_registry_archived": []
      }
    }
  ]
}
```

Security note: treat the sharing token as a secret. A sharing token can grant substantial access to the tricount.

## 5.3 Create a tricount — VERIFIED

```http
POST /v1/user/{userId}/registry
```

Request:

```json
{
  "currency": "JPY",
  "title": "Japan Trip",
  "description": "Trip expenses"
}
```

Response:

```json
{
  "Response": [
    {
      "Id": {
        "id": 104488759
      }
    }
  ]
}
```

## 5.4 Read one tricount — VERIFIED / APK path present

```http
GET /v1/user/{userId}/registry/{registryId}
```

Response object follows the `Registry` structure described above.

## 5.5 Update a tricount — VERIFIED

```http
PUT /v1/user/{userId}/registry/{registryId}
```

Update metadata:

```json
{
  "title": "New title",
  "emoji": "🍜",
  "category": "FOOD_AND_DRINK"
}
```

Archive:

```json
{
  "status": "READ_ONLY"
}
```

Unarchive:

```json
{
  "status": "READ_WRITE"
}
```

Set which member represents this client:

```json
{
  "membership_uuid_active": "<member-uuid>"
}
```

Rename members by updating the registry with the complete membership list:

```json
{
  "memberships": [
    {
      "uuid": "<member-uuid>",
      "status": "ACTIVE",
      "auto_add_card_transaction": "",
      "setting": null,
      "alias": {
        "type": "UUID",
        "value": "<member-uuid>",
        "name": "Alice"
      }
    }
  ]
}
```

Delete one or more memberships:

```json
{
  "memberships": [
    {
      "uuid": "<remaining-member-uuid>",
      "status": "ACTIVE",
      "alias": {
        "type": "UUID",
        "value": "<remaining-member-uuid>",
        "name": "Alice"
      }
    }
  ],
  "deleted_membership_ids": [438275026]
}
```

Observed categories include:

```text
GENERAL
OTHER
TRAVEL
FOOD_AND_DRINK
TRANSPORT
SHOPPING
ENTERTAINMENT
GROCERIES
```

## 5.6 Delete a tricount — VERIFIED

```http
DELETE /v1/user/{userId}/registry/{registryId}
```

No request body.

---

# 6. Members

## 6.1 List members — VERIFIED

```http
GET /v1/user/{userId}/registry/{registryId}/registry-membership
```

Representative response:

```json
{
  "Response": [
    {
      "RegistryMembershipNonUser": {
        "id": 438275026,
        "uuid": "356493be-...",
        "alias": {
          "display_name": "Alice",
          "pointer": {
            "type": "UUID",
            "value": "356493be-...",
            "name": "Alice"
          }
        },
        "status": "ACTIVE",
        "setting": {
          "auto_add_card_transaction": "INACTIVE"
        }
      }
    }
  ]
}
```

## 6.2 Update one membership — VERIFIED, limited usefulness

```http
PUT /v1/user/{userId}/registry/{registryId}/registry-membership/{membershipId}
```

Request:

```json
{
  "alias": {
    "name": "Alice",
    "type": "UUID",
    "value": "<member-uuid>"
  }
}
```

Alias request fields differ from response fields:

| Request | Response |
|---|---|
| `alias.name` | `alias.display_name` |
| `alias.type` | `alias.pointer.type` |
| `alias.value` | `alias.pointer.value` |

Observed alias types:

```text
UUID
EMAIL
PHONE_NUMBER
```

For renaming a member, updating the complete registry membership list via `PUT /registry/{registryId}` is more reliable.

---

# 7. Transactions / Registry entries

## 7.1 Create an expense — VERIFIED

```http
POST /v1/user/{userId}/registry/{registryId}/registry-entry
```

Expense example:

```json
{
  "uuid": "<uuid-v4>",
  "description": "Dinner",
  "amount": {
    "value": "-1200",
    "currency": "JPY"
  },
  "membership_uuid_owner": "<payer-member-uuid>",
  "allocations": [
    {
      "membership_uuid": "<member-1-uuid>",
      "amount": {
        "value": "-600",
        "currency": "JPY"
      },
      "type": "AMOUNT"
    },
    {
      "membership_uuid": "<member-2-uuid>",
      "amount": {
        "value": "-600",
        "currency": "JPY"
      },
      "type": "AMOUNT"
    }
  ],
  "type_transaction": "NORMAL",
  "status": "ACTIVE",
  "date": "2026-09-23 20:30:00.000000",
  "category": "FOOD_AND_DRINK"
}
```

### Transaction types

```text
NORMAL  -> expense
INCOME  -> income/refund
BALANCE -> reimbursement / settlement transfer
```

Observed sign convention:

- expenses: negative values;
- income: positive values;
- reimbursements: positive transfer amount.

### Ratio split

```json
{
  "allocations": [
    {
      "membership_uuid": "<member-1>",
      "amount": {
        "value": "-25.00",
        "currency": "EUR"
      },
      "type": "RATIO",
      "share_ratio": 1
    },
    {
      "membership_uuid": "<member-2>",
      "amount": {
        "value": "-50.00",
        "currency": "EUR"
      },
      "type": "RATIO",
      "share_ratio": 2
    }
  ]
}
```

### Foreign-currency transaction

```json
{
  "amount": {
    "value": "-15000",
    "currency": "JPY"
  },
  "amount_local": {
    "value": "-100.00",
    "currency": "USD"
  },
  "exchange_rate": "150",
  "allocations": [
    {
      "membership_uuid": "<member-uuid>",
      "amount": {
        "value": "-15000",
        "currency": "JPY"
      },
      "amount_local": {
        "value": "-100.00",
        "currency": "USD"
      },
      "type": "AMOUNT"
    }
  ]
}
```

### Optional fields

```text
category
category_custom
amount_local
exchange_rate
attachment
```

Observed standard expense categories:

```text
TRAVEL
ENTERTAINMENT
GROCERIES
HEALTHCARE
INSURANCE
RENT_AND_UTILITIES
FOOD_AND_DRINK
SHOPPING
TRANSPORT
OTHER
UNCATEGORIZED
```

Custom category example:

```json
{
  "category": "OTHER",
  "category_custom": "Coffee ☕️"
}
```

## 7.2 Update an entry — VERIFIED

```http
PUT /v1/user/{userId}/registry/{registryId}/registry-entry/{entryId}
```

Use the full transaction object rather than assuming PATCH semantics.

Example:

```json
{
  "description": "Updated dinner",
  "amount": {
    "value": "-1400",
    "currency": "JPY"
  },
  "membership_uuid_owner": "<payer-member-uuid>",
  "allocations": [
    {
      "membership_uuid": "<member-1-uuid>",
      "amount": {
        "value": "-700",
        "currency": "JPY"
      },
      "type": "AMOUNT"
    },
    {
      "membership_uuid": "<member-2-uuid>",
      "amount": {
        "value": "-700",
        "currency": "JPY"
      },
      "type": "AMOUNT"
    }
  ],
  "type_transaction": "NORMAL",
  "status": "ACTIVE",
  "date": "2026-09-23 20:30:00.000000",
  "category": "FOOD_AND_DRINK"
}
```

## 7.3 Delete an entry — VERIFIED

```http
DELETE /v1/user/{userId}/registry/{registryId}/registry-entry/{entryId}
```

No request body.

## 7.4 List entries directly — APK-OBSERVED

The APK contains `RegistryEntryListReadRequest` and the path:

```text
/user/{userId}/registry/{registryId}/registry-entry
```

However, a direct-list contract is not included as a VERIFIED endpoint here because the registry response already contains `all_registry_entry`, and current reverse-engineered references primarily read entries from the Registry object.

---

# 8. Attachments

## 8.1 Upload receipt/transaction attachment — VERIFIED

```http
POST /v1/user/{userId}/registry/{registryId}/attachment
```

Headers:

```http
Content-Type: image/jpeg
X-Bunq-Attachment-Description: ""
```

Body: raw binary image data.

Response:

```json
{
  "Response": [
    {
      "Id": {
        "id": 12345
      }
    }
  ]
}
```

Reference this attachment in an entry:

```json
{
  "attachment": [
    {
      "id": 12345
    }
  ]
}
```

## 8.2 Attachment read/delete paths — APK-OBSERVED

```text
/user/{userId}/registry/{registryId}/attachment
/user/{userId}/registry/{registryId}/attachment/{id}
```

The Android package contains request classes for registry attachment create/list/read, but exact current server behavior for each operation should be tested before depending on it.

---

# 9. Gallery attachments

## 9.1 List gallery attachments — VERIFIED

```http
GET /v1/user/{userId}/registry/{registryId}/gallery-attachment
```

Representative response:

```json
{
  "Response": [
    {
      "RegistryGalleryAttachment": {
        "attachment": {
          "id": 12345,
          "uuid": "abc123-...",
          "content_type": "image/jpeg",
          "urls": [
            {
              "type": "ORIGINAL",
              "url": "https://..."
            }
          ]
        },
        "membership_uuid": "<uploader-member-uuid>"
      }
    }
  ]
}
```

## 9.2 Upload gallery image — VERIFIED

```http
POST /v1/user/{userId}/registry/{registryId}/gallery-attachment/{uuid}
```

Headers:

```http
Content-Type: image/jpeg
X-Bunq-Attachment-Description: ""
```

Body: raw binary image.

## 9.3 Delete gallery image — VERIFIED

```http
DELETE /v1/user/{userId}/registry/{registryId}/gallery-attachment/{uuid}
```

---

# 10. Exchange rates

## 10.1 Get exchange rates — VERIFIED

```http
GET /v1/user/{userId}/exchange-rate?currency=USD
```

Representative response:

```json
{
  "Response": [
    {
      "ExchangeRate": {
        "currency_source": "USD",
        "currency_target": "JPY",
        "rate": "150.25",
        "description": "Japanese Yen",
        "number_of_decimal": 0,
        "symbol": "¥"
      }
    }
  ]
}
```

Interpretation:

```text
1 source_currency = rate * target_currency
```

---

# 11. User profile

## 11.1 Current API user — VERIFIED

```http
GET /v1/user/{userId}
```

Representative response:

```json
{
  "Response": [
    {
      "UserPerson": {
        "id": 12345678,
        "display_name": "tricount participant",
        "public_uuid": "...",
        "status": "SIGNUP",
        "sub_status": "NONE",
        "language": "en_US"
      }
    }
  ]
}
```

---

# 12. Settlement endpoint warning

The APK contains:

```text
/user/{userId}/registry/{registryId}/registry-settlement
```

and a `RegistrySettlementCreateRequest` class.

However, a current independent live probe dated 2026-09-12 reported:

```text
POST /registry/{id}/registry-settlement -> 404 Route not found
```

Therefore this route should be considered:

```text
BROKEN/CURRENTLY ABSENT
```

If a project needs balances or settlement suggestions, compute them locally from the transaction/allocation list instead of depending on this endpoint.

---

# 13. Other paths found in Tricount 14.0.3

These paths are useful for further reverse engineering, but are not part of the stable importable contract in the accompanying OpenAPI file:

```text
/user/{userId}/alias-registry
/user/{userId}/registry-public
/user/{userId}/registry-import-splitwise-csv
/user/{userId}/registry-membership-setting-card
/user/{userId}/slice-registry-delete-request
/user/{userId}/device/{deviceId}/registry-offline-analytics
/user/{userId}/monetary-account/{mId}/registry-request
/user/{userId}/monetary-account/{mId}/registry-request/{registryRequestId}
/user/{userId}/monetary-account/{monetaryAccountId}/registry-request
```

Do not depend on these without capturing real app traffic or performing targeted live tests.

---

# 14. Core data models

## 14.1 Amount

```json
{
  "value": "-1200",
  "currency": "JPY"
}
```

Rules:

- preserve `value` as a decimal string;
- do not convert through binary floating point when accuracy matters.

## 14.2 Registry

Important fields:

| Field | Type |
|---|---|
| `id` | integer |
| `uuid` | string |
| `title` | string |
| `description` | string/null |
| `currency` | string |
| `emoji` | string/null |
| `category` | string |
| `status` | `READ_WRITE` / `READ_ONLY` |
| `created` | datetime string |
| `public_identifier_token` | string |
| `memberships` | array |
| `all_registry_entry` | array |
| `all_registry_gallery_attachment` | array |

## 14.3 Registry entry

Important fields:

| Field | Type |
|---|---|
| `id` | integer |
| `uuid` | string |
| `date` | datetime string |
| `description` | string |
| `type` | usually `MANUAL` in responses |
| `type_transaction` | `NORMAL` / `INCOME` / `BALANCE` |
| `status` | string |
| `amount` | Amount |
| `amount_local` | Amount/null |
| `exchange_rate` | string/null |
| `membership_owned` | membership object |
| `allocations` | array |
| `category` | string/null |
| `category_custom` | string/null |
| `attachment` | array |

## 14.4 Allocation

Request form:

```json
{
  "membership_uuid": "<uuid>",
  "amount": {
    "value": "-600",
    "currency": "JPY"
  },
  "type": "AMOUNT",
  "share_ratio": null
}
```

---

# 15. Recommended client flow

```text
1. Load/create persistent app UUID + RSA key pair
2. POST /v1/session-registry-installation
3. Cache token + userId in memory
4. POST /v1/user/{userId}/registry-synchronization with sharing token
5. Read Registry.memberships and Registry.all_registry_entry
6. Perform writes only when explicitly needed
7. On 401: re-register session once, then retry once
```

For a personal homepage/dashboard, prefer read-only application logic even though the underlying API exposes mutation endpoints.

---

# 16. Minimal curl examples

Environment:

```bash
export TRICOUNT_BASE_URL='https://api.tricount.bunq.com'
export TRICOUNT_APP_ID='<uuid>'
export TRICOUNT_TOKEN='<session-token>'
export TRICOUNT_USER_ID='<user-id>'
export TRICOUNT_SHARE_TOKEN='tABC123xyz'
```

List/sync a tricount:

```bash
curl -sS "$TRICOUNT_BASE_URL/v1/user/$TRICOUNT_USER_ID/registry-synchronization" \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'User-Agent: com.bunq.tricount.android:RELEASE:7.0.7:3174:ANDROID:13:C' \
  -H "app-id: $TRICOUNT_APP_ID" \
  -H 'X-Bunq-Client-Request-Id: 049bfcdf-6ae4-4cee-af7b-45da31ea85d0' \
  -H "X-Bunq-Client-Authentication: $TRICOUNT_TOKEN" \
  --data "{\"all_registry_active\":[{\"public_identifier_token\":\"$TRICOUNT_SHARE_TOKEN\"}],\"all_registry_archived\":[],\"all_registry_deleted\":[]}"
```

Fetch registry list:

```bash
curl -sS "$TRICOUNT_BASE_URL/v1/user/$TRICOUNT_USER_ID/registry" \
  -H 'User-Agent: com.bunq.tricount.android:RELEASE:7.0.7:3174:ANDROID:13:C' \
  -H "app-id: $TRICOUNT_APP_ID" \
  -H 'X-Bunq-Client-Request-Id: 049bfcdf-6ae4-4cee-af7b-45da31ea85d0' \
  -H "X-Bunq-Client-Authentication: $TRICOUNT_TOKEN"
```

---

# 17. Production integration notes

- Keep `app_id`, RSA private key, session token, and sharing token on the backend.
- Treat sharing tokens as credentials.
- Use short HTTP timeouts and a bounded retry policy.
- Retry once on `401` only after re-registering a session.
- Cache read responses for dashboards instead of polling aggressively.
- Preserve money values as decimal strings / decimal types.
- Expect undocumented response fields to appear/disappear.
- Do not use the OpenAPI schema as proof of official support; it is an integration aid for a private API.

---

# 18. Evidence used for this reference

Local APK 14.0.3 inspection found:

```text
api.tricount.bunq.com
/v1/session-registry-installation
/v1/session-registry-refresh
/v1/session-registry-request
/v1/session-registry-social
/user/{userId}/registry
/user/{userId}/registry-public
/user/{userId}/registry/{registryId}
/user/{userId}/registry/{registryId}/registry-entry
/user/{userId}/registry/{registryId}/registry-entry/{registryEntryId}
/user/{userId}/registry/{registryId}/registry-membership
/user/{userId}/registry/{registryId}/registry-membership/{id}
/user/{userId}/registry/{registryId}/attachment
/user/{userId}/registry/{registryId}/attachment/{id}
/user/{userId}/registry/{registryId}/gallery-attachment
/user/{userId}/registry/{registryId}/gallery-attachment/{uuid}
/user/{userId}/registry/{registryId}/registry-settlement
```

Relevant APK request/model classes include:

```text
RegistryCreateRequest
RegistryReadRequest
RegistryListRequest
RegistryEntryCreateRequest
RegistryEntryListReadRequest
RegistryMembershipListReadRequest
RegistryMembershipUpdateRequest
TricountRegistryUpdateRequest
RegistrySettlementCreateRequest
AttachmentRegistryCreateRequest
AttachmentRegistryReadRequest
AttachmentRegistryListReadRequest
```

Cross-checks were made against current public reverse-engineered Tricount clients/documentation. These are not official Tricount/bunq API guarantees.
