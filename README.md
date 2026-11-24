# BTC15 iPhone Dashboard — GitHub + Streamlit Community Cloud

No candlestick chart. Designed for opening on an iPhone via an HTTPS Streamlit link.
This is an independently developed paper-only prediction dashboard, NOT thecallgate.com's private code.

## GitHub upload — easiest method

1. On GitHub, create a **new repository** (for example `btc15-paper-phone`).
2. In the repository, tap **Add file → Upload files**.
3. **Extract this ZIP first**. Upload all files at the *root* of the repository: `app.py`, `engine.py`, `requirements.txt`, `check_kalshi.py`, `worker.py`, `.gitignore`, and the `.streamlit` folder with `config.toml`. On iPhone, GitHub's web uploader may not reliably preserve the hidden `.streamlit` folder; the app can still deploy without it, but use a computer or GitHub file editor to create `.streamlit/config.toml` when desired.
4. Commit the changes. `app.py` must be at the repository root (not inside a nested `btc15_phone` folder).
5. Go to https://share.streamlit.io, sign in via GitHub, select your repo, choose branch `main`, and set **Main file path** to `app.py`. Deploy.
6. Under the app's **Settings → Secrets**, enter a private access password as below, then reboot the app. **Never put the password in the GitHub repo.**

```toml
APP_PASSWORD = "make-a-long-unique-password-here"
```

7. Open the HTTPS Streamlit app link in Safari on your iPhone, enter the password, and choose **Share → Add to Home Screen**.

## How it works

- Live Coinbase BTC candles, 15-minute timer, signal/learning/Quant Gate panels, signal history, real observed Kalshi asks where available.
- Maximum **$10 total** per automatic *paper* entry, including *estimated* fees, with only whole contracts simulated.
- Call predictions at minute 6, learning predictions at minute 4; Quant Gate may veto, with existing SKIP rules.
- P&L, wins, losses and reset are based on **paper quotes**, not executed fills.
- In Call's execution mode, choose **Place trades automatically** to enable paper entries. Default is **Display only** for safety; changing the setting later in a window will not backfill that window.
- The app auto-refreshes approximately every 20 seconds while open; it calls the engine during refresh.

## Critical Streamlit Community Cloud limitations

1. **This is not a guaranteed 24/7 bot.** Streamlit Cloud sleeps/restarts apps and does not continuously run `worker.py` while no user session is active. Signal time windows and entries can be missed.
2. **History is not durable in Streamlit Cloud.** Local SQLite files can disappear after redeploy/restart. Your laptop's existing `quantgate.sqlite3` is not synced to this deployment. Use CSV downloads to save results. Do not upload your local database to a public GitHub repo.
3. App settings/paper history are shared across viewers on the deployment. Set `APP_PASSWORD` in Streamlit secrets before using or sharing the URL. A password reduces casual exposure but does not provide individual accounts.
4. Live Kalshi API access can be unavailable, market quotes may not imply executable fills, and fee calculations are only estimates. Missing quotes mean **no paper entry**.
5. No live orders and no Kalshi API key required.

For *truly continuous* paper tracking across iPhone lock and reliable persistent history, deploy `worker.py` to a persistent service and use a shared persistent database with a service designed for it. This bundle does not claim those properties.

## Project files

- `app.py` — mobile Streamlit dashboard and active-session engine runner
- `engine.py` — signals, market quotes, simulated entries, SQLite
- `requirements.txt` — Python dependencies installed by Streamlit
- `.streamlit/config.toml` — dark phone styling
- `worker.py` — OPTIONAL laptop/host background worker; Streamlit Cloud will not run it continuously
- `check_kalshi.py` — optional diagnostic, run from terminal, not needed for Streamlit deployment

## Local test

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

Keep the trading model and history distinct: a correct Coinbase direction forecast does not guarantee a profitable Kalshi trade.
