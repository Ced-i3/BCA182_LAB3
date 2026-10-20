# BCA152 Laboratory Activity 3 — Activity Recognition System

An undergraduate IoT project that reads motion from an RT-Spark board, sends
sensor messages over Wi-Fi and MQTT, stores them in a local backend, and shows
sensor and experimental activity information in a responsive web dashboard.

## Objectives

The laboratory work combines embedded firmware, Wi-Fi/MQTT communication, a
backend API, activity-recognition software, persistent data storage, and a
user interface. The original guide describes a cloud backend and a mobile app.
This project uses a laptop-hosted backend and a Next.js web dashboard; those
deployment differences are explained below.

## System architecture

```text
RT-Spark / ICM20608
        │ Wi-Fi, MQTT QoS 1
        ▼
Laptop MQTT broker ──► Flask MQTT subscriber ──► SQLite
                              │                     │
                              └─ inference worker   └─ read-only REST API
                                                            │
                                             Next.js dashboard on laptop
```

The broker, Flask API and subscriber, inference worker, and SQLite database
run on the laptop. The dashboard reads the Flask API through its Next.js
server-side proxy. The website does not publish MQTT messages or modify
database records.

## Hardware requirements

- RT-Thread RT-Spark board with STM32F407ZGT6.
- On-board ICM20608 accelerometer and gyroscope.
- On-board RW007 Wi-Fi module.
- USB connection for power/programming and the UART console; an ST-LINK
  interface is used for authorized firmware programming.
- Laptop on the same private Wi-Fi network as the board for the local demo.

The laboratory PDF mentions LSM6DSL and ISM43362 in its generic firmware
examples. This project uses the ICM20608 and RW007 fitted to the RT-Spark.

## Software stack

- **Firmware:** RT-Thread 5.3.0, STM32F407 RT-Spark BSP, ICM20608, RW007,
  lwIP, software I²C, FinSH/msh commands.
- **Transport:** aMQTT 0.12.x broker and MQTT 3.1.1 QoS 1 messages.
- **Backend:** Python 3.13 environment, Flask, Paho MQTT, SQLite, NumPy,
  scikit-learn, joblib; pandas is used by the offline training scripts.
- **Web:** Next.js 16, React 19, TypeScript, Tailwind CSS, npm.

## Project structure

```text
AGENTS.md                         Project-specific development instructions
README.md                         Project overview and local setup
backend/
  app.py                          Flask API, MQTT subscriber, DB startup
  activity_recognition.py         Experimental idle/model inference
  inference_service.py            Bounded background inference worker
  broker.example.yaml             Example private-LAN broker configuration
  broker.yaml                     Local-only configuration; excluded from Git
  data/                           Local SQLite DB and source dataset
  models/                         Included corrected model and preprocessing metadata
  ml/                              Training/evaluation scripts and reports
  tests/                           Isolated backend unit tests
firmware/project-source/          Pinned dependency manifest, patches, overlays,
                                  and reconstruction instructions for publication
firmware/rt-thread/               Known-working local RT-Thread checkout; excluded
                                  from the proposed public Git repository
web/
  src/app/                         Next.js dashboard and read-only API proxy
  package.json, package-lock.json  Reproducible frontend dependencies
```

The working RT-Thread and `rw007-download/` directories remain intact locally
but are excluded from the proposed public repository. The small
[`firmware/project-source/`](firmware/project-source/README.md) package pins
their upstream commits and preserves the project-specific changes without
copying either nested Git history.
See [PUBLICATION_PLAN.md](PUBLICATION_PLAN.md) for the proposed Git staging
allowlist and excluded third-party materials.

## Prerequisites and quick start

For the local dashboard, install Python 3.13, Node.js 24 with npm, and Git.
Real live measurements also require the RT-Spark STM32F407ZGT6 board with
ICM20608 and RW007, a compatible ST-LINK/serial connection, a trusted local
Wi-Fi network, and the laptop MQTT broker. The included corrected model is
ready to load; the original training CSV and model retraining are **not**
needed to run inference. A clone without the board can run software tests and
show the dashboard's unavailable/empty states, but cannot produce genuine live
sensor readings.

From the repository root in PowerShell, install the backend and copy its
local-only broker example. If this working copy was moved after its virtual
environment was created, follow the
[backend virtual environment recovery procedure](backend/README.md#recovering-a-virtual-environment-after-moving-the-checkout)
instead of reusing that environment.

```powershell
Set-Location backend
py -3.13 -m venv .venv_lab3
.\.venv_lab3\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path broker.yaml)) { Copy-Item broker.example.yaml broker.yaml }
```

Check the laptop's Wi-Fi IPv4 address with `Get-NetIPConfiguration`. Edit the
copied `broker.yaml`: replace its example `192.168.1.50` listener address with
that private Wi-Fi address. Keep the `127.0.0.1:1883` listener for Flask. In
separate PowerShell terminals opened in `backend/`, run:

```powershell
.\.venv_lab3\Scripts\amqtt.exe -c broker.yaml
```

```powershell
.\.venv_lab3\Scripts\python.exe app.py
```

The first
backend start creates an empty `data/motion.db` with both tables; it does not
require a database download or manual SQL. Then, from `web/`, run:

```powershell
Set-Location ..\web
npm.cmd ci
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
npm.cmd run dev
```

Open `http://127.0.0.1:3000`. This is a documented series of terminals rather
than an automatic launcher, so broker and backend startup errors stay visible.
For fresh live data, manually join Wi-Fi on the STM32, synchronize UTC, point
`mqtt_config` to the laptop's LAN address, and run `mqtt_stream start` as
described below. No command automatically enters Wi-Fi credentials or starts
the board's MQTT stream.

## Verified features

- The ICM20608 is configured over `swi2c2` with ±4 g acceleration and
  ±500 degrees/second gyroscope ranges. Physical sensor acquisition at about
  25 Hz has been verified.
- The board can manually associate with Wi-Fi, synchronize UTC through SNTP,
  and publish genuine sensor readings over MQTT QoS 1.
- A documented 27.8-second run delivered 140 MQTT messages at about 5 Hz;
  the board reported 25 Hz acquisition, zero missed deadlines, and zero I²C
  errors. A later configuration regression delivered 106 messages at about
  5.01 messages/second and stored 106 corresponding records.
- The backend validates incoming sensor payloads, stores readings in SQLite,
  and runs activity inference in a bounded background worker.
- The Flask API and responsive Next.js dashboard expose sensor readings,
  activity history, and backend/inference state. Current activity is not
  shown when the API says its prediction is stale or unavailable.

These transport and storage tests do **not** validate walking/running model
accuracy. Activity outputs are experimental. The prior movement checks did
not constitute a controlled, ground-truthed walking/running study.

## Data flow and message format

The board samples at about 25 Hz and, when manually started, publishes selected
samples at a default 5 Hz to `lab3/sensors/motion`. The publisher decimates
samples; it does not average them. Timestamps come from the board's manually
synchronized UTC clock.

```json
{
  "device_id": "rt-spark-001",
  "timestamp": "2026-10-18T12:34:56.789Z",
  "accel_m_s2": {"x": 0.123, "y": -0.456, "z": 9.807},
  "gyro_rad_s": {"x": 0.010, "y": -0.020, "z": 0.030}
}
```

Acceleration is in m/s² and angular velocity is in rad/s. The actual payload
must contain a timezone-aware ISO 8601 timestamp. Do not use simulated
publisher output as evidence of physical sensor streaming.

## Firmware setup

The known-working BSP is at
`firmware/rt-thread/bsp/stm32/stm32f407-rt-spark`. For a new checkout, follow
[`firmware/project-source/README.md`](firmware/project-source/README.md) and
its exact [`dependency-manifest.json`](firmware/project-source/dependency-manifest.json)
to reconstruct the RT-Thread BSP with pinned package versions and the
project patches. This was verified in a separate reconstruction with ARM GCC
12.3.1 and SCons 4.11.1; ELF, BIN, and HEX artifacts were generated. The
working firmware checkout was not changed.

From PowerShell, use a terminal where the existing SCons and ARM GCC tools are
available. The BSP's `rtconfig.py` accepts `RTT_EXEC_PATH`; set it for that
terminal to the directory containing `arm-none-eabi-gcc.exe`. Its checked-in
default is a placeholder path, not a portable toolchain location.

```powershell
Set-Location firmware\reconstruction-work\rt-thread\bsp\stm32\stm32f407-rt-spark
$env:RTT_EXEC_PATH = "$env:USERPROFILE\.platformio\packages\toolchain-gccarmnoneeabi\bin"
python "$env:USERPROFILE\.platformio\packages\tool-scons\scons.py" -j1
```

The GCC BSP build configuration generates `rt-thread.elf`, `rtthread.bin`,
and `rtthread.hex`. The command above uses the existing PlatformIO cache if
installed; otherwise supply the paths to compatible ARM GCC and SCons tools.
For a separately authorized physical flash, connect ST-LINK under reset at
100 kHz, confirm the STM32F405/F407 family device ID `0x413` and 1024 KiB
Flash, program only the reconstructed BSP's `rtthread.hex`, and verify the
written Flash against the HEX. Do not mass erase or change option bytes.
Open the board's enumerated serial port at 115200 baud, 8-N-1. Building alone
does not prove hardware functionality; this phase does not flash the board.

The local reconstruction used the installed PlatformIO toolchain cache. A
clean-machine download of all upstream repositories and a build on another
computer remain to be verified; installed cache paths are machine-specific.

## Wi-Fi and MQTT setup

Wi-Fi association and time synchronization are manual. Use the board's
private credential-entry prompt; never put a Wi-Fi password in a shell
command, source file, issue, or log. See the published
[`TIME_SYNC_TEST.md`](firmware/project-source/overlays/rt-thread/bsp/stm32/stm32f407-rt-spark/TIME_SYNC_TEST.md) for the
`wifi status`, `time_sync`, and `time_status` procedure.

The RAM-only MQTT settings are managed from the UART shell:

```text
mqtt_config show
mqtt_config set broker <private-laptop-ip-or-hostname>
mqtt_config set port 1883
mqtt_config set device_id <unique-device-id>
time_status
mqtt_stream start
mqtt_stream status
mqtt_stream stop
```

The current client uses plain MQTT over TCP and the development broker is
anonymous on the private LAN. It does not support TLS or MQTT credentials in
the current firmware. Keep this broker on a trusted private network; do not
forward its port to the internet. Settings are RAM-only and return to the
development defaults after reset. See
[`MQTT_STREAM_TEST.md`](firmware/project-source/overlays/rt-thread/bsp/stm32/stm32f407-rt-spark/MQTT_STREAM_TEST.md)
for physical test results and diagnostic checks.

## Verify local sensor streaming

With broker and Flask running, open the board's enumerated UART port at
115200 baud, 8-N-1. Connect Wi-Fi through the private prompt, run `time_sync`,
and confirm `time_status` reports valid UTC. Run `mqtt_config show`; set the
broker to the laptop's current private Wi-Fi IPv4 address if needed. Then run
`mqtt_stream start`, check `mqtt_stream status`, and query `/api/latest` and
`/api/history?limit=5` on Flask. A genuine stream advances acquisition
timestamps and adds rows with the board's device ID. Stop with
`mqtt_stream stop` and verify stopped status. The simulator is for software
tests only and does not demonstrate hardware streaming.

## Backend setup (Windows PowerShell)

The following commands are for a new local setup. In this working copy, the
virtual environment and database already exist. Do not overwrite the local
`backend/broker.yaml` if it is already configured.

```powershell
Set-Location backend
py -3.13 -m venv .venv_lab3
.\.venv_lab3\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path broker.yaml)) { Copy-Item broker.example.yaml broker.yaml }
```

Before starting the broker, edit the copied `broker.yaml` and replace the
example private address with the laptop's current private Wi-Fi IPv4 address.
The example permits anonymous clients for an isolated laboratory LAN only.
Do not expose it to public networks. This project currently has no secure MQTT
TLS/authenticated firmware path.

Start the broker and Flask backend in separate PowerShell terminals, from the
`backend` directory:

```powershell
.\.venv_lab3\Scripts\amqtt.exe -c broker.yaml
```

```powershell
.\.venv_lab3\Scripts\python.exe app.py
```

Check the backend without starting duplicate services:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/health
Invoke-RestMethod http://127.0.0.1:5000/api/latest
```

`app.py` defaults to `127.0.0.1:5000`, connects to the broker at
`127.0.0.1:1883`, and stores SQLite data at `backend/data/motion.db`. These
values can be overridden with `API_HOST`, `API_PORT`, `MQTT_HOST`, `MQTT_PORT`,
and `MOTION_DB_PATH`. The current `app.py` starts the subscriber, inference
worker, and Flask development server together; it is for the local lab setup,
not a public production deployment.

The included `publish_simulated.py` sends **simulated** readings. Use it only
for software development; its messages are not physical hardware evidence.

## Activity recognition

The backend first applies a configurable rule-based stationarity detector to
each complete window. If the window is not classified as IDLE, the corrected
DecisionTreeClassifier predicts WALKING or RUNNING. The backend loads
`activity_model_corrected.joblib` and
`activity_preprocessing_corrected.json`; it does not use the older model as a
fallback.

The model expects a 10-sample window and 5-sample stride at the nominal 5 Hz
incoming rate. It calculates mean, population standard deviation (`ddof=0`),
minimum, and maximum for each of acceleration X/Y/Z and gyroscope X/Y/Z, in the
exact order in the preprocessing metadata. The training dataset is the
Run-or-Walk dataset. Its sensor units, placement, orientation, and gravity
representation are undocumented; the classifier has not been validated on
controlled RT-Spark walking/running trials. No confidence percentage is
reported. Read [`ACTIVITY_RECOGNITION.md`](backend/ACTIVITY_RECOGNITION.md)
and the model training reports for details and limitations.

The downloaded CSV remains in the local `backend/data/archive/` directory but
is excluded from Git until its redistribution terms are confirmed. The
project owner authorized redistribution of the existing corrected `.joblib`
artifact, so a fresh clone can run inference without the CSV or retraining.
This owner decision does not establish independent third-party dataset rights.
Only load joblib artifacts from trusted sources: deserialization can execute
code. The model's SHA-256, verified dependency versions, provenance, and
limits are documented in [`backend/models/README.md`](backend/models/README.md).

## REST API

All endpoints are read-only and served by Flask:

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Database, MQTT subscriber, and inference-worker health |
| `GET /api/latest` | Latest stored raw sensor reading, if any |
| `GET /api/history?limit=20` | Recent raw sensor readings (`limit` 1–100) |
| `GET /api/activity/latest?device_id=rt-spark-001` | Current prediction status and freshness |
| `GET /api/activity/history?limit=20&device_id=rt-spark-001` | Recent stored predictions |

Activity responses distinguish `available`, `pending`, and `unavailable` from
the three labels IDLE, WALKING, and RUNNING. A stale prediction is not returned
as current. Every hardware-facing prediction is marked experimental.

## Web dashboard setup

Node.js and npm are required. From PowerShell:

```powershell
Set-Location web
npm.cmd ci
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
npm.cmd run dev
```

Open `http://127.0.0.1:3000`. The server-side proxy defaults to Flask at
`http://127.0.0.1:5000`; set `BACKEND_URL` in `web/.env.local` only if the
local Flask address differs. The variable is server-side and must not be
renamed to `NEXT_PUBLIC_*`. The API proxy allows only the five read-only
routes listed above.

Run frontend checks from `web/`:

```powershell
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
npm.cmd run build
```

The dashboard works with an unavailable backend by showing its disconnected
state. It must not show old sensor data or an old prediction as live.

## Tests and verification

Backend tests use isolated temporary databases and do not need a running MQTT
broker:

See [VALIDATION.md](VALIDATION.md) for the current software-check results,
historical firmware and data-flow evidence, reproduction steps, and remaining
validation limits.

```powershell
Set-Location backend
.\.venv_lab3\Scripts\python.exe -m unittest discover -s tests -v
```

The documented physical baseline verifies sensor transport and storage for
the tested hardware/network setup only. It does not establish activity-model
accuracy or portability to other boards and networks.

## Deployment

The intended Vercel project root is `web/`, with `main` as the production
branch after a GitHub repository is created. Only the Next.js frontend is
planned for Vercel. A Vercel server cannot reach `127.0.0.1` on this laptop;
without a separately authorized hosted or private API design, a deployed page
will correctly show the backend as unavailable. No tunnel, public Flask
listener, or public MQTT listener is configured by this project.

### Deployment Limitations — Local Server Instead of Cloud Hosting

The laboratory guide originally proposes running the MQTT broker, backend,
classifier, and database on a cloud virtual machine. We investigated free
cloud-hosting options, including Oracle Cloud Free Tier and Microsoft Azure
student hosting. Account verification, payment-method requirements, and
free-tier access limitations prevented us from provisioning a suitable cloud
backend with the resources available for this project. This describes our
project experience; it does not mean that every provider rejected an
application.

We therefore run the MQTT broker, Flask API and subscriber, activity
classifier, and SQLite database on a laptop. The STM32 reaches that laptop
through Wi-Fi on the local network. This setup has demonstrated the complete
sensor-to-dashboard data path for the tested configuration, but it is not a
cloud deployment and does not fully meet the guide's cloud-hosting proposal.
The laptop must remain powered on and the local services must be running for
the backend to function. The local MQTT broker and API are not automatically
accessible over the public internet and must not be exposed for this demo.

The planned Vercel deployment will host only the Next.js frontend, not Flask,
MQTT, the classifier, or SQLite. A public Vercel site cannot reach a backend
bound to the laptop's localhost. Cloud backend hosting remains possible future
work, subject to suitable access, security, and resources.

## Known limitations

- WALKING and RUNNING predictions are experimental and are not validated by a
  controlled, labelled hardware study. Offline scores do not establish
  real-world accuracy.
- The local firmware MQTT implementation currently uses anonymous plaintext
  MQTT. It is suitable only for the existing private-lab-network setup and
  must not be pointed at a public broker.
- The backend runs Flask's development server and starts MQTT/inference in the
  same process. It needs a deliberate process split and a production WSGI
  server before public hosting.
- The local SQLite file contains sensor history and is excluded from Git.
- The firmware's development broker default and current local broker config
  refer to the laptop's private network; other users must configure their own
  network settings.
- Dataset redistribution rights have not been established from the files in
  this project. Verify the dataset terms before publishing its CSV.

## Troubleshooting

- **`/health` returns 503/degraded:** Flask is reachable but its MQTT
  subscriber is disconnected. Check the broker terminal, both listener
  addresses in `broker.yaml`, and whether port 1883 is already occupied.
- **No new readings:** confirm the STM32 joined the same LAN, has valid UTC,
  uses the laptop's current LAN address in `mqtt_config`, and has
  `mqtt_stream` started. Existing database rows are historical.
- **Activity unavailable:** check `/health` for the inference-worker status
  and verify the corrected model and preprocessing metadata are present.
  A complete recent window is needed before a prediction appears.
- **Frontend cannot reach Flask:** check `http://127.0.0.1:5000/health`,
  `web/.env.local`, and restart Next.js after changing `BACKEND_URL`.
- **Firmware build tool missing:** install a compatible ARM GCC and SCons,
  set `RTT_EXEC_PATH` for the current terminal, and follow the pinned
  reconstruction guide. Do not substitute another board's BSP.

## Future improvements

- Run controlled, labelled RT-Spark activity tests and report transition
  delay, class-wise metrics, and limitations.
- Review redistribution rights for the Kaggle dataset and derived model.
- Document clean-machine firmware/toolchain setup and verify it on another
  compatible Windows installation.
- Verify the pinned firmware reconstruction on a second computer and review
  remaining third-party source and dataset publication rights.
- Consider authenticated, TLS-protected MQTT and API transport only as a
  separately planned project phase.
- If a reachable backend is later provisioned, design Vercel authentication
  and API access before deployment.

## Credits and third-party licenses

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the pinned firmware
components, inspected upstream license files, attribution requirements, and
unresolved RW007 licensing question.

The proposed public source package contains patches and overlays, while its
manifest fetches the upstream RT-Thread and driver repositories at pinned
commits. Preserve their license and copyright notices. RT-Thread,
CMSIS-Core, STM32F4 CMSIS, and the ICM20608 package have Apache-2.0 license
files; the STM32F4 HAL package has BSD-3-Clause terms. RW007 has an
Apache-2.0 repository license, but its `SConscript` carries a separate GPLv3
annotation. lwIP sources contain BSD-style file notices. Review the
file-level licensing details in the firmware reconstruction guide before
redistributing bundled vendor source.

The Run-or-Walk dataset was obtained from Kaggle. Its CSV redistribution
license is not recorded here, so the proposed public staging set excludes the
CSV. The project owner explicitly authorized inclusion of the existing
corrected `.joblib` model for this repository; this is not an independent
assessment of the dataset's third-party terms. A fresh clone can load that
model using the pinned backend dependencies, without retraining. No
project-wide license is declared here. Choose one only after reviewing
authorship and third-party rights.

## References

- BCA180 ESP — Laboratory Activity 3 course PDF (kept locally; redistribution permission not established)
- [RT-Thread project](https://github.com/RT-Thread/rt-thread)
- [RT-Thread license information](https://rt-thread.github.io/rt-thread/page_code_contribution.html)
- [RW007 driver repository](https://github.com/RT-Thread-packages/rw007)
- [Run-or-Walk dataset](https://www.kaggle.com/datasets/vmalyi/run-or-walk)
- [Flask deployment guidance](https://flask.palletsprojects.com/en/stable/deploying/)
- [Next.js documentation](https://nextjs.org/docs)
- [Vercel environment variables](https://vercel.com/docs/environment-variables)
- [Vercel deployment protection](https://vercel.com/docs/deployment-protection)

