# Gym SaaS Platform

## User Guides

- [Nexus Platform Owner Guide](docs/super-admin-guide.md) - platform plans, gym onboarding, subscriptions, analytics, settings, and governance.
- [Gym Owner Guide](docs/gym-owner-guide.md) - daily gym operations, members, attendance, payments, AI Insights, staff, and reports.
- [Gym Owner Marketing Brochure](docs/gym-owner-marketing-brochure.pdf) - shareable client-demo PDF with product visuals and gym-owner value messaging.
- Editable source: [generate_gym_owner_marketing_pdf.py](scripts/generate_gym_owner_marketing_pdf.py)

A production-ready gym management SaaS built with FastAPI, SQLAlchemy, Jinja templates, and browser-based attendance scanning. The platform supports gym owners, staff, trainers, and a super-admin console for multi-gym operations.

## Overview

This project is designed as a single application deployment, not a split architecture. The main FastAPI app hosts both the management dashboard and the attendance workflows. This avoids Railway deployment issues caused by a separate kiosk process that depends on native face-recognition libraries.

The app includes:
- gym and plan management
- member management
- attendance tracking
- face-based check-in/check-out flow
- billing and subscription management
- churn and retention insights
- notifications and marketing nudges
- AI-style operational recommendations
- super-admin controls for all gyms

## Who is this for?

This platform is designed for:
- independent gym owners
- multi-branch gym groups
- fitness SaaS operators managing multiple gyms from one control panel
- staff and trainers who need daily attendance and membership workflows
- super-admin teams who manage pricing and gym onboarding centrally

## Architecture

The application follows a single-service deployment pattern:
- backend: FastAPI
- ORM: SQLAlchemy
- templates: Jinja2
- database: SQLAlchemy SQL backend by default, with staged MongoDB infrastructure
- authentication: JWT
- document / email: SMTP with Brevo
- attendance: same app handles browser camera workflows
- dependency management: one root requirements file only; no separate kiosk requirements file

### Dependency policy

Use the root dependency file for all installs:

```bash
pip install -r requirements.txt
```

There is no separate kiosk client dependency file in this project. Any kiosk or browser-attendance logic stays inside the main service architecture to avoid split installs and deployment drift.

### Important deployment note

The project intentionally avoids a second kiosk service in production. Face recognition is executed through the main FastAPI app, and the app gracefully falls back to manual attendance when the native recognition library is unavailable. This makes Railway deployments more stable and avoids silent runtime failures.

## Features

### Gym management
- create gyms from the super-admin console
- update gym details
- assign platform plan and subscription status
- change gym owner email/password
- delete gym and cascade cleanup of related records

### Super-admin console
The super-admin panel includes:
- platform overview statistics
- gym list with active/trial statuses
- platform plan management
- create, update, delete for plans
- create, update, delete for gyms
- MRR and member metrics
- owner account management for each gym

### Platform plans
- monthly, quarterly, yearly billing intervals
- optional member limits
- optional Razorpay plan mapping
- plan updates and deletion with safe cleanup of linked gyms

### Membership and attendance
- add members to a gym
- upload member photos for recognition
- face check-in and check-out by scanning a member face
- minimum checkout gap protection (15 minutes)
- stale open attendance auto-close logic
- manual attendance fallback when recognition is unavailable

### Dashboard analytics
- daily attendance stats
- active and expired member counts
- current in-gym count
- revenue summary
- peak hours chart
- AI-style churn risk and operational intelligence

### AI-powered insights
The project includes explainable AI-style insights such as:
- churn risk scoring
- attendance health status
- peak hour recommendations
- operational actions for staff coverage and retention

These are designed to be transparent, defensible, and easy to replace with a more advanced ML model later without restructuring the app.

## Super-admin Requirements

The platform supports a super-admin account with all platform-level controls. The app includes full CRUD operations for:
- gyms
- platform plans
- plan assignment
- gym subscriptions
- gym owner data

## 3-step deployment workflow

### Step 1: Install and configure the app
Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create environment variables in `.env`:

```env
DB_BACKEND=sql
DATABASE_URL=sqlite:///./gym_saas.db
MONGODB_URL=mongodb+srv://username:password@cluster.mongodb.net
MONGODB_DATABASE=gym_nexus
JWT_SECRET_KEY=replace_with_a_secure_secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USER=your_brevo_login
SMTP_PASSWORD=your_brevo_smtp_key
FROM_EMAIL=your_email
BREVO_API_KEY=your_brevo_v3_api_key
BREVO_SENDER_NAME=GYM-NEXUS
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=
```

### Database backend flag

`DB_BACKEND` accepts `sql` or `mongo` and defaults to `sql`. The SQL path remains
independent and is the authoritative application backend during this staged
migration. With `DB_BACKEND=mongo`, the app validates the MongoDB connection,
creates the MongoDB indexes, reports MongoDB status from `/health`, and keeps the
SQL backend available for the existing routes while Mongo repositories are being
migrated feature by feature. It does not silently fall back to SQL if MongoDB is
selected or misconfigured.

MongoDB transactions require MongoDB Atlas or a replica-set deployment. A
standalone MongoDB server is suitable for connectivity and index checks, but not
for the multi-document transaction behavior used by the application.

For Railway deployments, configure `BREVO_API_KEY` and `FROM_EMAIL` as service variables. When `BREVO_API_KEY` is present, the app uses Brevo's HTTPS API instead of SMTP, avoiding Railway SMTP port restrictions.

For production, swap SQLite for PostgreSQL:

```env
DATABASE_URL=postgresql://user:password@host:5432/gymdb
```

### Step 2: Run the app as a single service
Use one Railway service only.

This repository is configured for direct Railway deployment with a single app service and a `uvicorn` start command.

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Railway direct deploy files included in the repo:
- `railway.json`
- `runtime.txt`
- `Procfile`

Recommended Railway setup:
- add app repo
- add PostgreSQL database service
- add environment variables in Railway Variables
- deploy the app as one service only
- use the generated HTTPS URL for browser camera access

### Step 3: Verify the live platform
After deployment:
1. open the app URL
2. log in as the super-admin
3. create a platform plan
4. create a gym and assign the plan
5. test edit/update actions
6. test delete actions and confirm cleanup works
7. open the dashboard and check AI-style insights
8. open attendance page and verify camera access works
9. confirm `/health` returns status OK
10. verify email sending works with the Brevo SMTP configuration

## Email configuration

The project uses SMTP for outbound emails.

Required environment variables:
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `FROM_EMAIL`

Example for Brevo:
- Host: `smtp-relay.brevo.com`
- Port: `587`
- Login: your Brevo SMTP login
- Password: your SMTP key

Never commit real credentials to the repository. Use environment variables or Railway secrets.

## Running the app

Important: ensure you start the server with the same Python interpreter that has the project dependencies installed (i.e., your virtualenv). If you installed packages into a virtualenv named `.venv` or `env`, starting `uvicorn` from a different Python will make optional packages (like APScheduler) unavailable to the worker process.

Recommended (guarantees the same interpreter):

```bash
# If your virtualenv is activated (recommended):
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Or explicitly use the venv python (if your venv folder is `env`):
./env/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Or use the provided helper script (expects a venv at ./env):
./run_dev.sh
```

If the scheduler fails to start with "No module named 'apscheduler'", it usually means the server process is using a different Python. Use the commands above to ensure the correct interpreter is used.

Previously the shorter `uvicorn app.main:app` form can resolve to a system-installed uvicorn binary that is not tied to your active venv; prefer `python -m uvicorn` to avoid that mismatch.

## Health check

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status": "ok"}
```

## Key app routes

- `/login` - login page
- `/app/dashboard` - gym dashboard
- `/app/attendance` - attendance log and face scanner
- `/app/members` - member management
- `/app/billing` - billing and subscription screen
- `/app/superadmin` - platform admin console
- `/logout` - sign out

## Face recognition behavior

The app supports live face attendance scanning from the browser. The recognition flow is safe for deployment:
- when the native recognition library loads, face scan works normally
- when it is unavailable, the app returns a clear fallback message instead of failing silently
- manual attendance entry remains available as a backup

Important: browser camera APIs require HTTPS. On Railway, use the live HTTPS domain generated by the platform.

## Quick-start usage guide

### Super-admin
1. Log in with the super-admin account.
2. Go to the platform overview page.
3. Create a platform plan.
4. Create a gym and assign a plan.
5. Update gym details or owner credentials when needed.
6. Delete gyms when necessary, ensuring related records are cleaned up.

### Gym owner
1. Log in with the gym owner account.
2. Manage members, plans, and staff.
3. Monitor attendance and dashboard analytics.
4. Use face scan for quick attendance.
5. Review AI insights for retention and churn.

### Staff / trainer
1. Use attendance page to check members in and out.
2. Add or manage classes as needed.
3. Monitor active attendance and gym usage.

## Testing

Run focused validation:

```bash
pytest tests/test_attendance.py tests/test_dashboard.py tests/test_superadmin.py -q
```

## Notes

- This project is a single-service deployment model for Railway stability.
- The app is designed to be extendable with advanced AI features later.
- The architecture supports future ML upgrades without changing the business-facing dashboard and domain logic.

## Future improvements

Possible future enhancements:
- ML-based churn prediction with historical data
- AI-generated member engagement campaigns
- attendance anomaly detection
- SMS + WhatsApp notifications
- Stripe or Razorpay webhook syncing
- reporting exports and dashboards
