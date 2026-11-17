"""Consulta, borrado y exportación del histórico."""
from fastapi import APIRouter, Depends, Response
from ...core.runtime import Runtime
from ..dependencies import get_runtime

router = APIRouter(tags=["historian"])


@router.get("/api/historian/recent")
async def get_recent_historian(limit: int = 40, rt: Runtime = Depends(get_runtime)):
    return {"total_records": rt.historian.get_count(),
            "rows": rt.historian.get_recent_rows(limit=min(200, max(5, limit)))}


@router.delete("/api/historian")
async def clear_historian(rt: Runtime = Depends(get_runtime)):
    rt.historian.clear_history()
    return {"status": "cleared", "total_records": 0}


@router.get("/api/historian/export.csv")
async def export_historian_csv(rt: Runtime = Depends(get_runtime)):
    headers = {"Content-Disposition": 'attachment; filename="flotation_PI_FF_historian.csv"'}
    return Response(content=rt.historian.export_csv_string(limit=10000),
                    media_type="text/csv; charset=utf-8", headers=headers)
