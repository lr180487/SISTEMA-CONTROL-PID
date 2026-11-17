"""
Controlador Regulatorio PI + Feedforward para Nivel de Pulpa con Bombas Peristálticas
Referencia científica:
Quintanilla, P., Navia, D., Moreno, F., Neethling, S.J., & Brito-Parada, P.R. (2023).
"A methodology to implement a closed-loop feedback-feedforward level control in a
laboratory-scale flotation bank using peristaltic pumps." MethodsX, 10, 102081.
"""

from dataclasses import dataclass


@dataclass
class PeristalticCalibration:
    """
    Curva de calibración linealizada de bomba peristáltica Masterflex / Watson-Marlow:
    Q_pump [L/min] = alpha * RPM + beta  (válida para RPM > deadband)
    Para cubrir rango experimental 0 - 40 L/min con 0 - 350 RPM:
    alpha = 0.125 L/(min·RPM), beta = 0.0
    """
    alpha: float = 0.125  # [L / (min * RPM)] -> 200 RPM = 25.0 L/min
    beta: float = 0.0
    rpm_min: float = 0.0
    rpm_max: float = 350.0

    def flow_from_rpm(self, rpm: float) -> float:
        rpm_clamped = max(self.rpm_min, min(self.rpm_max, rpm))
        if rpm_clamped <= 1.0:
            return 0.0
        return max(0.0, self.alpha * rpm_clamped + self.beta)

    def rpm_from_flow(self, flow_lpm: float) -> float:
        if flow_lpm <= 0.0:
            return 0.0
        rpm = (flow_lpm - self.beta) / self.alpha
        return max(self.rpm_min, min(self.rpm_max, rpm))


class PIFeedforwardController:
    """
    Lazo cerrado de control de nivel por descarga con bomba peristáltica (acción inversa).
    - Error: e(t) = SP(t) - PV(t)  [mm]
      Si PV > SP (nivel alto) -> e < 0. Con Kp < 0 y Ki < 0, u_PI aumenta las RPM de descarga
      para evacuar más colas y restituir el nivel al SP.
    - Ley de control combinada (Quintanilla et al., 2023):
      u_total(k) = u_PI(k) + u_FF(k)
      donde u_FF(k) = K_ff * RPM_eq(Q_in_medido - Q_conc_estimado)
    - Incluye:
      1) Anti-windup por clamping condicional / back-calculation
      2) Transferencia sin saltos (bumpless transfer) entre MANUAL <-> AUTO y al activar/desactivar FF
    """

    def __init__(
        self,
        cell_id: str,
        kp: float = -6.5,
        ki: float = -0.55,
        kff: float = 1.0,
        calibration: PeristalticCalibration | None = None,
    ):
        self.cell_id = cell_id
        self.kp = kp
        self.ki = ki
        self.kff = kff
        self.cal = calibration or PeristalticCalibration()

        self.integral_term: float = 0.0
        self.last_mode: str = "AUTO"
        self.last_ff_enabled: bool = True
        self.last_rpm: float = 176.0
        self.initialized: bool = False

    def reset(self, current_rpm: float = 176.0) -> None:
        self.integral_term = 0.0
        self.last_rpm = current_rpm
        self.initialized = False

    def compute(
        self,
        sp: float,
        pv: float,
        q_disturbance_lpm: float,
        q_conc_est_lpm: float,
        dt: float,
        mode: str = "AUTO",
        ff_enabled: bool = True,
        manual_rpm: float = 176.0,
    ) -> tuple[float, float, float, float]:
        """
        Retorna: (rpm_total, rpm_pi, rpm_ff, error_mm)
        """
        error = sp - pv  # [mm]

        # Cálculo de prealimentación (Feedforward) basada en caudal de entrada medido
        net_inflow_est = max(0.0, q_disturbance_lpm - q_conc_est_lpm)
        rpm_ff_raw = self.cal.rpm_from_flow(net_inflow_est) * self.kff
        rpm_ff = rpm_ff_raw if ff_enabled else 0.0

        # Inicialización suave en el primer ciclo
        if not self.initialized:
            if ff_enabled:
                self.integral_term = 0.0
            else:
                self.integral_term = self.cal.rpm_from_flow(net_inflow_est)
            self.last_mode = mode
            self.last_ff_enabled = ff_enabled
            self.initialized = True

        # Modo MANUAL: seguimiento para transferencia bumpless al volver a AUTO
        if mode == "MANUAL":
            rpm_out = max(self.cal.rpm_min, min(self.cal.rpm_max, manual_rpm))
            p_term = self.kp * error
            self.integral_term = rpm_out - rpm_ff - p_term
            self.last_mode = "MANUAL"
            self.last_ff_enabled = ff_enabled
            self.last_rpm = rpm_out
            return rpm_out, rpm_out - rpm_ff, rpm_ff, error

        # Bumpless transfer si se conmuta FF en caliente estando en AUTO
        if ff_enabled != self.last_ff_enabled and self.last_mode == "AUTO":
            p_term = self.kp * error
            self.integral_term = self.last_rpm - rpm_ff - p_term

        p_term = self.kp * error
        candidate_integral = self.integral_term + (self.ki * error * dt)

        u_pi_unclamped = p_term + candidate_integral
        u_total_unclamped = u_pi_unclamped + rpm_ff

        # Saturación física de la bomba peristáltica [0, 350 RPM] + Anti-windup
        if u_total_unclamped > self.cal.rpm_max:
            rpm_out = self.cal.rpm_max
            # Permitir integrar solo si reduce la saturación
            if (self.ki * error) < 0:
                self.integral_term = candidate_integral
        elif u_total_unclamped < self.cal.rpm_min:
            rpm_out = self.cal.rpm_min
            if (self.ki * error) > 0:
                self.integral_term = candidate_integral
        else:
            rpm_out = u_total_unclamped
            self.integral_term = candidate_integral

        rpm_pi = rpm_out - rpm_ff
        self.last_mode = "AUTO"
        self.last_ff_enabled = ff_enabled
        self.last_rpm = rpm_out

        return rpm_out, rpm_pi, rpm_ff, error
