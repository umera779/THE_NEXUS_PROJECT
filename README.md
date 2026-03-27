# Legacy Portal

A digital will and inheritance platform for Nigerian investment apps built with FastAPI. This platform allows users to manage investment portfolios, trade stocks, and secure their assets with automatic disbursement to beneficiaries upon proof-of-life failure.

Link to project: https://legacyportal.onrender.com

## Features

- **Authentication**: Signup with email verification (5-digit OTP), login with JWT cookie, password reset, role-based access.
- **PIN System**: 6-digit transaction PIN with OTP email confirmation on first setup.
- **Backup Email**: Verified backup email address that becomes active for password reset if proof-of-life fails.
- **Investment Dashboard**: Connect investment accounts, view portfolio, and track holdings (Simulated or Real-time via ISW/Itick).
- **Trading**: Buy and sell Nigerian stocks (NSE) with real-time market data.
- **Wallet & Payments**: Fund wallet via **Interswitch** payment gateway; transaction history and balance tracking.
- **Beneficiaries**: Add up to 100% of portfolio across multiple beneficiaries; bank accounts verified via **Interswitch** before saving; PIN required.
- **Proof-of-Life Check-In**: Configurable check-in intervals; reminders sent at 30, 14, 7, 3, 1 days before due; grace period after deadline.
- **Automatic Disbursement**: Funds automatically disbursed to verified beneficiaries using **Interswitch Transfer API** when proof-of-life fails.
- **Admin Panel**: Separate role-based admin login; user management; stock price editing; platform stats.

## Project Structure

```text
├── alembic
│   ├── env.py
│   └── __pycache__
├── app
│   ├── api
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   └── routes
│   │       ├── admin.py
│   │       ├── auth.py
│   │       ├── dashboard.py
│   │       ├── __init__.py
│   │       ├── market.py
│   │       ├── payment.py
│   │       ├── __pycache__
│   │       └── trading.py
│   ├── core
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── dependencies.py
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   └── security.py
│   ├── __init__.py
│   ├── models
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── __pycache__
│   │   └── schemas.py
│   ├── __pycache__
│   ├── services
│   │   ├── checkin_service.py
│   │   ├── disbursement_service.py
│   │   ├── email_service.py
│   │   ├── __init__.py
│   │   ├── isw_service.py
│   │   ├── itick_service.py
│   │   ├── market_service.py
│   │   ├── __pycache__
│   │   └── stock_service.py
│   └── templates
│       ├── admin
│       │   ├── dashboard.html
│       │   └── login.html
│       ├── auth
│       │   ├── forgot_password.html
│       │   ├── login.html
│       │   ├── reset_password.html
│       │   ├── signup.html
│       │   └── verify_email.html
│       ├── base.html
│       ├── dashboard
│       │   └── index.html
│       ├── fund.html
│       └── trading.html
├── create_admin.py
├── main.py
├── README.md
├── requirements.txt
├── scripts
│   ├── create_admin.py
│   └── __init__.py
└── TODO
```

## Setup

### 1. Prerequisites
- Python 3.11+
- PostgreSQL database
- **Interswitch** account (test keys for development)
- Resend account for emails
- Investment Data API credentials (ISW/Itick)

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
**Development (auto-creates tables on startup):**
```bash
# Tables are auto-created when APP_ENV=development
uvicorn main:app --reload
```

**Production (use Alembic migrations):**
```bash
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

### 5. Create first admin
**Option A — Interactive CLI (recommended for initial setup):**
```bash
python scripts/create_admin.py
```



### 6. Run the app
**Development**
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Production**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## API Reference

### Auth
| Method | Path | Description |
| :--- | :--- | :--- |
| GET | `/signup` | Signup Page |
| POST | `/signup` | Register new user |
| GET | `/verify-email` | Verify Email Page |
| POST | `/verify-email` | Verify email with 5-digit code |
| GET | `/login` | Login Page |
| POST | `/login` | Login, returns JWT cookie |
| POST | `/logout` | Clear JWT cookie |
| GET | `/forgot-password` | Forgot Password Page |
| POST | `/forgot-password` | Request password reset code |
| GET | `/reset-password` | Reset Password Page |
| POST | `/reset-password` | Confirm reset with code |

### Dashboard
| Method | Path | Description |
| :--- | :--- | :--- |
| GET | `/dashboard` | Dashboard Home |
| GET | `/dashboard/portfolio` | Get Investment Portfolio |
| GET | `/dashboard/wallet` | Get Wallet Balance |
| GET | `/dashboard/balance` | Get Balance |
| GET | `/dashboard/profile` | Get User Profile |
| POST | `/dashboard/request-pin-otp` | Request PIN setup OTP |
| POST | `/dashboard/setup-pin` | Set 6-digit PIN |
| POST | `/dashboard/backup-email` | Set backup email |
| POST | `/dashboard/backup-email/verify` | Verify backup email OTP |
| GET | `/dashboard/beneficiaries` | List beneficiaries |
| POST | `/dashboard/beneficiaries` | Add beneficiary (PIN required) |
| POST | `/dashboard/beneficiaries/resolve` | Resolve Beneficiary Account |
| DELETE | `/dashboard/beneficiaries/{id}` | Remove beneficiary |
| GET | `/dashboard/checkin` | Get Check-in Status |
| POST | `/dashboard/checkin` | Record proof-of-life |
| PUT | `/dashboard/checkin/config` | Update check-in interval/grace period |
| GET | `/dashboard/fund` | Fund Wallet Page |

### Market
| Method | Path | Description |
| :--- | :--- | :--- |
| GET | `/market/stream` | Price Stream |
| GET | `/market/prices` | Get Current Prices |
| POST | `/market/refresh` | Manual Refresh |

### Payment
| Method | Path | Description |
| :--- | :--- | :--- |
| GET | `/fund` | Fund Page |
| POST | `/fund/initiate` | Initiate Funding (Interswitch) |
| GET | `/payment/callback` | Payment Callback |
| POST | `/payment/webhook` | Payment Webhook |

### Trading
| Method | Path | Description |
| :--- | :--- | :--- |
| GET | `/trading/market` | Get Market |
| GET | `/trading/holdings` | Get Holdings |
| POST | `/trading/buy` | Buy Stock |
| POST | `/trading/sell` | Sell Stock |
| GET | `/trading/history` | Trade History |



## Key Flows

1.  **User Registration**: 
    - `POST /signup` → creates **Interswitch** customer (fails if **Interswitch** fails) → sends 5-digit email OTP.
    - `POST /verify-email` → activates account.
    - `POST /login` → sets HttpOnly JWT cookie.
2.  **First Login — PIN Setup**: 
    - `GET /dashboard` → frontend detects `is_first_login=true`.
    - `POST /dashboard/request-pin-otp` → sends 6-digit OTP to email.
    - `POST /dashboard/setup-pin` → saves bcrypt-hashed PIN.
3.  **Adding Beneficiary**: 
    - `POST /dashboard/beneficiaries` with `pin` field.
    - Backend: verifies PIN → resolves bank code → verifies account via **Interswitch** → creates recipient → saves beneficiary.
4.  **Payment Funding**: 
    - `POST /fund/initiate` → creates transaction reference → redirects to **Interswitch** payment page.
    - `GET /payment/callback` → handles user return from payment gateway.
    - `POST /payment/webhook` → verifies signature → credits user wallet upon success.
5.  **Proof-of-Life Check-In**: 
    - Daily job runs at 08:00 UTC.
    - Reminder emails sent at 30, 14, 7, 3, 1 days before due date.
    - On missed check-in: status → `OVERDUE`.
    - After grace period: disbursement triggered via **Interswitch Transfer API**; backup email notified.
6.  **Automatic Disbursement**: 
    - Reads all verified beneficiaries.
    - Splits wallet balance by percentage.
    - Calls **Interswitch** `POST /transfer` for each beneficiary.
    - Creates transaction records for audit trail.

## Security Notes

- Passwords and PINs are bcrypt-hashed.
- JWT tokens stored in HttpOnly, SameSite=Lax cookies.
- `secure=True` on cookies in production.
- **Interswitch** webhook signature verified via HMAC.
- Email enumeration prevented on password reset endpoint.
- Admin creation requires `ADMIN_SECRET_KEY`.
- Environment-based configuration via `.env`.

## Team Members and Contributors

| Name | Role |
| :--- | :--- |
| Adenike | Team Leader |
| Kanu Onette | Backend Developer |
| [Name 2] | [Role, e.g., Frontend Developer] |
| [Name 3] | [Role, e.g., DevOps/Security] |

---
*For more details, refer to the `.env.example` file or contact the development team.*