# Phase 12 remote monitoring setup

## Current implementation: public university demo

The [original Vercel production dashboard](https://bca182-lab3.vercel.app)
is deployed and opens without a viewer login
when `CLOUD_MONITOR_MODE=cloud`. `GET /api/cloud/monitor` publicly returns a
bounded, read-only snapshot for the single enabled `rt-spark-001` device. The
server queries only approved sensor, prediction, and heartbeat columns using a
server-only Supabase secret; requests cannot choose a device, owner, table, or
query. The response is cached at the CDN for at most three seconds and polled
every five seconds. Errors are not cached. Stored readings are marked stale or
offline when the heartbeat and sync timestamps expire. The experimental model
label remains visible as history when it is no longer current.

The Supabase tables retain owner-only RLS and no anonymous table grants. The
token-protected ingest route and durable laptop outbox remain unchanged. Public
viewers can see the six sensor axes, activity predictions, status, and times for
this device. Do not use this mode for private monitoring. Supabase Auth may
remain configured, but the demo website no longer sends magic links or uses
viewer sessions. The older owner-login deployment notes below describe the
previous private mode and do not apply to the current demo build. On October
29, 2026, real STM32 sensor data was reported to have reached the cloud.
See [validation](VALIDATION.md) for the recorded counts and their limitations.

Production needs only `CLOUD_MONITOR_MODE=cloud`, `SUPABASE_URL`,
`SUPABASE_SECRET_KEY`, and `CLOUD_INGEST_TOKEN_HASHES` as Vercel server-side
variables. Do not set privileged values with `NEXT_PUBLIC_` names. Keep the
dedicated token on the laptop. Before deployment, record the current production
deployment ID for Instant Rollback and verify the public endpoint, invalid
ingest-token rejection, and browser bundle do not expose secrets.

To demonstrate real data, start the existing broker and Flask in separate
PowerShell terminals from `backend/`:

```powershell
.\.venv_lab3\Scripts\amqtt.exe -c broker.yaml
.\.venv_lab3\Scripts\python.exe app.py
```

In a third `backend/` terminal, load the private, Git-ignored cloud environment
for that terminal and run:

```powershell
foreach ($line in Get-Content .env.cloud.local) {
  if ($line -match '^([A-Z][A-Z0-9_]*)=(.*)$') {
    [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process')
  }
}
.\.venv_lab3\Scripts\python.exe cloud_sync.py
```

On the board console, connect Wi-Fi, wait for valid SNTP time, set the laptop's
reachable broker IP with `mqtt_config set broker HOST`, then run
`mqtt_stream start 5`. Do not use the simulated publisher. Open the original
Vercel URL on Android with Wi-Fi off. Verify fresh timestamps, six axes,
prediction history, and a current activity only while the stream is fresh.

After a demo, stop `mqtt_stream` and the sync worker. If the owner decides to
retire the demo, review rollback and backups, remove the production cloud
environment values after the route is retired, and rotate the ingest token.
Review ownership before changing hosted resources. Preserve cloud data and
local SQLite and sync state. No automatic cloud-data deletion is enabled.

### Historical provisioning status (earlier on 2026-10-29)

At the time of the preview checks, the existing Supabase Free project
had migration `202610290001_cloud_monitoring` applied. All four application
tables had RLS enabled, authenticated owner-only SELECT policies, and no
anonymous table grants. The verified owner owned the enabled `rt-spark-001`
device. Public sign-up was disabled, email sign-in remained enabled,
and the owner signed in to the protected Vercel Preview. Local development
credentials were stored only in Git-ignored environment files. Preview-only
Vercel variables were configured; production variables and the existing
production deployment remained unchanged. No genuine STM32 cloud stream or
Android mobile-data test had been completed. These statements describe that
earlier preview, before the reported production hardware-to-cloud demonstration.

**Original Phase 12 result:** local implementation and mock tests only. Cloud
provisioning was performed later under Phase 12C and 12D authorization.

## Data path and contracts

### Historical Phase 12D live checks (2026-10-29 preview)

An isolated, temporary unrelated Auth user signed in and saw no owner device;
its direct table write and an anonymous read were denied. The test user was
removed. An isolated sensor/prediction batch was uploaded twice through the
local Next.js ingest route and stored once with the registered owner and source
timestamps; those test rows were removed. A disposable SQLite fixture tested
the real cloud sync worker's first-run history fence, failed HTTPS outbox
retention, and restart recovery against a protected Vercel Preview. For the
successful Preview request, the worker used a test sender backed by the
official `vercel curl` protection bypass. The production worker's built-in
HTTPS sender had not yet completed a successful Vercel request at that stage.
All cloud test rows were removed, and the historical laptop SQLite database
was not opened.

Supabase CLI 2.122.0 maps `[auth.email] enable_signup = false` to disabling the
email provider on the hosted project. Keep `[auth] enable_signup = false` and
the email provider enabled so existing users can sign in. The Auth settings
endpoint confirmed that sign-up is blocked and email is enabled. The security
advisor reports a leaked-password-protection warning; Supabase documents that
feature as Pro-only, so it was not enabled on this Free project. That preview
used passwordless email links; the current public demo does not use viewer login.

The STM32 still sends its established 5 Hz MQTT payload to the laptop. Flask
still stores every accepted reading and experimental prediction in the local
SQLite database. Run `backend/cloud_sync.py` as a separate laptop process; it
reads only rows for `CLOUD_DEVICE_ID`, selects about one reading per local
receive second, sends every stored prediction, and sends a small status report
over HTTPS. It never changes the source database or MQTT flow. A separate
`backend/data/cloud_sync.db` stores scan cursors and a durable outbox.

The Vercel ingest route accepts a bearer token only for its mapped device. It
looks up the registered owner in Supabase, validates a batch, and writes rows
idempotently. Partial cloud failures can leave some rows written, but the
worker retains and resends the whole batch; the unique `(device_id,event_id)`
key makes retries safe. `last_successful_sync_at` is set only after all row
writes succeed. The source `timestamp`, SQLite `received_at`, prediction
window times, and `created_at` remain distinct from cloud receipt time.

The current public dashboard requests a fixed-device snapshot every five
seconds. It reuses the existing cards and response contracts. Freshness uses
local receive and prediction times, the backend observation, and successful
cloud sync time. Stored readings remain historical when any of those age out.
The initial thresholds are 15 seconds for sensor/prediction freshness and 20
seconds for heartbeat/sync; validate these in a real network trial.

## Historical provisioning and external setup

The following describes the earlier provisioning workflow, not steps needed
for an already configured deployment. Further changes to hosted resources
require the owner's authorization:

1. Create one Supabase Free project in an agreed region. Payment information
   is generally not needed for Free, subject to the current account and plan.
   The plan has database size, egress, and project inactivity limits; review
   current quotas in the [Supabase billing docs](https://supabase.com/docs/guides/platform/billing-on-supabase).
2. Configure Auth for an existing owner email. Disable public sign-ups, keep
   email confirmation enabled, and allow `https://bca182-lab3.vercel.app/auth/callback`
   as a redirect. Create/invite the owner through the official dashboard.
3. Apply `supabase/migrations/202610290001_cloud_monitoring.sql` in the SQL
   Editor or a reviewed migration workflow. Register one device using its
   stable `device_id` and the owner user's Auth UUID. This SQL is not applied
   by the local build. Test RLS with an owner, a second user, and anon before
   sending any genuine readings.
4. For the current public demo, configure `CLOUD_MONITOR_MODE=cloud`,
   `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, and `CLOUD_INGEST_TOKEN_HASHES`
   as server-side Vercel values. Keep privileged values out of `NEXT_PUBLIC_`
   variables and leave `BACKEND_URL` unset. Coordinate any deployment change.
5. Configure the laptop process with the values in `backend/.env.example`.
   Store actual values in a private environment file or OS secret store,
   outside Git. Start the worker only after the approved cloud route is live.

Use the official dashboards or secure environment-variable controls for all
credentials. Do not paste tokens or keys into chat, source, or issue trackers.
Do not create a public tunnel or expose local ports 5000/1883.

## Token creation and rotation

Generate a dedicated URL-safe token with at least 32 random bytes using a
trusted password manager or local cryptographic random generator. Put the
token only in the laptop environment. Put its lowercase SHA-256 hex digest in
the Vercel `CLOUD_INGEST_TOKEN_HASHES` JSON map, keyed by registered device ID.
For example, a local secure terminal can compute the digest from a private
environment value without printing the token:

```powershell
node -e "console.log(require('node:crypto').createHash('sha256').update(process.env.CLOUD_INGEST_TOKEN).digest('hex'))"
```

To rotate without data loss, stop the worker, configure a fresh token and hash
in the respective environments, deploy the Vercel change, and restart the
worker. The outbox retains unsent rows. The current implementation maps one
hash per device, so overlap between old and new tokens is not supported.

## Laptop operation and backlog behavior

Start the existing broker and Flask backend as documented in `backend/README.md`.
Then run `python cloud_sync.py` in `backend/` using that backend environment.
The worker requires HTTPS and rejects missing/short tokens or invalid batch
settings. HTTP/network failures leave events in the outbox and retry with
bounded exponential backoff. The outbox holds at most 10,000 events; scanning
pauses at capacity and later catches up from the untouched SQLite source.
Thus the queue is bounded without dropping source rows. Keep the source DB and
sync-state DB backed up together. If the source DB is deleted, rows cannot be
recovered from the cursor. If the state DB is lost, the worker replays the
source, and cloud event uniqueness prevents duplicates. A malformed historical
row stops scanning at that row and requires manual review; it is not silently
skipped. The worker sends only rows matching `CLOUD_DEVICE_ID`; device ID alone
does not cryptographically prove physical origin, so do not run the simulator
under the same ID during a hardware demo.

Initial startup fences off existing history and mirrors only new rows. Historical
backfill requires separate owner approval. After startup, an offline backlog
still catches up from the durable cursor when connectivity returns. Do not clear
the state or delete local records to speed it up. The worker sends a heartbeat
even when there are no new events, including an explicit backend-offline flag
when Flask cannot be reached.

## Security and retention review

The migration enables RLS on all four exposed tables. Only `authenticated`
gets `SELECT`, restricted by `auth.uid() = owner_id`; `anon` has no table grants
and no read policy. Users get no write grants. The server-side public monitor
route uses a privileged key to read only the fixed enabled demo device and
returns a bounded snapshot without exposing the key. The ingest route also
uses the server-only secret key, which bypasses RLS after it has matched the
dedicated token to a registered enabled device and server-resolved owner.
Every batch has at most 25 events and 64 KiB.
Credential failures return 401, device mismatch 403, malformed input 400,
oversize 413, and cloud storage failure 503 for retry.

**Seven-day cloud mirror target:** review retention against actual Postgres
storage and recovery needs. No automatic deletion, cron task, or retention
migration is enabled. Preserve local SQLite and cloud data while retention is
reviewed separately, including how delayed uploads should be handled.

## Further validation

The reported October 29 physical stream demonstrates cloud delivery, not
classification accuracy. For a further remote test, start the local services
and board as above, check that the outbox drains and timestamps and event IDs
match, then inspect the public dashboard from Android mobile data. Record
latency and stale/offline behavior under controlled disconnection. Labelled
walking/running trials and independent model evaluation remain outstanding.

## Production rollback

Before activation, record the current Vercel production deployment ID and keep
it available. If the cloud deployment fails, use Vercel's **Instant Rollback**
to the immediately previous production deployment (or `vercel rollback` from
the linked project), then verify the original dashboard URL. On the Hobby
plan, only the immediately previous production deployment is eligible for this
rollback. This changes routing to the old build without deleting Supabase or
SQLite records. Stop the laptop sync worker if cloud ingestion is failing.
After rollback, inspect Vercel's production-domain auto-assignment setting
before any later push: rollback can disable automatic assignment. Do not delete
cloud rows or local sync state as part of rollback. See the
[Vercel rollback guide](https://vercel.com/docs/deployments/rollback-production-deployment).
