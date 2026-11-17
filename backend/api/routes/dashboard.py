"""Entrega de la aplicación frontend."""
from fastapi import APIRouter
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from ...settings import settings

router = APIRouter(tags=["dashboard"])


@router.get("/", include_in_schema=False)
async def serve_dashboard():
    return FileResponse(str(settings.frontend_dir / "index.html"))
