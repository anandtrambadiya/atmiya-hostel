# Deploy to PythonAnywhere (Free)

## What you need

- A [PythonAnywhere](https://www.pythonanywhere.com) account — free, no credit card

Your app will be live at: `https://YOUR_USERNAME.pythonanywhere.com`

---

## Step 1 — Sign up

Go to [pythonanywhere.com](https://www.pythonanywhere.com) → **Pricing & signup** → **Create a Beginner account** (free).

Pick a username carefully — it becomes your URL.

---

## Step 2 — Upload your project files

### Option A — via ZIP (easiest)

1. Zip your entire `hostel_app` folder on your computer
2. In PythonAnywhere dashboard → **Files** tab
3. Click **Upload a file** → upload the ZIP
4. Open a **Bash console** (Dashboard → **New console → Bash**)
5. Run:

```bash
cd ~
unzip hostel_app.zip
ls hostel_app/   # verify files are there
```

### Option B — via GitHub

If your code is on GitHub:

```bash
cd ~
git clone https://github.com/YOUR_USERNAME/hostel-app.git hostel_app
```

---

## Step 3 — Install Flask

In the Bash console:

```bash
pip3 install --user flask
```

---

## Step 4 — Create your .env file

In the Bash console:

```bash
cd ~/hostel_app
cp .env.example .env
nano .env
```

Edit the values — use arrow keys to move, type your values:

```
SECRET_KEY=xK9mP2qR7nL4wZ3vB8   ← any long random string
ADMIN_ID=YourChosenID            ← NOT 1234
ADMIN_PASS=YourStrongPassword    ← NOT 5005
DB_PATH=/home/YOUR_USERNAME/hostel_app/hostel.db
```

Replace `YOUR_USERNAME` with your actual PythonAnywhere username.

Press **Ctrl+X → Y → Enter** to save.

---

## Step 5 — Test it runs

In the Bash console:

```bash
cd ~/hostel_app
python3 wsgi.py
```

You should see no errors. Press Ctrl+C to stop.

---

## Step 6 — Set up the Web App

1. Go to PythonAnywhere **Web** tab → **Add a new web app**
2. Click **Next** → choose **Manual configuration** → choose **Python 3.10**
3. Click **Next** → your web app is created

### Set the source code path

In the **Code** section:

- **Source code:** `/home/YOUR_USERNAME/hostel_app`
- **Working directory:** `/home/YOUR_USERNAME/hostel_app`

### Set the WSGI file

Click the link to edit your WSGI file (something like `/var/www/YOUR_USERNAME_pythonanywhere_com_wsgi.py`).

**Delete everything** in that file and paste this:

```python
import sys
import os

project_home = '/home/YOUR_USERNAME/hostel_app'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

env_file = os.path.join(project_home, '.env')
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, val = line.partition('=')
                os.environ.setdefault(key.strip(), val.strip())

from app import app, init_db
init_db()
application = app
```

Replace `YOUR_USERNAME` with your actual username. **Save the file.**

---

## Step 7 — Reload and open

Back on the **Web** tab → click the big green **Reload** button.

Visit `https://YOUR_USERNAME.pythonanywhere.com` — your app is live! 🎉

---

## Updating the app later

When you make changes to the code:

### If you used ZIP upload:

1. Upload the new ZIP → unzip again
2. Web tab → click **Reload**

### If you used GitHub:

```bash
cd ~/hostel_app
git pull
```

Then Web tab → click **Reload**

Your database (`hostel.db`) is never touched by updates — it lives at `/home/YOUR_USERNAME/hostel_app/hostel.db` and persists forever.

---

## Keep the free app awake

PythonAnywhere free accounts go to sleep after a while with no visits.
To keep it awake, set a monthly task to ping it:

1. PythonAnywhere → **Tasks** tab
2. Add a **Scheduled task** → run daily:

```bash
curl -s https://YOUR_USERNAME.pythonanywhere.com/ > /dev/null
```

---

## Security checklist

- [x] Admin credentials in `.env` file, not in source code
- [x] `.env` is in `.gitignore` — won't go to GitHub
- [x] `.env` lives only on PythonAnywhere server
- [x] Passwords are SHA-256 hashed
- [x] HTTPS provided automatically by PythonAnywhere
- [x] Database persists forever on free plan
- [ ] Change default volunteer password after first login
- [ ] Don't share your PythonAnywhere password with anyone

---

## Troubleshooting

**"ModuleNotFoundError: No module named flask"**

```bash
pip3 install --user flask
```

Then reload the web app.

**"500 Internal Server Error"**
Go to Web tab → click the **error log** link → read the last few lines for the actual error.

**App shows old content after update**
Web tab → click **Reload** button.

**Database is empty after update**
That's normal if you changed `DB_PATH`. Check that `.env` has the correct path.
