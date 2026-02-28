from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.playground.router import router as playground_router
from app.proxy.router import router as proxy_router
from app.settings_router import router as settings_router
from app.vault.store import vault
from app.ws.manager import manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("✓ Cut It proxy running → http://localhost:8080")
    print("  Configure clients to use http://localhost:8080 instead of api.mistral.ai")
    yield
    print("Cut It proxy shutting down")


app = FastAPI(
    title="Cut It",
    description="Privacy-first AI proxy — local screening, clean data to cloud",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "Cut It Proxy", "version": "0.1.0"}


@app.get("/vault")
async def get_vault():
    return vault.all_sessions()


@app.get("/vault/{session_id}")
async def get_session_vault(session_id: str):
    return vault.get_session(session_id)


@app.delete("/vault/{session_id}")
async def clear_session_vault(session_id: str):
    vault.clear_session(session_id)
    return {"cleared": session_id}


app.include_router(settings_router)
app.include_router(playground_router)
app.include_router(proxy_router)
