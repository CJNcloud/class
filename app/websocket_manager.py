from typing import Dict, Set
from starlette.websockets import WebSocket


class GroupWebSocketManager:
    def __init__(self) -> None:
        self.group_connections: Dict[int, Set[WebSocket]] = {}

    async def connect(self, group_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self.group_connections.setdefault(group_id, set()).add(websocket)

    def disconnect(self, group_id: int, websocket: WebSocket) -> None:
        conns = self.group_connections.get(group_id)
        if not conns:
            return
        conns.discard(websocket)
        if not conns:
            self.group_connections.pop(group_id, None)

    async def broadcast_json(self, group_id: int, message: dict) -> None:
        for ws in list(self.group_connections.get(group_id, set())):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(group_id, ws)


ws_manager = GroupWebSocketManager()

