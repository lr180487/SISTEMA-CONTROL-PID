"""Operaciones de celdas, alimentación y alarmas."""
from fastapi import APIRouter, Depends, HTTPException

from ...models import (AlarmAckRequest, AlarmAckResponse, CellUpdateRequest,
                       FeedSimulationConfig)
from ...core.runtime import Runtime
from ..dependencies import get_runtime
from ..schemas import DisturbanceStepRequest, GlobalActionRequest

router = APIRouter(tags=["process"])


@router.post("/api/cells/{cell_id}")
async def update_cell(cell_id: str, req: CellUpdateRequest, rt: Runtime = Depends(get_runtime)):
    cid = cell_id.upper()
    if cid not in rt.process.configs:
        raise HTTPException(status_code=404, detail=f"Celda {cid} no existe. Use C1, C2 o C3.")
    cfg = rt.process.configs[cid]
    for key, value in req.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(cfg, key, value)
    if cfg.alarm_low >= cfg.alarm_high - 20.0:
        cfg.alarm_low = cfg.alarm_high - 25.0
    return {"status": "ok", "cell": cfg, "telemetry": rt.telemetry()}


@router.post("/api/feed")
async def update_feed_simulation(cfg: FeedSimulationConfig, rt: Runtime = Depends(get_runtime)):
    if cfg.profile != rt.process.feed_cfg.profile:
        rt.process.profile_start_sec = rt.process.elapsed_sec
    rt.process.feed_cfg = cfg
    return {"status": "ok", "feed": rt.process.feed_cfg}


@router.post("/api/feed/disturbance")
async def apply_instant_disturbance(req: DisturbanceStepRequest, rt: Runtime = Depends(get_runtime)):
    new_flow = rt.process.trigger_instant_disturbance(req.delta_lpm)
    return {"status": "ok", "base_flow_lpm": round(new_flow, 2)}


@router.post("/api/system/action")
async def execute_system_action(req: GlobalActionRequest, rt: Runtime = Depends(get_runtime)):
    act = req.action.upper()
    if act == "PAUSE":
        rt.process.running = False
    elif act == "RESUME":
        rt.process.running = True
    elif act == "RESET":
        rt.process.reset_simulation()
    elif act == "ALL_AUTO":
        for cfg in rt.process.configs.values():
            cfg.mode = "AUTO"
    elif act == "ALL_FF_ON":
        for cfg in rt.process.configs.values():
            cfg.ff_enabled = True
    elif act == "ALL_FF_OFF":
        for cfg in rt.process.configs.values():
            cfg.ff_enabled = False
    else:
        raise HTTPException(status_code=400, detail=f"Acción desconocida: {act}")
    return {"status": "ok", "telemetry": rt.telemetry()}


@router.get("/api/alarms")
async def get_alarms(rt: Runtime = Depends(get_runtime)):
    return {
        "active": [a for a in rt.process.alarm_history if a.active],
        "history": rt.process.alarm_history[:40],
        "unacked": rt.process.unacked_count(),
    }


@router.post("/api/alarms/ack", response_model=AlarmAckResponse)
async def acknowledge_alarms(req: AlarmAckRequest, rt: Runtime = Depends(get_runtime)):
    n = rt.process.acknowledge_alarms(req.cell_id)
    return AlarmAckResponse(
        acknowledged=n,
        remaining_unacked=rt.process.unacked_count(),
        telemetry=rt.telemetry(),
    )
