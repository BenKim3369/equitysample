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
If NAVER credentials are present, the pipeline also pulls recent Naver news API results before RSS fallback.
Main candidate selection prioritizes Naver results so that at least 70% of Main News Candidates are sourced from Naver when available.
Final output ordering also prioritizes Naver News links first, targeting a Naver-heavy result list.
기사 우선순위는 `네이버 뉴스 > 한국 언론 기사 > 글로벌 기사` 순으로 적용됩니다.
수집 대상 시간대는 KST 기준으로 전일 24시간(00:00~23:59:59)이며, 월요일 실행 시에는 금/토/일 3일치를 포함합니다.
최종 출력 시 기사 제목이 한국어가 아니면 한국어 번역을 시도하며, 링크 길이가 70자 이상이면 단축 URL로 변환을 시도합니다.

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
> Never commit `.env` (real credentials) to git.
> Low-quality SEO aggregators (e.g., Travel And Tour World, thetraveler.org) are excluded.
