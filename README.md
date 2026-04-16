# FaceID Portal — Cafeteria Management System

A comprehensive Django-based **cafeteria meal ordering system** with **Face Recognition login**, staff credits/wallet, vending machine integration, event catering, and kiosk support. Mobile-friendly PWA with light-mode UI. Deployable to **Railway** with PostgreSQL + Cloudinary.

---

## Features

### Authentication & Access
- **Face ID login** — webcam-based face recognition with liveness detection (anti-spoofing)
- **Staff ID + password** login
- **Kiosk PIN** login for quick queue access
- **Role-based access** — Staff, Kitchen, Cafe Bar, Kitchen Admin, Admin, Root
- **Temp staff / Intern accounts** — auto-disable after contract end date

### Cafeteria Ordering
- **Multi-menu support** — Local Kitchen, International Kitchen, Cafe Bar
- **Mixed-menu cart** — order from all menus and checkout together
- **Kiosk mode** — standalone ordering for walk-in public + staff
- **Staff PWA** — mobile-first progressive web app with offline support
- **Admin ordering** — admins can place orders from the dashboard
- **Operating hours** — per-weekday schedules + public holiday calendar
- **Vegetarian indicator** on menu items

### Kitchen & Counter
- **Kitchen display** — real-time order queue for kitchen staff
- **Cafe bar counter** — separate display for cafe bar orders
- **QR code collection** — HMAC-signed one-time QR codes for order pickup
- **HID QR scanner support** — external barcode scanner for counter tablets
- **Per-counter collection tracking** — mixed orders tracked independently per counter
- **WebSocket real-time updates** — via Django Channels + Redis

### Staff Wallet & Credits
- **Monthly credit allowance** — auto-renewed on the 1st of each month (GitHub Actions cron)
- **Prorated credit** for new staff added mid-month
- **Admin-configurable working days** for proration calculation
- **Wallet QR code** on PWA home — for vending machine purchases
- **Credit transaction ledger** — full audit trail of all debits/credits

### Vending Machine Integration
- **REST API** for vending machines to deduct staff credit via QR scan
- **Bearer token authentication** for machine-to-server communication
- **Atomic credit deduction** with row-level locking (race-condition safe)
- **Transaction history** — success/failed with reasons visible in staff PWA
- **Admin vending report** — monthly reconciliation with CSV export for vendor payment
- **API documentation page** with downloadable .doc file

### Events & Catering
- **Event menu packages** — created by Kitchen Admin with components (mains, sides, drinks, desserts)
- **Staff booking** — employees can browse and book events (pending approval)
- **Admin approval workflow** — pending → approved / rejected
- **Admin auto-approve** — admins can book directly without approval
- **Kitchen event view** — kitchen staff see upcoming approved events

### Thermal Printing
- **RawBT silent printing** — ESC/POS receipt with raster QR via Android RawBT app
- **58mm receipt format** — optimized for MPT-2 thermal printers
- **Browser print** — standalone print page for non-RawBT setups

### Admin Dashboard
- **Revenue reports** — daily/weekly/monthly with menu type & payment breakdowns
- **Vending reports** — per-machine transaction summary + CSV download
- **Stock management** — daily quantity tracking with sold/remaining/low-stock indicators
- **Staff management** — search, role filter, pagination, credit adjustments
- **Bulk user import** — CSV and Excel (.xlsx) with downloadable templates
- **Order management** — view, cancel, refund orders
- **Face login audit logs** — IP, device, confidence, timestamp
- **System settings** — kiosk timeouts, credit working days

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django 5.x, Python 3.11+ |
| Database | PostgreSQL (Railway) / SQLite (local dev) |
| Auth | Face Recognition (dlib), HMAC-signed QR tokens |
| Real-time | Django Channels + Redis (WebSocket) |
| Media | Cloudinary (or Railway Volume) |
| Payments | Stripe, PayNow QR |
| Task Queue | Celery + Redis |
| Frontend | Server-rendered Django templates, vanilla JS |
| PWA | Service Worker, Web App Manifest |
| Printing | ESC/POS via RawBT (Android) |
| Hosting | Railway (nixpacks) |

---

## Deploy to Railway

### Prerequisites
- [Railway account](https://railway.app)
- [Cloudinary account](https://cloudinary.com) (free tier — for photo storage)
- GitHub repository with this code

### Step 1 — Create Railway Project

1. Go to [railway.app](https://railway.app) → **New Project**
2. Choose **Deploy from GitHub repo**
3. Select your repository
4. Railway detects `nixpacks.toml` and builds automatically

### Step 2 — Add PostgreSQL

1. In Railway dashboard, click **+ New → Database → PostgreSQL**
2. Railway auto-injects `DATABASE_URL` — nothing else needed

### Step 3 — Add Redis (optional — enables real-time)

1. Click **+ New → Database → Redis**
2. Copy the `REDIS_URL` and add it to your app's environment variables
3. Enables: WebSocket order updates, Celery task queue

### Step 4 — Set Environment Variables

**Required:**

| Variable | Value | Notes |
|---|---|---|
| `SECRET_KEY` | `your-random-50-char-string` | Generate at djecrety.ir |
| `DEBUG` | `False` | Always False in production |
| `ADMIN_STAFF_ID` | `ADMIN-001` | Initial admin login ID |
| `ADMIN_EMAIL` | `admin@company.com` | Admin email |
| `ADMIN_PASSWORD` | `your-secure-password` | Admin password |
| `CLOUDINARY_URL` | `cloudinary://KEY:SECRET@CLOUD` | From Cloudinary dashboard |

**Optional:**

| Variable | Default | Notes |
|---|---|---|
| `FACE_TOLERANCE` | `0.4` | Face match strictness (0.4=strict, 0.6=lenient) |
| `FACE_VERIFY_CONSECUTIVE_MATCHES` | `2` | Frames needed before login (1-5) |
| `DEFAULT_MONTHLY_CREDIT` | `50.00` | Default monthly credit for new staff |
| `CREDIT_RESET_DAY` | `1` | Day of month to reset credits |
| `VENDING_API_KEY` | *(none)* | Bearer token for vending machine API |
| `CRON_SECRET` | *(none)* | Bearer token for GitHub Actions cron |
| `STRIPE_SECRET_KEY` | *(none)* | Stripe payment integration |
| `STRIPE_PUBLISHABLE_KEY` | *(none)* | Stripe client-side key |
| `STRIPE_WEBHOOK_SECRET` | *(none)* | Stripe webhook verification |
| `REDIS_URL` | *(none)* | Enables WebSockets + Celery |
| `BRAND_NAME` | `FaceID Portal` | App name shown in UI |
| `BRAND_ACCENT_COLOR` | `#1e56b8` | Primary accent color |

### Step 5 — Deploy

Railway auto-deploys on every push. First build takes 5-10 minutes (dlib compilation).

### Step 6 — Get Your URL

Railway → Settings → Domains → Generate Domain
→ `https://your-app.up.railway.app`

---

## Monthly Credit Reset (GitHub Actions)

Credits reset automatically on the 1st of each month via a daily GitHub Actions cron.

1. Set `CRON_SECRET` env var on Railway
2. Add the secret to GitHub: Settings → Secrets → `CRON_SECRET` and `RAILWAY_URL`
3. The workflow at `.github/workflows/monthly-credit-reset.yml` runs daily at 16:01 UTC (00:01 SGT)
4. Server checks if it's the 1st in SGT before resetting

---

## Vending Machine API

Full documentation available at `/cafeteria/admin/vending-api/` (admin login required) or in [`VENDING_API.md`](VENDING_API.md).

**Quick start:**
```bash
# Set the API key
export VENDING_API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# Test deduction
curl -X POST https://your-domain.com/cafeteria/api/vending/deduct/ \
  -H "Authorization: Bearer $VENDING_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"qr_token":"VEND:EMP-001.abc...","amount":2.50,"machine_id":"VM-01","description":"Coffee"}'
```

---

## Bulk User Import

Admin → Users → **Bulk Import**

- Download CSV or Excel template
- Fill in staff details (staff_id, email, full_name, password, department, staff_type, contract_end_date)
- Upload — credits are auto-prorated for the current month

---

## Post-Deploy First Steps

1. Log in as admin with `ADMIN_STAFF_ID` / `ADMIN_PASSWORD`
2. **Users** → Add staff accounts (or bulk import via CSV/Excel)
3. **Menu** → Add menu items for Local Kitchen, International Kitchen, and Cafe Bar
4. **Stock** → Set daily quantities
5. **Hours** → Configure operating hours per weekday
6. Staff install PWA (Add to Home Screen) and enroll Face ID via Profile
7. Set up kiosk tablets at `/cafeteria/kiosk/`

---

## Project Structure

```
facerecog/
├── accounts/
│   ├── models.py              # StaffUser, Order, MenuItem, CreditTransaction, etc.
│   ├── views.py               # Auth, admin user management, Face ID
│   ├── cafeteria_views.py     # All cafeteria views (ordering, kitchen, reports, API)
│   ├── face_utils.py          # Face recognition + encoding cache
│   ├── consumers.py           # WebSocket consumers for real-time updates
│   ├── forms.py               # User creation/edit forms
│   ├── urls.py                # URL routing (~140 patterns)
│   ├── templates/
│   │   ├── accounts/          # Login, profile, admin user pages
│   │   └── cafeteria/         # PWA, kiosk, kitchen, admin pages
│   └── migrations/
├── faceid/
│   ├── settings.py            # All configuration
│   ├── urls.py                # Root URL config
│   ├── asgi.py                # ASGI for WebSockets
│   └── wsgi.py
├── templates/
│   └── base.html              # Admin shell template
├── static/                    # manifest.json, service worker, icons
├── .github/workflows/         # Monthly credit reset cron
├── nixpacks.toml              # Railway build config
├── requirements.txt           # Python dependencies
├── VENDING_API.md             # Vending machine API documentation
└── Procfile                   # Process config
```

---

## Troubleshooting

| Issue | Solution |
|---|---|
| Build fails on dlib | `nixpacks.toml` handles cmake/gcc. If still failing, set `NIXPACKS_PYTHON_VERSION=3.11` |
| Photos lost after redeploy | Set `CLOUDINARY_URL` — Railway containers are ephemeral |
| Face login fails | Check `/admin-panel/face-logs/` for attempt details. Try `FACE_TOLERANCE=0.6` |
| Camera blocked | HTTPS required for webcam. Railway domains are HTTPS by default |
| Excel import fails | `openpyxl` must be in requirements.txt (already included) |
| WebSocket not connecting | Deploy Redis on Railway and set `REDIS_URL` |
| Credits not resetting | Check GitHub Actions workflow runs + `CRON_SECRET` matches |
