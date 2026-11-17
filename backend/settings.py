"""Configuración central y rutas del proyecto S_C_PID."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env", override=False)


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    return min(maximum, max(minimum, value))


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    return min(maximum, max(minimum, value))


@dataclass(frozen=True)
class Settings:
    app_version: str = "1.2.0"
    simulation_dt: float = 0.5
    frontend_dir: Path = BASE_DIR / "frontend"
    scl_file: Path = BASE_DIR / "plc_s7_1200" / "FB_PI_Feedforward_S7_1200.scl"
    cors_origins: tuple[str, ...] = tuple(
        item.strip()
        for item in os.getenv(
            "SCADA_CORS_ORIGINS",
            "http://127.0.0.1:8000,http://localhost:8000",
        ).split(",")
        if item.strip()
    )

    @property
    def database_path(self) -> Path:
        configured = Path(os.getenv("SCADA_DB_PATH", "data/flotation_historian.db"))
        return configured if configured.is_absolute() else BASE_DIR / configured

    @property
    def control_writes_enabled(self) -> bool:
        return env_bool("SCADA_ENABLE_CONTROL_WRITES", False)

    @property
    def opcua_endpoint(self) -> str:
        return os.getenv("SCADA_OPCUA_ENDPOINT", "opc.tcp://127.0.0.1:4840")

    @property
    def opcua_security_policy(self) -> str:
        return os.getenv("SCADA_OPCUA_SECURITY_POLICY", "None")

    @property
    def opcua_username(self) -> str:
        return os.getenv("SCADA_OPCUA_USERNAME", "")

    @property
    def opcua_password(self) -> str:
        return os.getenv("SCADA_OPCUA_PASSWORD", "")

    @property
    def opcua_namespace_index(self) -> int:
        return _env_int("SCADA_OPCUA_NAMESPACE_INDEX", 3, 1, 20)

    @property
    def opcua_poll_ms(self) -> int:
        return _env_int("SCADA_OPCUA_POLL_MS", 500, 100, 5000)

    @property
    def opcua_timeout_s(self) -> float:
        return _env_float("SCADA_OPCUA_TIMEOUT_S", 4.0, 1.0, 30.0)

    @property
    def opcua_active(self) -> bool:
        return env_bool("SCADA_OPCUA_ACTIVE", True)


settings = Settings()
