from new.api.ws import manager
from new.db import engine
from new.models import Run


async def pipeline_to_ws(agent: str, status: str, message: str):
    try:
        from sqlmodel import Session, select
        # Find active runs - broadcast to all connected clients
        # In practice, we need the run_id. The pipeline callbacks receive it via closure.
        pass
    except Exception:
        pass


def make_ws_callback(run_id: str):
    async def callback(agent: str, status: str, message: str):
        await manager.broadcast(run_id, agent, status, message)
        if status in ("completed", "failed") and agent == "pipeline":
            with Session(engine) as session:
                run_obj = session.get(Run, run_id)
                job_count = run_obj.job_count if run_obj else 0
            await manager.broadcast_complete(run_id, status, job_count)
        if status == "failed":
            await manager.broadcast_error(run_id, message, agent)

    return callback
