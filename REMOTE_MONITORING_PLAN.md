# Vercel Deployment and Remote Monitoring Readiness

Reviewed 2026-10-22. No GitHub repository, Vercel project, Supabase project,
or other external resource has been created or connected.

## Current implementation

- The existing dashboard is in `web/`; its package lockfile is self-contained
  in that directory. Vercel should use `web` as its Root Directory.
- The browser calls only same-origin `/api/monitor/...` routes. The Next.js
  server proxy allows five read-only Flask paths and validates their JSON
  contracts.
- In production, if the server-only `BACKEND_URL` is absent, the proxy returns
  HTTP 503 without trying localhost. The page still renders a clear unavailable
  state. Old readings and predictions are not labeled live.
- The current dashboard has no sign-in flow. Keep cloud data private until
  authentication and row-level access rules are added.
- Local Node.js is 24.19.0. The Next.js 16.4.2 production build passed with
  Node 24; Vercel currently offers Node 24.x as its default supported runtime.
- The local tree has no Vercel project link or `vercel.json`. The project needs
  no custom Vercel build settings.

## First deployment: frontend only

Use these settings when the private repository and Vercel project are
explicitly approved:

| Setting | Value |
| --- | --- |
| Git repository | `BCA182_LAB3` (private, personal account) |
| Production branch | `main` |
| Root Directory | `web` |
| Framework | Next.js |
| Node.js | `24.x` |
| Install / build / output | Vercel's detected Next.js defaults |
| Environment variables | None |

There is no `vercel.json` requirement. Do not set `BACKEND_URL` to
`127.0.0.1`, the laptop's LAN address, or a public tunnel. Do not set
`NEXT_PUBLIC_BACKEND_URL`. The first HTTPS deployment will provide the usable
Android phone page and disconnected states, but no live measurements. Vercel's
Hobby plan is for personal, non-commercial use; verify the project and private
repository arrangement against its [terms](https://vercel.com/legal/terms).

The exact account and deployment steps are in
[`web/README.md`](web/README.md#vercel-frontend-deployment).

## Recommended live-data architecture

Keep the working laptop system as the source of truth and add an outbound-only
sync path:

```text
STM32 / ICM20608
      │ existing MQTT on the private LAN
      ▼
Local aMQTT → Flask + classifier → local SQLite
                                │
                      local retry queue
                                │ outbound HTTPS only
                                ▼
               Vercel authenticated ingest route
                                │ server-only Supabase key
                                ▼
             Supabase Postgres mirror + Auth/RLS
                                ▲
       Vercel read-only routes with signed-in user session
                                │ same-origin HTTPS polling
                                ▼
                  Android browser dashboard
```

This avoids opening inbound ports on the laptop. The existing Flask API,
MQTT broker, classifier, SQLite records, and sensor payload remain unchanged.
The sync code would be additive: a local SQLite outbox or cursor, an
idempotent batch sender, and Vercel routes for authenticated ingest and
read-only dashboard snapshots. It should retry with backoff and acknowledge
events only after the cloud write succeeds. SQLite remains canonical; a sync
outage must not block MQTT ingestion or inference.

### Data and freshness policy

- Keep the local 5 Hz sensor stream and all local records. Initially mirror at
  most one sensor reading per second to cloud; this is enough for the current
  display and its ten-second report count while reducing cloud storage.
- Mirror experimental prediction events and a small backend heartbeat
  (MQTT connection and inference-worker state). Do not relabel predictions as
  validated.
- Give every mirrored event a stable source ID and enforce a unique key such
  as `(device_id, source_id)` so retrying a batch cannot duplicate records.
- Start with seven days of cloud history, then review actual database size and
  egress. Keep the existing laptop SQLite history untouched. Longer retention
  should be an explicit quota decision.
- Preserve sensor event time and local receive time. The cloud route must
  calculate freshness from these source timestamps and the last heartbeat,
  never from the time a retry eventually reaches Supabase.
- If the heartbeat or latest sensor/prediction exceeds its freshness window,
  return `unavailable`/stale and keep any old values visibly historical.
- The current browser requests five endpoints every two seconds. For cloud
  mode, use one compact snapshot request for live status and refresh history
  less often; otherwise repeated database reads may consume the free egress
  allowance. The freshness UI can keep its existing two-second update cadence.

With the present 5 Hz input, the classifier first needs ten samples (about
two seconds) before a prediction is available. A one-second upload cadence,
network latency, and the dashboard's two-second polling suggest a few seconds
of end-to-end delay under good connectivity. This is a design estimate, not a
measured cloud result. When the laptop is offline, local collection continues;
cloud values age and become unavailable until sync resumes.

### Supabase feasibility and security

Supabase is a reasonable initial cloud candidate for a small academic demo,
with limits that make retention and polling relevant:

| Free-plan item | Current allowance / behavior | Effect here |
| --- | --- | --- |
| Database size | 500 MB per project | Seven-day retention and 1 Hz sensor mirroring are a reasonable starting point; measure real row/index size. Over-quota projects can become read-only. |
| Uncached egress | 5 GB | Database API responses count; use a compact live snapshot and avoid returning full history every two seconds. |
| Monthly active users | 50,000 | More than enough for a single authenticated phone user. |
| Inactivity | Low-activity free projects may pause after seven days | A dormant lab instance may need to be resumed manually. |
| Active free projects | Two | Enough for one project, subject to the account's existing project use. |

See [Supabase plan quotas](https://supabase.com/docs/guides/platform/billing-on-supabase),
[database size behavior](https://supabase.com/docs/guides/platform/database-size),
and [free-project pausing](https://supabase.com/docs/guides/platform/free-project-pausing).
The free plan is plausible for a short rolling mirror, not an unlimited archive;
the current endpoint polling should be consolidated before live cloud data is
enabled.

Use Supabase Auth email OTP or magic link for the dashboard owner. Create a
`devices` ownership mapping plus `sensor_readings`, `activity_predictions`,
and `device_status` tables. Enable RLS on all exposed tables and allow
authenticated `SELECT` only for the signed-in owner's device. Do not allow
anonymous reads or writes. The Vercel ingest handler validates a separate
high-entropy sync token, strict event schemas, device ID, payload size, and
timestamps before inserting.

Supabase publishable keys are not secrets, but RLS must restrict what they can
read. Supabase secret keys bypass RLS; keep the secret key only in the Vercel
server environment and never in browser code or the laptop. The laptop holds
only the narrow ingest token and sends outbound HTTPS to Vercel. See
[Supabase API key guidance](https://supabase.com/docs/guides/getting-started/api-keys),
[RLS guidance](https://supabase.com/docs/guides/database/postgres/row-level-security),
and [Supabase Auth](https://supabase.com/docs/guides/auth).

### Exact external resources for live monitoring

After explicit approval, the minimal service resources are:

1. **Private GitHub repository** `BCA182_LAB3`, owned by the account that will
   connect it to Vercel.
2. **Vercel project** connected to that repository with Root Directory `web`.
   Its first deployment needs no environment variables.
3. **One Supabase Free project** with Postgres and Auth enabled, in a region
   chosen near the device/operator. No public MQTT broker, public Flask host,
   Supabase Storage bucket, or Supabase Edge Function is required by this
   design.
4. **Database migration** for device ownership, mirrored sensor readings,
   prediction history, heartbeat state, indexes, RLS, and a seven-day cleanup
   policy.
5. **Dashboard sign-in** using Supabase Auth and an owner-only RLS policy.
6. **Server-only Vercel environment values** for Supabase URL, publishable key,
   Supabase secret key, and the ingest token. Keep every value out of Git and
   client-side variables.
7. **Laptop-only environment values** for the Vercel ingest URL and the same
   ingest token. Store them outside source control; do not add them to firmware
   or MQTT settings.

No provider SDK, cloud credential, database schema, or external resource has
been added in this preparation phase. Once Supabase and the external accounts
are approved, build and test the outbox, ingest/read routes, Auth/RLS, and
reconnect behavior locally with a mock endpoint before the first cloud write.

## Repository and account status

At review time, `main` was clean at `311d8bf` with no Git remote configured.
GitHub CLI is installed, but `gh auth status` reports that its saved token is
invalid. Reauthenticate with:

```powershell
gh auth login -h github.com -p https --web
gh auth status
```

After private-repository creation and push are explicitly approved, the
prepared commands are:

```powershell
gh repo create BCA182_LAB3 --private --source . --remote origin
git push -u origin main
```

Then authorize Vercel's GitHub app for this repository and import it as
described in `web/README.md`. No GitHub repository, Vercel account connection,
or deployment has been performed.
