# The Nexus

A digital will and inheritance platform for Nigerian investment apps built with FastAPI.

## Features

- **Authentication**: Signup with email verification (5-digit OTP), login with JWT cookie, password reset, role-based access
- **PIN System**: 6-digit transaction PIN with OTP email confirmation on first setup
- **Backup Email**: Verified backup email address that becomes active for password reset if proof-of-life fails
- **Simulated Portfolio**: Dummy Nigerian stock portfolios (NSE stocks) with admin-editable prices
- **Beneficiaries**: Add up to 100% of portfolio across multiple beneficiaries; bank accounts verified via Paystack before saving; PIN required
- **Proof-of-Life Check-In**: Configurable check-in intervals; reminders sent at 30/14/7/3/1 days before due; grace period after deadline
- **Automatic Disbursement**: Paystack Transfer API used to disburse funds to verified beneficiaries when proof-of-life fails
- **Admin Panel**: Separate role-based admin login; user management; stock price editing; platform stats

---

## Project Structure

```
legacy_portal/
├── main.py                      # FastAPI app entry point
├── requirements.txt
├── .env.example                 # Copy to .env and fill in
├── alembic.ini
├── alembic/env.py               # Async Alembic migrations
├── scripts/
│   └── create_admin.py          # Interactive CLI to create admin users
└── app/
    ├── core/
    │   ├── config.py            # Settings (pydantic-settings)
    │   ├── database.py          # Async SQLAlchemy engine
    │   ├── security.py          # Password/PIN hashing, JWT, OTP generation
    │   └── dependencies.py      # FastAPI dependency injection
    ├── models/
    │   ├── models.py            # All SQLAlchemy models
    │   └── schemas.py           # Pydantic request/response schemas
    ├── services/
    │   ├── email_service.py     # Resend API email functions
    │   ├── paystack_service.py  # Paystack REST client
    │   ├── disbursement_service.py  # Automatic inheritance disbursement
    │   ├── checkin_service.py   # APScheduler daily check-in job
    │   └── stock_service.py     # Nigerian stock simulation + portfolio
    ├── api/routes/
    │   ├── auth.py              # /signup /login /verify-email /reset-password
    │   ├── dashboard.py         # /dashboard/* user endpoints
    │   └── admin.py             # /admin/* admin endpoints
    └── templates/
        ├── base.html
        ├── auth/                # signup, login, verify, reset
        ├── dashboard/           # main dashboard
        └── admin/               # admin login + dashboard
```

---

## Setup

### 1. Prerequisites

- Python 3.11+
- PostgreSQL database
- Paystack account (test keys for development)
- Resend account for emails

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 4. Database

**Development** (auto-creates tables on startup):
```bash
# Tables are auto-created when APP_ENV=development
uvicorn main:app --reload
```

**Production** (use Alembic migrations):
```bash
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

### 5. Create first admin

**Option A** — Interactive CLI (recommended for initial setup):
```bash
python scripts/create_admin.py
```

**Option B** — Via API (requires `ADMIN_SECRET_KEY` from `.env`):
```bash
curl -X POST http://localhost:8000/admin/create-admin \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "Admin",
    "last_name": "User",
    "email": "admin@example.com",
    "phone_number": "+2348000000000",
    "password": "SecurePass123",
    "role": "super_admin",
    "admin_secret_key": "your-admin-secret-key"
  }'
```

### 6. Run the app

```bash
# Development
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## Key Flows

### User Registration
1. POST `/signup` → creates Paystack customer (fails if Paystack fails) → sends 5-digit email OTP
2. POST `/verify-email` → activates account
3. POST `/login` → sets HttpOnly JWT cookie

### First Login — PIN Setup
1. GET `/dashboard` → frontend detects `is_first_login=true`
2. POST `/dashboard/request-pin-otp` → sends 6-digit OTP to email
3. POST `/dashboard/setup-pin` → saves bcrypt-hashed PIN

### Adding Beneficiary
1. POST `/dashboard/beneficiaries` with `pin` field
2. Backend: verifies PIN → resolves bank code → verifies account via Paystack → creates Paystack recipient → saves beneficiary

### Proof-of-Life Check-In
- Daily job runs at 08:00 UTC
- Reminder emails sent at 30, 14, 7, 3, 1 days before due date
- On missed check-in: status → OVERDUE
- After grace period: disbursement triggered via Paystack Transfer API; backup email notified

### Automatic Disbursement
- Reads all verified beneficiaries
- Splits wallet balance by percentage
- Calls Paystack `POST /transfer` for each beneficiary
- Creates transaction records for audit trail

---

## API Reference

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | `/signup` | Register new user |
| POST | `/verify-email` | Verify email with 5-digit code |
| POST | `/login` | Login, returns JWT cookie |
| POST | `/logout` | Clear JWT cookie |
| POST | `/forgot-password` | Request password reset code |
| POST | `/reset-password` | Confirm reset with code |

### Dashboard (authenticated)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/dashboard` | Dashboard HTML |
| GET | `/dashboard/profile` | User profile |
| GET | `/dashboard/portfolio` | Investment portfolio with current values |
| GET | `/dashboard/wallet` | Wallet balance + transactions |
| POST | `/dashboard/request-pin-otp` | Request PIN setup OTP |
| POST | `/dashboard/setup-pin` | Set 6-digit PIN |
| POST | `/dashboard/backup-email` | Set backup email |
| POST | `/dashboard/backup-email/verify` | Verify backup email OTP |
| GET | `/dashboard/beneficiaries` | List beneficiaries |
| POST | `/dashboard/beneficiaries` | Add beneficiary (PIN required) |
| DELETE | `/dashboard/beneficiaries/{id}` | Remove beneficiary |
| GET | `/dashboard/checkin` | Check-in status |
| POST | `/dashboard/checkin` | Record proof-of-life |
| PUT | `/dashboard/checkin/config` | Update check-in interval/grace period |

### Admin (admin/super_admin role)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/admin/login` | Admin login |
| GET | `/admin` | Admin dashboard HTML |
| POST | `/admin/create-admin` | Create admin user |
| GET | `/admin/users` | List all users |
| GET | `/admin/users/{id}` | User detail |
| POST | `/admin/users/{id}/suspend` | Suspend user |
| POST | `/admin/users/{id}/unsuspend` | Unsuspend user |
| GET | `/admin/stocks` | List stock prices |
| PUT | `/admin/stocks/{symbol}` | Update stock price |
| GET | `/admin/stats` | Platform stats |

---

## Security Notes

- Passwords and PINs are bcrypt-hashed
- JWT tokens stored in HttpOnly, SameSite=Lax cookies
- `secure=True` on cookies in production
- Paystack webhook signature verified via HMAC-SHA512
- Email enumeration prevented on password reset endpoint
- Admin creation requires `ADMIN_SECRET_KEY`
- Environment-based configuration via `.env`
