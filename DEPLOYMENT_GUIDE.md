# 🚀 Job Agent: Complete Deployment Guide

This document provides a step-by-step guide to deploying the autonomous Job Agent system to your Ubuntu server. It covers the infrastructure, connectivity, and the manual steps required to keep the system running.

---

## 🛠 1. System Connectivity Map

Understanding how the "microservices" talk to each other:

| Connection | Protocol | Description |
| :--- | :--- | :--- |
| **User ↔ Frontend** | HTTP (Port 80/8082) | You access the Dashboard UI via your browser. |
| **Frontend ↔ Backend** | HTTP/JSON (Port 8000) | The React UI sends commands (Start/Stop) to the FastAPI backend. |
| **Frontend ↔ WebSocket** | WS (Port 8000/ws) | The Backend streams live logs and progress updates to the UI. |
| **Backend ↔ Browser** | Playwright (CDP) | The Python code controls Google Chrome via the remote debugging protocol. |
| **User ↔ NoVNC** | WebSockets (Port 6080) | Proxied through Nginx, allowing you to see the virtual browser in the dashboard. |
| **Backend ↔ SQLite** | Local File System | The `tracker_agent` saves application logs to `/app/db/job_agent.db`. |

---

## 📋 2. Prerequisites

### Local Machine (Windows/Mac/Linux)
- **Python 3.10+** (To run `run_deploy.py`)
- **tar.exe** or any zip utility (To package the code)
- **SSH Access** to your Ubuntu server.

### Remote Server (Ubuntu 22.04+)
- **Docker** and **Docker Compose** installed.
- **Ports Open**: 80 (Nginx), 8000 (Backend API), 6080 (NoVNC).
- **Disk Space**: At least 5GB for Docker images and Chrome cache.

---

## 🚀 3. Step-by-Step Deployment

### Step A: Local Configuration
Ensure your `.env` file is filled with your credentials:
```env
OPENAI_API_KEY=your_key
LINKEDIN_USER=your_email
LINKEDIN_PASS=your_password
NAUKRI_USER=your_email
NAUKRI_PASS=your_password
```

### Step B: Create the Deployment Package
We create a zip file containing only the necessary source code, excluding bulky folders like `node_modules` or `browser_data`.
```powershell
tar.exe -a -c -f deploy_new.zip --exclude="frontend/node_modules" --exclude="*/__pycache__" --exclude="browser_data" agents db engine frontend graph server tools docker-compose.yml Dockerfile.backend main.py requirements.txt start.sh .env
```

### Step C: Execute the Deployment Script
Run the automated deployment script. It will upload the zip, unzip it on the server, and restart the Docker containers.
```bash
python run_deploy.py
```

---

## 🐋 4. Server-Side Execution (Manual)
If you ever need to run commands directly on the server:

1. **SSH into your server**:
   ```bash
   ssh root@YOUR_SERVER_IP
   ```
2. **Navigate to the app directory**:
   ```bash
   cd /root/job_agent
   ```
3. **Check Logs**:
   ```bash
   docker compose logs -f backend
   ```
4. **Restart Services**:
   ```bash
   docker compose down && docker compose up -d
   ```

---

## 🔒 5. Handling Browser Sessions
The system uses **Persistent Context**. This means once you log into LinkedIn or Naukri, the session is saved in the `/app/browser_data` volume.

**To Log In Manually:**
1. Open the dashboard at `http://jobagent.agenticrag.online`.
2. Go to the **Browser** tab (NoVNC).
3. If Chrome asks for a password or OTP, fill it manually in this view.
4. Close the view. The agent will now use this active session automatically.

---

## ⚠️ 6. Troubleshooting

| Issue | Solution |
| :--- | :--- |
| **"Profile in use" error** | The system now automatically deletes `SingletonLock`. Just restart the workflow. |
| **NoVNC not loading** | Ensure port 6080 is open in your cloud firewall (e.g., AWS Security Group / DigitalOcean Firewall). |
| **WebSocket Disconnected** | Refresh the page. Nginx might have timed out the long-lived connection. |
| **Naukri/LinkedIn Bot Detection** | The system uses `stealth` mode and a real `Chrome` binary. If blocked, wait 2 hours or solve a Captcha manually via NoVNC. |
