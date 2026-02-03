import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, List

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from agent.core import AgentRuntime
from config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.agent_sessions: Dict[str, AgentRuntime] = {}
    
    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        self.agent_sessions[session_id] = AgentRuntime(session_id)
        logger.info(f"Session {session_id} connected")
    
    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
        if session_id in self.agent_sessions:
            del self.agent_sessions[session_id]
    
    async def send_message(self, session_id: str, message: dict):
        if session_id in self.active_connections:
            await self.active_connections[session_id].send_json(message)

manager = ConnectionManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    app.state.tool_registry = None
    app.state.memory_store = None
    
    # Start Telegram bot if configured
    if settings.TELEGRAM_TOKEN:
        from channels.telegram_bot import TelegramChannel
        telegram = TelegramChannel(manager)
        asyncio.create_task(telegram.start())
        app.state.telegram = telegram
    
    # Start Discord bot if configured
    if settings.DISCORD_TOKEN:
        from channels.discord_bot import DiscordChannel
        discord_chan = DiscordChannel(manager)
        asyncio.create_task(discord_chan.start())
        logger.info("Discord bot started")
    
    logger.info(f"🚀 AgentVault Gateway started on ws://0.0.0.0:{settings.GATEWAY_PORT}")
    yield
    
    # SHUTDOWN
    logger.info("Shutting down")

app = FastAPI(title="AgentVault Gateway", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await manager.connect(websocket, session_id)
    try:
        while True:
            data = await websocket.receive_json()
            agent = manager.agent_sessions[session_id]
            response = await agent.process_message(data)
            await manager.send_message(session_id, {
                "type": "agent_response",
                "timestamp": datetime.utcnow().isoformat(),
                "data": response
            })
    except WebSocketDisconnect:
        manager.disconnect(session_id)

@app.get("/api/v1/tools")
async def list_tools():
    from tools.registry import ToolRegistry
    registry = ToolRegistry()
    return {"tools": registry.list_tools()}

@app.get("/api/v1/sessions/{session_id}/history")
async def get_history(session_id: str):
    if session_id not in manager.agent_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"history": manager.agent_sessions[session_id].get_history()}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.GATEWAY_PORT)