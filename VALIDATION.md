# Validation record

This record separates automated checks run in this checkout from earlier
firmware and physical data-flow results. Software tests do not establish
walking/running accuracy or validate hardware behavior.

## Reported physical hardware-to-cloud demonstration (2026-10-29)

The project owner reports that genuine RT-Spark ICM20608 readings reached
Supabase through the laptop MQTT broker, Flask/SQLite, authenticated HTTPS
cloud-sync worker, and Vercel ingest route on October 29, 2026. Supabase was
subsequently reported to contain 4,859 sensor readings and 4,856 activity
predictions, with the latest recorded sync at approximately 9:13 PM Philippine
time (UTC+8) on October 29. These are recorded totals, not a claimed count of
messages from a single run. They were supplied for this documentation update;
the database and demonstration were not independently rechecked during it.

This demonstrates the reported data path, not the correctness of activity
labels. The public read-only Vercel website does not require viewer login.
Fresh data still requires the board stream and laptop services to be running.

## Previously recorded automated software checks (2026-10-20)

On 2026-10-20, after the frontend proxy regression tests were added:

| Check | Result |
| --- | --- |
| Backend `python -m unittest discover -s tests -v` | 32 tests passed. The suite used its isolated test data and did not start a broker or overwrite the runtime database. |
| Frontend `npm.cmd test` | 13 tests passed, including production behavior with no `BACKEND_URL`, an unreachable upstream, invalid upstream content, and the proxy allowlist. |
| Frontend `npm.cmd run typecheck` | Passed. |
| Frontend `npm.cmd run lint` | Passed. |
| Frontend `npm.cmd run build` | Passed with Next.js 16.4.2. |
| `git diff --check` | Passed for the reviewed changes. |
| Corrected model SHA-256 | Matched the recorded value `85200d80466093a98ded077b4c02ea11f3c030eebb935224e0da806472b7d82f`. |

The model-loading and inference-worker tests load the committed corrected
artifact. The backend suite includes database, raw API, activity API, freshness,
and worker error-path coverage. The frontend production build compiled the
Next.js API proxy; the proxy tests invoke it with isolated environment and
network stubs. No Vercel deployment or hardware test was run in this phase.

## Previously recorded firmware and physical verification

These results are retained from earlier project phases and were not rerun as
part of this documentation and frontend-test update:

- A separate firmware reconstruction from the pinned manifest and project
  patches produced ELF, BIN, and HEX files with ARM GCC 12.3.1 and SCons
  4.11.1. The known-working firmware checkout was preserved. See
  [`firmware/project-source/README.md`](firmware/project-source/README.md).
- RT-Spark sensor acquisition, Wi-Fi association, time synchronization, and
  MQTT delivery were physically demonstrated. The recorded 2026-10-18 runs
  delivered 140 messages in 27.8 seconds and later 106 messages at about
  5.01 messages per second. The backend stored the readings and served them
  through Flask. See the test records in
  [`firmware/project-source/overlays/rt-thread/bsp/stm32/stm32f407-rt-spark/MQTT_STREAM_TEST.md`](firmware/project-source/overlays/rt-thread/bsp/stm32/stm32f407-rt-spark/MQTT_STREAM_TEST.md).
- Earlier software verification covered 32 backend tests, nine frontend
  contract/freshness tests, TypeScript, ESLint, a Next.js production build,
  corrected-model loading, empty SQLite initialization, and the five Flask
  API endpoints. This phase adds four frontend proxy tests; its current test
  totals are listed above.
- Phase 12D preview security checks included owner/other-user isolation,
  anonymous read and user-write denial, ingest deduplication, and a disposable
  cloud-sync fixture. These were historical checks, not rerun for this update;
  see [Phase 12](PHASE12_REMOTE_MONITORING.md#historical-phase-12d-live-checks-2026-10-29-preview).

These are historical checks for the recorded machine, dependency set, board,
and local network. They are not new measurements from this phase.

## Reproduce software checks

Each example starts from a new PowerShell terminal opened at the repository
root. The backend test suite runs without starting MQTT or using the runtime
database:

```powershell
Set-Location backend
.\.venv_lab3\Scripts\python.exe -m unittest discover -s tests -v
```

For a clean clone, first create the environment and install
`backend/requirements.txt` as described in [`backend/README.md`](backend/README.md).
If a working copy and its environment were moved, follow that README's
recovery procedure and use the replacement environment. Do not edit or delete
the old environment as an automatic cleanup step.

Run the frontend checks from `web/`:

```powershell
Set-Location web
npm.cmd ci
npm.cmd test
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
```

`npm.cmd ci` is for a fresh clone with dependencies not yet installed. The
model hash can be checked from the repository root with:

```powershell
Get-FileHash backend\models\activity_model_corrected.joblib -Algorithm SHA256
```

The expected hash and model limitations are recorded in
[`backend/models/README.md`](backend/models/README.md). Firmware reconstruction
and build reproduction steps are in
[`firmware/project-source/README.md`](firmware/project-source/README.md);
they require the pinned dependencies and compatible ARM GCC/SCons tools.

## Unperformed scientific validation and remaining limitations

- Real-world walking/running accuracy on RT-Spark hardware. The model remains
  experimental and has not been evaluated on controlled, labelled trials.
- The laboratory's proposed cloud-hosted MQTT broker and classifier and native
  Android app. This implementation keeps the broker, classifier, Flask, and
  SQLite on the laptop, mirrors data to Supabase, and uses a responsive website.
  Instructor acceptance of these architectural substitutions is not assumed.
- Fresh upstream dependency downloads and firmware reconstruction on an
  arbitrary external computer or hardware setup.
- Hardware behavior after the latest software and documentation changes. No
  STM32 was flashed or tested for this phase.

## Local Python environment note

The ignored `backend/.venv_lab3` directory was created before the project folder
was renamed. Its `pyvenv.cfg` and `amqtt.exe` launcher still contain the former
absolute path. The Python executable ran the 32-test backend suite, but the
`amqtt.exe --help` launcher check exited with status 1. No files in
the environment were changed or deleted. Use the separate-environment recovery
procedure in [`backend/README.md`](backend/README.md) before starting the local
broker from this moved checkout.

## Deployment and next work

The Vercel project root is `web/`. Its authenticated ingest route and
fixed-device public monitor use Supabase; Flask, MQTT, inference, and SQLite
remain local. Do not expose Flask or MQTT directly or point Vercel at the
laptop's `127.0.0.1`. The [root README](README.md#deployment) explains the
difference from the laboratory's cloud-hosting proposal.

Next validation work is to collect labelled RT-Spark walking/running trials,
verify the pinned firmware reconstruction on a clean computer, resolve the
RW007 licensing annotation and the dataset redistribution terms. The
model's accuracy must not be described as hardware-validated until that
measurement work is complete.
