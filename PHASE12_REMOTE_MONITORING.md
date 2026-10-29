# Phase 12 remote monitoring setup

**Status:** local implementation and mock tests only. No Supabase project, migration,
secret, production setting, cloud write, STM32 live run, or Android test was
performed in this phase. The existing Vercel site remains on its prior deployment.

## Data path and contracts

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

The cloud dashboard uses one owner-authenticated snapshot request every five
seconds. It reuses the existing cards and response contracts. Freshness uses
local receive and prediction times, the backend observation, and successful
cloud sync time. Stored readings remain historical when any of those age out.
The initial thresholds are 15 seconds for sensor/prediction freshness and 20
seconds for heartbeat/sync; validate these in a real network trial.

## Approval boundary and external setup

These operations require the owner's explicit approval before execution:

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
4. Configure Vercel production environment values: `CLOUD_MONITOR_MODE=cloud`,
   `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`,
   `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, and `CLOUD_INGEST_TOKEN_HASHES`.
   Only the publishable URL/key have `NEXT_PUBLIC_` prefixes. Keep the secret
   key in server-only Vercel settings. Leave `BACKEND_URL` unset. Changing
   these values and deploying this code changes the public site from the
   disconnected dashboard to a sign-in page, so coordinate deployment.
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

Initial startup scans the existing history for the selected device. At large
backlog sizes, catch-up can take time and exceed cloud quotas. Review the
source row count and cloud quota before the first real sync; do not clear the
state or delete local records to speed it up. The worker sends a heartbeat
even when there are no new events, including an explicit backend-offline flag
when Flask cannot be reached.

## Security and retention review

The migration enables RLS on all four exposed tables. Only `authenticated`
gets `SELECT`, restricted by `auth.uid() = owner_id`; `anon` has no table grants
and no read policy. Browser/SSR reads use a publishable key and verified user
claims, then explicitly select only that owner's registered device. Users get
no write grants. The ingest route alone uses the server-only secret key, which
bypasses RLS after it has matched the dedicated token to a registered enabled
device and server-resolved owner. Every batch has at most 25 events and 64 KiB.
Credential failures return 401, device mismatch 403, malformed input 400,
oversize 413, and cloud storage failure 503 for retry.

**Seven-day cloud mirror target:** keep seven days by source/local receive
time after measuring actual Postgres storage and confirming recovery needs.
No automatic deletion, cron task, or retention migration is enabled. Once
approved, a separately reviewed maintenance job can delete old mirrored
sensor and prediction rows in bounded batches. Never apply that cleanup to
local SQLite. If delayed uploads exceed the retention window, decide whether
to archive, reject, or briefly retain them before enabling any cleanup.

## Verification before claiming live Android monitoring

1. Apply the migration in the approved Supabase project. Register the device
   with the correct owner UUID and confirm anon/other-user reads and all user
   writes fail; confirm owner reads work. Review grants and policies in the
   dashboard. No live RLS check was possible without a project.
2. Deploy the completed commit to the existing Vercel project only after
   production settings are approved. Check signed-out redirects, email link
   sign-in, expiry/refresh, logout, owner access, and other-user denial.
3. Run the existing local broker and Flask service, then the sync worker.
   Start the STM32 stream manually after Wi-Fi and synchronized time are
   available. Check the worker's outbox falls, cloud event IDs remain unique,
   source timestamps match SQLite, and history updates without duplicate rows.
4. Open the Vercel HTTPS URL on Android with Wi-Fi **off** and mobile data on.
   Verify six axes, prediction history, last sync time, and all stale/offline
   states by controlled disconnection and reconnection. Record latency and
   label any walking/running trials; classifier accuracy remains experimental.

Until these steps pass, the cloud code is a locally tested integration, not a
verified working remote monitor.
