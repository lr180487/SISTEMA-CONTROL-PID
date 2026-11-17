"""Dependencias compartidas para HTTP y WebSocket."""
from fastapi import HTTPException
from starlette.requests import HTTPConnection

from ..core.runtime import Runtime


def get_runtime(connection: HTTPConnection) -> Runtime:
    """Obtiene Runtime desde app.state en endpoints HTTP y WebSocket."""
    runtime = getattr(connection.app.state, "runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="Runtime SCADA no inicializado")
    return runtime
