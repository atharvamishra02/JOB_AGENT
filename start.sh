#!/bin/bash
set -e

# Start Xvfb
Xvfb :99 -screen 0 1366x768x16 -nolisten tcp -nolisten unix &
export DISPLAY=:99

# Start a lightweight window manager
fluxbox -display :99 &

# Start x11vnc
x11vnc -display :99 -nopw -forever -shared -bg

# Start WebSockify + NoVNC
websockify --web /usr/share/novnc 0.0.0.0:6080 localhost:5900 &

# Start the actual application
echo "Starting backend..."
exec uvicorn server.app:app --host 0.0.0.0 --port 8000 --forwarded-allow-ips="*"
