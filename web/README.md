# Activity Monitor web dashboard

A read-only, responsive frontend for the BCA152 Lab 3 RT-Spark activity-monitoring system. Next.js runs on the laptop and reads the existing Flask API. The STM32 publishes measurements through MQTT to Flask; the browser does not talk to MQTT or SQLite.

## Stack and prerequisites

- Next.js App Router, React, TypeScript, Tailwind CSS, npm
- Node.js 20.9 or later (the project was built with Node.js 24)
- Existing Flask backend for live data; the existing MQTT broker and STM32 stream are needed for **new** readings

Run all frontend commands from `BCA152_LAB3\web` in PowerShell:

```powershell
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

If Flask is not already running, check `http://127.0.0.1:5000/health` first. From `BCA152_LAB3\backend`, start the existing broker and backend **only if they are not already running**:

```powershell
.\.venv_lab3\Scripts\amqtt.exe -c broker.yaml
.\.venv_lab3\Scripts\python.exe app.py
```

Use separate terminals. A broker connection alone does not mean the STM32 is streaming. The frontend never sends MQTT commands or changes the database.

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

## Future deployment

This Next.js app can build for a Node/Vercel deployment, but Vercel cannot reach Flask at `127.0.0.1` on the laptop. A future deployment needs a separately designed secure connection to a reachable backend, such as a hosted authenticated API or controlled private relay. Do not publish Flask or MQTT directly to the internet. When a production backend URL is absent, the dashboard shows an unavailable state rather than attempting to reach the laptop.
