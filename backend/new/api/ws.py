import asyncio
import json
from datetime import datetime, timezone
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlmodel import Session, select

from new.db import engine
from new.models import RunEvent, Run

router = APIRouter(tags=["new-ws"])


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, Set[WebSocket]] = {}

    async def connect(self, run_id: str, ws: WebSocket):
        await ws.accept()
        if run_id not in self._connections:
            self._connections[run_id] = set()
        self._connections[run_id].add(ws)
        # Send existing events on connect
        with Session(engine) as session:
            events = session.exec(
                select(RunEvent)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.timestamp)
            ).all()
        for e in events:
            try:
                await ws.send_json({
                    "type": "event",
                    "data": {
                        "agent": e.agent,
                        "status": e.status,
                        "message": e.message,
                        "timestamp": e.timestamp.isoformat(),
                    },
                })
            except Exception:
                pass

    async def disconnect(self, run_id: str, ws: WebSocket):
        if run_id in self._connections:
            self._connections[run_id].discard(ws)
            if not self._connections[run_id]:
                del self._connections[run_id]

    async def broadcast(self, run_id: str, agent: str, status: str, message: str):
        payload = {
            "type": "event",
            "data": {
                "agent": agent,
                "status": status,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }
        if run_id in self._connections:
            dead = set()
            for ws in self._connections[run_id]:
                try:
                    await ws.send_json(payload)
                except Exception:
                    dead.add(ws)
            for ws in dead:
                self._connections[run_id].discard(ws)

    async def broadcast_complete(self, run_id: str, status: str, job_count: int):
        payload = {
            "type": "complete",
            "data": {
                "run_id": run_id,
                "status": status,
                "job_count": job_count,
            },
        }
        if run_id in self._connections:
            dead = set()
            for ws in self._connections[run_id]:
                try:
                    await ws.send_json(payload)
                except Exception:
                    dead.add(ws)
            for ws in dead:
                self._connections[run_id].discard(ws)

    async def broadcast_error(self, run_id: str, message: str, agent: str = ""):
        payload = {
            "type": "error",
            "data": {"message": message, "agent": agent},
        }
        if run_id in self._connections:
            dead = set()
            for ws in self._connections[run_id]:
                try:
                    await ws.send_json(payload)
                except Exception:
                    dead.add(ws)
            for ws in dead:
                self._connections[run_id].discard(ws)


manager = ConnectionManager()


@router.websocket("/ws/new/runs/{run_id}")
async def run_websocket(websocket: WebSocket, run_id: str):
    await manager.connect(run_id, websocket)

    # Check whether the run has already finalized; if so, send a final
    # terminal event and close cleanly without entering the recv loop.
    with Session(engine) as session:
        run_obj = session.get(Run, run_id)
        if run_obj and run_obj.status in ("completed", "failed", "stopped"):
            final_status = run_obj.status
            try:
                if final_status == "completed":
                    await websocket.send_json({
                        "type": "complete",
                        "data": {
                            "run_id": run_id,
                            "status": final_status,
                            "job_count": run_obj.job_count,
                        },
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "data": {
                            "message": f"Run {final_status}",
                            "agent": "pipeline",
                            "status": final_status,
                        },
                    })
            except Exception:
                pass
            await manager.disconnect(run_id, websocket)
            try:
                await websocket.close()
            except Exception:
                pass
            return

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        await manager.disconnect(run_id, websocket)
    except Exception:
        await manager.disconnect(run_id, websocket)
