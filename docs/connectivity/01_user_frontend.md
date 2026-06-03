# Step 1: User ↔ Frontend Connectivity

## Overview
This is the entry point for you as the user. You interact with the **Job Agent Dashboard** using your web browser (Chrome, Firefox, etc.).

## Technical Details
- **Protocol**: HTTP / HTTPS
- **Primary Port**: `80` (Internal Docker) / `8082` (External Host)
- **Technology**: React (Frontend) + Nginx (Web Server)

## How it works
1. You type `http://jobagent.agenticrag.online` into your browser.
2. The request hits the **Nginx** server running inside the `frontend` container.
3. Nginx serves the compiled **React (Vite)** files (`index.html`, `main.js`, etc.) to your browser.
4. Your browser renders the dashboard UI locally on your computer.

## Critical Files
- `frontend/nginx.conf`: Configures how Nginx handles your requests.
- `frontend/dist/`: Contains the actual website files.
