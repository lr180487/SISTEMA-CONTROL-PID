"""Endpoints OPC UA y servidor OPC UA de prueba local."""
from fastapi import APIRouter, Depends, HTTPException
from ...core.runtime import Runtime
from ...models import OPCUAConnectionConfig
from ...opcua_client import ASYNCUA_AVAILABLE, DB_NAME, OPCUA_TAG_MAP, node_identifier
from ..dependencies import get_runtime
from ..schemas import OPCUATestServerRequest

router = APIRouter(tags=["opcua"])

INIT_VALUES = {
    "Q_Feed_LPM": 22.0,
    "C1_PV_mm": 330.0, "C1_SP_mm": 330.0, "C1_Pump_RPM": 171.0, "C1_Kp": -6.8, "C1_Ki": -0.62, "C1_Kff": 1.0,
    "C2_PV_mm": 320.0, "C2_SP_mm": 320.0, "C2_Pump_RPM": 166.0, "C2_Kp": -6.5, "C2_Ki": -0.58, "C2_Kff": 1.0,
    "C3_PV_mm": 310.0, "C3_SP_mm": 310.0, "C3_Pump_RPM": 161.0, "C3_Kp": -6.2, "C3_Ki": -0.55, "C3_Kff": 1.0,
}


@router.get("/api/opcua/status")
async def get_opcua_status(rt: Runtime = Depends(get_runtime)):
    return rt.opcua_client.get_status()


@router.post("/api/opcua/config")
async def update_opcua_config(cfg: OPCUAConnectionConfig, rt: Runtime = Depends(get_runtime)):
    return rt.opcua_client.update_config(cfg)


@router.post("/api/opcua/connect")
async def connect_opcua(cfg: OPCUAConnectionConfig, rt: Runtime = Depends(get_runtime)):
    rt.opcua_client.update_config(cfg)
    status = await rt.opcua_client.connect()
    if status.get("connected"):
        rt.plc_client.config.mode = "OPC_UA"
        status["last_error"] = f"Conectado a {cfg.endpoint} · {status.get('nodes_ok')}/{status.get('nodes_total')} nodos OK"
    return status


@router.post("/api/opcua/disconnect")
async def disconnect_opcua(rt: Runtime = Depends(get_runtime)):
    status = await rt.opcua_client.disconnect()
    if rt.plc_client.config.mode == "OPC_UA":
        rt.plc_client.config.mode = "SIMULATION"
    return status


@router.get("/api/opcua/tags")
async def get_opcua_tags(rt: Runtime = Depends(get_runtime)):
    return {
        "namespace_index": rt.opcua_client.config.namespace_index,
        "nodes_total": rt.opcua_client.nodes_total,
        "nodes_ok": rt.opcua_client.nodes_ok,
        "connected": rt.opcua_client.connected,
        "tags": rt.opcua_client.get_status()["tag_map"],
    }


@router.get("/api/opcua/browse")
async def browse_opcua(rt: Runtime = Depends(get_runtime)):
    if not rt.opcua_client.connected:
        return {"connected": False, "nodes": [], "detail": rt.opcua_client.last_error}
    return {"connected": True, "nodes": await rt.opcua_client.browse()}


@router.post("/api/opcua/write")
async def write_opcua_tag(payload: dict, rt: Runtime = Depends(get_runtime)):
    if not rt.control_writes_enabled:
        raise HTTPException(status_code=403, detail="Escrituras de control deshabilitadas. Configure SCADA_ENABLE_CONTROL_WRITES=true tras asegurar la red y permisos.")
    tag, value = payload.get("tag", ""), payload.get("value")
    if value is None or not tag:
        raise HTTPException(status_code=400, detail="Debe indicar 'tag' y 'value'")
    result = await rt.opcua_client.write_tag(tag, value)
    if result.get("status") != "ok":
        raise HTTPException(status_code=400, detail=result.get("detail", "Error de escritura OPC UA"))
    return result


@router.post("/api/opcua/test-server/start")
async def start_opcua_test_server(req: OPCUATestServerRequest, rt: Runtime = Depends(get_runtime)):
    if rt.opcua_test_server is not None:
        raise HTTPException(status_code=409, detail="El servidor OPC UA de prueba ya está iniciado")
    if not rt.asyncua_available:
        raise HTTPException(status_code=503, detail="asyncua no instalado")
    try:
        from asyncua import Server, ua
        server = Server()
        await server.init()
        server.set_endpoint(f"opc.tcp://127.0.0.1:{req.port}")
        idx = await server.register_namespace(req.namespace_uri)
        db = await server.nodes.objects.add_object(idx, DB_NAME)
        for item in OPCUA_TAG_MAP:
            nodeid = ua.NodeId(node_identifier(item["tag"], "TIA"), idx)
            if item["type"] == "Bool":
                variable = await db.add_variable(nodeid, item["tag"], True, varianttype=ua.VariantType.Boolean)
            else:
                variable = await db.add_variable(nodeid, item["tag"], INIT_VALUES.get(item["tag"], 0.0), varianttype=ua.VariantType.Float)
            if "W" in item["rw"]:
                await variable.set_writable()
        await server.start()
        rt.opcua_test_server = server
        rt.opcua_test_endpoint = f"opc.tcp://127.0.0.1:{req.port}"
        return {"status": "ok", "endpoint": rt.opcua_test_endpoint,
                "namespace_index": idx, "variables": len(OPCUA_TAG_MAP),
                "detail": "Servidor OPC UA de prueba activo con el DB100_FlotationSCADA"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo iniciar el servidor OPC UA de prueba: {exc}") from exc


@router.post("/api/opcua/test-server/stop")
async def stop_opcua_test_server(rt: Runtime = Depends(get_runtime)):
    if rt.opcua_test_server is not None:
        try:
            await rt.opcua_test_server.stop()
        finally:
            rt.opcua_test_server = None
            rt.opcua_test_endpoint = None
    return {"status": "stopped"}


@router.get("/api/opcua/test-server/status")
async def opcua_test_server_status(rt: Runtime = Depends(get_runtime)):
    return {"running": rt.opcua_test_server is not None, "endpoint": rt.opcua_test_endpoint}
