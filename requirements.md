# BiDiB2WLED — Requirements and AI handoff

This file is the project specification. An agent with no prior chat history should be able to continue work from this document plus the source tree.

The user of this project typically writes in **German**. The **product default language is English**. Answer the user in the language they use; keep code, YAML keys, API fields, and enum values in English.

Companion user docs: `README.md` (English first, then German). This file is the machine-oriented contract, not a substitute for the README’s Rocrail walkthrough.

---

## 1. Product

BiDiB2WLED is a virtual [BiDiB](https://bidib.org) node (**netBiDiB** over TCP) that drives [WLED](https://kno.wled.ge/) controllers (WS2812 / WS2811-style LEDs) on a model railway.

Host software such as **Rocrail**, BiDiB-Wizard or iTrain does not speak WLED. The host switches ordinary BiDiB accessories. This bridge turns those commands into WLED JSON-API pixel and effect updates.

- Package: `bidib2wled` **0.1.0**
- Python **≥ 3.11**
- License: MIT
- Platforms: Linux, Windows, macOS
- Entry point: `bidib2wled` → `bidib2wled.__main__:main`
- Only persistence: `config.yaml` (the web UI writes it; hand-edits are reloaded)

Simulation (`--simulate`) needs no hardware. Real layouts need WLED on the LAN.

---

## 2. Goals and non-goals

### Goals (implemented)

- Present one BiDiB accessory node to a host (normally as **netBiDiB server** on port **62875**).
- Drive one or more WLED controllers (JSON API, bind by MAC, mDNS discovery).
- Model lighting as logical objects: lamp, house/window, group, sequence, signal, special, vehicle.
- Share a WS2811 pixel across objects via RGB **channel** `r` / `g` / `b` / `rgb`.
- Web UI to claim controllers, identify LEDs, name LEDs, insert/remove LEDs on the bus, create/test/edit/delete objects.
- English YAML + English API. Browser-selected UI language via JSON files. German YAML still **loads**.
- Favicon in the address bar.

### Non-goals (not implemented)

Documented in README as later stages (detail was in `KONZEPT.md`, which is **gitignored** and not in the repo):

- Direct Rocrail RCP / XML client (port **8051**). `adapter.client` exists as a stub only.
- Time automation from a model clock.
- WLED presets / UDP scenes. The bridge orchestrates pixels itself; controller sync should stay off.

Do not implement those unless the user asks.

---

## 3. Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| Web | FastAPI + Uvicorn |
| Models | Pydantic v2 |
| Config | PyYAML |
| HTTP to WLED | aiohttp |
| mDNS | zeroconf / AsyncZeroconf |
| Paths | platformdirs (`user_config_dir("bidib2wled")`) |
| Frontend | Vanilla JS + HTML + CSS (no framework, no bundler) |
| Tests | pytest + pytest-asyncio (`asyncio_mode = auto`) |
| Build | hatchling (`pyproject.toml`) |
| Lint config | ruff line-length 100 (no CI required by the repo itself) |

Runtime dependencies: `aiohttp`, `fastapi`, `uvicorn[standard]`, `pydantic`, `pyyaml`, `zeroconf`, `platformdirs`.

Dev extras: `pytest`, `pytest-asyncio`, `httpx`.

---

## 4. Repository layout

```
bidib2wled/
  pyproject.toml
  README.md                 # user docs, EN then DE
  requirements.md           # this file
  config.example.yaml       # committed template (English keys)
  install.sh                # venv + pip install -e ".[dev]" only
  packaging/bidib2wled.service
  src/bidib2wled/
    __main__.py             # CLI
    config.py               # Pydantic schema, accessories, LED maps
    legacy.py               # German YAML → English on load
    service.py              # lifecycle, status, claim, LED insert/delete
    web.py                  # HTTP API + static mount
    core.py                 # Engine: switch objects, vehicle ticker
    vehicles.py             # blinker/beacon/strobe pixel patterns
    pixels.py               # RGB component math, index shift/delete
    adapters/               # BiDiB constants + netBiDiB TCP
    wled/                   # WLED client, discovery, simulate
    static/                 # UI
      index.html
      app.js                # cache-bust ?v=35
      style.css             # cache-bust ?v=22
      favicon-32.png
      apple-touch-icon.png
      i18n/en.json
      i18n/de.json
  tests/
```

### Do not commit

`.venv/`, `config.yaml`, `config.yaml.bak*`, `KONZEPT.md`, `dist/`, `build/`, caches. See `.gitignore`.

User config lives at `./config.yaml` if present, otherwise `{user_config_dir}/config.yaml`.

---

## 5. How to run and test

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m pytest
bidib2wled --simulate              # http://127.0.0.1:8080
```

CLI:

| Flag | Meaning |
|---|---|
| `--config PATH` | YAML path |
| `--host ADDRESS` | Web bind (YAML default / `0.0.0.0`) |
| `--port N` | Web port (default `8080`) |
| `--simulate` | No HTTP to WLED |
| `-v` | DEBUG logs |

If another instance already occupies 8080, use `--port 8090`.

After changing `app.js` or `style.css`, bump the `?v=` query in `index.html`.

---

## 6. Rules for any AI working on this repo

1. **YAML keys and enum values are English.** Never write `lampen`, `einschalten: nacheinander`, `art: rundum` on save. Load still accepts German via `legacy.py` + Pydantic aliases.
2. **User-entered strings may be any language** (IDs `haus-baecker`, names `Straßenlaterne`, aspect `Halt`).
3. **HTML element IDs are often German** (`l-farbe`, `h-fenster`, `v-kanaele`, `art-fahrzeug`). Do not rename them without updating every `app.js` reference (`LED_GROUPS`, `EDIT_META`, handlers).
4. **`<select>` option `value`s stay English** (`random`, `beacon`, `channels`). Labels come from i18n.
5. **New UI strings** go into **every** file under `static/i18n/`. `test_language_files_cover_the_same_keys` requires identical key sets. Adding a language = adding `static/i18n/<code>.json` (2-letter stem). No Python change needed; `GET /api/languages` globs the folder.
6. **Default UI language is English.** `initI18n()` uses `navigator.languages` (first two letters) against supported files; otherwise `en`.
7. **Python may keep German compatibility properties** (`cfg.lampen`, `house.fenster`, `vehicle.kanaele`) for tests and older call sites. New code should use English fields (`cfg.lamps`, `house.windows`, `vehicle.channels`).
8. **LED indices in YAML are 0-based.** The LED-name text editor and UI lists are 1-based (`LED 1` = index 0).
9. **BiDiB accessories are 0-based.** Rocrail address = accessory + 1, port always 0, protocol Default, Accessory on.
10. **Do not invent Rocrail XML, model-clock, or WLED-preset features.**
11. **Tests may feed German YAML as input.** That does not authorize emitting German keys.
12. When the UI changes, verify in the browser (or curl + pytest if no browser). Exercise Status, Setup, Objects, YAML, and any other tab that shares the changed state.

---

## 7. Architecture

```
Host (Rocrail / Wizard / iTrain)
        │  netBiDiB TCP :62875
        ▼
 NetBidibAdapter ── pairing, ACCESSORY_SET/GET/NOTIFY
        │
        ▼
     Engine  ── desired aspect per object, house/sequence timing, vehicle ticker
        │
        ▼
    WledPool ── /json/info, /json/cfg, /json/state, overlay segments
        │
        ▼
   WLED controller(s)
```

Web UI (FastAPI `/` + `/static` + `/api/*`) talks to `Service`, which owns `Engine`, `WledPool`, `WledDiscovery`, `NetBidibAdapter`.

`Service.start()`:

1. `engine.load(config)`
2. `bidib.configure(config)`
3. `ensure_accessories()` (auto-fill map, persist if changed)
4. Generate `unique_id` from adapter UID if missing
5. Start pool + mDNS browse `_wled._tcp`
6. Bind configured controllers
7. Start netBiDiB
8. Advertise `_http._tcp` and (if server enabled) `_bidib._tcp`
9. Rebind loop (`discovery.interval`, default 30s) and YAML mtime watch (**2 seconds**)

`PUT /api/config` validates the full document, saves English YAML, then `apply_config()`. Changing netBiDiB port/mode/enabled restarts the adapter.

---

## 8. Configuration schema

Source of truth: `src/bidib2wled/config.py`. Load: `AppConfig.model_validate` after `migrate_legacy_config`. Save: `model_dump(by_alias=False, exclude_none=True)` plus `_omit_empty_channels` (drops empty signal `channels`, default vehicle `steps: auto`, empty controller `names`). Backup: `config.yaml.bak`. Atomic write via `.tmp`.

### 8.1 Top level

```yaml
adapter: { netbidib: {...}, client: {...} }
discovery: { mdns: true, interval: 30s, timeout: 90s }
web: { host: 0.0.0.0, port: 8080 }
controller: []          # list of named WLED devices
lamps: {}
houses: {}
groups: {}
sequences: {}
signals: {}
special: {}
vehicles: {}
```

German top-level aliases on load: `lampen`, `haeuser`, `gruppen`, `sequenzen`, `signale`, `spezial`, `fahrzeuge`, `erkennung`. `adapter.rocrail` migrates to `adapter.client`.

### 8.2 Enums (canonical English)

| Field | Values |
|---|---|
| `channel` | `r`, `g`, `b`, `rgb` |
| `turn_on` | `immediate`, `sequential`, `random` (default `random`) |
| `order` | `defined`, `random` (default `random`), or a list of group IDs |
| vehicle `type` | `continuous`, `blinker`, `beacon`, `strobe`, `double_strobe` |
| vehicle `steps` | `auto`, `leds`, `channels` (default `auto`; omitted on save when `auto`) |
| netBiDiB `mode` | `server`, `client` |

Load aliases (also in `legacy.py` / parse helpers):

- channel: `rot`/`red`→`r`, `gruen`/`grün`/`green`→`g`, `blau`/`blue`→`b`, `alle`/`all`→`rgb`
- turn_on: `sofort`→`immediate`, `nacheinander`→`sequential`, `zufällig`→`random`
- order: `definiert`→`defined`
- type: `dauerlicht`/`dauer`/`steady`→`continuous`; `warnblinker`/`blinker-links`/`blinker-rechts`→`blinker`; `rundumlicht`/`rundum`→`beacon`; `blitz`→`strobe`; `doppelblitz`/`double`→`double_strobe`
- steps: `automatisch`→`auto`; `pixel`/`pixeln`→`leds`; `kanaele`/`kanäle`/`anteile`/`rgb`→`channels`

Colors: `RRGGBB` without `#`. Durations: number or `"Ns"`. MAC: 12 hex digits → `aa:bb:cc:dd:ee:ff`.

### 8.3 Adapter

`adapter.netbidib`:

| Field | Default | Load aliases |
|---|---|---|
| `enabled` | `true` | `aktiv` |
| `mode` | `server` | `modus` |
| `port` | `62875` | |
| `host` | `null` | client mode only |
| `node_name` | `BiDiB2WLED` | `knotenname` |
| `unique_id` | generated | 14-char hex |
| `trusted` | `[]` | paired host UIDs |
| `pairing_timeout` | `30.0` | |
| `accessories` | `{}` | `{int: object_id}` BiDiB index → object |

`adapter.client` (future, unused): `enabled` false, `host` 127.0.0.1, `port` 8051, `id_prefix` `wled-`.

### 8.4 Controller

```yaml
controller:
  - name: dorf          # required, referenced by objects
    mdns: wled-dorf     # optional
    mac: aa:bb:...      # bind key
    ip: 192.168.1.51
    port: 80
    leds: 80            # last known WLED length
    names:              # display names, 0-based
      - { led: 0, name: Straßenlaterne }          # led → start=end
      - { start: 2, end: 6, name: Haus3 }
      - { led: 11, channel: r, name: Halt }
```

`names` aliases: `namen`; `von`/`bis` → `start`/`end`; `anteil` → `channel`.

### 8.5 Object models

**Lamp** `lamps.<id>`: `controller`, `leds` (min 1), `color` FFFFFF, `brightness` 180 (0–255), `channel` rgb.

**House** `houses.<id>`: `controller`, `windows` `{ <window_id>: { leds, color, brightness, channel } }`, `turn_on`, `delay` `["2s","8s"]`, `night_probability` 1.0.

Window runtime ID: `{house_id}.{window_id}`. Windows are **not** auto-assigned BiDiB accessories.

**Group** `groups.<id>`: `members` (object IDs or other groups).

**Sequence** `sequences.<id>`: `groups`, `order`, `delay` `["10s","120s"]`.

**Signal** `signals.<id>`:

```yaml
aspects:
  0: { name: Halt, leds: { 12: "FF0000" }, channels: { 12: r } }
  1: { name: Fahrt, leds: { 12: "00FF00" }, channels: { 12: g } }
```

`channels` may be omitted (means `rgb`). `null` channels are dropped on load.

**Special** `special.<id>`: `controller`, `leds`, `effect` 0, `palette` 0, `speed` 128, `intensity` 128, `color`, `brightness` optional (1–255), `channel`. Effects apply to the **whole pixel**.

**Vehicle** `vehicles.<id>`:

```yaml
channels:
  licht: { leds: [30], channel: rgb, color: "FFFFCC", type: continuous }
  blinker-l: { leds: [31], channel: r, color: "FF8000", type: blinker }
modes:                    # optional; defaults computed if empty
  0: { name: Off, channels: [] }
  1: { name: Lights, channels: [licht] }
blink_period: 0.75s
beacon_step: 0.12s
```

Default modes when `modes` is empty:

| Aspect | Name | Channels |
|---|---|---|
| 0 | Off | none |
| next | Lights | all `continuous` |
| next | Hazards | continuous + blinker |
| next | Emergency | continuous + beacon/strobe/double_strobe |
| fallback | On | all channels if nothing else but Off |

Mode channel names must exist. `resolved_modes()` returns YAML modes or these defaults.

### 8.6 Validation (`AppConfig._refs`)

- Every lamp/house/signal/special/vehicle `controller` must exist in `controller[].name`.
- Group members must be known objects or groups. Sequence `groups` must exist.
- Accessory map values must be known object IDs (including windows if someone assigned them by hand).
- Inserting LEDs must not exceed the WLED-reported length. Deleting must not leave an object with zero LEDs.

### 8.7 Accessories

`accessory_map()` keeps fixed `adapter.netbidib.accessories` entries, then assigns the lowest free index to remaining **switchable** IDs: lamps, houses, groups, sequences, signals, special, vehicles. Windows are skipped.

`set_accessory(id, 0..255)` swaps on collision. UI column **Address** is this index. Rocrail uses **index + 1**.

`object_kind(id)` slugs: `lamp`, `house`, `window`, `group`, `sequence`, `signal`, `special`, `vehicle`.

`aspect_count`: signal/vehicle = `max(keys)+1` (or 2); else 2.

`host_setup_info(kind, accessory)` returns English Rocrail hints (`address N+1`, port 0, bus 0, protocol Default, accessory on). Windows: “no own address – switch the house”.

---

## 9. Switching semantics

`Engine.switch(object_id, aspect, source=...)` cancels an in-flight task for the same object, sets `in_progress` / `pending_aspect`, then:

| Kind | aspect 0 | aspect ≠ 0 |
|---|---|---|
| lamp | clear `channel` on `leds` | set color/brightness |
| window `{house}.{win}` | clear that window | set that window |
| house | stagger-off windows (`random` shuffles, else reverse) | pick windows by `night_probability` (at least one if any exist); `random` shuffles; `sequential`/`immediate` keep order; delay between windows unless `immediate` |
| group | switch each member | same |
| sequence | members off in reverse (or shuffle if `order: random`) | members on in defined/random order; delay `delay_range` between members; a new command aborts the running sequence |
| signal | (any valid aspect) | clear all aspect LEDs first, then set the chosen aspect (Halt and Fahrt may share one WS2811 via `r`/`g`) |
| special | `clear_effect` + clear channel | `apply_effect` overlay segment |
| vehicle | mode 0 / empty channels: clear | set `_vehicle_aspects` and tick patterns |

Unknown object → `KeyError`. Unknown signal/vehicle aspect → error.

`ObjectState.reported_aspect()` is `pending_aspect` while in progress, else `aspect`. Status JSON: lamps/houses/groups/sequences/specials expose `on` bool; signals and vehicles expose `on: null` plus `states: [{value, name}]`.

Vehicle ticker (50 ms) runs while any active mode has a non-`continuous` channel. Blinker periods are desynced per object (`SHA-256` of ID, ±22% around `blink_period`, min 0.2 s) so several cars do not blink in lockstep; left/right on the **same** vehicle stay in phase.

Beacon `steps`:

| `steps` | Meaning |
|---|---|
| `channels` | Walk R→G→B per LED (one WS2811 + `channel: rgb` = 3-step beacon) |
| `leds` | Walk whole pixels (selected channels together) |
| `auto` | One LED with several components → channels; else leds |

Special effects are overlay WLED segments after hardware output segments. Stale overlays are deleted explicitly. Do **not** create per-house segments in the WLED UI.

Identify: blink one global LED white, 4× 0.25 s.

Pixel writes only touch selected RGB components (`set_components` / `clear_components`) so three objects can share one chip.

---

## 10. HTTP API

Mounted by `create_app(service)` in `web.py`. JSON uses English keys.

| Method | Path | Body | Result |
|---|---|---|---|
| GET | `/` | | `index.html` |
| GET | `/static/*` | | UI assets |
| GET | `/api/status` | | status dict (below) |
| GET | `/api/config` | | full config dump |
| PUT | `/api/config` | full config object | validated dump |
| POST | `/api/reload` | | `{ok: true}` from disk |
| GET | `/api/discovery` | | `{unbound: [WledInfo, …]}` |
| POST | `/api/controllers/claim` | `{name, mac?, mdns?, ip?, port=80, leds?}` | `{ok: true}` |
| POST | `/api/controllers/manual` | same as claim | `{ok: true}` |
| POST | `/api/switch` | `{object_id, aspect=1}` | `{ok: true}` |
| POST | `/api/identify` | `{controller, index, output=0}` | `{ok: true}` |
| POST | `/api/address` | `{object_id, address 0–255}` | full status |
| POST | `/api/leds/insert` | `{controller, output=0, after≥-1, count 1–255}` | result + status |
| POST | `/api/leds/delete` | `{controller, output=0, start≥0, count 1–255}` | result + status |
| POST | `/api/pairing/accept` | | `{ok: "pairing"}` |
| POST | `/api/pairing/reject` | | `{ok: "rejected"}` |
| GET | `/api/languages` | | `{languages: ["de","en"], default: "en"}` |

Errors: HTTP 400 with exception text.

### Status shape (important keys)

```
config_path, wizard (true if no controllers)
bidib: enabled, mode, port, node_name, unique_id, logged_on, sessions,
       trusted[], pairing_open, pending|{uid,prod,user}, peers[], accessories
controllers[]: name, mac, mdns, ip, port, url, leds, outputs[{id,start,len,pin,label}],
               reachable, simulate, effects[], palettes[],
               warnings[]   # keys: warn.udp_recv | warn.udp_send | warn.dmx
objects[]: id, kind, kind_label, on, state, in_progress, error,
           states|null, accessory, address, info[{program,text}]
usage: leds, channels, objects
```

Frontend **rebuilds** output labels from `id/start/len/pin` via i18n (`output.name` = “Output {n}” / “Ausgang {n}”). Backend `label` is English (`Output 1 (GPIO 16, 10 LEDs, Index 0–9)`). Warnings are i18n keys, not prose.

The YAML tab in the UI shows **JSON**, not YAML text.

---

## 11. Web UI

Tabs: **Status** | **Setup** (`data-tab="wizard"`) | **Objects** | **YAML** (`#tab-config`).

Setup: adapter → claim/manual controllers → identify LED → insert/remove bus LEDs → LED names textarea (`LED1 = street lamp`, `3-7 = House3`, `12r = Halt`).

Objects: one form per type. Save does `GET /api/config`, mutates English keys, `PUT /api/config`. Used LEDs/channels are marked. Vehicle **Beacon steps** (`#v-schritte-wrap`) is shown only when type is `beacon` (CSS + JS).

i18n attributes: `data-i18n`, `data-i18n-placeholder`, `data-i18n-title`, `data-i18n-aria`. `t(key, {var})` substitutes `{var}`.

Favicon: `/static/favicon-32.png` (32×32) and `apple-touch-icon.png` (180×180), sourced from the OpenDeck RocRail plugin icon.

Refresh: about 4 s, paused while the user edits inputs (except clicks inside `#objects` that are not address fields).

### Known UI bug

`loadVehicle()` reads `vehicle.modi`. The API returns `modes`. Editing an existing vehicle therefore often **does not fill the modes textarea** and falls back to default mode lines. Saving still writes `modes` correctly. Fix: read `vehicle.modes || vehicle.modi`. Do not “fix” by making the API emit `modi`.

---

## 12. netBiDiB and Rocrail

- Default: **server** on **62875**. Client mode only if the bridge must connect to an existing netBiDiB server.
- Protocol 0.8, product `BiDiB2WLED`, product id `0x2B01`, class accessory, VID `0x0000`.
- UID: `[0x04, 0x00, VID_lo, VID_hi, serial_lo, serial_hi]`; hex in YAML is 14 chars.
- Pairing: unknown host → pending banner; **Pairing mode** trusts the UID (`adapter.netbidib.trusted`); **Reject** sends unpaired. Only one host should log on at a time.
- The bridge understands **accessory commands only**, not LC ports. Rocrail: Accessory ticked, protocol **Default**, port **0**, address **BiDiB+1**.
- Signals and multi-mode vehicles are Rocrail **signals**; lamps/houses/groups/sequences/specials are **outputs**.
- Engine status callbacks emit `MSG_ACCESSORY_NOTIFY` (WAIT while in progress, then DONE) so Rocrail symbols leave “in progress”.
- Features: accessory count (max 127), surveilled, string size 24.

Full Rocrail click-path is in `README.md`. Do not invent a second transport.

---

## 13. WLED integration

Used HTTP:

| Call | Path |
|---|---|
| GET | `/json/info` |
| GET | `/json/cfg` (outputs `hw.led.ins`, sync/DMX warnings) |
| GET | `/json/eff`, `/json/pal` |
| POST | `/json/state` |

`state` body: frozen hardware segments (one per output) with per-LED hex in `"i"`; overlay segments for specials (`frz: false`). Simulate: no HTTP, default 80 LEDs, two fake outputs (GPIO 16 and 2), canned effect/palette names.

WLED prep (user): set LED type/GPIO/count, boot preset dark, **disable** UDP sync / E1.31. Do not create layout segments in WLED.

mDNS browse: `_wled._tcp.local.`. Advertise: `BiDiB2WLED._http._tcp` and `{node_name}._bidib._tcp`.

---

## 14. LED bus maintenance

**Insert:** raise WLED length first. `after` is the local 0-based index on the output (`-1` = before LED 1). All object addresses and LED names at `output.start + after + 1` and later increment. Cannot exceed WLED count.

**Delete:** first missing local LED + count. Later addresses decrement. A smaller WLED length does **not** block delete (difference is shown so several gaps can be fixed in sequence). Objects that would lose all LEDs are rejected.

Helpers: `pixels.shift_*` / `delete_*`; `AppConfig.shift_controller_leds` / `delete_controller_leds`.

---

## 15. Tests

`python -m pytest` (pythonpath `src`).

| File | Covers |
|---|---|
| `test_config.py` | schema, accessories, Rocrail +1, LED names, insert/delete, i18n key parity, German YAML saves as English |
| `test_engine.py` | simulate switching: lamp channels, house/window, signal same-LED Halt/Fahrt, sequence, special, vehicle ticker (German YAML input) |
| `test_insert.py` | service insert/delete vs WLED length |
| `test_pixels.py` | RGB components, shift/delete |
| `test_protocol.py` | netBiDiB encode/decode, UID, framing |
| `test_vehicles.py` | beacon steps, blinker desync, channel merge |
| `test_wled_outputs.py` | multi-output indexing, state body, warning keys, simulate |

Add tests when changing schema, switching, protocol, or i18n keys.

---

## 16. Packaging and service

`packaging/bidib2wled.service`: user `bidib2wled`, `ExecStart=/usr/bin/bidib2wled --config /etc/bidib2wled/config.yaml`, restart on failure. Adjust `ExecStart` for venv installs.

`install.sh` only creates a venv and `pip install -e ".[dev]"`. Production steps are in the README.

Wheel force-includes `src/bidib2wled/static`.

---

## 17. Language and docs contract

- README: English section first, then `# BiDiB2WLED (Deutsch)`. The German README YAML example may still show a few mixed keys; **code and `config.example.yaml` are English-only**.
- CLI help and log messages: English.
- Module docstrings may still be German; new ones should be English.
- UI: `en.json` / `de.json` (~307 keys). Browser `de` / `de-DE` → German strings; YAML/API remain English (`turn_on: random` even if the dropdown label is “zufällig”).

---

## 18. Ports

| Port | Role |
|---|---|
| 8080/tcp | Web UI |
| 62875/tcp | netBiDiB node |
| 80 | WLED HTTP (per controller, configurable) |
| 8051 | reserved for future Rocrail client (unused) |

Firewall: 8080 and 62875 inbound if the host is on another machine.

---

## 19. Change checklist

When adding an object field:

1. English name on the Pydantic model; German `validation_alias` + `legacy.py` map if old files exist.
2. Engine / vehicles / pixels if it affects light.
3. `app.js` save/load with English keys; keep German element IDs unless you update all references.
4. i18n keys in **en.json and de.json**.
5. Tests (German input still OK).
6. README example if users must see the field.
7. Bump `app.js?v=` / `style.css?v=` if static files changed.

When adding a language: add `static/i18n/<code>.json` with the same keys as `en.json`.

---

## 20. Pointers into the code

| Topic | File |
|---|---|
| Models, accessories, LED maps | `src/bidib2wled/config.py` |
| German → English migration | `src/bidib2wled/legacy.py` |
| Switch engine | `src/bidib2wled/core.py` |
| Vehicle patterns | `src/bidib2wled/vehicles.py` |
| HTTP API | `src/bidib2wled/web.py` |
| Process / status | `src/bidib2wled/service.py` |
| BiDiB TCP | `src/bidib2wled/adapters/netbidib.py` |
| WLED + simulate | `src/bidib2wled/wled/__init__.py` |
| UI + i18n | `src/bidib2wled/static/app.js`, `static/i18n/*.json` |
