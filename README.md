# Polymarket US Dashboard

A dashboard that pulls your Polymarket US account data (open orders, positions,
trades, balances) via the [`polymarket-us`](https://docs.polymarket.us) Python
SDK and **regroups the flat order data into a clean `Event → Market/Contract`
hierarchy** so you can see everything you have going on per market at a glance.

- **Backend** — Python + FastAPI. Wraps the `polymarket-us` SDK, does the
  grouping/aggregation, and exposes a JSON API.
- **Frontend** — Next.js (App Router, TypeScript, Tailwind). Renders the grouped
  dashboard with per-event and per-contract rollups, filtering, expand/collapse
  all, and auto-refresh.

```
polymarket-dashboard/
├── .env                # your Polymarket credentials (git-ignored)
├── .env.example        # template
├── backend/            # FastAPI app + grouping service
│   ├── app/
│   │   ├── config.py           # loads ../.env
│   │   ├── client.py           # PolymarketUS client factory
│   │   ├── schemas.py          # JSON response contract
│   │   ├── services/dashboard.py  # the Event → Contract grouping logic
│   │   └── routers/            # /api/dashboard + raw pass-through endpoints
│   ├── tests/
│   ├── requirements.txt
│   └── run.py
└── frontend/           # Next.js dashboard UI
    ├── app/
    ├── components/
    └── lib/            # api client + types (mirror of backend schemas)
```

## 1. Credentials

Create an API key in your Polymarket US account. You need two values:

- `POLYMARKET_KEY_ID` — the API key ID (a UUID)
- `POLYMARKET_SECRET_KEY` — the base64-encoded Ed25519 secret key

Copy the template and fill them in:

```bash
cp .env.example .env
# then edit .env and paste your real values
```

`.env` lives at the **project root** and is git-ignored — it is read by the
backend. Never commit it.

## 2. Run the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# start the API (reads ../.env), serves http://127.0.0.1:8000
python run.py
```

Check it:

```bash
curl http://127.0.0.1:8000/api/health
# {"status":"ok","credentials_configured":true, ...}
```

Interactive API docs are at http://127.0.0.1:8000/docs.

## 3. Run the frontend

In a second terminal:

```bash
cd frontend
npm install

# point the UI at the backend (defaults to http://127.0.0.1:8000)
cp .env.local.example .env.local

npm run dev
# open http://localhost:3000
```

## API

All data endpoints require credentials; without them the API returns
`503 {"error":"missing_credentials"}` and the UI shows setup instructions.

| Method & path                    | Description                                          |
| -------------------------------- | ---------------------------------------------------- |
| `GET /api/health`                | Liveness + whether credentials are configured.       |
| `GET /api/dashboard`             | **Grouped** view: events → contracts + rollup stats. |
| `GET /api/orders`                | Raw open orders (SDK pass-through).                  |
| `GET /api/portfolio/positions`   | Raw positions.                                       |
| `GET /api/portfolio/activities`  | Raw recent activity (trades, resolutions).           |
| `GET /api/account/balances`      | Raw account balances.                                |

### `GET /api/dashboard` query params

- `max_activities` (default `300`, max `2000`) — how many recent activity
  records to pull for trade grouping.
- `enrich_events` (default `true`) — look up human event titles via the public
  events API (falls back to a humanized slug if unavailable).

### How grouping works

Every order, position, trade, and resolution carries a `marketSlug` and an
`eventSlug` in its `marketMetadata`. The backend buckets each record by
`marketSlug` into a **contract**, then groups contracts by `eventSlug` into an
**event**, rolling up open-order counts/notional, position value/cost, realized
P&L, trade count, and resolution count at each level.

A trade's metadata is nested under its execution legs rather than at the top
level, so the grouper digs it out (`aggressorExecution.order.marketMetadata` and
siblings); this means markets you've fully closed by selling still group into
their event instead of falling into the "Ungrouped markets" bucket. Only records
with genuinely no `eventSlug` land in "Ungrouped".

### Realized P&L

Realized P&L is de-duplicated across the SDK's three overlapping sources so it is
neither double-counted nor undercounted:

- **Open positions** use `position.realized` (the authoritative cumulative
  realized-from-selling, not truncated by the activity window). The individual
  sell trades are already baked into it, so they are not re-added.
- **Closed-by-selling positions** (no live position record) use the sum of their
  trades' `realizedPnl`.
- **Resolved/expired positions** book their payout via the resolution delta
  (`afterPosition.realized − beforePosition.realized`). Held-to-expiry winners
  never appear as a trade, so without this their profit would be missed.

Account **cash flows — deposits, withdrawals, transfers, referral bonuses — are
deliberately excluded** from realized P&L; they are not trading gains. (Note that
the raw `balances` endpoint reports `currentBalance`, which still includes
pending withdrawals; `buyingPower` is the actually-spendable figure.)

## Tests

```bash
cd backend
source .venv/bin/activate
python tests/test_dashboard_grouping.py   # or: pytest tests
```

The test drives the grouping service with a stub SDK client, so it runs without
credentials or network access.

## Notes

- Monetary values are normalized to USD floats in the API for easy formatting.
- Prices are 0–1 probabilities and are shown in cents (¢) in the UI.
- The frontend polls `/api/dashboard` every 15s when "Auto" is enabled; you can
  also refresh manually.
- The backend never logs or returns your secret key; `/api/health` only reports
  whether credentials are present.
