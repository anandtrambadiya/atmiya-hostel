# Deploy to Railway.app

## What you need

- A [GitHub](https://github.com) account
- A [Railway](https://railway.app) account (free, sign in with GitHub)

---

## Step 1 — Push your code to GitHub

Open a terminal in the `hostel_app` folder and run:

```bash
git init
git add .
git commit -m "Initial commit"
```

Go to [github.com/new](https://github.com/new), create a **new repository** (name it anything, e.g. `hostel-app`), then run:

```bash
git remote add origin https://github.com/YOUR_USERNAME/hostel-app.git
git branch -M main
git push -u origin main
```

---

## Step 2 — Create Railway project

1. Go to [railway.app](https://railway.app) → **New Project**
2. Choose **Deploy from GitHub repo**
3. Select your `hostel-app` repo
4. Railway auto-detects Python and builds it — wait ~1 minute

---

## Step 3 — Add a Volume (persistent database)

Without this, your database resets every deploy.

1. In your Railway project → click **+ New** → **Volume**
2. Set **Mount Path** to `/data`
3. Click **Add**

---

## Step 4 — Set Environment Variables

In your Railway project → click your service → **Variables** tab → add these one by one:

| Variable     | Value                    | Notes                                      |
| ------------ | ------------------------ | ------------------------------------------ |
| `SECRET_KEY` | `any-long-random-string` | e.g. `xK9#mP2$qR7!nL4@wZ` — make it random |
| `ADMIN_ID`   | `your_chosen_id`         | Don't use `1234`                           |
| `ADMIN_PASS` | `your_strong_password`   | Don't use `5005`                           |
| `DB_PATH`    | `/data/hostel.db`        | Must match the Volume mount path           |

**How to pick a good SECRET_KEY:** Just mash your keyboard: `aK3!xP9#mQ2$rL7@nW5`

---

## Step 5 — Deploy

Railway redeploys automatically after you set env vars. Wait ~30 seconds.

Click **View Logs** to confirm it started. You'll see:

```
[gunicorn] Booting worker with pid: ...
```

Click the generated URL (e.g. `hostel-app.up.railway.app`) — your app is live!

---

## Step 6 — Change the volunteer password

Once deployed, log in as admin → Dashboard → **Volunteer Password** → set a new strong password.

---

## After first deploy — updating the app

Whenever you make changes:

```bash
git add .
git commit -m "describe your change"
git push
```

Railway auto-redeploys on every push. Database is preserved on the Volume.

---

## Security checklist

- [x] Admin credentials in Railway env vars, not in code
- [x] `.env` and `*.db` in `.gitignore` — won't be pushed to GitHub
- [x] Passwords are SHA-256 hashed, never stored in plain text
- [x] Flask secret key from environment
- [x] HTTPS provided automatically by Railway
- [ ] Change default volunteer password after first login
- [ ] Don't share your Railway dashboard with anyone

---

## Local development

```bash
# Create your local .env
cp .env.example .env
# Edit .env and set your local values

# Install dependencies
pip install -r requirements.txt

# Run locally
python app.py
# Open http://localhost:5000
```
