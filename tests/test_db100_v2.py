import struct
from backend.plc_s7 import DB100_TAG_MAP, SiemensS71200Client


def test_db100_v2_map_has_expected_size_and_offsets():
    by_tag = {item["tag"]: item for item in DB100_TAG_MAP}
    assert by_tag["C1_Pump_RPM_PV"]["byte_offset"] == 80
    assert by_tag["C3_Output_RPM"]["byte_offset"] == 100
    assert by_tag["PLC_CycleCounter"]["byte_offset"] == 104
    assert by_tag["PLC_Heartbeat"]["byte_offset"] == 108
    assert by_tag["DB_Version"]["byte_offset"] == 112
    assert max(x["byte_offset"] + (1 if x["type"] == "Bool" else 2 if x["type"] == "Int" else 4) for x in DB100_TAG_MAP) == 122


def test_db100_real_big_endian_decode():
    item = next(x for x in DB100_TAG_MAP if x["tag"] == "C1_PV_mm")
    raw = bytearray(122)
    raw[4:8] = struct.pack(">f", 321.5)
    assert SiemensS71200Client._decode_tag(bytes(raw), item) == 321.5


def test_db100_bool_bit_decode():
    item = next(x for x in DB100_TAG_MAP if x["tag"] == "C3_FF_Enable")
    raw = bytearray(122)
    raw[76] = 1 << 5
    assert SiemensS71200Client._decode_tag(bytes(raw), item) is True


def test_db100_write_rejects_read_only_tag_without_io():
    client = SiemensS71200Client()
    client.connected = True
    class Fake:
        def db_write(self, *args):
            raise AssertionError("No debe escribir")
    client._client = Fake()
    result = client.write_db100_tag("C1_PV_mm", 300.0)
    assert result["status"] == "error"
    assert "no escribible" in result["detail"]


def test_db100_write_rejects_out_of_range_without_io():
    client = SiemensS71200Client()
    client.connected = True
    class Fake:
        def db_write(self, *args):
            raise AssertionError("No debe escribir")
    client._client = Fake()
    result = client.write_db100_tag("C1_SP_mm", 999.0)
    assert result["status"] == "error"
    assert "fuera de rango" in result["detail"]


class FakeSnap7:
    def __init__(self, image):
        self.image = bytearray(image)
        self.writes = []

    def db_read(self, db_number, start, size):
        return self.image[start:start + size]

    def db_write(self, db_number, start, data):
        data = bytes(data)
        self.image[start:start + len(data)] = data
        self.writes.append((db_number, start, data))


def test_db100_read_returns_complete_good_snapshot():
    image = bytearray(122)
    image[0:4] = struct.pack(">f", 22.0)
    image[4:8] = struct.pack(">f", 321.5)
    image[104:108] = struct.pack(">I", 1234)
    image[112:116] = struct.pack(">I", 2)
    image[108] = 0b00000011
    client = SiemensS71200Client()
    client.connected = True
    client._client = FakeSnap7(image)
    result = client.read_db100()
    assert result["status"] == "ok"
    assert result["quality"] == "GOOD"
    assert result["values"]["Q_Feed_LPM"] == 22.0
    assert result["values"]["C1_PV_mm"] == 321.5
    assert result["values"]["PLC_CycleCounter"] == 1234
    assert result["values"]["DB_Version"] == 2
    assert result["values"]["PLC_Heartbeat"] is True
    assert result["values"]["PLC_DataValid"] is True


def test_db100_write_real_encodes_big_endian_and_preserves_range():
    client = SiemensS71200Client()
    client.connected = True
    fake = FakeSnap7(bytearray(122))
    client._client = fake
    result = client.write_db100_tag("C1_SP_mm", 325.5)
    assert result["status"] == "ok"
    assert fake.image[8:12] == struct.pack(">f", 325.5)


def test_db100_write_bool_preserves_other_bits_in_same_byte():
    client = SiemensS71200Client()
    client.connected = True
    image = bytearray(122)
    image[76] = 0b00000101
    fake = FakeSnap7(image)
    client._client = fake
    result = client.write_db100_tag("C2_FF_Enable", True)
    assert result["status"] == "ok"
    assert fake.image[76] == 0b00001101


def test_opcua_and_snap7_maps_have_same_db100_tag_set():
    from backend.opcua_client import OPCUA_TAG_MAP
    snap = {x["tag"]: x["offset"] for x in DB100_TAG_MAP}
    opc = {x["tag"]: x["db"] for x in OPCUA_TAG_MAP}
    assert snap == opc
    assert len(snap) == 39


def test_opcua_telemetry_uses_rpm_process_value_not_setpoint():
    from backend import main
    old_rpm = main.process.pump_rpm_actual["C1"]
    try:
        main.apply_opcua_values({
            "C1_Pump_RPM": 180.0,       # RPM_SP
            "C1_Pump_RPM_PV": 142.5,    # RPM medida
        })
        assert main.process.pump_rpm_actual["C1"] == 142.5
    finally:
        main.process.pump_rpm_actual["C1"] = old_rpm


def test_scl_contains_db100_v2_layout_fields():
    from pathlib import Path
    scl = Path(__file__).resolve().parents[1] / "plc_s7_1200" / "FB_PI_Feedforward_S7_1200.scl"
    source = scl.read_text(encoding="utf-8")
    for tag in (
        "C1_Pump_RPM_PV", "C2_Pump_RPM_PV", "C3_Pump_RPM_PV",
        "C1_Output_RPM", "C2_Output_RPM", "C3_Output_RPM",
        "PLC_CycleCounter", "PLC_Heartbeat", "PLC_DataValid", "PLC_Fault",
        "DB_Version", "C1_Output_AQ", "C2_Output_AQ", "C3_Output_AQ",
    ):
        assert tag in source
    assert "_Reserved_77_79" in source
    assert "_Reserved_109_111" in source
