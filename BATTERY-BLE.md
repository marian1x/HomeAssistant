# Easyway UNIV-16kWh (WP) – Bluetooth protocol notes

These notes come from an Android HCI capture of the ENW BMS app (RaymonIoT, `com.energy.ejbms`)
taken on 2026-11-24. They are not vendor documentation. The capture also contains a firmware
update and write commands. A local reader may send ONLY the read request described below.

## Transport

- BLE peripheral `X07EA21112D005FD` (`74:E9:D8:E7:97:B5`), the battery's WiFi/BT module.
- Custom 128-bit service. The app writes the value of ATT handle `0x0016` (Write Request) and
  receives Indications on handle `0x0013`. It enables them with CCCD handles `0x0014` and `0x0004`
  (value `0x0002`). Handles may change after firmware updates, so discover them by UUID.
- Messages form a byte stream that can span several indications. Each frame starts with a
  `u32` big-endian length, followed by that many bytes.

## Frames

Request (app to battery):

```
u32 len | u16 seq | u16 0x0000 | u8 cmd | payload
```

Response (battery to app):

```
u32 len | u16 0x0000 | u16 seq | u8 status(1=ok) | payload
```

Commands seen in the capture:

| cmd | Meaning | Payload | Safe |
|-----|---------|---------|------|
| 04 | List devices | none | read |
| 05 | Read one device | `u8 n` + SN (ASCII) | read |
| 03 | Start firmware upgrade | SN + `06 bf 00 00 02 e8 db` | NEVER |
| 09 | Firmware chunk | Intel HEX text | NEVER |

There are two devices:

- `00EY3126040204140150` is the controller: settings and limits, 181 fields.
- `00EY3126040204140150-P` is the pack: live values, 175 fields.

## Read payload (cmd 05 response)

The payload is `u8 n` + SN, then `u32 count`, then `count` records. Each record is
`u32 field_id`, `u8 type`, value:

- `S`: i16
- `I`: i32
- `D`: f64
- `X`: u16 length + UTF-8 text

All numbers are big-endian.

### Pack fields

Pack fields were identified by matching them against the app's own screen.

| id | value |
|----|-------|
| 100100 | pack SN |
| 100300 | cell count (16) |
| 100400-101900 | cell 1..16 voltage, V |
| 102000 | temperature sensor count (4) |
| 102100-102400 | cell temperatures 1..4, °C |
| 102500 | probably the MOS/power-stage temperature, °C. It rose under 143 A. |
| 102600 | probably the board/ambient temperature, °C |
| 102700 | current, A (negative = discharge) |
| 102800 | total voltage, V |
| 102900 | remaining capacity, Ah |
| 103100 | full capacity, Ah (319.2) |
| 103200 | SOC % |
| 103300 | rated capacity, Ah (314) |
| 103400 | cycles |
| 103500 | SOH % |
| 103600 | port voltage, V |
| 103700-103806 | unidentified |
| 103900-107708 | status, alarm and protection bits (all 0 in the capture) |

### Controller fields

The controller fields below are inferred from their values and pairs, not confirmed by the app.

| id | value |
|----|-------|
| 900 | firmware version |
| 4700-5600 | cell voltage alarm/protection thresholds and recovery values |
| 5700-6400 | pack voltage alarm/protection thresholds and recovery values |
| 6500-9600 | temperature thresholds and recovery values, in pairs |
| 6900/7000 | charge low-temperature alarm 3 °C, recovery 5 °C |
| 7300/7400 | charge low-temperature protection 0 °C, recovery 2 °C |
| 8300/8400 | 0 / 10 °C, possibly the heater start/stop. This is unconfirmed. |
| 9700/9800 | charge overcurrent 210 A, charge limit 157 A |
| 9900-10300 | discharge and short-circuit current limits |
| 14500 | BMS clock (about 6 h ahead in the capture) |
| 14800-15200 | live summary: voltage, current, power W, temperature, SOC |


## Read-only BLE reader (built 2026-11-24)

HA custom component modules `bms.py` (pure decode, tested in `tests/test_bms.py`) and
`bms_ble.py` (HA Bluetooth client). Runs on the HA Pi4 (RSSI -60..-73 dBm; the Pi5 USB BT
adapter will not power on). GATT service `e31c42f9-dd47-45bf-81eb-2b735d613659`, write char
`...365b`, indicate char `...365a` (stable UUIDs, survive firmware changes). Each poll (180 s)
connects, sends cmd 04 then cmd 05 for the pack and controller, parses, then DISCONNECTS so
the ENW phone app can still use Bluetooth between polls (one connection at a time). Never
writes. History in `/config/home_energy_policy_bms.db`. Exposed via websocket
`home_energy_policy/bms` and `GET /casa/api/battery/bms`; shown in the battery panel
(`src/Battery.tsx` BmsSection: 16 cells, cell temps, heater phase, read-only BMS settings).
Verified live: 16 cells, ~10-15 mV spread, 4 temps, heater phase from the manual's bands.

## Heating logic (from the official WP manual, authoritative)

Automatic, fixed: < -20 C below range; -20..2 C heats only (no charge); 2..10 C heats WHILE
charging; > 10 C charge, heating stops. The heater does NOT use battery power, needs the
inverter actively charging (external voltage > pack voltage) and normal inverter comms. So it
only runs when solar/grid is pushing charge; a cold pre-dawn pack with no charge source does
not heat. No user-settable heater threshold is needed or exposed; the dealer/installer
password is not in the manual and is not needed for this. Manual saved at the owner's
`Desktop/bt_logs/UNIV-16kWh-WP-User-Manual.pdf`.