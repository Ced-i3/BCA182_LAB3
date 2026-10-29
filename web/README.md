# Activity Monitor web dashboard

A read-only, responsive frontend for the BCA152 Lab 3 RT-Spark activity-monitoring system. Next.js runs on the laptop and reads the existing Flask API. The STM32 publishes measurements through MQTT to Flask; the browser does not talk to MQTT or SQLite.

Phase 12 adds a separate, owner-authenticated cloud mode. It is locally tested
but not provisioned or deployed. The existing local Flask mode remains the
default. See [Phase 12 setup](../PHASE12_REMOTE_MONITORING.md); the Vercel
frontend instructions below describe the earlier frontend-only deployment.

## Stack and prerequisites

- Next.js App Router, React, TypeScript, Tailwind CSS, npm
- Node.js 20.9 or later (the project was built with Node.js 24)
- Existing Flask backend for live data; the existing MQTT broker and STM32 stream are needed for **new** readings

From the project root, enter the `web` folder before running frontend commands:

```powershell
Set-Location .\web
npm.cmd ci
npm.cmd run dev
```

Open `http://127.0.0.1:3000`. `npm.cmd` works even when PowerShell script execution policy prevents `npm.ps1` from running. The site refreshes about every two seconds. It makes only read-only GET requests.

For a production build:

```powershell
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
npm.cmd run build
npm.cmd run start
```

## Connect to Flask locally

The Next.js server proxies five known read-only paths to Flask. Browser requests stay on the Next.js origin, so Flask CORS and its localhost binding need no change. In development, the server defaults to `http://127.0.0.1:5000`. Set `BACKEND_URL` in `web\.env.local` if your Flask address differs:

```text
BACKEND_URL=http://127.0.0.1:5000
```

Copy `.env.example` to `.env.local` as a starting point. Do not use a `NEXT_PUBLIC_` variable for this address. The proxy accepts only `/health`, `/api/latest`, `/api/history`, `/api/activity/latest`, and `/api/activity/history`; it does not accept an arbitrary destination. Production builds without `BACKEND_URL` show an unavailable state.

If Flask is not already running, check `http://127.0.0.1:5000/health` first. Start only services that are not already running. Open two PowerShell terminals from the project root and enter `backend` in each:

In the first terminal, start the MQTT broker:

```powershell
Set-Location .\backend
.\.venv_lab3\Scripts\amqtt.exe -c broker.yaml
```

In the second terminal, start Flask and its MQTT subscriber:

```powershell
Set-Location .\backend
.\.venv_lab3\Scripts\python.exe app.py
```

A broker connection alone does not mean the STM32 is streaming. The frontend never sends MQTT commands or changes the database.

## What the dashboard shows

- `IDLE`, `WALKING`, or `RUNNING` is displayed as **current** only when `/api/activity/latest` says `available` and its prediction is fresh. Pending, unavailable, and stale are not activity classes.
- Activity history stays visible as **previous predictions** even when no current prediction exists.
- Sensor axes come from `/api/latest`, with acceleration in m/s² and gyroscope values in rad/s. Old values are marked as last recorded data, not live readings.
- `/health` reports backend, MQTT subscriber, and inference-worker status. `/api/history` supports a count of recent sensor reports; `/api/activity/history` supplies the recent prediction list.
- Times are stored by Flask in UTC and displayed in the viewer's local time zone.

All predictions are experimental. The walking/running Decision Tree was trained on a different dataset with undocumented units and orientation, and its accuracy on this STM32 installation is **not established**. No confidence percentage is displayed.

## Common problems

- **Cannot connect to monitoring server:** check Flask at `http://127.0.0.1:5000/health`, then check `BACKEND_URL` and restart the Next.js server after changing `.env.local`.
- **Backend online, no recent sensor data:** the STM32 may not be publishing. Old database readings are intentionally shown as historical values.
- **Activity pending:** Flask needs a complete, recent ten-reading window before producing a prediction.
- **Recognition unavailable:** check Flask `/health` for model and inference-worker status. The frontend does not load or replace model artifacts.
- **PowerShell refuses `npm`:** use `npm.cmd` as shown above.
- **npm reports `ENOTCACHED` or a refused `127.0.0.1:9` proxy:** this terminal may have process-level offline or proxy settings. Check your network access, then override only that PowerShell session if appropriate; do not change global npm or Windows security settings. For example, `$env:NPM_CONFIG_OFFLINE='false'` disables npm's offline mode for the current terminal.

## Vercel frontend deployment

Vercel will host this Next.js frontend only. The local Flask API, MQTT broker,
classifier, and SQLite database stay on the laptop. The existing proxy is
same-origin, read-only, and allowlists five API paths. It cannot reach the
laptop through `127.0.0.1` from a Vercel function.

### Verified project settings

- **Root Directory:** `web` (the app and `package-lock.json` are here).
- **Framework Preset:** Next.js, detected automatically.
- **Node.js:** `24.x`. This matches the local Node.js 24 build and is a current
  Vercel runtime. See [Vercel's supported Node.js versions](https://vercel.com/docs/functions/runtimes/node-js/node-js-versions).
- **Install Command:** leave Vercel's detected npm command.
- **Build Command:** leave the Next.js default (`next build`).
- **Output Directory:** leave the Next.js default; do not set `out`.
- **Environment Variables:** leave empty for this frontend-only deployment.
  In particular, do not set `BACKEND_URL` or `NEXT_PUBLIC_BACKEND_URL`.
- No `vercel.json` or custom build/output configuration is needed. See
  [Vercel monorepo settings](https://vercel.com/docs/monorepos) and
  [build configuration](https://vercel.com/docs/builds/configure-a-build).

With `BACKEND_URL` absent in production, the proxy returns HTTP 503 without
making an upstream request. The dashboard still renders and reports the server
as disconnected; it does not try the laptop's localhost. This state is covered
by proxy tests and was checked in a local production browser run. A hosted
frontend without cloud sync will not show live laptop readings.

The production page was checked at 320, 375, 390, and 430 CSS pixels. It had no
horizontal overflow; representative six-axis values fit in the sensor cards;
fresh, stale, history, refresh, and backend-unavailable states were checked.
The live and stale readings in that browser pass were isolated test fixtures,
not physical sensor data.

### Import and deploy after approval

1. Authenticate GitHub CLI with `gh auth login -h github.com -p https --web`.
2. Create the private `BCA182_LAB3` repository from this checkout and push
   `main` only after repository creation and push are approved.
3. In Vercel, choose **Add New → Project**, connect the GitHub account, and
   import the private `BCA182_LAB3` repository. Grant Vercel access to this
   repository only.
4. Set **Root Directory** to `web`; choose **Next.js** and **Node.js 24.x**;
   keep the detected install/build/output settings and leave environment
   variables empty for the first frontend-only deployment.
5. Deploy, then open the generated HTTPS production URL on Android over mobile
   data or another network. The disconnected state is expected until remote
   sync and dashboard authentication are implemented.

Vercel Hobby is limited to personal, non-commercial use. Its private-repository
collaboration support is also limited, so the intended arrangement is a
personal repository imported by its owner. Review the [current Hobby
terms](https://vercel.com/legal/terms) and [private-repository collaboration
limits](https://vercel.com/docs/deployments/troubleshoot-project-collaboration)
before creating the project.

Never point this frontend at the laptop's localhost, expose Flask or MQTT to
the public internet, or use a tunnel as the backend path. Do not put secrets in
source, `.env.example`, browser code, or `NEXT_PUBLIC_` variables. See the
project-root [remote monitoring plan](../REMOTE_MONITORING_PLAN.md) for the
proposed authenticated cloud synchronization design and exact resources.
