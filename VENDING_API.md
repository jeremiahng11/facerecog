# Vending Machine API Documentation

**Base URL:** `https://<your-domain>`
**Version:** 1.0
**Last Updated:** April 2026

---

## Overview

This API allows cafeteria vending machines to deduct credit from staff accounts.
Each staff member has a unique QR code displayed on their phone (PWA Home screen).
The vending machine scans the QR, then calls this API to deduct the purchase amount.

---

## Authentication

All requests must include a **Bearer token** in the `Authorization` header.

```
Authorization: Bearer <VENDING_API_KEY>
```

The API key is configured on the server via the `VENDING_API_KEY` environment variable.
Contact the system administrator to obtain your API key.

**Generate a key:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Endpoints

### Deduct Credit

Deduct credit from a staff member's cafeteria balance.

```
POST /cafeteria/api/vending/deduct/
```

#### Request Headers

| Header          | Value                            |
|-----------------|----------------------------------|
| `Content-Type`  | `application/json`               |
| `Authorization` | `Bearer <VENDING_API_KEY>`       |

#### Request Body (JSON)

| Field         | Type   | Required | Description                                                |
|---------------|--------|----------|------------------------------------------------------------|
| `qr_token`    | string | Yes      | Full QR code string scanned from the staff member's phone  |
| `amount`      | number | Yes      | Positive amount to deduct in SGD (e.g. `2.50`)             |
| `machine_id`  | string | No       | Identifier for the vending machine (e.g. `"VM-01"`). Max 50 chars. |
| `description` | string | No       | Item description (e.g. `"Canned Coffee"`). Max 120 chars. Shown in user's transaction history. |

#### Example Request

```bash
curl -X POST https://your-domain.com/cafeteria/api/vending/deduct/ \
  -H "Authorization: Bearer your-secret-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "qr_token": "VEND:EMP-001.a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
    "amount": 2.50,
    "machine_id": "VM-LOBBY-01",
    "description": "Canned Coffee"
  }'
```

---

## Responses

All responses are JSON with a `success` boolean field.

### Success (HTTP 200)

Credit was deducted successfully.

```json
{
  "success": true,
  "balance": 47.50,
  "staff_id": "EMP-001",
  "transaction_id": 42
}
```

| Field            | Type   | Description                                    |
|------------------|--------|------------------------------------------------|
| `success`        | bool   | `true`                                         |
| `balance`        | number | User's remaining credit balance after deduction |
| `staff_id`       | string | Staff member's ID                               |
| `transaction_id` | number | Unique transaction ID for this purchase          |

### Insufficient Funds (HTTP 200)

User does not have enough credit for the requested amount.

```json
{
  "success": false,
  "error": "insufficient_funds",
  "message": "Insufficient credit. Balance: S$1.20, required: S$2.50",
  "balance": 1.20
}
```

| Field     | Type   | Description                         |
|-----------|--------|-------------------------------------|
| `success` | bool   | `false`                             |
| `error`   | string | `"insufficient_funds"`              |
| `message` | string | Human-readable explanation           |
| `balance` | number | User's current credit balance        |

### Invalid QR Code (HTTP 200)

The QR code is not recognised — tampered, wrong format, or user is inactive.

```json
{
  "success": false,
  "error": "invalid_qr",
  "message": "Invalid or unrecognised QR code"
}
```

### Unauthorized (HTTP 401)

Missing or invalid API key.

```json
{
  "success": false,
  "error": "unauthorized",
  "message": "Invalid API key"
}
```

### Bad Request (HTTP 400)

Missing required fields or invalid JSON.

```json
{
  "success": false,
  "error": "bad_request",
  "message": "qr_token is required"
}
```

Possible messages:
- `"Invalid JSON body"`
- `"qr_token is required"`
- `"amount is required"`
- `"amount must be a positive number"`
- `"amount must be greater than 0"`

### Server Error (HTTP 500)

The `VENDING_API_KEY` is not configured on the server.

```json
{
  "success": false,
  "error": "server_error",
  "message": "Vending API not configured"
}
```

---

## Error Codes Summary

| Error Code            | HTTP Status | Description                                              |
|-----------------------|-------------|----------------------------------------------------------|
| `unauthorized`        | 401         | Missing or invalid API key                               |
| `bad_request`         | 400         | Missing required fields or invalid JSON                  |
| `invalid_qr`         | 200         | QR code not recognised (tampered, wrong format, inactive user) |
| `insufficient_funds`  | 200         | User's credit balance is less than the requested amount  |
| `server_error`        | 500         | `VENDING_API_KEY` not configured on the server           |

> **Note:** `invalid_qr` and `insufficient_funds` return HTTP 200 (not 4xx) because the
> request itself was valid — the business logic rejected it. This makes it easier for
> vending machines to distinguish network/auth errors (4xx/5xx) from business outcomes (200).

---

## Integration Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Staff Phone   │     │ Vending Machine  │     │   Our Server    │
│   (PWA App)     │     │                  │     │                 │
└────────┬────────┘     └────────┬─────────┘     └────────┬────────┘
         │                       │                         │
         │  1. Staff opens PWA   │                         │
         │     Home page — QR    │                         │
         │     code is displayed │                         │
         │                       │                         │
         │  2. Staff holds phone │                         │
         │     to QR scanner     │                         │
         │ ─────────────────────>│                         │
         │                       │                         │
         │                       │  3. POST /cafeteria/    │
         │                       │     api/vending/deduct/ │
         │                       │ ───────────────────────>│
         │                       │                         │
         │                       │                         │ 4. Verify QR
         │                       │                         │    signature
         │                       │                         │
         │                       │                         │ 5. Check balance
         │                       │                         │
         │                       │                         │ 6. Deduct credit
         │                       │                         │    (atomic)
         │                       │                         │
         │                       │  7. Response:           │
         │                       │     success + balance   │
         │                       │ <───────────────────────│
         │                       │                         │
         │                       │  8. Dispense item       │
         │                       │     (or show error)     │
         │                       │                         │
         │  9. Transaction shows │                         │
         │     in History tab    │                         │
         │                       │                         │
```

1. Staff opens their **PWA Home** page — their unique QR code is displayed beside the credit balance
2. Staff holds their phone up to the vending machine's QR scanner
3. Vending machine reads the QR string (format: `VEND:<staff_id>.<hmac>`)
4. Vending machine calls `POST /cafeteria/api/vending/deduct/` with the QR token and item price
5. Server verifies the HMAC signature on the QR token
6. Server checks the user's credit balance
7. Server deducts credit atomically (row-level locking prevents race conditions)
8. Machine receives the response — dispenses the item on success, shows error on failure
9. Transaction appears in the staff member's **History → Vending** tab (success or failed with reason)

---

## QR Code Format

Staff QR codes follow this format:

```
VEND:<staff_id>.<hmac_signature>
```

**Example:**
```
VEND:EMP-001.a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
```

- `VEND:` — fixed prefix identifying this as a vending QR
- `<staff_id>` — the staff member's unique ID
- `.<hmac_signature>` — 32-character HMAC-SHA256 signature

The QR code is:
- **Permanent** — does not expire or change (unless the server's signing key changes)
- **Reusable** — can be scanned multiple times (unlike order collection QR codes)
- **Tamper-proof** — HMAC signature prevents forgery
- **User-bound** — each staff member has a unique QR; inactive users are automatically rejected

> **Important:** The vending machine should treat the QR token as an opaque string. Do not
> parse or validate the format client-side. Always send the full string to the API for
> server-side verification.

---

## Recommended Machine-Side Logic

```python
import requests

API_URL = "https://your-domain.com/cafeteria/api/vending/deduct/"
API_KEY = "your-secret-api-key"
MACHINE_ID = "VM-LOBBY-01"

def process_purchase(qr_code: str, item_price: float, item_name: str) -> bool:
    """
    Call after the user scans their QR and selects an item.
    Returns True if credit was deducted, False otherwise.
    """
    response = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "qr_token": qr_code,
            "amount": item_price,
            "machine_id": MACHINE_ID,
            "description": item_name,
        },
        timeout=10,
    )

    if response.status_code == 401:
        # API key is wrong — alert maintenance
        log_error("Invalid API key")
        display_message("System error. Please contact support.")
        return False

    if response.status_code != 200:
        display_message("Connection error. Please try again.")
        return False

    data = response.json()

    if data["success"]:
        display_message(f"Success! Remaining balance: S${data['balance']:.2f}")
        dispense_item()
        return True

    # Handle specific errors
    error = data.get("error", "")

    if error == "insufficient_funds":
        balance = data.get("balance", 0)
        display_message(f"Insufficient credit. Balance: S${balance:.2f}")
    elif error == "invalid_qr":
        display_message("QR code not recognised. Please try again.")
    else:
        display_message(data.get("message", "Error. Please try again."))

    return False
```

---

## Testing

### With cURL

```bash
# Successful deduction
curl -X POST https://your-domain.com/cafeteria/api/vending/deduct/ \
  -H "Authorization: Bearer your-secret-api-key" \
  -H "Content-Type: application/json" \
  -d '{"qr_token":"VEND:EMP-001.abc123...","amount":2.50,"machine_id":"VM-TEST","description":"Test Item"}'

# Test with wrong API key (should return 401)
curl -X POST https://your-domain.com/cafeteria/api/vending/deduct/ \
  -H "Authorization: Bearer wrong-key" \
  -H "Content-Type: application/json" \
  -d '{"qr_token":"VEND:EMP-001.abc123...","amount":2.50}'

# Test with invalid QR (should return invalid_qr)
curl -X POST https://your-domain.com/cafeteria/api/vending/deduct/ \
  -H "Authorization: Bearer your-secret-api-key" \
  -H "Content-Type: application/json" \
  -d '{"qr_token":"INVALID-TOKEN","amount":2.50}'

# Test with very large amount (should return insufficient_funds)
curl -X POST https://your-domain.com/cafeteria/api/vending/deduct/ \
  -H "Authorization: Bearer your-secret-api-key" \
  -H "Content-Type: application/json" \
  -d '{"qr_token":"VEND:EMP-001.abc123...","amount":99999}'
```

---

## Rate Limiting

There is currently no rate limit on this endpoint. If you need rate limiting, contact the
system administrator to configure it at the reverse proxy level.

---

## Support

For API key provisioning or technical issues, contact the system administrator.
The API documentation is also available in the admin dashboard at:
`/cafeteria/admin/vending-api/`
