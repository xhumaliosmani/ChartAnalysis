# Deploying to Streamlit Community Cloud (free)

Total time: ~3 minutes. You do this — I can't click through OAuth or
paste secrets into Streamlit for you.

## 0. Rotate any key that has been shared in chat

If you ever pasted your `ANTHROPIC_API_KEY` into a chat, email, Slack,
screenshot, or anything else not end-to-end encrypted, treat it as
public. Revoke it at https://console.anthropic.com/settings/keys and
generate a fresh one. Do not commit the new key to the repo. The only
place it should live is:

1. Your local `.env` (gitignored), for development.
2. The **Secrets** panel in the Streamlit Cloud dashboard, for prod.

That's it. Not a file. Not a comment. Not a README.

## 1. Push the repo to GitHub

You're already on branch `claude/trading-chart-analyzer-RcBdV`. Either
merge it to `main` or deploy the branch directly.

## 2. Connect to Streamlit Community Cloud

1. Go to https://share.streamlit.io and sign in with your GitHub account.
2. Click **Create app** → **Deploy a public app from GitHub**.
3. Fill in:
   - **Repository:** `xhumaliosmani/chartanalysis`
   - **Branch:** `claude/trading-chart-analyzer-RcBdV` (or `main` after merge)
   - **Main file path:** `app.py`
   - **App URL:** pick a subdomain (e.g. `mychartanalyzer`)
4. Expand **Advanced settings** and set **Python version** to **3.11**.
5. Click **Deploy**.

The first build pulls `requirements.txt`; give it ~2 minutes.

## 3. Add your API key as a Secret

1. After the app opens, click **⋯ → Settings → Secrets** (top-right).
2. Paste exactly:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-your-fresh-key-here"
   ```
3. Click **Save**. The app will restart automatically and pick it up.

Secrets are encrypted at rest, never shown in logs, and never committed
to your repo. The app reads them via `st.secrets[...]`.

## 4. (Recommended) Add a password gate

Your Anthropic API bill is charged for every analysis anyone runs on the
hosted app. A public Streamlit Cloud URL is findable. If you're not
ready to let strangers spend your credits, do one of:

- **Make the repo private** and deploy from private — Community Cloud
  supports private repos on the free tier, but the URL itself is still
  public. Anyone with the URL can use the app.
- **Add a password** — ask and I'll wire in Streamlit's
  `st.text_input(type="password")` gate against a second secret
  `APP_PASSWORD`.

## 5. Persistence caveat

Streamlit Community Cloud containers have **ephemeral filesystems**. The
SQLite `journal.db` will be wiped whenever the app is redeployed or the
container is recycled (periodically, on their side). For a personal
hosted copy this is fine for a while but not a permanent journal.

If you want a persistent journal, options in order of effort:

- **Stay local** — run `streamlit run app.py` on your own machine. The
  DB persists next to the code.
- **Swap SQLite for a hosted Postgres** (Supabase, Neon, Railway —
  all have free tiers). I can refactor `db.py` to use `psycopg` and
  a `DATABASE_URL` secret.
- **Export/import** — I can add a "Download journal" button that
  exports to JSON, and an "Import" button to reload it.

Say the word and I'll wire any of these in.
