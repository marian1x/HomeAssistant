"""Pure decoding of the Easyway/ENW battery BLE protocol. No I/O, no HA imports.

The module (74:E9:D8:E7:97:B5, advertises as X07EA...) speaks a length-prefixed stream over a
GATT service. The app's capture (2026-11-24) was reverse-engineered; this is read-only. Framing:

  request  = u32 len | u16 seq | u16 0x0000 | u8 cmd | payload
  response = u32 len | u16 seq | u16 flags   | u8 status(1=ok) | u8 n | sn[n] | u32 count | records
  record   = u32 field_id | u8 type | value      (types: S=i16, I=i32, D=f64, X=u16len+utf8)

cmd 04 lists devices; cmd 05 reads one device by serial. The pack serial ends in '-P' and holds
live cell data; the controller serial holds settings/limits. Writes (cmd 03/09, firmware) are
never produced here.
"""
import struct

CMD_LIST = 4
CMD_READ = 5

# Pack fields (serial '...-P'), confirmed against the app screen on 2026-11-24.
CELL_V_FIRST, CELL_V_LAST = 100400, 101900      # 16 cells, step 100
CELL_T_FIRST = 102100                            # cell temperatures, step 100
PACK = {
    'cells_reported': 100300, 'temps_reported': 102000,
    'current': 102700, 'voltage': 102800, 'remaining_ah': 102900, 'full_ah': 103100,
    'soc': 103200, 'rated_ah': 103300, 'cycles': 103400, 'soh': 103500, 'port_voltage': 103600,
    'mos_temp': 102500, 'ambient_temp': 102600,
}
# Controller fields (base serial). Pairs are (protect/alarm value, recovery value). The charge
# low-temperature pair and the heater pair matter for the cold-morning question; labelled
# cautiously because they are inferred from values, not from app text.
CONTROLLER = {
    'firmware': 900,
    'charge_lowtemp_alarm': 6900, 'charge_lowtemp_alarm_recover': 7000,
    'charge_lowtemp_protect': 7300, 'charge_lowtemp_protect_recover': 7400,
    'heater_on_below': 8300, 'heater_off_above': 8400,
    'charge_current_limit': 9800, 'discharge_current_limit': 10000,
    'clock': 14500, 'live_voltage': 14800, 'live_current': 14900, 'live_power': 15000,
    'live_temp': 15100, 'live_soc': 15200,
}


def build_request(seq, cmd, serial=b''):
    body = struct.pack('>HH', seq, 0) + bytes([cmd])
    if cmd == CMD_READ:
        if isinstance(serial, str):
            serial = serial.encode()
        body += bytes([len(serial)]) + serial
    return struct.pack('>I', len(body)) + body


class Stream:
    """Reassembles length-prefixed frames from arriving notification chunks."""

    def __init__(self):
        self.buf = bytearray()

    def feed(self, chunk):
        self.buf.extend(chunk)
        out = []
        while len(self.buf) >= 4:
            n = int.from_bytes(self.buf[:4], 'big')
            if n == 0 or n > 65535:        # not our framing: resync by dropping a byte
                del self.buf[0]
                continue
            if len(self.buf) < 4 + n:
                break
            out.append(bytes(self.buf[4:4 + n]))
            del self.buf[:4 + n]
        return out


def _records(frame):
    """Yield (field_id, value) from a cmd 05 response; tolerant of unknown trailing types."""
    if len(frame) < 11:
        return
    n = frame[5]
    p = 6 + n
    if p + 4 > len(frame):
        return
    p += 4  # skip count
    end = len(frame)
    while p + 5 <= end:
        fid = struct.unpack('>I', frame[p:p + 4])[0]
        typ = frame[p + 4]
        p += 5
        if typ == 0x58:  # 'X' u16-length utf8
            if p + 2 > end:
                break
            ln = struct.unpack('>H', frame[p:p + 2])[0]
            if p + 2 + ln > end:
                break
            yield fid, frame[p + 2:p + 2 + ln].decode('utf-8', 'replace')
            p += 2 + ln
        elif typ == 0x44:  # f64
            if p + 8 > end:
                break
            yield fid, struct.unpack('>d', frame[p:p + 8])[0]
            p += 8
        elif typ == 0x53:  # i16
            if p + 2 > end:
                break
            yield fid, struct.unpack('>h', frame[p:p + 2])[0]
            p += 2
        elif typ == 0x49:  # i32
            if p + 4 > end:
                break
            yield fid, struct.unpack('>i', frame[p:p + 4])[0]
            p += 4
        elif typ == 0x46:  # f32
            if p + 4 > end:
                break
            yield fid, struct.unpack('>f', frame[p:p + 4])[0]
            p += 4
        elif typ in (0x42, 0x5a, 0x43):  # u8-ish
            yield fid, frame[p]
            p += 1
        elif typ == 0x4c:  # i64
            if p + 8 > end:
                break
            yield fid, struct.unpack('>q', frame[p:p + 8])[0]
            p += 8
        else:
            break


def parse_device(frame):
    """A cmd 05 response -> {'serial', fields{id:value}} or None if it is not one."""
    if len(frame) < 11 or frame[4] != 1:
        return None
    n = frame[5]
    if 6 + n > len(frame):
        return None
    serial = frame[6:6 + n].decode('utf-8', 'replace')
    return {'serial': serial, 'fields': {fid: v for fid, v in _records(frame)}}


def _num(f, key_or_id):
    fid = key_or_id if isinstance(key_or_id, int) else None
    v = f.get(fid)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def pack_reading(fields):
    """Structured, read-only pack view from the '-P' device fields."""
    cells = [fields[i] for i in range(CELL_V_FIRST, CELL_V_LAST + 1, 100)
             if isinstance(fields.get(i), (int, float))]
    ntemp = fields.get(PACK['temps_reported']) or 0
    temps = [fields[CELL_T_FIRST + 100 * k] for k in range(int(ntemp))
             if isinstance(fields.get(CELL_T_FIRST + 100 * k), (int, float))]
    out = {'cells': [round(c, 3) for c in cells], 'cell_temps': [round(t, 1) for t in temps]}
    if cells:
        out['cell_min'] = round(min(cells), 3)
        out['cell_max'] = round(max(cells), 3)
        out['cell_spread_mv'] = round((max(cells) - min(cells)) * 1000, 1)
    for key, fid in PACK.items():
        if key in ('cells_reported', 'temps_reported'):
            continue
        v = fields.get(fid)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[key] = round(v, 3)
    return out


def controller_reading(fields):
    out = {}
    for key, fid in CONTROLLER.items():
        v = fields.get(fid)
        if isinstance(v, str):
            out[key] = v
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[key] = round(v, 2)
    return out


def heater_phase(cell_temp, charge_floor=2, heat_stop=10):
    """The manual's fixed heating bands, for display only. The device decides and the heater
    only runs when the inverter is actively charging; this is the band the temperature is in.
    charge_floor/heat_stop default to the manual's 2 C and 10 C, not the raw BMS fields."""
    if cell_temp is None:
        return 'necunoscut'
    if cell_temp < -20:
        return 'sub domeniul de functionare'
    if cell_temp < charge_floor:
        return 'incalzire, fara incarcare'
    if cell_temp < heat_stop:
        return 'incalzire in timpul incarcarii'
    return 'cald, incalzire oprita'
