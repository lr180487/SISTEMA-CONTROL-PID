"""
Módulo de Comunicación Industrial Siemens S7-1200 vía protocolo S7comm (python-snap7).
Adapta la arquitectura originalmente implementada en PLC GE Fanuc + MATLAB por
Quintanilla et al. (2023) a un autómata Siemens S7-1200 (CPU 1214C / 1215C DC/DC/DC)
con módulos analógicos SM 1231 AI (4-20 mA sensores ultrasónicos/presión y flujómetro)
y SM 1232 AQ (0-10 V / 4-20 mA hacia bombas peristálticas Masterflex / Watson-Marlow).
"""

import socket
import time
import math
import struct
import re
from datetime import datetime, timezone
from typing import Any, Dict

try:
    import snap7
    from snap7.util import get_real, set_real, get_bool, set_bool
    SNAP7_AVAILABLE = True
except Exception:
    SNAP7_AVAILABLE = False

from .models import PLCConnectionConfig


# Mapa oficial de direcciones en DB100 (Acceso NO optimizado habilitado en TIA Portal + PUT/GET permitido)
DB100_TAG_MAP = [
    {"offset": "DB100.DBD0", "tag": "Q_Feed_LPM", "type": "Real", "rw": "R", "desc": "Caudal alimentación banco [L/min] (AI 4-20mA)"},
    {"offset": "DB100.DBD4", "tag": "C1_PV_mm", "type": "Real", "rw": "R", "desc": "Nivel de pulpa medido Celda 1 [mm]"},
    {"offset": "DB100.DBD8", "tag": "C1_SP_mm", "type": "Real", "rw": "R/W", "desc": "Setpoint nivel Celda 1 [mm]"},
    {"offset": "DB100.DBD12", "tag": "C1_Pump_RPM", "type": "Real", "rw": "R/W", "desc": "Consigna de velocidad bomba B-1 (SP) [RPM]"},
    {"offset": "DB100.DBD16", "tag": "C1_Kp", "type": "Real", "rw": "R/W", "desc": "Ganancia Proporcional Kp C-1"},
    {"offset": "DB100.DBD20", "tag": "C1_Ki", "type": "Real", "rw": "R/W", "desc": "Ganancia Integral Ki C-1"},
    {"offset": "DB100.DBD24", "tag": "C1_Kff", "type": "Real", "rw": "R/W", "desc": "Ganancia Feedforward Kff C-1"},
    {"offset": "DB100.DBD28", "tag": "C2_PV_mm", "type": "Real", "rw": "R", "desc": "Nivel de pulpa medido Celda 2 [mm]"},
    {"offset": "DB100.DBD32", "tag": "C2_SP_mm", "type": "Real", "rw": "R/W", "desc": "Setpoint nivel Celda 2 [mm]"},
    {"offset": "DB100.DBD36", "tag": "C2_Pump_RPM", "type": "Real", "rw": "R/W", "desc": "Consigna de velocidad bomba B-2 (SP) [RPM]"},
    {"offset": "DB100.DBD40", "tag": "C2_Kp", "type": "Real", "rw": "R/W", "desc": "Ganancia Proporcional Kp C-2"},
    {"offset": "DB100.DBD44", "tag": "C2_Ki", "type": "Real", "rw": "R/W", "desc": "Ganancia Integral Ki C-2"},
    {"offset": "DB100.DBD48", "tag": "C2_Kff", "type": "Real", "rw": "R/W", "desc": "Ganancia Feedforward Kff C-2"},
    {"offset": "DB100.DBD52", "tag": "C3_PV_mm", "type": "Real", "rw": "R", "desc": "Nivel de pulpa medido Celda 3 [mm]"},
    {"offset": "DB100.DBD56", "tag": "C3_SP_mm", "type": "Real", "rw": "R/W", "desc": "Setpoint nivel Celda 3 [mm]"},
    {"offset": "DB100.DBD60", "tag": "C3_Pump_RPM", "type": "Real", "rw": "R/W", "desc": "Consigna de velocidad bomba B-3 (SP) [RPM]"},
    {"offset": "DB100.DBD64", "tag": "C3_Kp", "type": "Real", "rw": "R/W", "desc": "Ganancia Proporcional Kp C-3"},
    {"offset": "DB100.DBD68", "tag": "C3_Ki", "type": "Real", "rw": "R/W", "desc": "Ganancia Integral Ki C-3"},
    {"offset": "DB100.DBD72", "tag": "C3_Kff", "type": "Real", "rw": "R/W", "desc": "Ganancia Feedforward Kff C-3"},
    {"offset": "DB100.DBX76.0", "tag": "C1_AutoMode", "type": "Bool", "rw": "R/W", "desc": "Modo AUTO (1) / MANUAL (0) Celda 1"},
    {"offset": "DB100.DBX76.1", "tag": "C1_FF_Enable", "type": "Bool", "rw": "R/W", "desc": "Habilitar Feedforward Celda 1"},
    {"offset": "DB100.DBX76.2", "tag": "C2_AutoMode", "type": "Bool", "rw": "R/W", "desc": "Modo AUTO (1) / MANUAL (0) Celda 2"},
    {"offset": "DB100.DBX76.3", "tag": "C2_FF_Enable", "type": "Bool", "rw": "R/W", "desc": "Habilitar Feedforward Celda 2"},
    {"offset": "DB100.DBX76.4", "tag": "C3_AutoMode", "type": "Bool", "rw": "R/W", "desc": "Modo AUTO (1) / MANUAL (0) Celda 3"},
    {"offset": "DB100.DBX76.5", "tag": "C3_FF_Enable", "type": "Bool", "rw": "R/W", "desc": "Habilitar Feedforward Celda 3"},
    {"offset": "DB100.DBD80", "tag": "C1_Pump_RPM_PV", "type": "Real", "rw": "R", "desc": "Velocidad real bomba B-1 [RPM]"},
    {"offset": "DB100.DBD84", "tag": "C2_Pump_RPM_PV", "type": "Real", "rw": "R", "desc": "Velocidad real bomba B-2 [RPM]"},
    {"offset": "DB100.DBD88", "tag": "C3_Pump_RPM_PV", "type": "Real", "rw": "R", "desc": "Velocidad real bomba B-3 [RPM]"},
    {"offset": "DB100.DBD92", "tag": "C1_Output_RPM", "type": "Real", "rw": "R", "desc": "Salida calculada bomba B-1 [RPM]"},
    {"offset": "DB100.DBD96", "tag": "C2_Output_RPM", "type": "Real", "rw": "R", "desc": "Salida calculada bomba B-2 [RPM]"},
    {"offset": "DB100.DBD100", "tag": "C3_Output_RPM", "type": "Real", "rw": "R", "desc": "Salida calculada bomba B-3 [RPM]"},
    {"offset": "DB100.DBD104", "tag": "PLC_CycleCounter", "type": "DWord", "rw": "R", "desc": "Contador de ciclo PLC"},
    {"offset": "DB100.DBX108.0", "tag": "PLC_Heartbeat", "type": "Bool", "rw": "R", "desc": "Heartbeat PLC"},
    {"offset": "DB100.DBX108.1", "tag": "PLC_DataValid", "type": "Bool", "rw": "R", "desc": "Calidad de datos PLC"},
    {"offset": "DB100.DBX108.2", "tag": "PLC_Fault", "type": "Bool", "rw": "R", "desc": "Fallo de control/comunicación PLC"},
    {"offset": "DB100.DBD112", "tag": "DB_Version", "type": "DWord", "rw": "R", "desc": "Versión de estructura DB100 (2)"},
    {"offset": "DB100.DBW116", "tag": "C1_Output_AQ", "type": "Int", "rw": "R", "desc": "Salida analógica escalada C-1 [0..27648]"},
    {"offset": "DB100.DBW118", "tag": "C2_Output_AQ", "type": "Int", "rw": "R", "desc": "Salida analógica escalada C-2 [0..27648]"},
    {"offset": "DB100.DBW120", "tag": "C3_Output_AQ", "type": "Int", "rw": "R", "desc": "Salida analógica escalada C-3 [0..27648]"},
]

# Metadatos numéricos derivados de las direcciones absolutas para el transporte S7.
for _tag in DB100_TAG_MAP:
    _address = _tag["offset"].split(".", 1)[1]
    if "DBX" in _address:
        _byte, _bit = _address.replace("DBX", "").split(".")
        _tag["byte_offset"], _tag["bit"] = int(_byte), int(_bit)
    else:
        _match = re.search(r"DB([DW])(\d+)", _address)
        if _match is None:
            raise ValueError(f"Dirección DB100 no reconocida: {_address}")
        _tag["byte_offset"] = int(_match.group(2))
        _tag["bit"] = None



class SiemensS71200Client:
    def __init__(self):
        self.config = PLCConnectionConfig()
        self.connected: bool = False
        self.last_error: str = "Modo Simulación Digital Activo (Gemelo Hidráulico Local)"
        self.last_ping_ms: float | None = None
        self._client = snap7.client.Client() if SNAP7_AVAILABLE else None

    def get_status(self) -> Dict[str, Any]:
        return {
            "ip": self.config.ip,
            "rack": self.config.rack,
            "slot": self.config.slot,
            "db_number": self.config.db_number,
            "mode": self.config.mode,
            "poll_ms": self.config.poll_ms,
            "connected": self.connected,
            "snap7_installed": SNAP7_AVAILABLE,
            "last_error": self.last_error,
            "last_ping_ms": self.last_ping_ms,
            "tag_map": DB100_TAG_MAP,
        }

    def update_config(self, new_cfg: PLCConnectionConfig) -> Dict[str, Any]:
        self.config = new_cfg
        if new_cfg.mode == "SIMULATION":
            self.disconnect()
            self.last_error = "Modo Simulación Digital Activo (Gemelo Hidráulico Local)"
        return self.get_status()

    def test_and_connect(self) -> Dict[str, Any]:
        """
        Verifica alcanzabilidad TCP en el puerto ISO-on-TCP 102 (RFC1006) antes de invocar Snap7,
        evitando bloqueos largos si el PLC físico no está en la red local.
        """
        t0 = time.perf_counter()
        try:
            with socket.create_connection((self.config.ip, 102), timeout=1.5):
                pass
            tcp_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            self.last_ping_ms = tcp_ms
        except OSError as exc:
            self.connected = False
            self.last_ping_ms = None
            self.last_error = (
                f"Sin respuesta en {self.config.ip}:102 (ISO-on-TCP S7comm). "
                f"Verifique cable Ethernet Profinet, IP de subred y PUT/GET en TIA Portal. Detalle: {exc}"
            )
            return self.get_status()

        if not SNAP7_AVAILABLE or self._client is None:
            self.connected = False
            self.last_error = "Librería python-snap7 disponible sin binario libsnap7 o cliente no inicializado."
            return self.get_status()

        try:
            self._client.connect(self.config.ip, self.config.rack, self.config.slot)
            self.connected = bool(self._client.get_connected())
            if self.connected:
                self.config.mode = "PLC_S7_1200"
                self.last_error = f"Conectado exitosamente a CPU S7-1200 ({self.config.ip}, Rack {self.config.rack}, Slot {self.config.slot})"
            else:
                self.last_error = "Snap7 no confirmó sesión activa con la CPU S7-1200."
        except Exception as exc:
            self.connected = False
            self.last_error = f"Error protocolo S7comm al conectar con S7-1200: {exc}"

        return self.get_status()

    @staticmethod
    def _decode_tag(raw: bytes, item: Dict[str, Any]) -> Any:
        offset = item["byte_offset"]
        kind = item["type"]
        if kind == "Real":
            return struct.unpack(">f", raw[offset:offset + 4])[0]
        if kind == "DWord":
            return struct.unpack(">I", raw[offset:offset + 4])[0]
        if kind == "Int":
            return struct.unpack(">h", raw[offset:offset + 2])[0]
        if kind == "Bool":
            return bool(raw[offset] & (1 << item["bit"]))
        raise ValueError(f"Tipo DB100 no soportado: {kind}")

    @staticmethod
    def _encode_real(value: Any) -> bytes:
        if isinstance(value, bool):
            raise ValueError("No se acepta Boolean como REAL")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("El valor debe ser finito")
        return struct.pack(">f", number)

    def read_db100(self) -> Dict[str, Any]:
        """Lee una imagen coherente del DB100 (122 bytes) y descarta REAL no finitos."""
        if not self.connected or self._client is None:
            return {"status": "error", "quality": "BAD", "detail": "Snap7 sin conexión"}
        try:
            raw = bytes(self._client.db_read(self.config.db_number, 0, 122))
            if len(raw) != 122:
                raise ValueError(f"Longitud DB100 inesperada: {len(raw)} bytes")
            values = {}
            for item in DB100_TAG_MAP:
                value = self._decode_tag(raw, item)
                if isinstance(value, float) and not math.isfinite(value):
                    raise ValueError(f"Valor REAL no finito en {item['tag']}")
                values[item["tag"]] = value
            self.last_error = "Lectura DB100 correcta"
            return {"status": "ok", "quality": "GOOD", "db_number": self.config.db_number,
                    "size": len(raw), "timestamp": datetime.now(timezone.utc).isoformat(),
                    "values": values}
        except Exception as exc:
            self.last_error = f"Error de lectura DB100: {exc}"
            return {"status": "error", "quality": "BAD", "detail": self.last_error}

    def write_db100_tag(self, tag: str, value: Any) -> Dict[str, Any]:
        """Escribe un único tag de mando permitido; nunca escribe PV, salidas ni diagnóstico."""
        if not self.connected or self._client is None:
            return {"status": "error", "detail": "Snap7 sin conexión"}
        item = next((x for x in DB100_TAG_MAP if x["tag"] == tag), None)
        if item is None or "W" not in item["rw"]:
            return {"status": "error", "detail": f"Tag no escribible: {tag}"}
        try:
            if item["type"] == "Bool":
                if not isinstance(value, bool):
                    raise ValueError("El valor BOOL debe ser true/false")
                pos, bit = item["byte_offset"], item["bit"]
                current = bytearray(self._client.db_read(self.config.db_number, pos, 1))
                current[0] = (current[0] | (1 << bit)) if value else (current[0] & ~(1 << bit))
                self._client.db_write(self.config.db_number, pos, current)
                normalized = value
            else:
                number = float(value)
                if not math.isfinite(number):
                    raise ValueError("El valor debe ser finito")
                if tag.endswith("_SP_mm") and not 150 <= number <= 430:
                    raise ValueError("SP fuera de rango [150, 430] mm")
                if tag.endswith("_Pump_RPM") and not 0 <= number <= 350:
                    raise ValueError("RPM_SP fuera de rango [0, 350]")
                if tag.endswith("_Kp") and not -50 <= number <= 50:
                    raise ValueError("Kp fuera de rango [-50, 50]")
                if tag.endswith("_Ki") and not -15 <= number <= 15:
                    raise ValueError("Ki fuera de rango [-15, 15]")
                if tag.endswith("_Kff") and not 0 <= number <= 3:
                    raise ValueError("Kff fuera de rango [0, 3]")
                pos = item["byte_offset"]
                self._client.db_write(self.config.db_number, pos, self._encode_real(number))
                normalized = number
            return {"status": "ok", "tag": tag, "value": normalized}
        except (TypeError, ValueError, OSError, RuntimeError) as exc:
            self.last_error = f"Escritura DB100 rechazada/fallida en {tag}: {exc}"
            return {"status": "error", "detail": self.last_error}

    def disconnect(self) -> Dict[str, Any]:
        if self._client is not None and self.connected:
            try:
                self._client.disconnect()
            except Exception:
                pass
        self.connected = False
        self.config.mode = "SIMULATION"
        self.last_error = "Desconectado de PLC físico. Operando en Modo Simulación."
        return self.get_status()
