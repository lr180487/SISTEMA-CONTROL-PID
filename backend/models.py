from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class CellConfig(BaseModel):
    cell_id: str = Field(..., description="Identificador de celda: C1, C2, C3")
    sp: float = Field(320.0, ge=150.0, le=430.0, description="Setpoint de nivel de pulpa [mm]")
    mode: Literal["AUTO", "MANUAL"] = Field("AUTO", description="Modo de operación del lazo")
    ff_enabled: bool = Field(True, description="Habilitación de compensación Feedforward")
    manual_rpm: float = Field(150.0, ge=0.0, le=350.0, description="RPM manual de la bomba peristáltica")
    kp: float = Field(-6.5, ge=-50.0, le=50.0, description="Ganancia proporcional Kp [RPM/mm]")
    ki: float = Field(-0.55, ge=-15.0, le=15.0, description="Ganancia integral Ki [RPM/(mm·s)]")
    kff: float = Field(1.0, ge=0.0, le=3.0, description="Ganancia Feedforward adimensional Kff")
    alarm_high: float = Field(390.0, ge=200.0, le=445.0, description="Umbral alarma nivel alto HH/H [mm]")
    alarm_low: float = Field(230.0, ge=80.0, le=380.0, description="Umbral alarma nivel bajo LL/L [mm]")


class CellUpdateRequest(BaseModel):
    sp: Optional[float] = Field(None, ge=150.0, le=430.0)
    mode: Optional[Literal["AUTO", "MANUAL"]] = None
    ff_enabled: Optional[bool] = None
    manual_rpm: Optional[float] = Field(None, ge=0.0, le=350.0)
    kp: Optional[float] = Field(None, ge=-50.0, le=50.0)
    ki: Optional[float] = Field(None, ge=-15.0, le=15.0)
    kff: Optional[float] = Field(None, ge=0.0, le=3.0)
    alarm_high: Optional[float] = Field(None, ge=200.0, le=445.0)
    alarm_low: Optional[float] = Field(None, ge=80.0, le=380.0)


class FeedSimulationConfig(BaseModel):
    base_flow_lpm: float = Field(22.0, ge=5.0, le=45.0, description="Caudal de alimentación nominal Q_feed [L/min]")
    profile: Literal["CONSTANT", "STEP_QUINTANILLA", "PULSE", "SINE", "NOISY_RAMP"] = Field(
        "CONSTANT", description="Perfil dinámico de perturbación de alimentación"
    )
    noise_std: float = Field(0.18, ge=0.0, le=2.5, description="Ruido de medición de sensores")
    air_flow_lpm: float = Field(45.0, ge=10.0, le=90.0, description="Caudal de aireación Jg [L/min]")


class OPCUAConnectionConfig(BaseModel):
    endpoint: str = Field(
        "opc.tcp://192.168.0.10:4840",
        description="Endpoint del servidor OPC UA del S7-1200 (puerto habitual 4840)",
    )
    security_policy: Literal["None", "Basic256Sha256"] = Field(
        "None", description="Política de seguridad de la sesión OPC UA"
    )
    username: Optional[str] = Field("", description="Usuario (vacío = sesión anónima)")
    password: Optional[str] = Field("", description="Contraseña (no se registra en el histórico)")
    namespace_index: int = Field(3, ge=1, le=20, description="Namespace del DB del PLC en TIA Portal (habitual ns=3)")
    poll_ms: int = Field(500, ge=100, le=5000, description="Periodo de lectura de nodos [ms]")
    timeout_s: float = Field(4.0, ge=1.0, le=30.0, description="Timeout de sesión [s]")
    active: bool = Field(True, description="Canal OPC UA habilitado")


class PLCConnectionConfig(BaseModel):
    ip: str = Field("192.168.0.10", description="Dirección IP del PLC Siemens S7-1200")
    rack: int = Field(0, ge=0, le=7, description="Rack S7-1200 (por defecto 0)")
    slot: int = Field(1, ge=0, le=7, description="Slot CPU S7-1200 (por defecto 1)")
    db_number: int = Field(100, ge=1, le=9999, description="Número de Data Block DB de intercambio")
    mode: Literal["SIMULATION", "PLC_S7_1200", "OPC_UA"] = Field(
        "SIMULATION", description="Fuente de datos / actuación: simulación, Snap7 o OPC UA"
    )
    poll_ms: int = Field(500, ge=100, le=5000, description="Ciclo de muestreo Snap7 [ms]")


class CellRuntimeState(BaseModel):
    cell_id: str
    name: str
    pv: float
    sp: float
    error: float
    mode: str
    ff_enabled: bool
    rpm: float
    rpm_pi: float
    rpm_ff: float
    q_in_lpm: float
    q_out_lpm: float
    q_conc_lpm: float
    froth_depth_mm: float
    kp: float
    ki: float
    kff: float
    alarm_high: float
    alarm_low: float
    alarm_status: Literal["NORMAL", "HIGH", "LOW", "HH_CRITICAL", "LL_CRITICAL"]
    iae: float


class AlarmEvent(BaseModel):
    id: int
    timestamp: str
    cell_id: str
    severity: Literal["WARNING", "CRITICAL", "INFO"]
    type: str
    message: str
    value: float
    threshold: float
    active: bool
    acked: bool = Field(False, description="Alarma reconocida por el operador (ACK)")


class CommStatus(BaseModel):
    """Estado consolidado de los canales industriales (fuente activa + diagnósticos)."""
    active_source: Literal["SIMULATION", "PLC_S7_1200", "OPC_UA"]
    opcua_connected: bool
    opcua_endpoint: str
    opcua_latency_ms: Optional[float] = None
    opcua_nodes_ok: int = 0
    opcua_nodes_total: int = 0
    opcua_last_poll: Optional[str] = None
    opcua_error: Optional[str] = None
    snap7_connected: bool = False
    snap7_ip: str = ""


class SystemTelemetry(BaseModel):
    timestamp: str
    elapsed_sec: float
    q_feed_lpm: float
    q_feed_set_lpm: float
    feed_profile: str
    air_flow_lpm: float
    simulation_running: bool
    plc_connected: bool
    plc_mode: str
    plc_ip: str
    cells: Dict[str, CellRuntimeState]
    active_alarms: List[AlarmEvent]
    comm: Optional[CommStatus] = None


# ============================================================================
# CONTRATO COMPARTIDO BACKEND <-> FRONTEND  (versión de esquema)
# Cualquier cambio incompatible en estos modelos debe incrementar SCHEMA_VERSION
# y regenerar frontend/js/contract.generated.js con tools/sync_contract.py
# ============================================================================
SCHEMA_VERSION = "1.2.0"


class HealthStatus(BaseModel):
    status: Literal["ok", "degraded"] = "ok"
    app_version: str
    schema_version: str
    uptime_sec: float
    server_time: str
    simulation_running: bool
    simulation_hz: float
    ws_clients: int
    historian_rows: int
    plc_mode: str
    plc_connected: bool
    opcua_connected: bool = False
    opcua_endpoint: str = ""
    data_source: str = "SIMULATION"


class CalibrationInfo(BaseModel):
    alpha: float = Field(..., description="L/(min·RPM)")
    beta: float = Field(..., description="L/min")
    rpm_min: float
    rpm_max: float
    max_flow_lpm: float


class ConfigSnapshot(BaseModel):
    """Estado completo de configuración para hidratar el frontend al recargar."""
    schema_version: str
    feed: FeedSimulationConfig
    cells: Dict[str, CellConfig]
    plc: PLCConnectionConfig
    opcua: OPCUAConnectionConfig
    calibration: CalibrationInfo
    profiles: List[str]
    cell_level_max_mm: float
    limits: Dict[str, List[float]]


class ConfigUpdateRequest(BaseModel):
    """Actualización masiva y atómica de configuración (celdas + alimentación)."""
    cells: Optional[Dict[Literal["C1", "C2", "C3"], CellUpdateRequest]] = None
    feed: Optional[FeedSimulationConfig] = None


class ConfigUpdateResponse(BaseModel):
    status: str = "ok"
    applied_cells: List[str] = Field(default_factory=list)
    feed_applied: bool = False
    warnings: List[str] = Field(default_factory=list)
    config: ConfigSnapshot


class AlarmAckRequest(BaseModel):
    cell_id: Optional[Literal["C1", "C2", "C3"]] = Field(
        None, description="Celda a reconocer; None reconoce todas las alarmas activas"
    )


class AlarmAckResponse(BaseModel):
    status: str = "ok"
    acknowledged: int
    remaining_unacked: int
    telemetry: SystemTelemetry
