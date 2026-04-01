# Deploy to Render with PostgreSQL

## Step 1 — Create PostgreSQL database on Render

1. Render dashboard → **New → PostgreSQL**
2. Name it `hostel-db` → choose **Free** plan → **Create Database**
3. Wait ~1 minute → click the database → copy the **Internal Database URL**
   - Looks like: `postgresql://user:pass@host/dbname`

## Step 2 — Push to GitHub

```bash
git add .
git commit -m "switch to postgresql"
git push
```

## Step 3 — Create Web Service

1. Render → **New → Web Service** → connect GitHub repo
2. Settings:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120`

## Step 4 — Set Environment Variables

Render → your web service → **Environment** tab:

| Key | Value |
|-----|-------|
| `DATABASE_URL` | paste the Internal Database URL from Step 1 |
| `ADMIN_ID` | your chosen admin ID |
| `ADMIN_PASS` | your strong password |
| `SECRET_KEY` | auto-generated (from render.yaml) |

## Step 5 — Deploy

Click **Deploy** → your app is live. Database is fully persistent forever on free plan.

---

## Local development

Install PostgreSQL locally or use a free cloud DB (supabase.com).

```bash
cp .env.example .env
# Set DATABASE_URL to your local or cloud postgres URL

pip install -r requirements.txt
python app.py
```