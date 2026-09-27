# BiDiB2WLED

Virtual [BiDiB](https://bidib.org) node (**netBiDiB**) that drives [WLED](https://kno.wled.ge/) controllers with WS2812-style LEDs on a model railway.

Model-railway software such as **Rocrail**, BiDiB-Wizard or iTrain does not speak WLED. BiDiB2WLED sits in between: the host switches ordinary BiDiB accessories, and the bridge turns that into LED commands.

Runs on **Linux**, **Windows** and **macOS** (Python 3.11 or newer).

The default language of the tool is **English**. The web UI follows the browser language when a language file exists (`src/bidib2wled/static/i18n/<code>.json`); otherwise it falls back to English. Add another language by adding a JSON file next to `en.json` and `de.json`. YAML keys and enum values are always English. Only user-entered strings (object IDs, names such as *Straßenlaterne* or *Halt*) may be in another language.

## What you can do with it

| Object | Meaning | Switching |
|---|---|---|
| **Lamp** | one or more LEDs (lantern, single room) | off / on |
| **House** | several windows with color and turn-on behaviour (immediate, sequential, random) | the house as a whole; windows also individually |
| **Group** | several lamps/houses (e.g. a street) | all members together |
| **Sequence** | staggered on or off with pauses | on = order “on”, off = reverse |
| **Signal** | several aspects (Halt, Proceed, …), LEDs/colors per aspect (WS2811: also R/G/B of the same LED) | aspect 0, 1, 2, … |
| **Special** | built-in WLED effect (fire, candle, …) on the chosen LEDs | off / on |
| **Vehicle** | static model with light channels (headlights, indicators, beacon, …) | mode (Off, Lights, Hazards, Emergency, …) |

Also: find WLED devices on the network, identify LEDs on the model (blink them), name LEDs, insert or remove LEDs on the bus (later addresses and names shift), create and test everything in the web UI, run it as a service.

![Status page](status.png)

![Object configuration](objects.png)

## Requirements

- Python 3.11 or newer (Debian/Ubuntu: `sudo apt install python3-venv python3-pip`)
- WLED controllers on the same network (for real LEDs). Without hardware: `--simulate`
- Optional: host software with netBiDiB, e.g. [Rocrail](https://wiki.rocrail.net/), BiDiB-Wizard, iTrain

## Install and start

In the project directory:

```bash
python3 -m venv .venv
```

Activate the environment:

| System | Command |
|---|---|
| Linux / macOS | `source .venv/bin/activate` |
| Windows (cmd) | `.venv\Scripts\activate.bat` |
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |

```bash
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Simulation (no real WLED devices, UI for trying it out):

```bash
bidib2wled --simulate
```

or `python -m bidib2wled --simulate`.

Then in the browser: [http://127.0.0.1:8080](http://127.0.0.1:8080)

With real controllers (search for `_wled._tcp`):

```bash
bidib2wled
```

| Option | Meaning |
|---|---|
| `--config PATH` | YAML file. Default: `./config.yaml` if present, otherwise the user config directory |
| `--host ADDRESS` | Web bind, default `0.0.0.0` (all interfaces) |
| `--port N` | Web port, default `8080` |
| `--simulate` | no HTTP to WLED, pixels only internally |
| `-v` | verbose logs |

Tests:

```bash
python -m pytest
```

Optional package build:

```bash
python -m pip install build
python -m pip install -e .
python -m build
```

Artifacts are in `dist/`. Install with `pip install dist/bidib2wled-*.whl`.

## Start and stop scripts (Linux / macOS)

`start.sh` and `stop.sh` in the project directory start and stop the bridge without typing the venv path each time.

```bash
./start.sh          # start in the background
./stop.sh           # stop
./start.sh --simulate   # extra arguments are passed through
```

`start.sh` uses `.venv/bin/bidib2wled` if it exists, otherwise `bidib2wled` from the PATH. It writes the process ID to `bidib2wled.pid` and the output to `bidib2wled.log`; a second start while it is running does nothing. `./start.sh --foreground` runs in the foreground instead (for systemd or a terminal). `stop.sh` sends SIGTERM and after 15 seconds SIGKILL.

Settings via environment variables:

| Variable | Meaning |
|---|---|
| `BIDIB2WLED_CONFIG` | YAML file. Default: `config.yaml` in the project directory if present |
| `BIDIB2WLED_HOST` | Web bind address |
| `BIDIB2WLED_PORT` | Web port |
| `BIDIB2WLED_ARGS` | extra arguments, e.g. `"--simulate -v"` |
| `BIDIB2WLED_PIDFILE` | pid file |
| `BIDIB2WLED_LOG` | log file |

```bash
BIDIB2WLED_PORT=8099 BIDIB2WLED_ARGS="--simulate" ./start.sh
tail -f bidib2wled.log
```

## Linux: start automatically at boot

With systemd (Debian, Ubuntu, Raspberry Pi OS, Fedora, …) the bridge starts at boot, restarts after a crash and logs to the journal. Two variants – pick one.

### Variant A: project directory with venv (recommended for a Raspberry Pi)

The service runs `start.sh --foreground` under your own user. Nothing is copied; the config stays in the project directory.

```bash
cd ~/BiDiB2WLED                 # your project directory
python3 -m venv .venv
.venv/bin/pip install -e .
./start.sh --simulate           # short test, then ./stop.sh

sudo cp packaging/bidib2wled-venv.service /etc/systemd/system/bidib2wled.service
sudo nano /etc/systemd/system/bidib2wled.service   # adjust User, Group, WorkingDirectory, ExecStart
sudo systemctl daemon-reload
sudo systemctl enable --now bidib2wled
```

On a Raspberry Pi with the default user `pi` and the project in `/home/pi/BiDiB2WLED` the delivered file fits as it is. For another user replace `pi` and the paths everywhere.

### Variant B: system-wide installation with its own service user

After `pip install .` (system-wide or in a venv, then adjust `ExecStart`):

```bash
sudo useradd --system --home /var/lib/bidib2wled --create-home --shell /usr/sbin/nologin bidib2wled
sudo mkdir -p /etc/bidib2wled
sudo cp config.example.yaml /etc/bidib2wled/config.yaml
sudo chown -R bidib2wled:bidib2wled /etc/bidib2wled /var/lib/bidib2wled
sudo cp packaging/bidib2wled.service /etc/systemd/system/
# Adjust ExecStart to the pip path if it is not /usr/bin/bidib2wled
sudo systemctl daemon-reload
sudo systemctl enable --now bidib2wled
```

### Operating the service

| Command | Meaning |
|---|---|
| `sudo systemctl start bidib2wled` | start now |
| `sudo systemctl stop bidib2wled` | stop |
| `sudo systemctl restart bidib2wled` | restart (e.g. after editing the config) |
| `sudo systemctl status bidib2wled` | is it running? |
| `sudo systemctl enable bidib2wled` | start at boot |
| `sudo systemctl disable bidib2wled` | no longer start at boot |
| `journalctl -u bidib2wled -f` | follow the log live |

While the service is running do **not** start the bridge a second time with `start.sh` – port 8080 and 62875 can only be used once.

### Without systemd

- Cron of the user: `crontab -e`, then `@reboot /home/pi/BiDiB2WLED/start.sh` (log in `bidib2wled.log`).
- Desktop autostart: `.desktop` file in `~/.config/autostart/` with `Exec=/home/pi/BiDiB2WLED/start.sh`.
- Manual in a session: tmux/screen with `./start.sh --foreground`.

## Windows

1. Install [Python 3.11+](https://www.python.org/downloads/), tick “Add python.exe to PATH”.
2. Create a venv as above, `pip install -e .`, then `bidib2wled`.
3. Autostart: shortcut in the Startup folder or Task Scheduler on  
   `…\.venv\Scripts\bidib2wled.exe --config %APPDATA%\bidib2wled\config.yaml`
4. Firewall: inbound TCP **8080** (web) and **62875** (netBiDiB) if Rocrail runs on another machine.
5. If mDNS search is missing: enter the controller IP under **Setup** by hand.

## macOS

Same as Linux: venv, `pip install -e .`, `bidib2wled`. On first network access allow the firewall for ports 8080 and 62875.

Autostart e.g. as a LaunchAgent (`~/Library/LaunchAgents/local.bidib2wled.plist`) with `ProgramArguments` pointing at the venv `bidib2wled` and the config.

## Prepare WLED

On each controller (WLED web UI or app), **once**:

- Wi-Fi, LED type, GPIO, LED count, color order, current limit
- mDNS name (e.g. `wled-dorf`)
- Boot preset **off** / dark so nothing lights up uncontrolled after a power cut
- Sync between controllers **off** – the bridge orchestrates itself. If sync (or E1.31/DMX) is still on, that shows under **Status** on the controller.

**Do not** create segments per house or window in WLED. What each pixel means lives only in BiDiB2WLED. Special effects are created by the bridge as overlay segments.

## First setup

1. Start the service, open the browser on port 8080.
2. Under **Setup** check the node name and netBiDiB port. **Server** is the normal case: Rocrail connects to the bridge (default port **62875**).
3. Name found WLED devices and **claim** them – or enter an IP by hand.
4. Under **Status** click a controller IP to open its WLED page. Under **Setup** pick controller, output and LED and **identify** (“which lantern blinks?”).
5. If you soldered LEDs into or out of the chain: **Setup → Update LEDs on the bus**. To insert, first raise the LED count in WLED, then choose the position (e.g. after LED 5) – later addresses increment; you cannot exceed WLED. To remove, give the first missing LED and the count (e.g. from LED 6, three pieces) – later addresses decrement. A smaller WLED count does not block this; the difference is shown so you can update several places in sequence.
6. Under **Setup → LED names** you can name single LEDs, RGB channels and ranges, e.g. `LED1 = street lamp`, `3-7 = House3`, `12r = Halt`. In lists the name replaces the number: `LED 1 (street lamp)` instead of `LED 1 (No. 0)`. Several color names are joined with `/`, e.g. `LED 12 (Halt / Proceed)`. Names move with the LEDs when you update the bus. Numbers apply to the selected output (LED 1 is the first there).
7. Under **Objects** create lamps, houses, groups, sequences, signals, specials and vehicles. Each object can use an **RGB channel** (all / R / G / B only) so three LEDs on one pixel switch independently. Saving gives feedback; colors can be chosen with the wheel, HTML value or RGB. Already used LEDs and channels are marked in the lists. For vehicles, **Beacon steps** appears only when the channel type is **Beacon**.
8. Under **Status → Available objects** test (switch or signal aspect), then **Edit** or **Delete** if needed.

`config.yaml` is the only storage format. The UI writes it. Hand-editing is fine; then **Reload from disk** or just save – the service checks the file every 2 seconds.

Template: copy `config.example.yaml` to `config.yaml`.

Older configs with German keys (`lampen`, `einschalten: nacheinander`, …) still load and are rewritten as English on the next save.

## Connecting Rocrail

BiDiB2WLED appears in Rocrail as a **BiDiB node over netBiDiB** (TCP). There is **no** direct Rocrail XML client (port 8051) – that is reserved for a later stage. All switching uses BiDiB accessories.

Prerequisite: create objects in the web UI and test them in simulation or on the layout. Only then connect Rocrail.

### 1. Bridge as netBiDiB server

Under **Setup** (or in YAML):

```yaml
adapter:
  netbidib:
    enabled: true
    mode: server
    port: 62875
    node_name: BiDiB2WLED
```

The bridge then listens on port **62875**. Rocrail and BiDiB2WLED must reach each other (same machine: `127.0.0.1`; otherwise the LAN IP of the machine running the bridge). Open the firewall for 62875/tcp.

Under **Status → BiDiB** you see node name, UID, port/mode and whether someone is logged on.

### 2. Create a command station in Rocrail

In Rocview:

1. **File → Rocrail properties…** (only when Rocview is connected to the Rocrail server and automatic mode is off).
2. **Command station** tab. You can remove an existing virtual station if you do not need it.
3. Choose **bidib** at the bottom → **Add**. Double-click the new entry (or open properties).
4. **Interface ID (IID):** e.g. `bidib` – you need this IID later on every output/signal.
5. **Hostname:** IP or hostname of the bridge (`127.0.0.1` if Rocrail and BiDiB2WLED run on the same machine).
6. **TCP port:** `62875` (or the port set under Setup).
7. **Sub-library:** **netBiDiB** (not Serial/USB).
8. Close both dialogs with **OK**, **save** the plan, then **restart Rocrail and Rocview**. Only the restart takes the station.

There is **no** separate “start communication” button. After the restart Rocrail connects itself. Check it like this:

- In the **BiDiB2WLED web UI** under Status: pairing banner or **Logged on: yes**.
- In Rocview optionally **Control → Enable communication** (tick, no start button). BiDiB is supported there.
- **Control → Track power on** is not needed for BiDiB2WLED (the bridge has no track power).

The **Nodes** tab is not in the general Rocrail properties, but **in the bidib station properties**: File → Rocrail properties → Command station → double-click bidib → **Nodes**. The list fills only **after** the connection is up (restart and pairing). Alternatively: menu **Programming → BiDiB**. The entry is often named after the unique ID, not necessarily “BiDiB2WLED”.

Rocrail usually allows only **one** active netBiDiB logon on the same node. Do not point BiDiB-Wizard and Rocrail at the same node at once.

### 3. Pairing (first time only)

netBiDiB requires a trust relationship so not everyone on the network can control the node. TCP can already be connected while Rocrail still shows **“communication not ready (NOT paired)”** – that is this step.

1. BiDiB2WLED must be **running** before Rocrail connects.
2. Once Rocrail is connected, a yellow banner appears in the web UI with Rocrail’s UID/name. Under Status, **links** is at least 1, **Logged on** is still no.
3. Click **Pairing mode**. The bridge accepts Rocrail and stores the UID under **Trusted**.
4. Then **Logged on: yes**. Rocrail should lose “NOT paired”. If not: restart Rocrail once; pairing is stored.

Order does not matter: you can press **Pairing mode** first and then connect Rocrail; the bridge then accepts the next unknown host automatically.

Reject: **Reject request**. Pair again: delete the UID under `adapter.netbidib.trusted` in the YAML.

### 4. Look up the accessory number

Every object in BiDiB2WLED is a BiDiB **accessory**. The number is in the object list (**Address** column), e.g. `0` for church outdoor lighting. You can change it there. The **Object**, **Type** and **Address** columns are sortable.

BiDiB counts from **0**, Rocrail from **1**. The **Info** column lists the Rocrail values (address **+ 1**, port 0, …); further programs such as WinDigipet can be added there.

**Rocrail address = address + 1**, **port always 0**.

| Object list (address) | Rocrail address | Rocrail port |
|---|---|---|
| **0** church outdoor lighting | 1 | 0 |
| **1** church | 2 | 0 |

New objects (e.g. a signal) get the next free address automatically and keep it. Without a fixed entry the bridge assigns numbers in order (windows of a house are skipped – the house itself is switchable). Fixed numbers in YAML are BiDiB indices (0, 1, 2, …):

```yaml
adapter:
  netbidib:
    accessories:
      0: Aussenbeleuchtung Kirche
      1: Kirche
```

### 5. Create an output in Rocrail (lamp, house, group, sequence, special)

Prerequisite: **Logged on: yes** under Status. Automatic mode in Rocview off.

BiDiB2WLED understands only **accessory commands**, not individual LC ports. Therefore **Accessory** must be on in Rocrail and the protocol must stay **Default** (not NMRA-DCC).

1. In Rocview: **Tables → Outputs → New**.
2. **General** tab
   - **ID:** descriptive, e.g. `church-outdoor` (visible only in Rocrail).
   - Type: normal switch (on/off), not a push-button.
3. **Interface** tab

| Field | Value | Why |
|---|---|---|
| **Interface ID (IID)** | same as on the bidib station, e.g. `bidib` | otherwise the command goes to the wrong station |
| **Bus** | `0` | one virtual node |
| **UID name** (if present) | `BiDiB2WLED` or empty | optional; node name from the status page |
| **Protocol** | **Default** | not NMRA-DCC (that would be a DCC decoder behind a BiDiB station) |
| **Address** | object list **+ 1** (shown under Info) | BiDiB 0 = Rocrail 1 |
| **Port** | `0` | flat BiDiB addressing |
| **Accessory** | **ticked** | otherwise Rocrail sends port commands the bridge ignores |
| **Turnout** / **single output** | off | this is an on/off output, not a turnout |

Example **church outdoor lighting** (accessory 0): IID `bidib`, address **1**, port **0**, accessory on, protocol Default.

Example **church** (accessory 1): same fields, address **2**.

4. Save with **OK**. Drag the output from the table onto the layout (or place an “output” symbol and assign the ID).
5. Save the plan. Click the symbol: **on** = aspect 1, **off** = aspect 0.

What the click does:

- **Lamp:** LEDs on or off
- **House:** windows according to the behaviour set in the bridge
- **Special:** WLED effect on or off (not pixel by pixel)
- **Vehicle:** mode 1 = lights, higher modes depending on the setup (hazards, emergency); indicators of several vehicles are not synchronized
- **Group:** all members
- **Sequence:** on = staggered on, off = staggered off; a new command aborts a running sequence

The same outputs work in **actions**, **routes** and **schedules**.

If no switch command arrives:

- Is **Logged on: yes** under Status?
- Does **Info** show the same Rocrail address as in Rocrail (port 0)?
- **Accessory** on, **protocol Default**, **port 0**, IID identical to the station?
- Test: flip the object in the web UI – if that switches the LEDs, the error is the Rocrail address, not WLED.

### 6. Switch signals

A signal has several aspects, not just on/off.

In Rocview: **Tables → Signals → New**.

- IID, bus, address (object list **+ 1**, see **Info**), port 0 and **protocol Default** as for an output
- Enable **Accessory**
- Under **Pattern / aspects** enter the aspect numbers used in BiDiB2WLED, e.g.:

| Rocrail aspect | Value (number) | typical in the bridge |
|---|---|---|
| Red / Halt | 0 | Halt |
| Green / Proceed | 1 or 2 | depending on the aspects you created |
| Yellow | 1 | e.g. expect halt |

Aspect numbers are the same as in the bridge object list (Halt / Proceed …) or in YAML under `signals: … aspects:`. Halt and Proceed can share the same WS2811 LED if red and green are split as `channels` `r` and `g`.

**Vehicles** with several modes (Lights, Hazards, Emergency) are also created as a signal in Rocrail. Mode numbers match the object list (0 = Off).

### 7. Quick check

1. Bridge running, **Logged on: yes** under Status.
2. In **Available objects** the object can be tested with the switch.
3. In Rocrail switch the same accessory via the output/signal → LEDs and the switch in the web UI follow.
4. The layout symbol stays “in progress” during a sequence and then goes to the final state (the bridge reports accessory state back).

## Other BiDiB hosts

The same netBiDiB (server, port 62875, pairing) works with BiDiB-Wizard, iTrain and other hosts that switch accessories. Accessory numbers are the same. Client mode (`mode: client` plus `host:`) only if the bridge should connect to an existing netBiDiB server – the normal case is server.

## YAML (backup and bulk edits)

Example skeleton (see also `config.example.yaml`):

```yaml
adapter:
  netbidib:
    enabled: true
    mode: server
    port: 62875
    node_name: BiDiB2WLED
    accessories:
      0: laterne-01
      1: haus-baecker

controller:
  - name: dorf
    ip: 192.168.1.51
    leds: 80
    names:
      - { led: 0, name: Straßenlaterne }
      - { start: 2, end: 6, name: Haus3 }
      - { led: 11, channel: r, name: Halt }
      - { led: 11, channel: g, name: Fahrt }

lamps:
  laterne-01:
    controller: dorf
    leds: [0]
    color: "FFB060"
    channel: rgb

houses:
  haus-baecker:
    controller: dorf
    turn_on: sequential
    windows:
      wohnzimmer: { leds: [18, 19], color: "FFB060", channel: r }
      kueche: { leds: [18], color: "00FF00", channel: g }

groups:
  hauptstrasse:
    members: [laterne-01, haus-baecker]

sequences:
  seq-nacht:
    groups: [hauptstrasse]
    order: random
    delay: [2s, 8s]

signals:
  signal-ausfahrt:
    controller: dorf
    aspects:
      0: { name: Halt, leds: { 12: "FF0000" }, channels: { 12: r } }
      1: { name: Fahrt, leds: { 12: "00FF00" }, channels: { 12: g } }

special:
  kamin-feuer:
    controller: dorf
    leds: [10, 11, 12]
    effect: 10
    palette: 0
    speed: 128
    intensity: 128
    color: "FF6A00"

vehicles:
  pkw-rot:
    controller: dorf
    channels:
      licht: { leds: [30], channel: rgb, color: "FFFFCC", type: continuous }
      blinker-l: { leds: [31], channel: r, color: "FF8000", type: blinker }
      blinker-r: { leds: [31], channel: g, color: "FF8000", type: blinker }
    modes:
      0: { name: Off, channels: [] }
      1: { name: Licht, channels: [licht] }
      2: { name: Warnblinker, channels: [licht, blinker-l, blinker-r] }
  feuerwehr:
    controller: dorf
    channels:
      scheinwerfer: { leds: [32], channel: r, color: "FFFFCC", type: continuous }
      ruecklicht: { leds: [32], channel: g, color: "FF0000", type: continuous }
      rundum: { leds: [33], channel: rgb, color: "0000FF", type: beacon, steps: channels }
    modes:
      0: { name: Off, channels: [] }
      1: { name: Licht, channels: [scheinwerfer, ruecklicht] }
      3: { name: Einsatz, channels: [scheinwerfer, ruecklicht, rundum] }
```

Colors are `RRGGBB` without `#`. LED indices are global on the controller (output 1 starts at 0). `channel` (`r`/`g`/`b`/`rgb`) is the RGB share: that is how the three LEDs of a pixel switch independently. Special objects use the controller’s WLED effects (`effect` / `palette` are the numbers from the web UI); effects act on the whole pixel.

Under `controller.names` are display names: `led` (one LED) or `start`/`end` (inclusive range, 0-based), optional `channel` for one color of the same LED. In lists the name replaces `No. …`; several color names of one LED appear separated by `/`. When inserting or removing on the bus, names shift like object addresses.

Vehicles, beacon: `steps` controls what lights in sequence. In the UI the control appears only when the type is **Beacon**.

| `steps` | Meaning |
|---|---|
| `channels` | RGB channels in sequence. A WS2811 with `channel: rgb` is a 3-step beacon (R→G→B). Several pixels continue channel by channel. |
| `leds` | Whole LEDs in sequence (selected channels together). |
| `auto` (default) | One LED with several channels like `channels`, otherwise like `leds`. |

Indicators of different vehicles have different periods.

## Ports

| Port | Service |
|---|---|
| 8080/tcp | Web UI |
| 62875/tcp | netBiDiB (node server) |
| mDNS | `_wled._tcp` (search), `_bidib._tcp` and `_http._tcp` (advertise) |

## Architecture (stage 1)

- Core switches logical objects and keeps the desired state.
- netBiDiB adapter: pairing, logon, accessories (`MSG_ACCESSORY_SET` / `STATE` / `NOTIFY`).
- WLED: JSON API, mDNS discovery, bind to MAC.
- Web: wizard, claim, identify, test switching, edit, delete.

Not yet implemented (see `KONZEPT.md`): direct Rocrail RCP client, time automation via model clock, WLED presets/UDP scenes.

---

# BiDiB2WLED (Deutsch)

Virtueller [BiDiB](https://bidib.org)-Knoten (**netBiDiB**), der [WLED](https://kno.wled.ge/)-Controller mit WS2812-ähnlichen LEDs auf der Modellbahn steuert.

Modellbahn-Software wie **Rocrail**, BiDiB-Wizard oder iTrain kennt WLED nicht. BiDiB2WLED hängt dazwischen: Die Steuerung schaltet ganz normale BiDiB-Accessories, die Bridge setzt das in LED-Befehle um.

Läuft unter **Linux**, **Windows** und **macOS** (Python 3.11 oder neuer).

## Was du damit machen kannst

| Objekt | Bedeutung | Schalten |
|---|---|---|
| **Lampe** | eine oder mehrere LEDs (Laterne, einzelnes Zimmer) | aus / an |
| **Haus** | mehrere Fenster mit Farbe und Einschaltverhalten (sofort, nacheinander, zufällig) | Haus als Ganzes; Fenster auch einzeln |
| **Gruppe** | mehrere Lampen/Häuser (z. B. eine Straße) | alle Mitglieder gemeinsam |
| **Sequenz** | gestaffeltes Ein- oder Ausschalten mit Pausen | an = Reihenfolge „an“, aus = umgekehrt |
| **Signal** | mehrere Begriffe (Halt, Fahrt, …), je Begriff LEDs/Farben (WS2811: auch R/G/B derselben LED) | Begriff (Aspekt) 0, 1, 2, … |
| **Spezial** | eingebauter WLED-Effekt (Feuer, Kerze, …) auf den gewählten LEDs | aus / an |
| **Fahrzeug** | Standmodell mit Lichtkanälen (Scheinwerfer, Blinker, Rundumlicht, …) | Modus (aus, Licht, Warnblinker, Einsatz, …) |

Zusätzlich: WLED-Geräte im Netz finden, LEDs am Modell identifizieren (blinken lassen), LEDs benennen, LEDs in den Bus nachtragen (Adressen und Namen der folgenden LEDs werden verschoben), alles in der Weboberfläche anlegen und testen, dauerhaft als Dienst betreiben.

![Statusseite](status.png)

![Objektkonfiguration](objects.png)

## Voraussetzungen

- Python 3.11 oder neuer (Debian/Ubuntu: `sudo apt install python3-venv python3-pip`)
- WLED-Controller im selben Netz (für echte LEDs). Ohne Hardware: `--simulate`
- Optional: Steuerungssoftware mit netBiDiB, z. B. [Rocrail](https://wiki.rocrail.net/), BiDiB-Wizard, iTrain

## Installation und Start

Im Projektverzeichnis:

```bash
python3 -m venv .venv
```

Umgebung aktivieren:

| System | Befehl |
|---|---|
| Linux / macOS | `source .venv/bin/activate` |
| Windows (cmd) | `.venv\Scripts\activate.bat` |
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |

```bash
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Simulation (keine echten WLED-Geräte, Oberfläche zum Ausprobieren):

```bash
bidib2wled --simulate
```

oder `python -m bidib2wled --simulate`.

Danach im Browser: [http://127.0.0.1:8080](http://127.0.0.1:8080)

Mit echten Controllern (Suche nach `_wled._tcp`):

```bash
bidib2wled
```

| Option | Bedeutung |
|---|---|
| `--config PFAD` | YAML-Datei. Standard: `./config.yaml`, falls vorhanden, sonst das Benutzer-Konfigurationsverzeichnis |
| `--host ADRESSE` | Web-Bind, Standard `0.0.0.0` (alle Schnittstellen) |
| `--port N` | Web-Port, Standard `8080` |
| `--simulate` | kein HTTP zu WLED, Pixel nur intern |
| `-v` | ausführliche Logs |

Tests:

```bash
python -m pytest
```

Optional ein Installationspaket bauen:

```bash
python -m pip install build
python -m pip install -e .
python -m build
```

Artefakte liegen in `dist/`. Installation: `pip install dist/bidib2wled-*.whl`

## Start- und Stop-Skript (Linux / macOS)

`start.sh` und `stop.sh` im Projektverzeichnis starten und stoppen die Bridge, ohne jedes Mal den venv-Pfad zu tippen.

```bash
./start.sh          # im Hintergrund starten
./stop.sh           # beenden
./start.sh --simulate   # zusätzliche Argumente werden durchgereicht
```

`start.sh` nimmt `.venv/bin/bidib2wled`, falls vorhanden, sonst `bidib2wled` aus dem PATH. Die Prozess-ID steht in `bidib2wled.pid`, die Ausgabe in `bidib2wled.log`; ein zweiter Start bei laufendem Dienst passiert nicht. `./start.sh --foreground` läuft stattdessen im Vordergrund (für systemd oder ein Terminal). `stop.sh` schickt SIGTERM und nach 15 Sekunden SIGKILL.

Einstellungen über Umgebungsvariablen:

| Variable | Bedeutung |
|---|---|
| `BIDIB2WLED_CONFIG` | YAML-Datei. Standard: `config.yaml` im Projektverzeichnis, falls vorhanden |
| `BIDIB2WLED_HOST` | Web-Bind-Adresse |
| `BIDIB2WLED_PORT` | Web-Port |
| `BIDIB2WLED_ARGS` | zusätzliche Argumente, z. B. `"--simulate -v"` |
| `BIDIB2WLED_PIDFILE` | PID-Datei |
| `BIDIB2WLED_LOG` | Logdatei |

```bash
BIDIB2WLED_PORT=8099 BIDIB2WLED_ARGS="--simulate" ./start.sh
tail -f bidib2wled.log
```

## Linux: automatisch beim Booten starten

Mit systemd (Debian, Ubuntu, Raspberry Pi OS, Fedora, …) startet die Bridge beim Booten, startet nach einem Absturz neu und schreibt ins Journal. Zwei Varianten – eine davon auswählen.

### Variante A: Projektverzeichnis mit venv (empfohlen für den Raspberry Pi)

Der Dienst startet `start.sh --foreground` unter deinem eigenen Benutzer. Es wird nichts kopiert, die Konfiguration bleibt im Projektverzeichnis.

```bash
cd ~/BiDiB2WLED                 # dein Projektverzeichnis
python3 -m venv .venv
.venv/bin/pip install -e .
./start.sh --simulate           # kurzer Test, danach ./stop.sh

sudo cp packaging/bidib2wled-venv.service /etc/systemd/system/bidib2wled.service
sudo nano /etc/systemd/system/bidib2wled.service   # User, Group, WorkingDirectory, ExecStart anpassen
sudo systemctl daemon-reload
sudo systemctl enable --now bidib2wled
```

Auf einem Raspberry Pi mit dem Standardbenutzer `pi` und dem Projekt in `/home/pi/BiDiB2WLED` passt die mitgelieferte Datei unverändert. Bei einem anderen Benutzer überall `pi` und die Pfade ersetzen.

### Variante B: systemweite Installation mit eigenem Dienstbenutzer

Nach `pip install .` (systemweit oder in einer venv, dann `ExecStart` anpassen):

```bash
sudo useradd --system --home /var/lib/bidib2wled --create-home --shell /usr/sbin/nologin bidib2wled
sudo mkdir -p /etc/bidib2wled
sudo cp config.example.yaml /etc/bidib2wled/config.yaml
sudo chown -R bidib2wled:bidib2wled /etc/bidib2wled /var/lib/bidib2wled
sudo cp packaging/bidib2wled.service /etc/systemd/system/
# ExecStart auf den pip-Pfad anpassen, falls nicht /usr/bin/bidib2wled
sudo systemctl daemon-reload
sudo systemctl enable --now bidib2wled
```

### Dienst bedienen

| Befehl | Bedeutung |
|---|---|
| `sudo systemctl start bidib2wled` | jetzt starten |
| `sudo systemctl stop bidib2wled` | beenden |
| `sudo systemctl restart bidib2wled` | neu starten (z. B. nach Änderung der Konfiguration) |
| `sudo systemctl status bidib2wled` | läuft er? |
| `sudo systemctl enable bidib2wled` | beim Booten starten |
| `sudo systemctl disable bidib2wled` | nicht mehr beim Booten starten |
| `journalctl -u bidib2wled -f` | Log live mitlesen |

Solange der Dienst läuft, die Bridge **nicht** zusätzlich mit `start.sh` starten – Port 8080 und 62875 gibt es nur einmal.

### Ohne systemd

- Cron des Benutzers: `crontab -e`, dann `@reboot /home/pi/BiDiB2WLED/start.sh` (Log in `bidib2wled.log`).
- Desktop-Autostart: `.desktop`-Datei in `~/.config/autostart/` mit `Exec=/home/pi/BiDiB2WLED/start.sh`.
- Manuell in einer Sitzung: tmux/screen mit `./start.sh --foreground`.

## Windows

1. [Python 3.11+](https://www.python.org/downloads/) installieren, Haken bei „Add python.exe to PATH“.
2. Wie oben venv anlegen, `pip install -e .`, dann `bidib2wled`.
3. Autostart: Verknüpfung im Autostart-Ordner oder Aufgabenplanung auf  
   `…\.venv\Scripts\bidib2wled.exe --config %APPDATA%\bidib2wled\config.yaml`
4. Firewall: eingehend TCP **8080** (Web) und **62875** (netBiDiB), wenn Rocrail auf einem anderen Rechner läuft.
5. Fehlt die mDNS-Suche: IP des Controllers unter **Einrichtung** von Hand eintragen.

## macOS

Wie Linux: venv, `pip install -e .`, `bidib2wled`. Beim ersten Netz-Zugriff die Firewall für die Ports 8080 und 62875 erlauben.

Autostart z. B. als LaunchAgent (`~/Library/LaunchAgents/local.bidib2wled.plist`) mit `ProgramArguments` auf den venv-`bidib2wled` und die Config.

## WLED vorbereiten

Auf jedem Controller (WLED-Weboberfläche oder App), **einmalig**:

- WLAN, LED-Typ, GPIO, LED-Anzahl, Farbreihenfolge, Strombegrenzung
- mDNS-Name (z. B. `wled-dorf`)
- Boot-Preset **aus** / dunkel, damit nach Stromausfall nichts unkontrolliert leuchtet
- Sync zwischen Controllern **aus** – die Bridge orchestriert selbst. Ist Sync (oder E1.31/DMX) trotzdem aktiv, erscheint das unter **Status** am Controller.

**Nicht** in WLED anlegen: Segmente je Haus oder Fenster. Die Bedeutung der Pixel (welche LED welches Zimmer ist) liegt nur in BiDiB2WLED. Spezial-Effekte legt die Bridge selbst als Overlay-Segmente an.

## Ersteinrichtung

1. Dienst starten, Browser auf Port 8080.
2. Unter **Einrichtung** den Knotennamen und den netBiDiB-Port prüfen. **Server** ist der Normalfall: Rocrail verbindet sich zur Bridge (Standardport **62875**).
3. Gefundene WLED-Geräte benennen und **übernehmen** – oder IP von Hand eintragen.
4. Unter **Status** die IP eines Controllers anklicken, um dessen WLED-Seite zu öffnen. Unter **Einrichtung** Controller, Ausgang und LED wählen und **identifizieren** („welche Laterne blinkt?“).
5. Hast du LEDs in die Kette gelötet oder entfernt: unter **Einrichtung → LEDs im Bus nachtragen**. Zum Einfügen zuerst in WLED die LED-Anzahl erhöhen, dann die Stelle angeben (z. B. nach LED 5) – Folgeadressen werden hochgezählt, mehr als in WLED geht nicht. Zum Entfernen die erste fehlende LED und die Anzahl angeben (z. B. ab LED 6 drei Stück) – Folgeadressen werden heruntergezählt. Wenn WLED schon weniger LEDs hat, blockiert das nicht; die Differenz wird angezeigt, damit du an mehreren Stellen nacheinander nachtragen kannst.
6. Unter **Einrichtung → LED-Namen** kannst du einzelne LEDs, RGB-Anteile und Bereiche benennen, z. B. `LED1 = Straßenlaterne`, `3-7 = Haus3`, `12r = Halt`. In den Listen ersetzt der Name die Nummer: `LED 1 (Straßenlaterne)` statt `LED 1 (Nr. 0)`. Mehrere Farbnamen stehen mit `/` getrennt, z. B. `LED 12 (Halt / Fahrt)`. Beim Nachtragen im Bus wandern die Namen mit den LEDs mit. Die Nummern gelten für den gewählten Ausgang (LED 1 ist dort die erste).
7. Unter **Objekte** Lampen, Häuser, Gruppen, Sequenzen, Signale, Spezial-Effekte und Fahrzeuge anlegen. Jedes Objekt kann einen **RGB-Anteil** (alle / nur R / G / B) nutzen, damit drei LEDs an einem Pixel unabhängig schalten. Speichern gibt eine Rückmeldung; Farben lassen sich über Farbrad, HTML-Wert oder RGB wählen. Bereits vergebene LEDs und Kanäle sind in den Auswahllisten markiert. Bei Fahrzeugen erscheint **Rundum-Schritte** nur, wenn die Kanal-Art **Rundumlicht** ist.
8. Unter **Status → Verfügbare Objekte** testen (Schalter bzw. Signalbegriff), bei Bedarf **Ändern** oder **Löschen**.

Die Datei `config.yaml` ist das einzige Speicherformat. Die Oberfläche schreibt sie. Von Hand editieren geht ebenfalls; danach in der Oberfläche **Von Disk neu laden** oder einfach speichern – der Dienst prüft die Datei alle 2 Sekunden.

Vorlage: `config.example.yaml` nach `config.yaml` kopieren.

## Anbindung an Rocrail

BiDiB2WLED erscheint in Rocrail als **BiDiB-Knoten über netBiDiB** (TCP). Es gibt **keinen** direkten Rocrail-XML-Client (Port 8051) – der ist für eine spätere Ausbaustufe vorgesehen. Alles Schalten läuft über BiDiB-Accessories.

Voraussetzung: Objekte in der Weboberfläche anlegen und in der Simulation bzw. am Modell testen. Erst danach Rocrail anschließen.

### 1. Bridge als netBiDiB-Server

Unter **Einrichtung** (oder in der YAML):

```yaml
adapter:
  netbidib:
    enabled: true
    mode: server
    port: 62875
    node_name: BiDiB2WLED
```

Die Bridge lauscht dann auf Port **62875**. Rocrail und BiDiB2WLED müssen sich im Netz erreichen (gleiche Maschine: `127.0.0.1`; sonst die LAN-IP des Rechners, auf dem die Bridge läuft). Firewall für 62875/tcp öffnen.

Unter **Status → BiDiB** stehen Knotenname, UID, Port/Modus und ob jemand angemeldet ist.

### 2. Zentrale in Rocrail anlegen

In Rocview:

1. **Datei → Rocrail-Eigenschaften…** (nur verfügbar, wenn Rocview mit dem Rocrail-Server verbunden und der Automatikmodus aus ist).
2. Register **Zentrale**. Eine vorhandene virtuelle Zentrale kannst du entfernen, wenn du sie nicht brauchst.
3. Unten **bidib** wählen → **Hinzufügen**. Den neuen Eintrag **doppelklicken** (oder Eigenschaften öffnen).
4. **Schnittstellenkennung (IID):** z. B. `bidib` – diese IID brauchst du später an jedem Ausgang/Signal.
5. **Hostname:** IP oder Hostname der Bridge (`127.0.0.1`, wenn Rocrail und BiDiB2WLED auf demselben Rechner laufen).
6. **TCP-Port:** `62875` (oder der unter Einrichtung eingestellte Port).
7. **Sub-Bibliothek:** **netBiDiB** (nicht Serial/USB).
8. Beide Dialoge mit **OK** schließen, Plan **speichern**, danach **Rocrail und Rocview neu starten**. Erst der Neustart übernimmt die Zentrale.

Es gibt **keinen** eigenen Knopf „Kommunikation starten“. Nach dem Neustart verbindet Rocrail sich selbst. Prüfen kannst du das so:

- In der **BiDiB2WLED-Weboberfläche** unter Status: Pairing-Banner oder **Angemeldet: ja**.
- In Rocview optional **Steuerung → Kommunikation aktivieren** (Häkchen, kein Start-Button). BiDiB wird dort unterstützt.
- **Steuerung → Gleisspannung ein** ist bei BiDiB2WLED nicht nötig (die Bridge hat keine Gleisspannung).

**Register Knoten** liegt nicht in den allgemeinen Rocrail-Eigenschaften, sondern **in den Eigenschaften der bidib-Zentrale**: Datei → Rocrail-Eigenschaften → Zentrale → bidib-Eintrag doppelklicken → Register **Knoten**. Die Liste füllt sich erst, **nachdem** die Verbindung steht (also nach Neustart und Pairing). Alternativ: Menü **Programmieren → BiDiB**. Der Eintrag heißt oft nach der Unique-ID, nicht unbedingt „BiDiB2WLED“.

Rocrail erlaubt in der Regel nur **eine** aktive netBiDiB-Anmeldung am selben Knoten. BiDiB-Wizard und Rocrail nicht gleichzeitig auf denselben Knoten legen.

### 3. Pairing (nur beim ersten Mal)

netBiDiB verlangt eine Vertrauensstellung, damit nicht jeder im Netz den Knoten steuert. TCP kann schon verbunden sein, während Rocrail noch **„communication not ready (NOT paired)“** anzeigt – das ist genau dieser Schritt.

1. BiDiB2WLED muss **laufen**, bevor Rocrail verbindet.
2. Sobald Rocrail verbunden ist, erscheint in der Weboberfläche ein gelbes Banner mit der UID/dem Namen von Rocrail. Unter Status steht **Links** mindestens 1, **Angemeldet** noch nein.
3. **Pairing-Modus** klicken. Die Bridge akzeptiert Rocrail und merkt sich die UID unter **Vertraut**.
4. Danach **Angemeldet: ja**. Rocrail sollte die Meldung „NOT paired“ verlieren. Falls nicht: Rocrail einmal neu starten, Pairing ist gespeichert.

Reihenfolge ist egal: Du kannst auch zuerst **Pairing-Modus** drücken und danach Rocrail verbinden; die Bridge akzeptiert den nächsten unbekannten Host dann automatisch.

Ablehnen: **Anfrage ablehnen**. Erneutes Pairing: UID unter `adapter.netbidib.trusted` in der YAML löschen.

### 4. Accessory-Nummer nachschlagen

Jedes Objekt in BiDiB2WLED ist ein BiDiB-**Accessory**. Die Nummer steht in der Objektliste (Spalte **Adresse**), z. B. `0` bei Aussenbeleuchtung Kirche. Dort lässt sie sich auch ändern. Die Spalten **Objekt**, **Typ** und **Adresse** sind sortierbar.

BiDiB zählt ab **0**, Rocrail ab **1**. Die Spalte **Info** nennt die Werte für Rocrail (Adresse **+ 1**, Port 0, …); weitere Programme wie WinDigipet können dort ergänzt werden.

**Rocrail-Adresse = Adresse + 1**, **Port immer 0**.

| Objektliste (Adresse) | Rocrail-Adresse | Rocrail-Port |
|---|---|---|
| **0** Aussenbeleuchtung Kirche | 1 | 0 |
| **1** Kirche | 2 | 0 |

Neue Objekte (z. B. ein Signal) bekommen automatisch die nächste freie Adresse und behalten sie. Ohne festen Eintrag vergibt die Bridge die Nummern der Reihe nach (Fenster eines Hauses werden übersprungen – das Haus selbst ist schaltbar). Feste Nummern in der YAML sind BiDiB-Indizes (0, 1, 2, …):

```yaml
adapter:
  netbidib:
    accessories:
      0: Aussenbeleuchtung Kirche
      1: Kirche
```

### 5. Ausgang in Rocrail anlegen (Lampe, Haus, Gruppe, Sequenz, Spezial)

Voraussetzung: Unter Status **Angemeldet: ja**. Automatikmodus in Rocview aus.

BiDiB2WLED versteht nur **Accessory-Befehle**, keine einzelnen LC-Ports. Deshalb muss in Rocrail **Zubehör** an sein und das Protokoll **Default** bleiben (nicht NMRA-DCC).

1. In Rocview: **Tabellen → Ausgänge → Neu**.
2. Reiter **Allgemein**
   - **ID:** sprechend, z. B. `kirche-aussen` (nur in Rocrail sichtbar).
   - Typ: normaler Schalter (an/aus), kein Taster.
3. Reiter **Schnittstelle**

| Feld | Wert | Warum |
|---|---|---|
| **Schnittstellenkennung (IID)** | dieselbe wie an der bidib-Zentrale, z. B. `bidib` | sonst geht der Befehl an die falsche Zentrale |
| **Bus** | `0` | ein virtueller Knoten |
| **UID-Name** (falls vorhanden) | `BiDiB2WLED` oder leer | optional; Knotennamen von der Statusseite |
| **Protokoll** | **Default** | nicht NMRA-DCC (das wäre ein DCC-Decoder hinter einer BiDiB-Zentrale) |
| **Adresse** | Objektliste **+ 1** (steht unter Info) | BiDiB 0 = Rocrail 1 |
| **Port** | `0` | flache BiDiB-Adressierung |
| **Zubehör** | **Häkchen an** | sonst sendet Rocrail Port-Befehle, die die Bridge ignoriert |
| **Weiche** / **Einzel-Ausgang** | aus | das ist ein Ein/Aus-Ausgang, keine Weiche |

Beispiel **Aussenbeleuchtung Kirche** (Accessory 0): IID `bidib`, Adresse **1**, Port **0**, Zubehör an, Protokoll Default.

Beispiel **Kirche** (Accessory 1): dieselben Felder, Adresse **2**.

4. Mit **OK** speichern. Den Ausgang aus der Tabelle ins Stellwerk ziehen (oder Stellwerk-Symbol „Ausgang“ platzieren und die ID zuweisen).
5. Plan speichern. Klick auf das Symbol: **an** = Aspekt 1, **aus** = Aspekt 0.

Was der Klick bewirkt:

- **Lampe:** LEDs an oder aus
- **Haus:** Fenster nach dem in der Bridge eingestellten Verhalten
- **Spezial:** WLED-Effekt an oder aus (kein Pixel-für-Pixel)
- **Fahrzeug:** Modus 1 = Licht, höhere Modi je nach Anlage (Warnblinker, Einsatz); Blinker mehrerer Fahrzeuge sind nicht synchron
- **Gruppe:** alle Mitglieder
- **Sequenz:** an = gestaffelt ein, aus = gestaffelt aus; ein erneuter Befehl bricht eine laufende Sequenz ab

Dieselben Ausgänge funktionieren in **Aktionen**, **Fahrstraßen** und **Fahrplänen**.

Kommt kein Schaltbefehl an:

- Unter Status wirklich **Angemeldet: ja**?
- Steht unter **Info** dieselbe Rocrail-Adresse wie in Rocrail (Port 0)?
- **Zubehör** an, **Protokoll Default**, **Port 0**, IID identisch zur Zentrale?
- Test: Objekt in der Weboberfläche per Schalter umlegen – wenn das die LEDs schaltet, liegt der Fehler in der Rocrail-Adresse, nicht in WLED.

### 6. Signale schalten

Ein Signal hat mehrere Begriffe (Aspekte), nicht nur an/aus.

In Rocview: **Tabellen → Signale → Neu**.

- IID, Bus, Adresse (Objektliste **+ 1**, siehe Spalte **Info**), Port 0 und **Protokoll Default** wie beim Ausgang
- **Zubehör** aktivieren
- Unter **Muster / Begriffe** die Begriffsnummern eintragen, die in BiDiB2WLED gelten, z. B.:

| Rocrail-Begriff | Wert (Nummer) | typisch in der Bridge |
|---|---|---|
| Rot / Halt | 0 | Halt |
| Grün / Fahrt | 1 oder 2 | je nach angelegten Begriffen |
| Gelb | 1 | z. B. Halt erwarten |

Die Begriffsnummern sind dieselben wie in der Objektliste der Bridge (Auswahl **Halt** / **Fahrt** …) bzw. in der YAML unter `signals: … aspects:`. Halt und Fahrt können dieselbe WS2811-LED nutzen, wenn Rot und Grün als `channels` `r` und `g` getrennt sind.

**Fahrzeuge** mit mehreren Modi (Licht, Warnblinker, Einsatz) werden in Rocrail ebenfalls als Signal angelegt. Die Modusnummern entsprechen der Auswahl in der Objektliste (0 = Aus).

### 7. Kurz-Check

1. Bridge läuft, unter Status **Angemeldet: ja**.
2. In **Verfügbare Objekte** lässt sich das Objekt per Schalter testen.
3. In Rocrail denselben Accessory über den Ausgang/das Signal schalten → LEDs und der Schalter in der Weboberfläche folgen.
4. Stellwerkssymbol bleibt während einer Sequenz „in Arbeit“ und geht danach in die Endlage (die Bridge meldet den Accessory-Zustand zurück).

## Andere BiDiB-Hosts

Dasselbe netBiDiB (Server, Port 62875, Pairing) funktioniert mit BiDiB-Wizard, iTrain und anderen Hosts, die Accessories schalten. Die Accessory-Nummern sind dieselben. Client-Modus (`mode: client` plus `host:`) nur, wenn die Bridge sich zu einem bestehenden netBiDiB-Server verbinden soll – der Normalfall ist Server.

## YAML (für Sicherung und Massenänderungen)

Beispielgerüst (siehe auch `config.example.yaml`):

```yaml
adapter:
  netbidib:
    aktiv: true
    modus: server
    port: 62875
    knotenname: BiDiB2WLED
    accessories:
      0: laterne-01
      1: haus-baecker

controller:
  - name: dorf
    ip: 192.168.1.51
    leds: 80
    names:
      - { led: 0, name: Straßenlaterne }
      - { start: 2, end: 6, name: Haus3 }
      - { led: 11, channel: r, name: Halt }
      - { led: 11, channel: g, name: Fahrt }

lamps:
  laterne-01:
    controller: dorf
    leds: [0]
    color: "FFB060"
    channel: rgb

houses:
  haus-baecker:
    controller: dorf
    turn_on: sequential
    windows:
      wohnzimmer: { leds: [18, 19], color: "FFB060", channel: r }
      kueche: { leds: [18], color: "00FF00", channel: g }

groups:
  hauptstrasse:
    members: [laterne-01, haus-baecker]

sequences:
  seq-nacht:
    groups: [hauptstrasse]
    order: random
    delay: [2s, 8s]

signals:
  signal-ausfahrt:
    controller: dorf
    aspects:
      0: { name: Halt, leds: { 12: "FF0000" }, channels: { 12: r } }
      1: { name: Fahrt, leds: { 12: "00FF00" }, channels: { 12: g } }

special:
  kamin-feuer:
    controller: dorf
    leds: [10, 11, 12]
    effect: 10
    palette: 0
    speed: 128
    intensity: 128
    color: "FF6A00"

vehicles:
  pkw-rot:
    controller: dorf
    channels:
      licht: { leds: [30], channel: rgb, color: "FFFFCC", type: continuous }
      blinker-l: { leds: [31], channel: r, color: "FF8000", type: blinker }
      blinker-r: { leds: [31], channel: g, color: "FF8000", type: blinker }
    modes:
      0: { name: Off, channels: [] }
      1: { name: Licht, channels: [licht] }
      2: { name: Warnblinker, channels: [licht, blinker-l, blinker-r] }
  feuerwehr:
    controller: dorf
    kanaele:
      scheinwerfer: { leds: [32], channel: r, color: "FFFFCC", type: continuous }
      ruecklicht: { leds: [32], channel: g, color: "FF0000", type: continuous }
      rundum: { leds: [33], channel: rgb, color: "0000FF", type: beacon, steps: channels }
    modi:
      0: { name: Aus, kanaele: [] }
      1: { name: Licht, channels: [scheinwerfer, ruecklicht] }
      3: { name: Einsatz, channels: [scheinwerfer, ruecklicht, rundum] }
```

Farben sind `RRGGBB` ohne `#`. LED-Indizes sind global auf dem Controller (Ausgang 1 beginnt bei 0). `channel` (`r`/`g`/`b`/`rgb`) ist der RGB-Anteil: so werden die drei LEDs eines Pixels unabhängig geschaltet. Spezial-Objekte nutzen die WLED-Effekte des Controllers (`effect` / `palette` sind die Nummern aus der Weboberfläche); Effekte wirken auf das ganze Pixel.

Unter `controller.names` liegen Anzeigenamen: `led` (eine LED) oder `start`/`end` (Bereich, inklusive, 0-basiert), optional `channel` für eine Farbe derselben LED. In den Listen steht der Name statt `Nr. …`; mehrere Farbnamen einer LED erscheinen mit `/` getrennt. Beim Einfügen oder Entfernen im Bus werden die Namen wie die Objekt-Adressen verschoben.

Fahrzeuge, Rundumlicht: `steps` steuert, was nacheinander aufleuchtet. In der Oberfläche erscheint die Auswahl nur bei Art **Rundumlicht**.

| `steps` | Bedeutung |
|---|---|
| `channels` | RGB-Anteile nacheinander. Ein WS2811 mit `channel: rgb` ist ein 3er-Rundum (R→G→B). Mehrere Pixel werden kanalweise weitergezählt. |
| `leds` | Ganze LEDs nacheinander (gewählte Anteile zusammen). |
| `auto` (Standard) | Eine LED mit mehreren Anteilen wie `channels`, sonst wie `leds`. |

Blinker verschiedener Fahrzeuge haben unterschiedliche Perioden.

## Ports

| Port | Dienst |
|---|---|
| 8080/tcp | Weboberfläche |
| 62875/tcp | netBiDiB (Knoten-Server) |
| mDNS | `_wled._tcp` (Suche), `_bidib._tcp` und `_http._tcp` (Anzeige) |

## Architektur (Stufe 1)

- Kern schaltet logische Objekte und hält den Sollzustand.
- netBiDiB-Adapter: Pairing, Logon, Accessories (`MSG_ACCESSORY_SET` / `STATE` / `NOTIFY`).
- WLED: JSON-API, mDNS-Erkennung, Bindung an MAC.
- Web: Assistent, Übernehmen, Identifizieren, Testschalten, Bearbeiten, Löschen.

Noch nicht umgesetzt (siehe `KONZEPT.md`): direkter Rocrail-RCP-Client, Zeitautomatik über Modelluhr, WLED-Presets/UDP-Szenen.
