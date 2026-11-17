"""
Modelo Dinámico Hidráulico de 3 Celdas de Flotación en Serie (C-1 -> C-2 -> C-3)
Basado en Quintanilla et al. (2021, 2023):
- Celdas acrílicas de escala laboratorio: sección transversal 300 mm x 300 mm (A = 0.09 m²),
  altura total H_cell = 450 mm (volumen geométrico ~40.5 L; volumen efectivo con aireación/agitador ~30-34 L,
  A_eff = 0.078 m² -> 1 mm de nivel equivale a 0.078 L de pulpa).
- Balance de masa dinámico por celda i (i = 1, 2, 3):
  A_eff * dh_i/dt = Q_in,i(t) - Q_out,i(t) - Q_conc,i(h_i, J_g)
  donde:
    Q_in,1 = Q_feed (medido por flujómetro electromagnético -> entrada Feedforward C-1)
    Q_in,2 = Q_out,1 (descarga de bomba peristáltica B-1 -> entrada Feedforward C-2)
    Q_in,3 = Q_out,2 (descarga de bomba peristáltica B-2 -> entrada Feedforward C-3)
    Q_out,i = f_cal(RPM_i_actual) con dinámica de actuador de primer orden (tau_pump = 1.2 s)
    Q_conc,i = rebose de espuma de concentrado sobre el labio del vertedero cuando h_i se acerca al labio.
"""

import math
import random
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .controller import PIFeedforwardController, PeristalticCalibration
from .models import (
    SCHEMA_VERSION,
    AlarmEvent,
    CalibrationInfo,
    CellConfig,
    CellRuntimeState,
    CommStatus,
    ConfigSnapshot,
    FeedSimulationConfig,
    OPCUAConnectionConfig,
    PLCConnectionConfig,
    SystemTelemetry,
)


class ThreeCellFlotationProcess:
    CELL_HEIGHT_MM = 450.0
    LIP_HEIGHT_MM = 425.0
    EFFECTIVE_AREA_L_PER_MM = 0.078  # 0.078 L/mm -> 320 mm = 25.0 L de pulpa (celda de 30 L nominales)

    def __init__(self):
        self.cal = PeristalticCalibration(alpha=0.125, beta=0.0, rpm_min=0.0, rpm_max=350.0)

        # Configuraciones iniciales de cada celda (C-1, C-2, C-3) escalonadas o uniformes
        self.configs: Dict[str, CellConfig] = {
            "C1": CellConfig(
                cell_id="C1",
                sp=330.0,
                mode="AUTO",
                ff_enabled=True,
                manual_rpm=170.0,
                kp=-6.8,
                ki=-0.62,
                kff=1.00,
                alarm_high=385.0,
                alarm_low=250.0,
            ),
            "C2": CellConfig(
                cell_id="C2",
                sp=320.0,
                mode="AUTO",
                ff_enabled=True,
                manual_rpm=166.0,
                kp=-6.5,
                ki=-0.58,
                kff=1.00,
                alarm_high=380.0,
                alarm_low=245.0,
            ),
            "C3": CellConfig(
                cell_id="C3",
                sp=310.0,
                mode="AUTO",
                ff_enabled=True,
                manual_rpm=162.0,
                kp=-6.2,
                ki=-0.55,
                kff=1.00,
                alarm_high=375.0,
                alarm_low=240.0,
            ),
        }

        self.controllers: Dict[str, PIFeedforwardController] = {
            cid: PIFeedforwardController(
                cell_id=cid,
                kp=cfg.kp,
                ki=cfg.ki,
                kff=cfg.kff,
                calibration=self.cal,
            )
            for cid, cfg in self.configs.items()
        }

        self.feed_cfg = FeedSimulationConfig(
            base_flow_lpm=22.0,
            profile="CONSTANT",
            noise_std=0.15,
            air_flow_lpm=45.0,
        )

        self.running: bool = True
        self.elapsed_sec: float = 0.0
        self.profile_start_sec: float = 0.0

        # Estados físicos internos
        self.levels_mm: Dict[str, float] = {"C1": 330.0, "C2": 320.0, "C3": 310.0}
        self.pump_rpm_actual: Dict[str, float] = {"C1": 171.0, "C2": 166.0, "C3": 161.0}
        self.pump_rpm_cmd: Dict[str, float] = {"C1": 171.0, "C2": 166.0, "C3": 161.0}
        self.rpm_pi: Dict[str, float] = {"C1": 0.0, "C2": 0.0, "C3": 0.0}
        self.rpm_ff: Dict[str, float] = {"C1": 171.0, "C2": 166.0, "C3": 161.0}
        self.q_in: Dict[str, float] = {"C1": 22.0, "C2": 21.4, "C3": 20.8}
        self.q_out: Dict[str, float] = {"C1": 21.4, "C2": 20.8, "C3": 20.2}
        self.q_conc: Dict[str, float] = {"C1": 0.6, "C2": 0.6, "C3": 0.6}
        self.iae: Dict[str, float] = {"C1": 0.0, "C2": 0.0, "C3": 0.0}

        self.q_feed_current: float = 22.0
        self.alarm_counter: int = 0
        self.alarm_history: List[AlarmEvent] = []
        self.last_alarm_state: Dict[str, str] = {"C1": "NORMAL", "C2": "NORMAL", "C3": "NORMAL"}

    # ------------------------------------------------------------------
    # Contrato de configuración (consumido por el frontend al hidratarse)
    # ------------------------------------------------------------------
    def calibration_info(self) -> CalibrationInfo:
        return CalibrationInfo(
            alpha=self.cal.alpha,
            beta=self.cal.beta,
            rpm_min=self.cal.rpm_min,
            rpm_max=self.cal.rpm_max,
            max_flow_lpm=round(self.cal.flow_from_rpm(self.cal.rpm_max), 3),
        )

    def build_config_snapshot(self, plc_cfg: PLCConnectionConfig,
                              opcua_cfg: Optional[OPCUAConnectionConfig] = None) -> ConfigSnapshot:
        """Instantánea completa de configuración; plc_cfg lo aporta la capa API/PLC."""
        return ConfigSnapshot(
            schema_version=SCHEMA_VERSION,
            feed=self.feed_cfg,
            cells={cid: cfg for cid, cfg in self.configs.items()},
            plc=plc_cfg,
            opcua=opcua_cfg or OPCUAConnectionConfig(),
            calibration=self.calibration_info(),
            profiles=["CONSTANT", "STEP_QUINTANILLA", "PULSE", "SINE", "NOISY_RAMP"],
            cell_level_max_mm=self.CELL_HEIGHT_MM,
            limits={
                "sp": [150.0, 430.0],
                "kp": [-50.0, 50.0],
                "ki": [-15.0, 15.0],
                "kff": [0.0, 3.0],
                "manual_rpm": [0.0, self.cal.rpm_max],
                "alarm_high": [200.0, 445.0],
                "alarm_low": [80.0, 380.0],
                "base_flow_lpm": [5.0, 45.0],
                "noise_std": [0.0, 2.5],
                "air_flow_lpm": [10.0, 90.0],
            },
        )

    # ------------------------------------------------------------------
    # Alarmas: reconocimiento (ACK) tipo ISA-18.2
    # ------------------------------------------------------------------
    def acknowledge_alarms(self, cell_id: str | None = None) -> int:
        n = 0
        for ev in self.alarm_history:
            if not ev.active or ev.acked:
                continue
            if cell_id is None or ev.cell_id == cell_id:
                ev.acked = True
                n += 1
        return n

    def unacked_count(self) -> int:
        return sum(1 for ev in self.alarm_history if ev.active and not ev.acked)

    def reset_simulation(self) -> None:
        self.elapsed_sec = 0.0
        self.profile_start_sec = 0.0
        for cid, cfg in self.configs.items():
            self.levels_mm[cid] = cfg.sp
            eq_rpm = self.cal.rpm_from_flow(self.feed_cfg.base_flow_lpm - 0.6)
            self.pump_rpm_actual[cid] = eq_rpm
            self.pump_rpm_cmd[cid] = eq_rpm
            self.iae[cid] = 0.0
            self.controllers[cid].reset(eq_rpm)
            self.last_alarm_state[cid] = "NORMAL"

    def _compute_feed_flow(self) -> float:
        t = self.elapsed_sec - self.profile_start_sec
        base = self.feed_cfg.base_flow_lpm
        profile = self.feed_cfg.profile

        if profile == "CONSTANT":
            q = base
        elif profile == "STEP_QUINTANILLA":
            # Secuencia de 4 escalones inspirada en Quintanilla et al. (ciclo de 80 s para visualización ágil en laboratorio)
            phase = (t % 80.0) / 20.0
            if phase < 1.0:
                q = base
            elif phase < 2.0:
                q = min(42.0, base * 1.25)  # +25% escalón positivo
            elif phase < 3.0:
                q = min(44.0, base * 1.40)  # +40% escalón severo
            else:
                q = max(8.0, base * 0.82)   # -18% caída brusca de alimentación
        elif profile == "PULSE":
            # Pulso de perturbación cada 30 segundos (duración 10 s)
            q = min(43.0, base + 8.5) if (t % 30.0) < 10.0 else base
        elif profile == "SINE":
            q = base + 5.5 * math.sin(2.0 * math.pi * t / 35.0)
        elif profile == "NOISY_RAMP":
            cycle = (t % 60.0) / 60.0
            tri = 1.0 - abs(2.0 * cycle - 1.0)
            q = base - 4.0 + 10.0 * tri
        else:
            q = base

        # Pequeña fluctuación natural de pulpa + ruido de flujómetro magnético
        noise = random.gauss(0.0, self.feed_cfg.noise_std * 0.35)
        return max(4.0, min(44.0, q + noise))

    def _compute_concentrate_overflow(self, level_mm: float) -> float:
        """
        Caudal de rebose de espuma de concentrado Q_conc [L/min] en función de la altura de pulpa
        y aireación Jg. Mayor nivel de pulpa reduce el espesor de espuma y aumenta la descarga de concentrado.
        """
        air_factor = self.feed_cfg.air_flow_lpm / 45.0
        froth_depth = max(5.0, self.LIP_HEIGHT_MM - level_mm)
        # Relación física suave: a 320 mm (froth=105 mm) -> ~0.60 L/min; si sube a 410 mm -> ~2.5 L/min
        q_conc = 0.65 * air_factor * math.exp((320.0 - froth_depth - 215.0) / 55.0)
        if level_mm > self.LIP_HEIGHT_MM:
            # Rebose hidráulico directo (derrame por vertedero)
            q_conc += 0.45 * (level_mm - self.LIP_HEIGHT_MM)
        return max(0.05, min(12.0, q_conc))

    def trigger_instant_disturbance(self, delta_lpm: float) -> float:
        self.feed_cfg.base_flow_lpm = max(6.0, min(42.0, self.feed_cfg.base_flow_lpm + delta_lpm))
        return self.feed_cfg.base_flow_lpm

    def step(self, dt: float = 0.5) -> None:
        if not self.running:
            return

        self.elapsed_sec += dt
        self.q_feed_current = self._compute_feed_flow()

        cell_order = ["C1", "C2", "C3"]
        upstream_flow = self.q_feed_current

        for cid in cell_order:
            cfg = self.configs[cid]
            ctrl = self.controllers[cid]
            ctrl.kp = cfg.kp
            ctrl.ki = cfg.ki
            ctrl.kff = cfg.kff

            # Nivel medido por sensor ultrasónico/presión con ruido realista filtrado
            pv_true = self.levels_mm[cid]
            sensor_noise = random.gauss(0.0, self.feed_cfg.noise_std)
            pv_measured = max(0.0, min(self.CELL_HEIGHT_MM, pv_true + sensor_noise))

            q_conc_i = self._compute_concentrate_overflow(pv_true)

            # Cálculo de ley de control PI + Feedforward
            # Perturbación medida para C-1 es Q_feed; para C-2 es Q_out(C-1); para C-3 es Q_out(C-2)
            rpm_cmd, u_pi, u_ff, err = ctrl.compute(
                sp=cfg.sp,
                pv=pv_measured,
                q_disturbance_lpm=upstream_flow,
                q_conc_est_lpm=0.60,
                dt=dt,
                mode=cfg.mode,
                ff_enabled=cfg.ff_enabled,
                manual_rpm=cfg.manual_rpm,
            )

            self.pump_rpm_cmd[cid] = rpm_cmd
            self.rpm_pi[cid] = u_pi
            self.rpm_ff[cid] = u_ff

            # Dinámica de primer orden del variador/motor paso a paso de bomba peristáltica (tau = 1.1 s)
            tau_pump = 1.1
            alpha_dyn = dt / (tau_pump + dt)
            self.pump_rpm_actual[cid] += alpha_dyn * (rpm_cmd - self.pump_rpm_actual[cid])

            q_out_i = self.cal.flow_from_rpm(self.pump_rpm_actual[cid])
            # Si la celda está casi vacía, la bomba no puede extraer líquido inexistente
            if pv_true <= 15.0:
                q_out_i *= max(0.0, pv_true / 15.0)

            # Integración de la EDO de balance de volumen (conversión L/min -> L/s dividiendo entre 60)
            net_flow_lps = (upstream_flow - q_out_i - q_conc_i) / 60.0
            dh_mm = (net_flow_lps * dt) / self.EFFECTIVE_AREA_L_PER_MM
            new_level = max(10.0, min(self.CELL_HEIGHT_MM, pv_true + dh_mm))

            self.levels_mm[cid] = new_level
            self.q_in[cid] = upstream_flow
            self.q_out[cid] = q_out_i
            self.q_conc[cid] = q_conc_i
            self.iae[cid] += abs(cfg.sp - new_level) * dt

            # Evaluación de alarmas industriales ISA-18.2
            self._evaluate_alarms(cid, new_level, cfg)

            # La descarga de colas de la celda i alimenta en serie a la celda i+1
            upstream_flow = q_out_i

    def _evaluate_alarms(self, cid: str, pv: float, cfg: CellConfig) -> None:
        hh_limit = min(440.0, cfg.alarm_high + 25.0)
        ll_limit = max(50.0, cfg.alarm_low - 30.0)

        if pv >= hh_limit:
            state = "HH_CRITICAL"
            severity = "CRITICAL"
            msg = f"Nivel Muy Alto Crítico (HH) en {cid}: riesgo de rebose de pulpa ({pv:.1f} mm >= {hh_limit:.0f} mm)"
            thresh = hh_limit
        elif pv >= cfg.alarm_high:
            state = "HIGH"
            severity = "WARNING"
            msg = f"Alarma Nivel Alto (H) en {cid}: {pv:.1f} mm supera límite {cfg.alarm_high:.0f} mm"
            thresh = cfg.alarm_high
        elif pv <= ll_limit:
            state = "LL_CRITICAL"
            severity = "CRITICAL"
            msg = f"Nivel Muy Bajo Crítico (LL) en {cid}: riesgo cavitación/aire en bomba ({pv:.1f} mm <= {ll_limit:.0f} mm)"
            thresh = ll_limit
        elif pv <= cfg.alarm_low:
            state = "LOW"
            severity = "WARNING"
            msg = f"Alarma Nivel Bajo (L) en {cid}: {pv:.1f} mm inferior a {cfg.alarm_low:.0f} mm"
            thresh = cfg.alarm_low
        else:
            state = "NORMAL"
            severity = "INFO"
            msg = f"Nivel normalizado en {cid} ({pv:.1f} mm)"
            thresh = cfg.sp

        prev_state = self.last_alarm_state[cid]
        if state != prev_state:
            self.last_alarm_state[cid] = state
            if state != "NORMAL":
                self.alarm_counter += 1
                event = AlarmEvent(
                    id=self.alarm_counter,
                    timestamp=datetime.now(timezone.utc).strftime("%H:%M:%S"),
                    cell_id=cid,
                    severity=severity,
                    type=state,
                    message=msg,
                    value=round(pv, 2),
                    threshold=round(thresh, 2),
                    active=True,
                )
                self.alarm_history.insert(0, event)
                self.alarm_history = self.alarm_history[:60]
            else:
                for ev in self.alarm_history:
                    if ev.cell_id == cid and ev.active:
                        ev.active = False

    def build_comm_status(self, plc_status: dict, opcua_status: dict) -> CommStatus:
        mode = plc_status.get("mode", "SIMULATION")
        return CommStatus(
            active_source=mode,
            opcua_connected=bool(opcua_status.get("connected")),
            opcua_endpoint=opcua_status.get("endpoint", ""),
            opcua_latency_ms=opcua_status.get("latency_ms"),
            opcua_nodes_ok=int(opcua_status.get("nodes_ok", 0)),
            opcua_nodes_total=int(opcua_status.get("nodes_total", 0)),
            opcua_last_poll=opcua_status.get("last_poll_at"),
            opcua_error=opcua_status.get("last_error"),
            snap7_connected=bool(plc_status.get("connected")),
            snap7_ip=plc_status.get("ip", ""),
        )

    def build_telemetry(self, plc_status: dict, opcua_status: Optional[dict] = None) -> SystemTelemetry:
        names = {
            "C1": "Celda Rougher C-1",
            "C2": "Celda Scavenger C-2",
            "C3": "Celda Cleaner/Tail C-3",
        }
        cells_state: Dict[str, CellRuntimeState] = {}
        for cid in ["C1", "C2", "C3"]:
            cfg = self.configs[cid]
            pv = self.levels_mm[cid]
            froth = max(0.0, self.LIP_HEIGHT_MM - pv)
            cells_state[cid] = CellRuntimeState(
                cell_id=cid,
                name=names[cid],
                pv=round(pv, 2),
                sp=round(cfg.sp, 2),
                error=round(cfg.sp - pv, 2),
                mode=cfg.mode,
                ff_enabled=cfg.ff_enabled,
                rpm=round(self.pump_rpm_actual[cid], 2),
                rpm_pi=round(self.rpm_pi[cid], 2),
                rpm_ff=round(self.rpm_ff[cid], 2),
                q_in_lpm=round(self.q_in[cid], 2),
                q_out_lpm=round(self.q_out[cid], 2),
                q_conc_lpm=round(self.q_conc[cid], 2),
                froth_depth_mm=round(froth, 1),
                kp=round(cfg.kp, 3),
                ki=round(cfg.ki, 3),
                kff=round(cfg.kff, 3),
                alarm_high=round(cfg.alarm_high, 1),
                alarm_low=round(cfg.alarm_low, 1),
                alarm_status=self.last_alarm_state[cid],
                iae=round(self.iae[cid], 1),
            )

        active_alarms = [ev for ev in self.alarm_history if ev.active][:15]
        return SystemTelemetry(
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            elapsed_sec=round(self.elapsed_sec, 1),
            q_feed_lpm=round(self.q_feed_current, 2),
            q_feed_set_lpm=round(self.feed_cfg.base_flow_lpm, 2),
            feed_profile=self.feed_cfg.profile,
            air_flow_lpm=round(self.feed_cfg.air_flow_lpm, 1),
            simulation_running=self.running,
            plc_connected=plc_status["connected"],
            plc_mode=plc_status["mode"],
            plc_ip=plc_status["ip"],
            cells=cells_state,
            active_alarms=active_alarms,
            comm=self.build_comm_status(plc_status, opcua_status or {}),
        )
