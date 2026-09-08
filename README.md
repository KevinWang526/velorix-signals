# Velorix Signals — Deploy Guide (Render + Vercel)

This repository contains a FastAPI backend (`backend/`) and a Vite + React frontend (`frontend/`).
Use the steps below to create a permanent HTTPS demo URL using Render (backend) and Vercel (frontend).

## Overview
- Backend: Render (web service) — provides stable HTTPS URL and environment variables for secrets.
- Frontend: Vercel (static site) — serves the React app and points API calls to the Render backend.

## Backend (Render)

1. Push this repository to GitHub.
2. Create a new Web Service on Render and connect your GitHub repo.
3. Build & Start commands:

   - **Build Command**: leave blank (no build step for FastAPI)
   - **Start Command**: `uvicorn backend.app:app --host 0.0.0.0 --port $PORT`

4. Environment variables (set these in Render dashboard `Environment` section):

   - `ALPACA_API_KEY` — (optional) your Alpaca API key
   - `ALPACA_API_SECRET` — (optional) your Alpaca secret
   - `ALPACA_BASE_URL` — (optional) `https://paper-api.alpaca.markets` or your live base URL
   - `ORDER_DOLLARS` — (optional) default dollars to size simulated orders (e.g., `1000`)

5. Render will provide a stable HTTPS URL such as `https://your-app.onrender.com`.

## Frontend (Vercel)

1. In Vercel, create a new project and import the same GitHub repo.
2. Set the Root Directory to `frontend` when prompted.
3. Build & Output settings (Vite default):

   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`

4. Environment variables (in Vercel project settings):

   - `VITE_API_BASE` — set to your Render backend URL, e.g. `https://your-app.onrender.com`

5. Deploy. Vercel will provide a stable HTTPS URL for the frontend.

## Important Notes

- Do not commit or expose any production API keys publicly.
- If you need a private demo, you can enable password protection or restrict access on Render/Vercel.
- If your frontend uses a proxy (dev server), ensure `VITE_API_BASE` or your `fetch` calls point to the Render URL.

## One-line quick commands (local testing)

Start backend locally:

```bash
cd /path/to/repo
.venv/bin/python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```

Build frontend locally:

```bash
cd frontend
npm install
npm run build
```

## Troubleshooting

- If your frontend errors with `Failed to load signals`, confirm the backend URL is reachable from the browser and that `VITE_API_BASE` is set correctly.
- For long-running uploads or heavy file analysis, consider enabling background processing or a job queue.

---

If you want, I can commit these helper files (already added) and push them, then optionally prepare a small `render.yaml` or GitHub Action to automate deploys. Which next step would you like me to do?
# Velorix (Personal)

Minimal Python quant trading scaffold: data ingestion, simple strategies, backtester, and Alpaca paper/live execution.

Quick start

1. Create and activate a Python 3.10+ venv.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and fill your Alpaca keys.

3. Dry-run stream live Alpaca market data (no orders):

```bash
python scripts/stream_and_trade.py --tickers AAPL NVDA QQQ BTC-USD --interval 10
```

4. Paper submit (be careful):

```bash
python scripts/stream_and_trade.py --tickers AAPL NVDA --interval 10 --confirm
```

5. Run the Streamlit UI for interactive testing:

```bash
streamlit run scripts/streamlit_app.py
```

Notes
- For Canadian exchanges, add IBKR later — Alpaca covers US equities and some crypto only.
- Adjust sizing in `quanttrader/config.py` or set `ORDER_DOLLARS` in `.env`.
