"""Orquestación de fuentes de datos: SIMULATION, OPC UA y Snap7.

Este servicio mantiene la regla de aislamiento: una fuente industrial nunca
avanza el modelo de simulación para fabricar telemetría.
"""
from __future__ import annotations

import time
from typing import Any, Callable


OPC_TO_CELL = {
    "C1": {"pv": "C1_PV_mm", "sp": "C1_SP_mm", "rpm_sp": "C1_Pump_RPM", "rpm_pv": "C1_Pump_RPM_PV",
           "kp": "C1_Kp", "ki": "C1_Ki", "kff": "C1_Kff", "auto": "C1_AutoMode", "ff": "C1_FF_Enable"},
    "C2": {"pv": "C2_PV_mm", "sp": "C2_SP_mm", "rpm_sp": "C2_Pump_RPM", "rpm_pv": "C2_Pump_RPM_PV",
           "kp": "C2_Kp", "ki": "C2_Ki", "kff": "C2_Kff", "auto": "C2_AutoMode", "ff": "C2_FF_Enable"},
    "C3": {"pv": "C3_PV_mm", "sp": "C3_SP_mm", "rpm_sp": "C3_Pump_RPM", "rpm_pv": "C3_Pump_RPM_PV",
           "kp": "C3_Kp", "ki": "C3_Ki", "kff": "C3_Kff", "auto": "C3_AutoMode", "ff": "C3_FF_Enable"},
}


class DataSourceService:
    def __init__(self, process: Any, plc_client: Any, opcua_client: Any,
                 control_writes_enabled: Callable[[], bool], simulation_dt: float = 0.5):
        self.process = process
        self.plc_client = plc_client
        self.opcua_client = opcua_client
        self.control_writes_enabled = control_writes_enabled
        self.simulation_dt = simulation_dt
        self.last_opc_poll = 0.0

    def apply_opcua_values(self, values: dict) -> None:
        """Copia al estado de telemetría únicamente valores OPC UA válidos."""
        if not values:
            return
        feed = values.get("Q_Feed_LPM")
        if isinstance(feed, (int, float)) and not isinstance(feed, bool):
            self.process.q_feed_current = float(feed)

        for cell_id, tags in OPC_TO_CELL.items():
            cfg = self.process.configs[cell_id]
            pv = values.get(tags["pv"])
            if isinstance(pv, (int, float)) and not isinstance(pv, bool):
                self.process.levels_mm[cell_id] = max(0.0, float(pv))
            rpm_pv = values.get(tags["rpm_pv"])
            if isinstance(rpm_pv, (int, float)) and not isinstance(rpm_pv, bool):
                self.process.pump_rpm_actual[cell_id] = float(rpm_pv)

            for key, limits in (("sp", (150.0, 430.0)), ("kp", (-50.0, 50.0)),
                                ("ki", (-15.0, 15.0)), ("kff", (0.0, 3.0))):
                value = values.get(tags[key])
                if (isinstance(value, (int, float)) and not isinstance(value, bool)
                        and limits[0] <= float(value) <= limits[1]):
                    setattr(cfg, key, float(value))
            auto = values.get(tags["auto"])
            if isinstance(auto, bool):
                cfg.mode = "AUTO" if auto else "MANUAL"
            ff = values.get(tags["ff"])
            if isinstance(ff, bool):
                cfg.ff_enabled = ff

    async def sync_opcua_to_plc(self) -> list[str]:
        """Solicita escrituras de consignas; nunca escribe PV ni salidas físicas."""
        written: list[str] = []
        if not self.opcua_client.connected or not self.control_writes_enabled():
            return written
        for cell_id, tags in OPC_TO_CELL.items():
            cfg = self.process.configs[cell_id]
            pairs = [
                (tags["sp"], cfg.sp), (tags["kp"], cfg.kp), (tags["ki"], cfg.ki),
                (tags["kff"], cfg.kff),
                (tags["rpm_sp"], self.process.pump_rpm_cmd[cell_id]
                 if cfg.mode == "AUTO" else cfg.manual_rpm),
                (tags["auto"], cfg.mode == "AUTO"), (tags["ff"], cfg.ff_enabled),
            ]
            for tag, value in pairs:
                result = await self.opcua_client.write_tag(tag, value)
                if result.get("status") == "ok":
                    written.append(tag)
        return written

    async def advance_active_source(self, mode: str, now_ms: float | None = None) -> bool:
        """Avanza exactamente una fuente; True indica que llegó una muestra nueva."""
        if mode == "SIMULATION":
            self.process.step(dt=self.simulation_dt)
            return True

        if mode == "OPC_UA":
            now_ms = now_ms if now_ms is not None else time.monotonic() * 1000.0
            cfg = self.opcua_client.config
            if (self.opcua_client.connected and cfg.active
                    and now_ms - self.last_opc_poll >= cfg.poll_ms):
                self.last_opc_poll = now_ms
                values = await self.opcua_client.read_all()
                if values:
                    self.apply_opcua_values(values)
                    if self.control_writes_enabled():
                        await self.sync_opcua_to_plc()
                    return True
            return False

        # Snap7 no se considera fuente activa hasta tener adquisición cíclica real.
        return False
