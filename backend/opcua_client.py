"""
Cliente OPC UA industrial para el SCADA de flotación (Siemens S7-1200).

Cadena de comunicación (según diagrama de arquitectura):

    Dashboard HTML  ──►  API Python FastAPI  ──►  OPC UA (Ethernet/PROFINET, puerto 4840)  ──►  PLC S7-1200

El PLC expone su **servidor OPC UA** (TIA Portal: CPU 1214C/1215C FW ≥ V4.4, "OPC UA server"
habilitado, bloques de datos con acceso no optimizado) y este módulo actúa como **cliente**:

  · Lectura cíclica de nivel (PV), caudal de alimentación y velocidad real de bombas.
  · Escritura de consigna (SP), ganancias Kp/Ki/Kff, umbrales de alarma, modo AUTO/MANUAL,
    habilitación de Feedforward y consigna de RPM de cada bomba peristáltica.
  · Exploración (browse) del árbol de nodos del DB100 para verificar el mapa de tags.

Los NodeIds siguen la convención de TIA Portal:  ns=3;s="DB100_FlotationSCADA"."C1_PV_mm"
"""

from __future__ import annotations

import asyncio
import math
import socket
import time
from urllib.parse import urlsplit
from typing import Any, Dict, List, Optional

try:
    from asyncua import Client, ua
    ASYNCUA_AVAILABLE = True
except Exception:  # pragma: no cover
    Client = None  # type: ignore
    ua = None  # type: ignore
    ASYNCUA_AVAILABLE = False

from .models import OPCUAConnectionConfig

DB_NAME = "DB100_FlotationSCADA"

# Mapa de nodos: tag lógico ↔ identificador dentro del DB ↔ dirección S7 equivalente
OPCUA_TAG_MAP: List[Dict[str, Any]] = [
    {"tag": "Q_Feed_LPM",  "node": f'"{DB_NAME}"."Q_Feed_LPM"',  "db": "DB100.DBD0",  "type": "Float", "rw": "R",  "desc": "Caudal de alimentación medido [L/min]"},
    {"tag": "C1_PV_mm",    "node": f'"{DB_NAME}"."C1_PV_mm"',    "db": "DB100.DBD4",  "type": "Float", "rw": "R",  "desc": "Nivel de pulpa C-1 [mm]"},
    {"tag": "C1_SP_mm",    "node": f'"{DB_NAME}"."C1_SP_mm"',    "db": "DB100.DBD8",  "type": "Float", "rw": "RW", "desc": "Setpoint C-1 [mm]"},
    {"tag": "C1_Pump_RPM", "node": f'"{DB_NAME}"."C1_Pump_RPM"', "db": "DB100.DBD12", "type": "Float", "rw": "RW", "desc": "Consigna de velocidad bomba B-1 (SP) [RPM]"},
    {"tag": "C1_Kp",       "node": f'"{DB_NAME}"."C1_Kp"',       "db": "DB100.DBD16", "type": "Float", "rw": "RW", "desc": "Kp C-1 [RPM/mm]"},
    {"tag": "C1_Ki",       "node": f'"{DB_NAME}"."C1_Ki"',       "db": "DB100.DBD20", "type": "Float", "rw": "RW", "desc": "Ki C-1 [RPM/(mm·s)]"},
    {"tag": "C1_Kff",      "node": f'"{DB_NAME}"."C1_Kff"',      "db": "DB100.DBD24", "type": "Float", "rw": "RW", "desc": "Kff C-1 [–]"},
    {"tag": "C2_PV_mm",    "node": f'"{DB_NAME}"."C2_PV_mm"',    "db": "DB100.DBD28", "type": "Float", "rw": "R",  "desc": "Nivel de pulpa C-2 [mm]"},
    {"tag": "C2_SP_mm",    "node": f'"{DB_NAME}"."C2_SP_mm"',    "db": "DB100.DBD32", "type": "Float", "rw": "RW", "desc": "Setpoint C-2 [mm]"},
    {"tag": "C2_Pump_RPM", "node": f'"{DB_NAME}"."C2_Pump_RPM"', "db": "DB100.DBD36", "type": "Float", "rw": "RW", "desc": "Consigna de velocidad bomba B-2 (SP) [RPM]"},
    {"tag": "C2_Kp",       "node": f'"{DB_NAME}"."C2_Kp"',       "db": "DB100.DBD40", "type": "Float", "rw": "RW", "desc": "Kp C-2 [RPM/mm]"},
    {"tag": "C2_Ki",       "node": f'"{DB_NAME}"."C2_Ki"',       "db": "DB100.DBD44", "type": "Float", "rw": "RW", "desc": "Ki C-2 [RPM/(mm·s)]"},
    {"tag": "C2_Kff",      "node": f'"{DB_NAME}"."C2_Kff"',      "db": "DB100.DBD48", "type": "Float", "rw": "RW", "desc": "Kff C-2 [–]"},
    {"tag": "C3_PV_mm",    "node": f'"{DB_NAME}"."C3_PV_mm"',    "db": "DB100.DBD52", "type": "Float", "rw": "R",  "desc": "Nivel de pulpa C-3 [mm]"},
    {"tag": "C3_SP_mm",    "node": f'"{DB_NAME}"."C3_SP_mm"',    "db": "DB100.DBD56", "type": "Float", "rw": "RW", "desc": "Setpoint C-3 [mm]"},
    {"tag": "C3_Pump_RPM", "node": f'"{DB_NAME}"."C3_Pump_RPM"', "db": "DB100.DBD60", "type": "Float", "rw": "RW", "desc": "Consigna de velocidad bomba B-3 (SP) [RPM]"},
    {"tag": "C3_Kp",       "node": f'"{DB_NAME}"."C3_Kp"',       "db": "DB100.DBD64", "type": "Float", "rw": "RW", "desc": "Kp C-3 [RPM/mm]"},
    {"tag": "C3_Ki",       "node": f'"{DB_NAME}"."C3_Ki"',       "db": "DB100.DBD68", "type": "Float", "rw": "RW", "desc": "Ki C-3 [RPM/(mm·s)]"},
    {"tag": "C3_Kff",      "node": f'"{DB_NAME}"."C3_Kff"',      "db": "DB100.DBD72", "type": "Float", "rw": "RW", "desc": "Kff C-3 [–]"},
    {"tag": "C1_AutoMode", "node": f'"{DB_NAME}"."C1_AutoMode"', "db": "DB100.DBX76.0", "type": "Bool", "rw": "RW", "desc": "C-1 AUTO(1)/MANUAL(0)"},
    {"tag": "C1_FF_Enable","node": f'"{DB_NAME}"."C1_FF_Enable"',"db": "DB100.DBX76.1", "type": "Bool", "rw": "RW", "desc": "C-1 Feedforward habilitado"},
    {"tag": "C2_AutoMode", "node": f'"{DB_NAME}"."C2_AutoMode"', "db": "DB100.DBX76.2", "type": "Bool", "rw": "RW", "desc": "C-2 AUTO(1)/MANUAL(0)"},
    {"tag": "C2_FF_Enable","node": f'"{DB_NAME}"."C2_FF_Enable"',"db": "DB100.DBX76.3", "type": "Bool", "rw": "RW", "desc": "C-2 Feedforward habilitado"},
    {"tag": "C3_AutoMode", "node": f'"{DB_NAME}"."C3_AutoMode"', "db": "DB100.DBX76.4", "type": "Bool", "rw": "RW", "desc": "C-3 AUTO(1)/MANUAL(0)"},
    {"tag": "C3_FF_Enable","node": f'"{DB_NAME}"."C3_FF_Enable"',"db": "DB100.DBX76.5", "type": "Bool", "rw": "RW", "desc": "C-3 Feedforward habilitado"},
    {"tag": "C1_Pump_RPM_PV", "node": f'"{DB_NAME}"."C1_Pump_RPM_PV"', "db": "DB100.DBD80", "type": "Float", "rw": "R", "desc": "Velocidad real bomba B-1 [RPM]"},
    {"tag": "C2_Pump_RPM_PV", "node": f'"{DB_NAME}"."C2_Pump_RPM_PV"', "db": "DB100.DBD84", "type": "Float", "rw": "R", "desc": "Velocidad real bomba B-2 [RPM]"},
    {"tag": "C3_Pump_RPM_PV", "node": f'"{DB_NAME}"."C3_Pump_RPM_PV"', "db": "DB100.DBD88", "type": "Float", "rw": "R", "desc": "Velocidad real bomba B-3 [RPM]"},
    {"tag": "C1_Output_RPM", "node": f'"{DB_NAME}"."C1_Output_RPM"', "db": "DB100.DBD92", "type": "Float", "rw": "R", "desc": "Salida calculada B-1 [RPM]"},
    {"tag": "C2_Output_RPM", "node": f'"{DB_NAME}"."C2_Output_RPM"', "db": "DB100.DBD96", "type": "Float", "rw": "R", "desc": "Salida calculada B-2 [RPM]"},
    {"tag": "C3_Output_RPM", "node": f'"{DB_NAME}"."C3_Output_RPM"', "db": "DB100.DBD100", "type": "Float", "rw": "R", "desc": "Salida calculada B-3 [RPM]"},
    {"tag": "PLC_CycleCounter", "node": f'"{DB_NAME}"."PLC_CycleCounter"', "db": "DB100.DBD104", "type": "UInt32", "rw": "R", "desc": "Contador de ciclo PLC"},
    {"tag": "PLC_Heartbeat", "node": f'"{DB_NAME}"."PLC_Heartbeat"', "db": "DB100.DBX108.0", "type": "Bool", "rw": "R", "desc": "Heartbeat PLC"},
    {"tag": "PLC_DataValid", "node": f'"{DB_NAME}"."PLC_DataValid"', "db": "DB100.DBX108.1", "type": "Bool", "rw": "R", "desc": "Calidad de datos PLC"},
    {"tag": "PLC_Fault", "node": f'"{DB_NAME}"."PLC_Fault"', "db": "DB100.DBX108.2", "type": "Bool", "rw": "R", "desc": "Fallo PLC"},
    {"tag": "DB_Version", "node": f'"{DB_NAME}"."DB_Version"', "db": "DB100.DBD112", "type": "UInt32", "rw": "R", "desc": "Versión DB100 = 2"},
    {"tag": "C1_Output_AQ", "node": f'"{DB_NAME}"."C1_Output_AQ"', "db": "DB100.DBW116", "type": "Int16", "rw": "R", "desc": "Salida analógica escalada C-1 [0..27648]"},
    {"tag": "C2_Output_AQ", "node": f'"{DB_NAME}"."C2_Output_AQ"', "db": "DB100.DBW118", "type": "Int16", "rw": "R", "desc": "Salida analógica escalada C-2 [0..27648]"},
    {"tag": "C3_Output_AQ", "node": f'"{DB_NAME}"."C3_Output_AQ"', "db": "DB100.DBW120", "type": "Int16", "rw": "R", "desc": "Salida analógica escalada C-3 [0..27648]"},
]

READ_TAGS = [t for t in OPCUA_TAG_MAP if t["rw"] in ("R", "RW")]
WRITE_TAGS = {t["tag"] for t in OPCUA_TAG_MAP if "W" in t["rw"]}


# Estilos de NodeId admitidos
#   TIA  -> ns=3;s="DB100_FlotationSCADA"."C1_PV_mm"   (S7-1200 real con TIA Portal)
#   FLAT -> ns=2;s=C1_PV_mm                            (servidor de prueba / tags planos)
#   OBJ  -> ns=2;s=DB100_FlotationSCADA.C1_PV_mm
NODE_STYLES = ("TIA", "OBJ", "FLAT")


def node_identifier(tag: str, style: str) -> str:
    if style == "TIA":
        return f'"{DB_NAME}"."{tag}"'
    if style == "OBJ":
        return f"{DB_NAME}.{tag}"
    return tag


class SiemensOPCUAClient:
    """Cliente OPC UA asíncrono con reconexión, latencia y diagnóstico de nodos."""

    def __init__(self) -> None:
        self.config = OPCUAConnectionConfig()
        self.client: Optional["Client"] = None
        self.connected: bool = False
        self.last_error: str = "Cliente OPC UA no inicializado"
        self.last_latency_ms: Optional[float] = None
        self.last_read: Dict[str, Any] = {}
        self.nodes_ok: int = 0
        self.nodes_total: int = len(OPCUA_TAG_MAP)
        self.last_poll_at: Optional[str] = None
        self.namespace_resolved: bool = False
        self.node_style: str = "TIA"
        self._node_map: Dict[str, Any] = {}   # tag -> NodeId descubierto por browse
        self.namespace_uris: List[str] = []
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Configuración y estado
    # ------------------------------------------------------------------ #
    def update_config(self, cfg: OPCUAConnectionConfig) -> Dict[str, Any]:
        self.config = cfg
        if not cfg.active and self.connected:
            self.last_error = "Canal OPC UA deshabilitado por configuración"
        return self.get_status()

    def get_status(self) -> Dict[str, Any]:
        return {
            "endpoint": self.config.endpoint,
            "security_policy": self.config.security_policy,
            "username": self.config.username,
            "namespace_index": self.config.namespace_index,
            "namespace_resolved": getattr(self, "namespace_resolved", False),
            "node_style": self.node_style,
            "namespaces": getattr(self, "namespace_uris", []),
            "poll_ms": self.config.poll_ms,
            "active": self.config.active,
            "connected": self.connected,
            "library_available": ASYNCUA_AVAILABLE,
            "last_error": self.last_error,
            "latency_ms": None if self.last_latency_ms is None else round(self.last_latency_ms, 2),
            "nodes_ok": self.nodes_ok,
            "nodes_total": self.nodes_total,
            "last_poll_at": self.last_poll_at,
            "values": {k: round(v, 3) if isinstance(v, float) else v for k, v in self.last_read.items()},
            "tag_map": [
                {
                    "tag": t["tag"],
                    "node_id": (
                        self._node_map[t["tag"]].to_string()
                        if self.node_style == "BROWSE" and t["tag"] in self._node_map
                        else f'ns={self.config.namespace_index};s={node_identifier(t["tag"], self.node_style)}'
                    ),
                    "db": t["db"],
                    "type": t["type"],
                    "rw": t["rw"],
                    "desc": t["desc"],
                    "value": self.last_read.get(t["tag"]),
                }
                for t in OPCUA_TAG_MAP
            ],
        }

    # ------------------------------------------------------------------ #
    # Conexión
    # ------------------------------------------------------------------ #
    def _tcp_precheck(self) -> tuple[bool, str]:
        """Verifica alcance del puerto 4840 antes de abrir la sesión OPC UA."""
        host, port = self._parse_endpoint(self.config.endpoint)
        try:
            with socket.create_connection((host, port), timeout=1.5):
                return True, f"Puerto {port} alcanzable en {host}"
        except OSError as exc:
            return False, f"Sin respuesta OPC UA en {host}:{port}. {exc}"

    @staticmethod
    def _parse_endpoint(endpoint: str) -> tuple[str, int]:
        parsed = urlsplit(endpoint)
        if parsed.scheme != "opc.tcp" or not parsed.hostname:
            raise ValueError("Endpoint OPC UA inválido; se requiere opc.tcp://host:puerto")
        port = parsed.port or 4840
        if not 1 <= port <= 65535:
            raise ValueError("Puerto OPC UA fuera de rango")
        return parsed.hostname, port

    def _node_id(self, identifier: str):
        return ua.NodeId(identifier, self.config.namespace_index)

    async def connect(self) -> Dict[str, Any]:
        if not ASYNCUA_AVAILABLE:
            self.last_error = "Librería asyncua no instalada (pip install asyncua)"
            return self.get_status()

        try:
            ok, msg = self._tcp_precheck()
        except (ValueError, OSError) as exc:
            self.connected = False
            self.last_error = f"Endpoint OPC UA inválido: {exc}"
            return self.get_status()
        if not ok:
            self.connected = False
            self.last_error = msg
            return self.get_status()

        # Desconectar fuera del lock: disconnect() adquiere el mismo lock.
        if self.client is not None:
            await self.disconnect()
        async with self._lock:
            try:
                client = Client(url=self.config.endpoint, timeout=self.config.timeout_s)
                if self.config.username:
                    client.set_user(self.config.username)
                    client.set_password(self.config.password)
                # Políticas con firma/cifrado requieren certificados X.509 intercambiados
                if self.config.security_policy != "None":
                    await client.set_security_string(
                        f"{self.config.security_policy},"
                        f"certificate:data/certs/scada_client_cert.der,"
                        f"private_key:data/certs/scada_client_key.pem,"
                        f"mode:SignAndEncrypt"
                    )
                await asyncio.wait_for(client.connect(), timeout=self.config.timeout_s)
                self.client = client
                self.connected = True
                # Resolver automáticamente el namespace y el estilo de NodeId
                await self._resolve_namespace()
                await self._detect_node_style()
                self.last_error = f"Conectado al servidor OPC UA {self.config.endpoint}"
                # Primera lectura completa obligatoria antes de declarar el canal listo.
                await self.read_all()
                if self.nodes_ok != len(READ_TAGS):
                    raise RuntimeError(
                        f"Mapa OPC UA incompleto: {self.nodes_ok}/{len(READ_TAGS)} nodos legibles"
                    )
            except asyncio.TimeoutError:
                self.connected = False
                self.last_error = f"Timeout de sesión OPC UA ({self.config.timeout_s} s) contra {self.config.endpoint}"
                if self.client is not None:
                    try:
                        await self.client.disconnect()
                    except Exception:
                        pass
                    self.client = None
            except Exception as exc:
                self.connected = False
                self.last_error = f"Error al abrir sesión OPC UA: {exc}"
                if self.client is not None:
                    try:
                        await self.client.disconnect()
                    except Exception:
                        pass
                    self.client = None
            return self.get_status()

    async def disconnect(self) -> Dict[str, Any]:
        async with self._lock:
            if self.client is not None:
                try:
                    await self.client.disconnect()
                except Exception:
                    pass
            self.client = None
            self.connected = False
            self.nodes_ok = 0
            self.last_latency_ms = None
            self.last_error = "Desconectado del servidor OPC UA"
        return self.get_status()

    async def _resolve_namespace(self) -> None:
        """Lee el NamespaceArray del servidor y ajusta el índice del DB.

        En un S7-1200 real el DB de usuario suele estar en ns=3; el servidor de
        prueba local lo registra en un índice distinto. Si se detecta un namespace
        propio del SCADA se usa ese índice; si no, se respeta el configurado.
        """
        if self.client is None:
            return
        try:
            ns_array = await asyncio.wait_for(
                self.client.get_node("ns=0;i=2255").read_value(), timeout=3.0
            )
            uris = list(ns_array) if ns_array else []
            for i, uri in enumerate(uris):
                if "flotation" in str(uri).lower():
                    self.config.namespace_index = i
                    self.namespace_resolved = True
                    self.namespace_uris = [str(u) for u in uris]
                    return
            self.namespace_uris = [str(u) for u in uris]
        except Exception:
            pass

    async def _detect_node_style(self) -> None:
        """Determina el esquema de NodeId del servidor: TIA, objeto, plano o descubierto por browse."""
        if self.client is None:
            return
        sonda = READ_TAGS[0]["tag"]
        for style in NODE_STYLES:
            try:
                node = self.client.get_node(ua.NodeId(node_identifier(sonda, style), self.config.namespace_index))
                await asyncio.wait_for(node.read_value(), timeout=2.0)
                self.node_style = style
                self._node_map = {}
                return
            except Exception:
                continue

        # Respaldo: descubrir los NodeId reales recorriendo el objeto del DB
        self._node_map = await self._browse_node_map()
        self.node_style = "BROWSE" if self._node_map else "TIA"

    async def _browse_node_map(self) -> Dict[str, Any]:
        """Construye {tag: NodeId} recorriendo el objeto DB del PLC (cualquier esquema de NodeId)."""
        mapa: Dict[str, Any] = {}
        if self.client is None:
            return mapa
        try:
            for child in await self.client.nodes.objects.get_children():
                nombre = (await child.read_browse_name()).Name
                if DB_NAME.lower() not in nombre.lower():
                    continue
                for var in await child.get_children():
                    vname = (await var.read_browse_name()).Name
                    if any(vname == t["tag"] for t in OPCUA_TAG_MAP):
                        mapa[vname] = var.nodeid
        except Exception:
            pass
        return mapa

    def _resolve_node(self, tag: str):
        """Devuelve el NodeId efectivo de un tag según el esquema detectado."""
        if self.node_style == "BROWSE" and tag in self._node_map:
            return self._node_map[tag]
        return ua.NodeId(node_identifier(tag, self.node_style), self.config.namespace_index)

    # ------------------------------------------------------------------ #
    # Lectura / escritura
    # ------------------------------------------------------------------ #
    async def read_all(self) -> Dict[str, Any]:
        """Lectura masiva de tags; devuelve {tag: valor} y actualiza el diagnóstico."""
        if not self.connected or self.client is None:
            return {}

        t0 = time.perf_counter()
        values: Dict[str, Any] = {}
        ok = 0
        error: Optional[str] = None
        try:
            for item in READ_TAGS:
                node = self.client.get_node(self._resolve_node(item["tag"]))
                try:
                    val = await asyncio.wait_for(node.read_value(), timeout=2.0)
                    values[item["tag"]] = val
                    ok += 1
                except Exception as exc:
                    error = f"{item['tag']}: {exc}"
        except Exception as exc:
            error = str(exc)
            self.connected = False

        self.last_latency_ms = (time.perf_counter() - t0) * 1000.0
        self.nodes_ok = ok
        self.nodes_total = len(READ_TAGS)
        if ok != len(READ_TAGS):
            self.last_error = f"Lectura incompleta ({ok}/{len(READ_TAGS)} nodos); muestra descartada. {error or ''}"
            return {}
        self.last_read = values
        self.last_poll_at = time.strftime("%H:%M:%S")
        self.last_error = f"Lectura correcta de {ok} nodos OPC UA"
        return values

    async def write_tag(self, tag: str, value: Any) -> Dict[str, Any]:
        """Escribe únicamente tags permitidos y valores dentro de límites."""
        if not self.connected or self.client is None:
            self.last_error = "Escritura rechazada: sin sesión OPC UA activa"
            return {"status": "error", "detail": self.last_error}
        if tag not in WRITE_TAGS:
            self.last_error = f"Tag '{tag}' no escribible o desconocido"
            return {"status": "error", "detail": self.last_error}

        item = next(t for t in OPCUA_TAG_MAP if t["tag"] == tag)
        try:
            if item["type"] == "Bool":
                if not isinstance(value, bool):
                    raise ValueError("El valor del tag Boolean debe ser true o false")
                variant = ua.Variant(value, ua.VariantType.Boolean)
                normalized = value
            else:
                if isinstance(value, bool):
                    raise ValueError("No se acepta Boolean como valor numérico")
                numeric = float(value)
                if not math.isfinite(numeric):
                    raise ValueError("El valor debe ser un número finito")
                if tag.endswith("_SP_mm") and not 150.0 <= numeric <= 430.0:
                    raise ValueError("SP fuera de rango permitido [150, 430] mm")
                if tag.endswith("_Pump_RPM") and not 0.0 <= numeric <= 350.0:
                    raise ValueError("RPM fuera de rango permitido [0, 350]")
                if tag.endswith("_Kp") and not -50.0 <= numeric <= 50.0:
                    raise ValueError("Kp fuera de rango permitido [-50, 50]")
                if tag.endswith("_Ki") and not -15.0 <= numeric <= 15.0:
                    raise ValueError("Ki fuera de rango permitido [-15, 15]")
                if tag.endswith("_Kff") and not 0.0 <= numeric <= 3.0:
                    raise ValueError("Kff fuera de rango permitido [0, 3]")
                variant = ua.Variant(numeric, ua.VariantType.Float)
                normalized = numeric

            node = self.client.get_node(self._resolve_node(tag))
            await asyncio.wait_for(node.write_value(variant), timeout=2.0)
            return {"status": "ok", "tag": tag, "value": normalized}
        except (TypeError, ValueError) as exc:
            self.last_error = f"Validación de escritura fallida en {tag}: {exc}"
            return {"status": "error", "detail": self.last_error}
        except Exception as exc:
            self.last_error = f"Error de escritura en {tag}: {exc}"
            return {"status": "error", "detail": self.last_error}

    # ------------------------------------------------------------------ #
    # Exploración del árbol de nodos (verificación del DB en TIA Portal)
    # ------------------------------------------------------------------ #
    async def browse(self) -> List[Dict[str, Any]]:
        if not self.connected or self.client is None:
            return []
        salida: List[Dict[str, Any]] = []
        try:
            root = self.client.nodes.objects
            for child in await root.get_children():
                nombre = (await child.read_browse_name()).Name
                if DB_NAME.lower() not in nombre.lower():
                    continue
                salida.append({"name": nombre, "node_id": child.nodeid.to_string(), "type": "Object"})
                for var in await child.get_children():
                    vname = (await var.read_browse_name()).Name
                    try:
                        val = await var.read_value()
                    except Exception:
                        val = None
                    salida.append({
                        "name": vname,
                        "node_id": var.nodeid.to_string(),
                        "type": type(val).__name__,
                        "value": val if isinstance(val, (int, float, bool, str)) else None,
                    })
        except Exception as exc:
            self.last_error = f"Error al explorar nodos: {exc}"
        return salida


opcua_client = SiemensOPCUAClient()
