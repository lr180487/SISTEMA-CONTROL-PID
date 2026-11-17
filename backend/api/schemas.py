"""Esquemas HTTP locales que no forman parte del contrato de telemetría."""
from pydantic import BaseModel, Field


class DisturbanceStepRequest(BaseModel):
    delta_lpm: float = Field(..., ge=-1000.0, le=1000.0)


class GlobalActionRequest(BaseModel):
    action: str


class OPCUATestServerRequest(BaseModel):
    port: int = Field(default=4840, ge=1024, le=65535)
    namespace_uri: str = "urn:flotation-scada:plc-sim"
