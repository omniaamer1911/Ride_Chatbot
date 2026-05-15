import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/trips/{user_id}")
async def trip_updates_ws(websocket: WebSocket, user_id: str):
    await websocket.accept()
    bus = websocket.app.state.bus
    q = await bus.subscribe(user_id)
    try:
        while True:
            try:
                payload = await asyncio.wait_for(q.get(), timeout=30.0)
                await websocket.send_text(payload)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        await bus.unsubscribe(user_id, q)
