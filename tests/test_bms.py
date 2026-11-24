"""Pure decode of the battery BLE protocol: framing, TLV, pack/heater logic. No HA, no I/O."""
import importlib.util
import struct
from pathlib import Path

spec = importlib.util.spec_from_file_location('bms', Path(__file__).resolve().parents[1] / 'ha/custom_components/home_energy_policy/bms.py')
bms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bms)


def rec(fid, typ, value):
    if typ == 0x44:
        return struct.pack('>IB d', fid, typ, value)
    if typ == 0x53:
        return struct.pack('>IB h', fid, typ, value)
    if typ == 0x49:
        return struct.pack('>IB i', fid, typ, value)
    if typ == 0x58:
        b = value.encode()
        return struct.pack('>IB H', fid, typ, len(b)) + b
    raise ValueError(typ)


def response(serial, records):
    sn = serial.encode()
    body = struct.pack('>HHB', 1, 1, 1) + bytes([len(sn)]) + sn + struct.pack('>I', len(records))
    for fid, typ, value in records:
        body += rec(fid, typ, value)
    return body


def framed(body):
    return struct.pack('>I', len(body)) + body


def test_pack_reading_cells_temps_and_scalars():
    recs = [(bms.PACK['cells_reported'], 0x53, 16)]
    volts = [3.185, 3.189, 3.182, 3.176, 3.18, 3.19, 3.19, 3.191, 3.186, 3.184, 3.177, 3.185, 3.187, 3.183, 3.183, 3.179]
    for i, v in enumerate(volts):
        recs.append((bms.CELL_V_FIRST + 100 * i, 0x44, v))
    recs.append((bms.PACK['temps_reported'], 0x53, 4))
    for i, t in enumerate([11.0, 12.2, 11.9, 12.2]):
        recs.append((bms.CELL_T_FIRST + 100 * i, 0x44, t))
    recs += [(bms.PACK['current'], 0x44, -143.0), (bms.PACK['voltage'], 0x44, 50.95),
             (bms.PACK['soc'], 0x44, 64.4), (bms.PACK['soh'], 0x44, 100.0), (bms.PACK['cycles'], 0x49, 67)]
    dev = bms.parse_device(response('00EY3126040204140150-P', recs))
    assert dev['serial'].endswith('-P')
    r = bms.pack_reading(dev['fields'])
    assert len(r['cells']) == 16 and r['cells'][3] == 3.176
    assert r['cell_spread_mv'] == 15.0 and r['cell_min'] == 3.176 and r['cell_max'] == 3.191
    assert r['cell_temps'] == [11.0, 12.2, 11.9, 12.2]
    assert r['soc'] == 64.4 and r['soh'] == 100.0 and r['cycles'] == 67 and r['current'] == -143.0


def test_controller_and_heater_phase_match_the_manual():
    recs = [(bms.CONTROLLER['firmware'], 0x58, 'V12.05'), (bms.CONTROLLER['heater_on_below'], 0x44, 0.0),
            (bms.CONTROLLER['heater_off_above'], 0x44, 10.0), (bms.CONTROLLER['charge_current_limit'], 0x44, 157.0)]
    dev = bms.parse_device(response('00EY3126040204140150', recs))
    c = bms.controller_reading(dev['fields'])
    assert c['firmware'] == 'V12.05' and c['heater_off_above'] == 10.0
    # Manual's bands: heats-only below 2, heats-while-charging 2..10, stops above 10.
    assert bms.heater_phase(-25) == 'sub domeniul de functionare'
    assert bms.heater_phase(1.5) == 'incalzire, fara incarcare'
    assert bms.heater_phase(2.6) == 'incalzire in timpul incarcarii'
    assert bms.heater_phase(12) == 'cald, incalzire oprita'
    assert bms.heater_phase(None) == 'necunoscut'


def test_request_builder_matches_the_captured_app_frames():
    assert bms.build_request(1, bms.CMD_LIST).hex() == '000000050001000004'
    r = bms.build_request(2, bms.CMD_READ, '00EY3126040204140150-P')
    assert r.hex().startswith('0000001c00020000051630304559')  # len 0x1c, cmd05, n=0x16


def test_stream_reassembles_fragments_and_resyncs_on_garbage():
    body = response('00EY3126040204140150-P', [(bms.PACK['soc'], 0x44, 50.0)])
    wire = framed(body)
    st = bms.Stream()
    got = []
    for i in range(0, len(wire), 7):      # arbitrary fragmentation like BLE notifications
        got += st.feed(wire[i:i + 7])
    assert len(got) == 1 and got[0] == body
    # A spurious leading byte must not wedge the parser for the next good frame.
    st2 = bms.Stream()
    assert st2.feed(b'\xff' + wire) and st2.feed(wire)


def test_parse_device_rejects_non_read_frames():
    assert bms.parse_device(b'\x00\x01\x00\x00\x08\x00') is None   # a status/ack frame, not a read
    assert bms.parse_device(b'\x00') is None
