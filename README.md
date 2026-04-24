# Daily News Pipeline

Generate daily news candidates and optionally send the result to Telegram.

## Run locally

```bash
python src/main.py
```

To also send Telegram notifications:

```bash
python src/main.py --send-telegram
```

## Environment variables

Copy `.env.example` to `.env` and set values:

- `NAVER_CLIENT_ID`
- `NAVER_CLIENT_SECRET`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

If Telegram variables are missing, the pipeline still generates `outputs/daily_news_candidates.md` and prints a warning instead of failing.

## GitHub Actions + Secrets

Workflow: `.github/workflows/daily_news.yml`

- Runs every day at **22:30 UTC** (07:30 KST).
- Supports manual run via `workflow_dispatch`.

Set the following repository secrets before enabling scheduled delivery:

- `NAVER_CLIENT_ID`
- `NAVER_CLIENT_SECRET`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

> Safety: Telegram delivery is skipped unless `TELEGRAM_CHAT_ID` is explicitly provided.
