# Contrato API — Backend FastAPI ↔ Frontend SCADA

- **app_version:** `1.2.0`
- **schema_version:** `1.2.0`
- **WebSocket:** `/ws` (telemetría cada 500 ms)

> Archivo generado por `tools/sync_contract.py`; no editar a mano.

## Endpoints

| Método | Ruta | Handler |
|---|---|---|
| GET | `/api/alarms` | `get_alarms` |
| POST | `/api/alarms/ack` | `acknowledge_alarms` |
| POST | `/api/cells/{cell_id}` | `update_cell` |
| GET | `/api/config` | `get_config` |
| PATCH | `/api/config` | `patch_config` |
| POST | `/api/feed` | `update_feed_simulation` |
| POST | `/api/feed/disturbance` | `apply_instant_disturbance` |
| GET | `/api/health` | `health` |
| DELETE | `/api/historian` | `clear_historian` |
| GET | `/api/historian/export.csv` | `export_historian_csv` |
| GET | `/api/historian/recent` | `get_recent_historian` |
| GET | `/api/meta` | `api_meta` |
| GET | `/api/opcua/browse` | `browse_opcua` |
| POST | `/api/opcua/config` | `update_opcua_config` |
| POST | `/api/opcua/connect` | `connect_opcua` |
| POST | `/api/opcua/disconnect` | `disconnect_opcua` |
| GET | `/api/opcua/status` | `get_opcua_status` |
| GET | `/api/opcua/tags` | `get_opcua_tags` |
| POST | `/api/opcua/test-server/start` | `start_opcua_test_server` |
| GET | `/api/opcua/test-server/status` | `opcua_test_server_status` |
| POST | `/api/opcua/test-server/stop` | `stop_opcua_test_server` |
| POST | `/api/opcua/write` | `write_opcua_tag` |
| POST | `/api/plc/config` | `update_plc_config` |
| POST | `/api/plc/connect` | `connect_plc` |
| POST | `/api/plc/disconnect` | `disconnect_plc` |
| GET | `/api/plc/scl` | `get_tia_portal_scl` |
| GET | `/api/plc/status` | `get_plc_status` |
| GET | `/api/state` | `get_state` |
| POST | `/api/system/action` | `execute_system_action` |
| WEBSOCKET | `/ws` | `websocket_endpoint` |

## Campos por modelo (Pydantic)

### SystemTelemetry

```
timestamp, elapsed_sec, q_feed_lpm, q_feed_set_lpm, feed_profile, air_flow_lpm, simulation_running, plc_connected, plc_mode, plc_ip, cells, active_alarms, comm
```

### CellRuntimeState

```
cell_id, name, pv, sp, error, mode, ff_enabled, rpm, rpm_pi, rpm_ff, q_in_lpm, q_out_lpm, q_conc_lpm, froth_depth_mm, kp, ki, kff, alarm_high, alarm_low, alarm_status, iae
```

### CellConfig

```
cell_id, sp, mode, ff_enabled, manual_rpm, kp, ki, kff, alarm_high, alarm_low
```

### CellUpdateRequest

```
sp, mode, ff_enabled, manual_rpm, kp, ki, kff, alarm_high, alarm_low
```

### AlarmEvent

```
id, timestamp, cell_id, severity, type, message, value, threshold, active, acked
```

### FeedSimulationConfig

```
base_flow_lpm, profile, noise_std, air_flow_lpm
```

### PLCConnectionConfig

```
ip, rack, slot, db_number, mode, poll_ms
```

### ConfigSnapshot

```
schema_version, feed, cells, plc, opcua, calibration, profiles, cell_level_max_mm, limits
```

### ConfigUpdateResponse

```
status, applied_cells, feed_applied, warnings, config
```

### HealthStatus

```
status, app_version, schema_version, uptime_sec, server_time, simulation_running, simulation_hz, ws_clients, historian_rows, plc_mode, plc_connected, opcua_connected, opcua_endpoint, data_source
```

## Rangos de validación

| Parámetro | Mín | Máx |
|---|---|---|
| `sp` | 150.0 | 430.0 |
| `manual_rpm` | 0.0 | 350.0 |
| `kp` | -50.0 | 50.0 |
| `ki` | -15.0 | 15.0 |
| `kff` | 0.0 | 3.0 |
| `alarm_high` | 200.0 | 445.0 |
| `alarm_low` | 80.0 | 380.0 |
| `base_flow_lpm` | 5.0 | 45.0 |
| `noise_std` | 0.0 | 2.5 |
| `air_flow_lpm` | 10.0 | 90.0 |
