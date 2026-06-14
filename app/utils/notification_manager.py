import json
from typing import Dict, Set
from fastapi import WebSocket
from datetime import datetime


class NotificationManager:
    def __init__(self):
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, role: str, client_id: str, websocket: WebSocket):
        await websocket.accept()
        if role not in self.active_connections:
            self.active_connections[role] = {}
        self.active_connections[role][client_id] = websocket

    def disconnect(self, role: str, client_id: str):
        if role in self.active_connections and client_id in self.active_connections[role]:
            del self.active_connections[role][client_id]

    async def send_to_role(self, role: str, message: dict):
        if role not in self.active_connections:
            return
        message_with_timestamp = {
            **message,
            "timestamp": datetime.utcnow().isoformat(),
        }
        dead_connections = []
        for client_id, websocket in list(self.active_connections[role].items()):
            try:
                await websocket.send_text(json.dumps(message_with_timestamp, ensure_ascii=False))
            except Exception:
                dead_connections.append((role, client_id))
        for r, cid in dead_connections:
            self.disconnect(r, cid)

    async def send_to_recipient(self, role: str, recipient_name: str, message: dict):
        if role not in self.active_connections:
            return
        message_with_timestamp = {
            **message,
            "timestamp": datetime.utcnow().isoformat(),
        }
        for client_id, websocket in list(self.active_connections[role].items()):
            if client_id == recipient_name:
                try:
                    await websocket.send_text(json.dumps(message_with_timestamp, ensure_ascii=False))
                except Exception:
                    self.disconnect(role, client_id)

    async def broadcast(self, message: dict, roles: list = None):
        if not roles:
            roles = list(self.active_connections.keys())
        for role in roles:
            await self.send_to_role(role, message)

    def get_connection_count(self, role: str = None) -> int:
        if role:
            return len(self.active_connections.get(role, {}))
        return sum(len(v) for v in self.active_connections.values())


notification_manager = NotificationManager()
