# Step 3: Frontend ↔ WebSocket Connectivity

## Overview
This connection is used for **real-time streaming**. Instead of your browser asking "Is it done yet?" every second, the backend "pushes" updates to you instantly.

## Technical Details
- **Protocol**: WS (WebSockets)
- **Endpoint**: `/ws`
- **Technology**: FastAPI WebSockets

## How it works
1. As soon as you open the Dashboard, your browser establishes a **persistent** WebSocket connection to the backend.
2. When an agent (e.g., `job_discovery_agent`) finds a job or does an action, it logs it.
3. The `WorkflowManager` in `server/app.py` catches that log and broadcasts it through the WebSocket.
4. Your browser receives the message instantly and adds it to the **Live Logs** terminal in the UI.

## Critical Files
- `server/app.py`: Defines the `@app.websocket("/ws")` endpoint.
- `frontend/src/App.jsx`: Contains the `createWebSocket` logic to listen for incoming messages.
