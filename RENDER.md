# CampusFix — Render.com Deployment Guide

Deploying **CampusFix** on [Render](https://render.com/) is **100% Free** and fully supports **MongoDB Atlas** with no port restrictions!

---

## 🚀 Step-by-Step Deployment Guide

### Step 1: Push project to GitHub

If you haven't pushed your latest code to GitHub yet:
```bash
git add .
git commit -m "Add Render configuration and Gunicorn"
git push origin main
```

---

### Step 2: Create a Web Service on Render

1. Go to **[Render.com](https://dashboard.render.com/)** and log in (or sign up with GitHub).
2. Click **New +** → Select **Web Service**.
3. Connect your **CampusFix** GitHub repository (`https://github.com/sriharini27/CampusFix.git`).
4. Fill in the following settings:
   - **Name**: `campusfix` (or any custom name)
   - **Region**: Choose closest to you (e.g. Singapore or Frankfurt)
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Instance Type**: **Free**

---

### Step 3: Add Environment Variables in Render

Scroll down to **Environment Variables** (or click the *Environment* tab) and add:

| Key | Value |
| :--- | :--- |
| `MONGO_URI` | `mongodb+srv://campusfix:YOUR_DB_PASSWORD@cluster0.iihk69x.mongodb.net/?appName=Cluster0` |
| `DB_NAME` | `campusfix` |
| `SECRET_KEY` | `62abbf8ac4b8e4a6ba57c41cc04d989b296b049e6706475d99bcb3c8d1ddf8ff` |
| `FLASK_DEBUG` | `0` |
| `GOOGLE_CLIENT_ID` | `YOUR_GOOGLE_CLIENT_ID` |
| `GOOGLE_CLIENT_SECRET` | `YOUR_GOOGLE_CLIENT_SECRET` |
| `GOOGLE_REDIRECT_URI` | `https://campusfix.onrender.com/auth/google/callback` *(replace `campusfix` with your Render app name)* |
| `GOOGLE_ALLOWED_DOMAIN` | `nec.edu.in` |
| `PUBLIC_BASE_URL` | `https://campusfix.onrender.com` *(replace `campusfix` with your Render app name)* |

---

### Step 4: Click Deploy!

Click **Create Web Service**. Render will automatically build and deploy your application.

---

### Step 5: Seed Database (Initial Users)

Once the deployment finishes and shows **Live**:

1. Click on **Shell** in your Render service menu.
2. Run:
   ```bash
   python seed.py
   ```

Your app will be live at `https://campusfix.onrender.com`! 🎉
