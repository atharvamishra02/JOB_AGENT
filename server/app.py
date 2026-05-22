"""
server/app.py — FastAPI backend entry point
═══════════════════════════════════════════
Main entry point that assembles all modular routes and starts the server.
"""

import asyncio
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path and load environment variables
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.workflow_manager import wf_manager
from server.auth import decode_token
from server.routes import auth, user, workflow, data, dashboard

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-30s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("server")

# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="Job Agent Dashboard", version="2.1.0")

@app.middleware("http")
async def forward_proto_middleware(request, call_next):
    proto = request.headers.get("x-forwarded-proto")
    if proto:
        request.scope["scheme"] = proto
    response = await call_next(request)
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Include Routers ──────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(user.router)
app.include_router(workflow.router)
app.include_router(data.router)
app.include_router(dashboard.router)

# ── WebSocket ────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(None)):
    await ws.accept()
    
    # Store event loop for the workflow manager to use for broadcasts
    if not wf_manager.event_loop:
        wf_manager.event_loop = asyncio.get_event_loop()

    # Auth
    user_id = None
    if token:
        try:
            payload = decode_token(token)
            user_id = int(payload["sub"])
            ws.user_id = user_id # Tag the socket
        except Exception:
            await ws.send_json({"type": "error", "message": "Invalid token"})
            await ws.close()
            return
    else:
        ws.user_id = None

    wf_manager.connections.append(ws)
    logger.info("WebSocket client connected (user=%s, %d total)", user_id, len(wf_manager.connections))

    # Send current state on connect
    status = wf_manager.get_status(user_id)
    state = wf_manager.get_state(user_id)
    
    await ws.send_json({
        "type": "init",
        "data": status,
        "logs": state.logs[-50:],
    })

    try:
        while True:
            data = await ws.receive_text()
            # Basic heartbeat or status requests
            import json
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
            elif msg.get("type") == "get_status":
                status = wf_manager.get_status(user_id)
                await ws.send_json({
                    "type": "status",
                    "data": status,
                })
    except WebSocketDisconnect:
        if ws in wf_manager.connections:
            wf_manager.connections.remove(ws)
        logger.info("WebSocket client disconnected")

# ── Health Check ─────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    from datetime import datetime, timezone
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
