# Step 5: User ↔ NoVNC Connectivity

## Overview
This allows you to "Remote Desktop" into the headless server and see exactly what the AI is doing in the browser. It's essential for manual logins and solving CAPTCHAs.

## Technical Details
- **Stack**: Xvfb → X11VNC → Websockify → NoVNC
- **Internal Port**: `6080`
- **External Path**: `/vnc/` (proxied by Nginx)

## How it works
1. You navigate to the "Browser" tab in the Dashboard.
2. An `<iframe>` loads the NoVNC web client.
3. NoVNC connects to the `websockify` server on the backend.
4. Websockify streams the images from the virtual monitor (`Xvfb`) to your screen.
5. Your mouse clicks and keyboard presses are sent back through the same tunnel to control Chrome.

## Critical Files
- `start.sh`: Starts the entire visualization stack (Xvfb, fluxbox, x11vnc, websockify).
- `frontend/nginx.conf`: Proxies `/vnc/` and `/websockify` traffic correctly.
