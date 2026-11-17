"""
Histórico de Datos de Proceso en SQLite + Exportación CSV
Registra series temporales de Q_feed, SP, PV, Error, RPM (Total, PI, FF), Kp, Ki, Kff y estado de alarma
para las 3 celdas C-1, C-2 y C-3.
"""

import csv
import io
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from .models import SystemTelemetry
from .settings import settings

DB_PATH = settings.database_path


class HistorianDB:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._sample_counter = 0

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS process_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    elapsed_sec REAL NOT NULL,
                    q_feed_lpm REAL NOT NULL,
                    feed_profile TEXT NOT NULL,
                    c1_sp REAL, c1_pv REAL, c1_err REAL, c1_rpm REAL, c1_rpm_pi REAL, c1_rpm_ff REAL,
                    c1_mode TEXT, c1_ff INTEGER, c1_kp REAL, c1_ki REAL, c1_kff REAL, c1_alarm TEXT,
                    c2_sp REAL, c2_pv REAL, c2_err REAL, c2_rpm REAL, c2_rpm_pi REAL, c2_rpm_ff REAL,
                    c2_mode TEXT, c2_ff INTEGER, c2_kp REAL, c2_ki REAL, c2_kff REAL, c2_alarm TEXT,
                    c3_sp REAL, c3_pv REAL, c3_err REAL, c3_rpm REAL, c3_rpm_pi REAL, c3_rpm_ff REAL,
                    c3_mode TEXT, c3_ff INTEGER, c3_kp REAL, c3_ki REAL, c3_kff REAL, c3_alarm TEXT
                )
                """
            )
            conn.commit()

    def record_telemetry(self, tel: SystemTelemetry, every_n_ticks: int = 2) -> None:
        self._sample_counter += 1
        if self._sample_counter % every_n_ticks != 0:
            return

        c1 = tel.cells["C1"]
        c2 = tel.cells["C2"]
        c3 = tel.cells["C3"]

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO process_history (
                    timestamp, elapsed_sec, q_feed_lpm, feed_profile,
                    c1_sp, c1_pv, c1_err, c1_rpm, c1_rpm_pi, c1_rpm_ff, c1_mode, c1_ff, c1_kp, c1_ki, c1_kff, c1_alarm,
                    c2_sp, c2_pv, c2_err, c2_rpm, c2_rpm_pi, c2_rpm_ff, c2_mode, c2_ff, c2_kp, c2_ki, c2_kff, c2_alarm,
                    c3_sp, c3_pv, c3_err, c3_rpm, c3_rpm_pi, c3_rpm_ff, c3_mode, c3_ff, c3_kp, c3_ki, c3_kff, c3_alarm
                ) VALUES (
                    ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    tel.timestamp, tel.elapsed_sec, tel.q_feed_lpm, tel.feed_profile,
                    c1.sp, c1.pv, c1.error, c1.rpm, c1.rpm_pi, c1.rpm_ff, c1.mode, int(c1.ff_enabled), c1.kp, c1.ki, c1.kff, c1.alarm_status,
                    c2.sp, c2.pv, c2.error, c2.rpm, c2.rpm_pi, c2.rpm_ff, c2.mode, int(c2.ff_enabled), c2.kp, c2.ki, c2.kff, c2.alarm_status,
                    c3.sp, c3.pv, c3.error, c3.rpm, c3.rpm_pi, c3.rpm_ff, c3.mode, int(c3.ff_enabled), c3.kp, c3.ki, c3.kff, c3.alarm_status,
                ),
            )
            # Mantener base acotada a los últimos 10,000 registros
            conn.execute(
                "DELETE FROM process_history WHERE id NOT IN (SELECT id FROM process_history ORDER BY id DESC LIMIT 10000)"
            )
            conn.commit()

    def get_recent_rows(self, limit: int = 50) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM process_history ORDER BY id DESC LIMIT ?", (limit,)
            )
            return [dict(r) for r in cur.fetchall()]

    def get_count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT COUNT(*) FROM process_history")
            row = cur.fetchone()
            return int(row[0]) if row else 0

    def clear_history(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM process_history")
            conn.commit()

    def export_csv_string(self, limit: int = 5000) -> str:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT * FROM process_history ORDER BY id ASC LIMIT ?", (limit,)
            )
            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(cols)
        writer.writerows(rows)
        return buf.getvalue()
