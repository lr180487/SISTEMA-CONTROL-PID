"""Canal WebSocket de telemetría en tiempo real."""
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from ...core.runtime import Runtime
from ..dependencies import get_runtime

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, runtime: Runtime = Depends(get_runtime)):
    await runtime.ws_hub.connect(websocket)
    try:
        await websocket.send_json(runtime.telemetry().model_dump())
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        runtime.ws_hub.disconnect(websocket)
    except Exception:
        runtime.ws_hub.disconnect(websocket)
