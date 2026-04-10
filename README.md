# FaceID Portal 🔐

A Django staff authentication system with **Face Recognition login** and Staff ID/Password login. Mobile-friendly dark UI. Deployable to **Railway** with PostgreSQL + Cloudinary.

---

## Deploy to Railway (Step-by-Step)

### Prerequisites
- [Railway account](https://railway.app) (free tier works)
- [Cloudinary account](https://cloudinary.com) (free tier — for photo storage)
- Your code pushed to a **GitHub repository**

---

### Step 1 — Push to GitHub

```bash
cd faceid_project
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/faceid-portal.git
git push -u origin main
```

---

### Step 2 — Create Railway Project

1. Go to [railway.app](https://railway.app) → **New Project**
2. Choose **Deploy from GitHub repo**
3. Select your `faceid-portal` repository
4. Railway will detect `nixpacks.toml` and start building automatically

---

### Step 3 — Add PostgreSQL

1. In your Railway project dashboard, click **+ New**
2. Choose **Database → PostgreSQL**
3. Railway auto-injects `DATABASE_URL` into your app — nothing else needed

---

### Step 4 — Set Environment Variables

In Railway → your app service → **Variables**, add:

| Variable | Value | Notes |
|---|---|---|
| `SECRET_KEY` | `your-random-50-char-string` | Generate at djecrety.ir |
| `DEBUG` | `False` | Always False in production |
| `ADMIN_STAFF_ID` | `ADMIN-001` | Your admin login ID |
| `ADMIN_EMAIL` | `admin@yourcompany.com` | Admin email |
| `ADMIN_PASSWORD` | `your-secure-password` | Admin password |
| `CLOUDINARY_URL` | `cloudinary://KEY:SECRET@CLOUD` | From Cloudinary dashboard |
| `FACE_TOLERANCE` | `0.5` | Optional (0.4=strict, 0.6=lenient) |

**Getting CLOUDINARY_URL:**
1. Sign up at cloudinary.com
2. Dashboard → API Keys → copy the API environment variable string
3. Looks like: `cloudinary://123456789:abcdefgh@yourcloudname`

---

### Step 5 — Deploy

Railway auto-deploys on every GitHub push, or click Deploy manually.

The nixpacks.toml build does:
1. Installs cmake, gcc, openblas (required by dlib/face_recognition)
2. pip install -r requirements.txt
3. collectstatic, migrate, create_admin

First build takes 5-10 minutes (dlib compilation).

---

### Step 6 — Get Your URL

Railway → Settings → Domains → Generate Domain
You get: https://your-app-name.up.railway.app

---

## Post-Deploy First Steps

1. Log in as admin with ADMIN_STAFF_ID / ADMIN_PASSWORD
2. Manage Users → Add User to create staff accounts
3. Staff go to Profile & Face ID to enroll via webcam
4. Admin enables "Face ID login" per user
5. Users can now login via Face ID tab

---

## Troubleshooting

**Build fails on dlib:** nixpacks.toml handles cmake/gcc. If it still fails, set NIXPACKS_PYTHON_VERSION=3.11 in env vars.

**Photos lost after redeploy:** Set CLOUDINARY_URL — Railway containers are ephemeral.

**Face login fails:** Check /admin-panel/face-logs/ for attempt details. Try FACE_TOLERANCE=0.6.

**Camera blocked:** HTTPS is required for webcam. Railway domains are HTTPS by default.
