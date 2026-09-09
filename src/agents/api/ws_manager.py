"""In-process WebSocket rooms for parallel advisor/customer conversations."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class ConversationConnectionManager:
    """Manage multiple connections per conversation without cross-room leaks."""

    def __init__(self) -> None:
        self._rooms: dict[str, dict[str, WebSocket]] = defaultdict(dict)

    async def connect(self, conversation_id: str, key: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._rooms[conversation_id][key] = websocket

    def disconnect(self, conversation_id: str, key: str) -> None:
        room = self._rooms.get(conversation_id)
        if room is None:
            return
        room.pop(key, None)
        if not room:
            self._rooms.pop(conversation_id, None)

    async def broadcast(self, conversation_id: str, event: dict[str, Any], *, exclude_key: str | None = None) -> None:
        """Send an event to every live participant and clean dead sockets."""

        room = self._rooms.get(conversation_id, {})
        dead: list[str] = []
        for key, websocket in tuple(room.items()):
            if key == exclude_key:
                continue
            try:
                await websocket.send_json(event)
            except Exception:  # noqa: BLE001 - dead sockets have varied transport errors
                dead.append(key)
        for key in dead:
            self.disconnect(conversation_id, key)


ws_manager = ConversationConnectionManager()
