# Step 2: Frontend ↔ Backend Connectivity

## Overview
This is how the user interface (UI) communicates with the "brain" of the application. Every time you click a button like "Launch Workflow", this connection is used.

## Technical Details
- **Protocol**: HTTP / REST API
- **Internal Port**: `8000`
- **Data Format**: JSON

## How it works
1. When you click "Launch" in the React UI, an **Axios** (or fetch) request is sent to `/api/start-workflow`.
2. The **Nginx** proxy on the frontend catches this and forwards it to the `backend` container on port `8000`.
3. The **FastAPI** server on the backend receives the JSON data (e.g., your selected resume path).
4. The backend processes the request and sends back a JSON confirmation.

## Critical Files
- `frontend/src/api.js`: Contains the JavaScript functions that make these calls.
- `server/app.py`: Contains the FastAPI routes (endpoints) like `@app.post("/api/start-workflow")`.
