# Deploying to Streamlit Community Cloud (free)

Total time once you have a Neon account: ~10 minutes. You do all of
this — I can't click through OAuth or paste secrets on your behalf.

---

## 0. Rotate any key that has been shared in chat

If you ever pasted your `ANTHROPIC_API_KEY` into a chat, email, Slack,
screenshot, or anything else not end-to-end encrypted, treat it as
public. Revoke it at https://console.anthropic.com/settings/keys and
generate a fresh one. The key should only ever live in:

1. Your local `.env` (gitignored), for development.
2. The **Secrets** panel in the Streamlit Cloud dashboard, for prod.

Not a file. Not a comment. Not a README.

---

## 1. Push the repo to GitHub

You're on branch `claude/trading-chart-analyzer-RcBdV`. Either merge to
`main` or deploy the branch directly.

---

## 2. Create a free Postgres database (Neon)

Streamlit Cloud containers have ephemeral filesystems, so SQLite would
be wiped on redeploys. Neon gives you persistent Postgres on the free
tier.

1. Sign up at https://console.neon.tech (GitHub login works).
2. Create a new project — any region, default Postgres version is fine.
3. On the project dashboard, find **Connection string** (sometimes
   under "Connection Details"). Copy the **pooled** connection string.
   It looks like:
   ```
   postgresql://user:pass@ep-xyz-pooler.region.aws.neon.tech/dbname?sslmode=require
   ```
4. Save this string somewhere temporary. You'll paste it into Streamlit
   secrets in step 5. Do **not** commit it.

Alternatives: Supabase (https://supabase.com) gives Postgres too — copy
its "Connection string" from Project Settings → Database. Same secret
name: `DATABASE_URL`.

---

## 3. Deploy the app to Streamlit Community Cloud

1. Go to https://share.streamlit.io and sign in with GitHub.
2. Click **Create app → Deploy a public app from GitHub**.
3. Fill in:
   - **Repository:** `xhumaliosmani/chartanalysis`
   - **Branch:** `claude/trading-chart-analyzer-RcBdV` (or `main` after merge)
   - **Main file path:** `app.py`
   - **App URL:** pick a subdomain (e.g. `mychartanalyzer`)
4. Expand **Advanced settings** and set **Python version** to **3.11**.
5. Click **Deploy**. First build takes ~2–3 minutes.

---

## 4. Pick an app password

Choose something long and random. A passphrase works — e.g.
`correct-horse-battery-staple-7291`. Don't reuse your Anthropic
password. Don't paste it in chat anywhere.

---

## 5. Add all three secrets at once

In the deployed app, click **⋯ → Settings → Secrets** (top-right).
Paste all three lines:

```toml
ANTHROPIC_API_KEY = "sk-ant-your-fresh-key-here"
APP_PASSWORD      = "your-long-random-passphrase"
DATABASE_URL      = "postgresql://user:pass@ep-xyz-pooler.region.aws.neon.tech/dbname?sslmode=require"
```

Save. The app auto-restarts. On next load you'll see the password
screen. Enter your passphrase and you're in.

Verify in the sidebar: it should say **Storage: PostgreSQL** (not
SQLite).

---

## How the secrets are wired

- `ANTHROPIC_API_KEY` — read by `app.py`, used for Claude vision calls.
- `APP_PASSWORD` — read by `auth.py`. Compared with `hmac.compare_digest`
  (constant-time). If unset, the gate is disabled — useful for local dev.
- `DATABASE_URL` — read by `db.py`. If unset, falls back to
  `sqlite:///journal.db` in the repo dir.

All three are encrypted at rest in Streamlit Cloud's secret manager,
never rendered in logs, and never committed to your repo.

---

## Local development

```bash
cp .env.example .env
# Put your real key in .env — this file is gitignored.
# Leave APP_PASSWORD and DATABASE_URL unset locally; the app will
# skip the password gate and use a local SQLite file.

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

---

## Rotating the password or API key later

Just edit the Secrets panel. Changes apply on the next rerun.

If you think the URL has been shared with someone you no longer trust,
rotate `APP_PASSWORD`; they'll be locked out immediately.

If you think your API key has been leaked, rotate it in the Anthropic
console first, then update the secret. The leaked key has to be
revoked to stop costing you money — rotating the secret alone isn't
enough.
