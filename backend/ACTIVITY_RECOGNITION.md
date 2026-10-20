# Experimental Activity Recognition

This backend adds an experimental three-state activity layer to the existing
RT-Spark MQTT pipeline. Raw sensor ingestion and `/api/latest` and
`/api/history` remain available as before. Every generated activity result is
marked `experimental: true`; no walking/running result has been validated
against labelled RT-Spark activity trials.

## Classification

Each complete 10-reading window is processed in this order:

1. The rule-based detector checks whether the sensor is relatively stationary.
   If all idle thresholds pass, the result is `IDLE` with method `RULE_BASED`.
2. Otherwise the existing corrected Decision Tree is applied. Model class 0
   maps to `WALKING`; class 1 maps to `RUNNING`; both use method
   `DECISION_TREE`.

These are the only activity labels. API `pending` and `unavailable` statuses
describe data or service readiness and are not activity classes.

The detector uses the norm of all three acceleration axes, its population
standard deviation and range, the maximum change in acceleration direction,
and the RMS and population standard deviation of the three-axis gyroscope
magnitude. Acceleration magnitude includes gravity; the detector does not
expect stationary acceleration to be zero. Gyroscope readings may include
bias and noise.

The default thresholds are conservative engineering starting points:

| Setting | Default | Meaning |
| --- | ---: | --- |
| `ACTIVITY_IDLE_ACCEL_MAG_STD_M_S2` | `0.15` | Maximum acceleration-magnitude standard deviation |
| `ACTIVITY_IDLE_ACCEL_MAG_RANGE_M_S2` | `0.50` | Maximum acceleration-magnitude peak-to-peak range |
| `ACTIVITY_IDLE_GYRO_RMS_RAD_S` | `0.12` | Maximum three-axis gyro-magnitude RMS |
| `ACTIVITY_IDLE_GYRO_STD_RAD_S` | `0.05` | Maximum gyro-magnitude standard deviation |
| `ACTIVITY_IDLE_DIRECTION_SPREAD_DEG` | `3.0` | Maximum acceleration-direction spread in the window |

All limits are inclusive and may be overridden with environment variables
before starting `app.py`. Values must be finite and non-negative. The SQLite
database contains no activity labels. The documented 140-reading stationary
transport test (rows 7–146 in the current database) was used only as a sanity
reference: its 27 overlapping windows had acceleration-magnitude standard
deviation up to `0.054 m/s²`, range up to `0.214 m/s²`, gyro RMS up to
`0.028 rad/s`, gyro-magnitude standard deviation up to `0.0031 rad/s`, and
acceleration-direction spread up to `0.375°`. This short stationary run does
not scientifically validate the thresholds. Later readings are not assumed
to be stationary.

## Existing model and preprocessing

The backend loads only:

- `models/activity_model_corrected.joblib`
- `models/activity_preprocessing_corrected.json`

At startup, the loader checks the selected model filename, six-axis approach,
exact feature order, window/stride, class mapping, model type, and the
serialized model's feature count and classes. SHA-256 over the corrected
artifact, preprocessing metadata, and active idle thresholds is stored as the
model version. Missing, corrupt, or incompatible
artifacts leave raw ingestion running, mark inference unavailable, and are
reported in `/health` and `/api/activity/latest`. The older model artifact is
never used as a fallback.

The model expects 24 features. In order, each listed axis contributes
`mean`, population standard deviation (`ddof=0`), `min`, and `max`:

1. `acceleration_x`
2. `acceleration_y`
3. `acceleration_z`
4. `gyro_x`
5. `gyro_y`
6. `gyro_z`

The code uses incoming STM32 values unchanged: acceleration remains in
m/s² and angular velocity remains in rad/s. The training CSV's units, sensor
orientation, placement, and gravity handling are undocumented. The model is
especially sensitive to `acceleration_y_max`; its training threshold is in
unverified raw dataset units. SI inputs are passed as required for this
experiment, but this does not establish that the model's numeric scale is
compatible. Do not interpret its walking/running predictions as validated.

## Windowing and background worker

The STM32 acquires at 25 Hz and normally publishes about 5 selected samples
per second. The backend buffers acquisition timestamps per device, builds
10-sample windows, and advances by five samples after each window. At the
nominal rate, the first result follows about two seconds of readings and later
results are normally produced about once per second.

Readings are ordered by their timezone-aware acquisition timestamp. Duplicate
timestamps and out-of-order messages are rejected for inference. A timestamp
gap over the configured limit clears that device's partial window; missing
samples are never interpolated. Invalid samples clear the affected partial
window. Invalid MQTT payloads and raw-storage failures also trigger a
discontinuity reset before the next accepted inference sample. Device buffers
are capped at 64 devices by default, with least
recently used partial state evicted if the cap is reached.

After existing payload validation and raw SQLite storage, the MQTT callback
offers each reading to a bounded, nonblocking queue. A single background
worker handles windows, idle checks, model inference, and prediction writes.
The default queue holds 100 readings. If it fills, the raw reading remains
stored, the inference sample is counted as dropped, and all partial inference
windows are reset at the next accepted queue generation so a window cannot
silently bridge a queue loss. Worker/model failures are counted and logged
without interrupting raw sensor storage.

The service starts only from `main()` and the Flask development server keeps
`use_reloader=False`, preventing a second inference worker from starting due
to the Werkzeug reloader. Shutdown stops MQTT intake and then drains/stops the
inference worker with a bounded wait.

Settings may be provided as environment variables before `app.py` starts:

| Setting | Default | Purpose |
| --- | ---: | --- |
| `ACTIVITY_QUEUE_CAPACITY` | `100` | Maximum queued inference readings |
| `ACTIVITY_MAX_DEVICES` | `64` | Maximum per-device partial buffers |
| `ACTIVITY_MAX_SAMPLE_GAP_SECONDS` | `0.6` | Continuity limit between acquisition timestamps |
| `ACTIVITY_STALE_AFTER_SECONDS` | `3.0` | Maximum age before a result stops being current |

Invalid non-positive queue, device, gap, or freshness settings use the default
and are logged. Invalid idle thresholds make the inference model unavailable
rather than changing the values silently.

## SQLite and API

Startup adds an `activity_predictions` table and index with `CREATE TABLE IF
NOT EXISTS`; it does not alter or rewrite `sensor_readings`. The prediction
table stores device ID, label, code, detection method, model version, UTC
window start/end timestamps, UTC creation time, and an experimental flag.
Activity code values are `0=IDLE`, `1=WALKING`, and `2=RUNNING`. A unique key
on device, model version, window start, and window end makes repeated writes
idempotent. Existing sensor rows are never assigned labels, and no historical
predictions are generated.

### Latest activity

`GET /api/activity/latest` optionally accepts `device_id`:

```powershell
Invoke-RestMethod 'http://127.0.0.1:5000/api/activity/latest?device_id=rt-spark-001'
```

The response includes `status`, `reason`, `current_activity`, the latest
prediction, age fields, an `is_stale` flag, experimental status, and inference
health counters. Status is:

- `available` when a recent prediction is current;
- `pending` when recent readings exist but a complete/fresh window is not yet
  available;
- `unavailable` when there is no recent sensor input or inference cannot run.

When a prediction is stale, `current_activity` is `null` even though the last
stored prediction remains available for diagnostics.

### Activity history

`GET /api/activity/history` supports `limit` from 1 to 100 and an optional
`device_id` filter:

```powershell
Invoke-RestMethod 'http://127.0.0.1:5000/api/activity/history?limit=20&device_id=rt-spark-001'
```

The existing `/api/latest` and `/api/history` endpoints continue to return
only raw sensor measurements. `/health` retains its MQTT/database health
fields and includes an `activity_inference` status object with queue depth,
drops, worker errors, model version, and timestamp/window counters.

## Running and verifying locally

The project virtual environment already documented in `README.md` is used.
Start the broker and backend as before; inference is started automatically by
`app.py` when the corrected artifacts load. If the model cannot load, the
backend still accepts and stores valid raw sensor messages.

From `backend/`, run the automated software checks with:

```powershell
.\.venv_lab3\Scripts\python.exe -m unittest discover -s tests -v
```

These tests use controlled synthetic windows and isolated in-memory SQLite
databases. They verify software behavior only. They do not assign activity
labels to existing hardware records and do not validate real-world accuracy.

## Hardware validation still required

Keep the STM32's 25 Hz acquisition, 5 Hz decimation, SI units, and MQTT
configuration unchanged. With the board in its intended body placement,
use this procedure:

1. Start the existing local broker and Flask backend. Check `/health`; confirm
   `mqtt_connected` and `activity_inference.model_loaded` are true.
2. Manually confirm the board is connected to Wi-Fi and has valid UTC using
   the existing firmware commands. Do not change or flash firmware for this
   backend test.
3. Place the board in its intended body position. Keep an external timestamped
   ground-truth log for separate stationary, walking, and running intervals.
   Include transitions and repeat sessions; do not infer labels from the
   classifier output or assign labels to old unlabelled database rows.
4. Start the board's existing `mqtt_stream` command. Observe
   `/api/activity/latest` and `/api/activity/history` for that device and
   inspect `/health` inference counters. The first classification should
   follow ten valid readings; later windows should advance every five.
5. Stop the existing MQTT stream after the planned capture. Confirm raw
   `/api/latest` and `/api/history` remain populated and check inference queue
   drops, discontinuity resets, and errors.

Use separate sessions or participants for final evaluation. Report confusion
matrix, per-class precision and recall, transition delay, and queue/worker
errors only after collecting explicit ground-truth labels. Threshold tuning
trials must not also be counted as held-out evaluation. Until then, all
predictions remain experimental and not hardware-validated.
