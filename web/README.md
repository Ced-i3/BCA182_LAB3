# Activity Monitor web dashboard

A read-only, responsive frontend for the BCA152 Lab 3 RT-Spark activity-monitoring system. Next.js runs on the laptop and reads the existing Flask API. The STM32 publishes measurements through MQTT to Flask; the browser does not talk to MQTT or SQLite.

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

Vercel is intended to host this Next.js frontend only. The Flask API, MQTT
broker, classifier, and SQLite database stay on the laptop. A Vercel function
cannot reach the laptop through `127.0.0.1`, so a deployed page without a
separately designed and secured backend will load but show the backend as
disconnected and have no live laptop data. This frontend-only deployment does
not satisfy the laboratory guide's cloud-backend requirement; see the root
README's deployment limitations.

These are preparation instructions only. Do not publish the repository or
create a Vercel deployment until those actions are separately approved.

After publication is approved, import the repository into Vercel and use these
project settings:

1. Set **Root Directory** to `web/`, because the Next.js app and its lockfile
   are in that directory. See [Vercel's monorepo root-directory guide](https://vercel.com/docs/monorepos).
2. Select the detected **Next.js** framework preset and use Node.js **24.x**
   to match the verified local environment. Vercel currently supports 24.x;
   see [supported Node.js versions](https://vercel.com/docs/functions/runtimes/node-js/node-js-versions).
3. Keep the detected install, build, and output settings. The package has a
   lockfile and a `build` script (`next build`); Vercel detects the Next.js
   defaults. No custom output directory or `vercel.json` is required. See
   [Vercel build configuration](https://vercel.com/docs/builds/configure-a-build).
4. Do not set `BACKEND_URL` for the current frontend-only deployment. In
   production, the proxy returns HTTP 503 when this variable is absent, and
   the dashboard reports the backend as disconnected. The automated proxy
   tests cover this case and a failed upstream request.
5. Do not set `NEXT_PUBLIC_BACKEND_URL` or put credentials in client-side
   variables. The proxy reads `BACKEND_URL` on the server. Next.js exposes
   variables with a `NEXT_PUBLIC_` prefix in browser JavaScript; see the
   [Next.js environment-variable guidance](https://nextjs.org/docs/app/guides/environment-variables).

If a reachable backend is provisioned later, its URL and authentication must
be designed separately. Configure any approved server-only value in the
Vercel project's Environment Variables settings, never put credentials or a
production backend address in committed source or `.env.example`. Changes take
effect on a new deployment. Do not point this frontend at the laptop's
localhost or expose Flask or MQTT directly to the public internet or through a
tunnel. No Vercel project has been created and no deployment has been
performed.
