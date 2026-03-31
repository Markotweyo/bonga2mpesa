# Bonga2MPESA — Backend

Production-grade FastAPI backend for converting Safaricom Bonga Points to M-PESA cash via Daraja APIs.

---

## How It Works

```
User dials *126*2*2*Paybill# on Safaricom USSD
  → enters phone + bonga points amount
  → Safaricom deducts bonga, sends KES to your shortcode (C2B)
  → Your backend receives C2B callback
  → Validates transaction, checks profitability
  → Enqueues background worker
  → Worker triggers B2C payout to user
  → B2C result callback confirms success
  → Ledger records credit (inflow) + debit (payout)
```

**Rate example:**
- User has 767 Bonga Points
- Safaricom sends you: `767 × 0.20 = 153.40 KES`
- You pay user:        `767 × 0.133 = 102.01 KES`
- Your profit:         `153.40 − 102.01 = 51.39 KES`

---

## Project Structure

```
bonga2mpesa/
├── app/
│   ├── main.py                    # FastAPI app + lifespan
│   ├── api/routes/
│   │   └── callbacks.py           # POST /callbacks/c2b, /b2c/result, /b2c/timeout
│   ├── core/
│   │   ├── config.py              # Pydantic settings from .env
│   │   ├── logging.py             # structlog setup + correlation ID
│   │   └── security.py            # IP whitelist, phone validation
│   ├── db/
│   │   ├── base.py                # SQLAlchemy declarative base
│   │   └── session.py             # Async session + get_db()
│   ├── models/
│   │   └── __init__.py            # User, Transaction, LedgerEntry, WebhookLog
│   ├── schemas/
│   │   └── __init__.py            # Pydantic request/response models
│   ├── services/
│   │   ├── transaction_service.py # Core orchestration logic
│   │   ├── valuation_service.py   # Rate computation + profitability
│   │   ├── ledger_service.py      # Double-entry ledger
│   │   └── daraja_client.py       # Daraja OAuth + B2C API
│   └── workers/
│       ├── celery_app.py          # Celery config
│       └── tasks.py               # process_transaction_task
├── migrations/
│   ├── env.py                     # Alembic async env
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial_schema.py
├── tests/
│   ├── conftest.py
│   ├── test_valuation.py
│   ├── test_security.py
│   ├── test_callbacks.py
│   └── test_transaction_service.py
├── .env.example
├── alembic.ini
├── requirements.txt
└── pytest.ini
```

---

## Local Setup

### 1. Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis 6+

### 2. Clone & Install

```bash
git clone <your-repo>
cd bonga2mpesa

python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your real Daraja credentials and DB/Redis URLs
```

Key variables to set:

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL async URL |
| `REDIS_URL` | Redis connection string |
| `DARAJA_CONSUMER_KEY` | From Daraja portal |
| `DARAJA_CONSUMER_SECRET` | From Daraja portal |
| `DARAJA_SHORTCODE` | Your B2C shortcode |
| `DARAJA_INITIATOR_NAME` | B2C initiator username |
| `DARAJA_SECURITY_CREDENTIAL` | Encrypted credential from Daraja |
| `CALLBACK_BASE_URL` | Your public HTTPS domain |
| `YOUR_RATE` | KES per bonga point paid to user (e.g. `0.133`) |
| `SAFARICOM_RATE` | KES per bonga point Safaricom sends you (e.g. `0.2`) |

### 4. Run Database Migrations

```bash
alembic upgrade head
```

### 5. Start the API

```bash
uvicorn app.main:app --reload --port 8000
```

### 6. Start the Celery Worker

In a separate terminal:

```bash
celery -A app.workers.celery_app.celery_app worker \
  --loglevel=info \
  --queues=payouts,default,maintenance
```

### 7. (Optional) Celery Beat for Periodic Tasks

```bash
celery -A app.workers.celery_app.celery_app beat --loglevel=info
```

---

## Running Tests

```bash
pytest -v
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/callbacks/c2b` | Safaricom C2B payment callback |
| `POST` | `/callbacks/b2c/result` | Daraja B2C result callback |
| `POST` | `/callbacks/b2c/timeout` | Daraja B2C timeout callback |
| `GET` | `/health` | Health check |

---

## Transaction Status Flow

```
PENDING → VALIDATED → PROCESSING → SUCCESS
                   ↘             ↘ FAILED
```

- **PENDING**: C2B received, not yet validated
- **VALIDATED**: Amount/phone validated, queued for payout
- **PROCESSING**: B2C request sent to Daraja
- **SUCCESS**: B2C confirmed, ledger updated
- **FAILED**: Profitability check failed, max retries exceeded, or B2C rejected

---

## Security

- Safaricom callback IPs are whitelisted in production (`APP_ENV=production`)
- All secrets in environment variables — never hardcoded
- Idempotency enforced via Redis + DB unique constraints on `correlation_id` and `mpesa_receipt`
- Strict Pydantic validation on all incoming payloads
- Phone numbers sanitized and validated on every request

---

## Daraja Sandbox vs Production

Change these in `.env`:

```
# Sandbox
DARAJA_B2C_URL=https://sandbox.safaricom.co.ke/mpesa/b2c/v3/paymentrequest
DARAJA_AUTH_URL=https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials

# Production
DARAJA_B2C_URL=https://api.safaricom.co.ke/mpesa/b2c/v3/paymentrequest
DARAJA_AUTH_URL=https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials
```

---

## Generating Daraja Security Credential

```python
import base64
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization
from cryptography.x509 import load_pem_x509_certificate

# Download cert from: https://developer.safaricom.co.ke/
with open("ProductionCertificate.cer", "rb") as f:
    cert = load_pem_x509_certificate(f.read())

public_key = cert.public_key()
encrypted = public_key.encrypt(b"YOUR_INITIATOR_PASSWORD", padding.PKCS1v15())
credential = base64.b64encode(encrypted).decode()
print(credential)  # paste this as DARAJA_SECURITY_CREDENTIAL
```

---

## Notes

- The USSD flow (`*126*2*2*Paybill#`) is fully handled by Safaricom — no USSD session logic needed in this backend
- `BillRefNumber` in C2B payload carries the user's phone number entered during USSD
- Bonga points are inferred from the received amount using `SAFARICOM_RATE`
- All monetary amounts stored as `Numeric(10,2)` for precision
