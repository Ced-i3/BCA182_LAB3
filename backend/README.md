# BCA152 Activity Recognition — Phase 1 Backend

Minimal local service: MQTT sensor messages → validation → SQLite → Flask JSON API.
The included publisher generates **simulated** data; it does not read the RT-Spark.

## Message format

Topic: `lab3/sensors/motion`

```json
{
  "device_id": "simulator-1",
  "timestamp": "2026-10-16T00:00:00.000Z",
  "accel_m_s2": {"x": 0.1, "y": -0.2, "z": 9.8},
  "gyro_rad_s": {"x": 0.01, "y": 0.02, "z": -0.03}
}
```

Acceleration is in metres per second squared; angular velocity is in radians per second. Timestamps must include a timezone. The receiver rejects malformed messages and messages with missing or extra fields.

## Start on Windows PowerShell

For a fresh clone, run these from the `backend` folder. The virtual
environment keeps Python packages local to this project. If this is an
existing checkout moved after its environment was created, use the recovery
procedure below instead of reusing or updating that moved environment.

```powershell
py -3.13 -m venv .venv_lab3
.\.venv_lab3\Scripts\python.exe -m pip install -r requirements.txt
```

## Recovering a virtual environment after moving the checkout

Python virtual environments are not reliably relocatable. A moved Windows
environment can retain the old absolute project path in `pyvenv.cfg` and in
generated command launchers. The Python executable may still run while a
launcher such as `amqtt.exe` fails. Do not edit those generated files or
delete the old environment as part of recovery.

From `backend/`, create a second environment and install the pinned backend
requirements into it:

```powershell
py -3.13 -m venv .venv_lab3_rebuilt
.\.venv_lab3_rebuilt\Scripts\python.exe -m pip install -r requirements.txt
```

Keep the original environment until the replacement has been checked. Use
the replacement's commands from separate terminals in `backend/`:

```powershell
.\.venv_lab3_rebuilt\Scripts\amqtt.exe -c broker.yaml
.\.venv_lab3_rebuilt\Scripts\python.exe app.py
.\.venv_lab3_rebuilt\Scripts\python.exe -m unittest discover -s tests -v
```

Use `.venv_lab3_rebuilt\Scripts\python.exe` for the simulator as well. The
existing `broker.yaml` and SQLite database are separate local data files;
this procedure does not replace them. A fresh clone can continue using the
standard `.venv_lab3` setup above.

If `broker.yaml` does not exist, create a local copy from the example, then
replace the example private address with the laptop's current private Wi-Fi
IPv4 address:

```powershell
if (-not (Test-Path broker.yaml)) { Copy-Item broker.example.yaml broker.yaml }
```

Use `Get-NetIPConfiguration` to identify the laptop's current Wi-Fi IPv4
address and replace only the example LAN listener address in `broker.yaml`.
Keep the `127.0.0.1:1883` listener for the local subscriber. The sample
listens on port 1883, accepts the `lab3/sensors/motion` topic, and uses
anonymous MQTT only on a trusted private LAN. It does not bind to `0.0.0.0`.
The STM32 must be on the same reachable LAN; use its manual
`mqtt_config set broker HOST`, `mqtt_config set port 1883`, and
`mqtt_config set device_id ID` shell commands for that laptop address and a
unique device identifier. The usual development ID is `rt-spark-001`; it is
not a broker credential. Do not configure router port forwarding or use this
plaintext example on the public internet.

`broker.yaml` is a machine-local file and is excluded from Git. The example
allows anonymous clients on a private lab network only. Do not expose port
1883 publicly or reuse this anonymous configuration on an untrusted network.

Open separate PowerShell terminals in this folder:

1. Start the local MQTT broker: `.\.venv_lab3\Scripts\amqtt.exe -c broker.yaml`
2. Start Flask and its MQTT subscriber: `.\.venv_lab3\Scripts\python.exe app.py`
3. Publish simulated readings: `.\.venv_lab3\Scripts\python.exe publish_simulated.py --count 5 --interval 1`

The Flask subscriber and simulator connect to `127.0.0.1:1883` by default.
The RT-Spark uses the laptop's private LAN address to reach the second broker
listener. Mosquitto is not required for this local test. The backend and
publisher use the standard MQTT client library and can use another broker by
setting `MQTT_HOST` and `MQTT_PORT`.

## Check the API

```powershell
Invoke-RestMethod http://127.0.0.1:5000/health
Invoke-RestMethod http://127.0.0.1:5000/api/latest
Invoke-RestMethod 'http://127.0.0.1:5000/api/history?limit=5'
```

`/health` returns HTTP 200 when SQLite is available and MQTT is connected, or HTTP 503 when the MQTT subscriber is disconnected. `GET /api/history` accepts `limit` from 1 to 100 (default 20).

Database file: `data/motion.db` (created when the backend starts).
The first start creates the directory and the `sensor_readings` and
`activity_predictions` tables automatically; no downloaded database or manual
SQL is required. Set `MOTION_DB_PATH` to a different path for an isolated
database. An empty database yields empty raw/history responses; genuine new
rows require a publishing STM32 or an explicitly labelled simulator.

## Experimental activity predictions

When the corrected model artifacts load, `app.py` starts a bounded background
inference worker. The first activity result requires ten recent MQTT readings;
later windows advance by five readings. Idle checks use configurable
acceleration and gyroscope stability thresholds. Predictions are experimental
and have not been validated against labelled RT-Spark walking/running trials.
See [`ACTIVITY_RECOGNITION.md`](ACTIVITY_RECOGNITION.md) for the model contract,
window rules, thresholds, database fields, and limitations.
The corrected model and metadata are included in `models/`; a fresh clone
does not need the original training CSV or a training run. Runtime versions
are pinned in `requirements.txt`. Offline training alone additionally needs
`requirements-training.txt` and a separately obtained, rights-cleared CSV.
Only load the included joblib artifact from a trusted checkout, because
joblib deserialization can execute code. See [`models/README.md`](models/README.md)
for its SHA-256 and experimental limitations.

```powershell
Invoke-RestMethod 'http://127.0.0.1:5000/api/activity/latest?device_id=rt-spark-001'
Invoke-RestMethod 'http://127.0.0.1:5000/api/activity/history?limit=20&device_id=rt-spark-001'
```

`/api/activity/latest` reports `available`, `pending`, or `unavailable` and
does not expose a stale prediction as the current activity. These statuses are
not additional activity classes. `/health` includes inference queue and error
counters under `activity_inference`.

Run the backend software tests without publishing to the broker or touching
the project database:

```powershell
.\.venv_lab3\Scripts\python.exe -m unittest discover -s tests -v
```
