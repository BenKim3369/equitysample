from __future__ import annotations

import argparse
import html
import os
import re
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import urlopen
import xml.etree.ElementTree as ET

from notify.telegram_sender import send_markdown_to_telegram

OUTPUT_PATH = Path("outputs/daily_news_candidates.md")
MAX_MAIN = 20
MAX_REFERENCE = 20


SEED_ARTICLES = [
    {
        "title": "Global pop group announces comeback world tour after label contract renewal",
        "link": "https://example.com/news/pop-group-comeback-tour",
        "source": "Music Business Worldwide",
        "summary": "Major artist comeback and multi-continent tour expected to lift ticketing and streaming demand.",
        "published_at": "2026-04-24T08:30:00+00:00",
    },
    {
        "title": "Streaming platform says drama series breaks OTT viewership records in Asia",
        "link": "https://example.com/news/ott-viewership-record",
        "source": "Variety",
        "summary": "Content performance improved subscription and ad-supported watch time across key markets.",
        "published_at": "2026-04-24T06:00:00+00:00",
    },
    {
        "title": "Airport authority approves temporary fuel surcharge as airlines trim routes",
        "link": "https://example.com/news/airline-fuel-surcharge",
        "source": "Reuters",
        "summary": "Airline cancellations and surcharge updates could affect outbound tourism demand this quarter.",
        "published_at": "2026-04-23T23:00:00+00:00",
    },
    {
        "title": "Resort operator and gaming company sign strategic partnership for integrated leisure project",
        "link": "https://example.com/news/casino-hotel-partnership",
        "source": "Bloomberg",
        "summary": "Casino and hotel demand outlook improved after policy support for inbound visitors.",
        "published_at": "2026-04-23T19:00:00+00:00",
    },
    {
        "title": "Studio parent reports Q1 earnings beat with higher operating profit and revenue",
        "link": "https://example.com/news/studio-q1-earnings",
        "source": "CNBC",
        "summary": "Quarterly report highlighted stronger sales and guidance raise for the full year.",
        "published_at": "2026-04-24T07:15:00+00:00",
    },
    {
        "title": "Airline files annual report and IR presentation after weaker consensus forecast",
        "link": "https://example.com/news/airline-annual-report",
        "source": "MarketWatch",
        "summary": "Disclosure package detailed revised guidance and traffic outlook.",
        "published_at": "2026-04-24T05:45:00+00:00",
    },
]

RSS_FEEDS = [
    "https://news.google.com/rss/search?q=music+tour+comeback+contract+controversy+OTT+box+office+tourism+aviation+casino+hotel+M%26A&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=entertainment+content+performance+streaming+cinema+regulation+partnership&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=airline+fuel+surcharge+cancellation+tourism+demand&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=casino+hotel+leisure+policy+demand&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=earnings+guidance+quarterly+report+IR+filing&hl=en-US&gl=US&ceid=US:en",
]

REFERENCE_KEYWORDS = {
    "earnings": "earnings",
    "guidance": "guidance",
    "consensus": "guidance",
    "operating profit": "earnings",
    "sales": "earnings",
    "revenue": "earnings",
    "disclosure": "disclosure",
    "filing": "disclosure",
    "ir": "IR",
    "investor relations": "IR",
    "quarterly report": "earnings",
    "annual report": "earnings",
    "q1": "earnings",
    "q2": "earnings",
    "q3": "earnings",
    "q4": "earnings",
}

REFERENCE_PATTERNS = [
    (re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE), ref_type)
    for keyword, ref_type in REFERENCE_KEYWORDS.items()
]

MAIN_KEYWORD_WEIGHTS = {
    "comeback": 3,
    "tour": 3,
    "contract": 2,
    "controversy": 3,
    "viewership": 3,
    "ratings": 2,
    "streaming": 2,
    "ott": 2,
    "cinema": 2,
    "box office": 3,
    "inbound": 2,
    "outbound": 2,
    "tourism": 2,
    "cancellation": 2,
    "cancelled": 2,
    "fuel surcharge": 3,
    "casino": 2,
    "hotel": 2,
    "leisure": 2,
    "policy": 2,
    "demand": 2,
    "merger": 3,
    "acquisition": 3,
    "m&a": 3,
    "partnership": 2,
    "regulation": 2,
}


@dataclass
class Article:
    title: str
    link: str
    source: str
    summary: str
    published_at: datetime


@dataclass
class MainCandidate:
    article: Article
    importance: str
    reason: str


@dataclass
class ReferenceCandidate:
    article: Article
    ref_type: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily news candidate pipeline")
    parser.add_argument(
        "--send-telegram",
        action="store_true",
        help="Send outputs/daily_news_candidates.md to Telegram after generation.",
    )
    return parser.parse_args()


def load_dotenv(env_path: Path = Path(".env")) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            continue
        os.environ.setdefault(key, value.strip().strip("\"'"))


def fetch_feed(url: str) -> list[Article]:
    context = ssl.create_default_context()
    with urlopen(url, context=context, timeout=20) as resp:
        data = resp.read()

    root = ET.fromstring(data)
    channel = root.find("channel")
    if channel is None:
        return []

    out: list[Article] = []
    for item in channel.findall("item"):
        title = clean_text(item.findtext("title", "")).strip()
        link = normalize_url(item.findtext("link", "").strip())
        source = clean_text(item.findtext("source", "Unknown")).strip() or "Unknown"
        summary = clean_text(item.findtext("description", "")).strip()
        pub = parse_dt(item.findtext("pubDate", ""))
        if title and link:
            out.append(Article(title=title, link=link, source=source, summary=summary, published_at=pub))
    return out


def parse_dt(raw: str) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def clean_text(value: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", value)
    compact = re.sub(r"\s+", " ", html.unescape(no_tags))
    return compact


def normalize_url(url: str) -> str:
    if "news.google.com/rss/articles/" in url:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if "url" in params and params["url"]:
            return params["url"][0]
    return unquote(url)


def title_key(title: str) -> str:
    normalized = re.sub(r"[^a-z0-9 ]+", " ", title.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    words = [w for w in normalized.split() if len(w) > 2]
    return " ".join(words[:12])


def deduplicate(articles: Iterable[Article]) -> list[Article]:
    by_url: dict[str, Article] = {}
    for art in articles:
        current = by_url.get(art.link)
        if current is None or is_more_reliable(art, current):
            by_url[art.link] = art

    by_title: dict[str, Article] = {}
    for art in by_url.values():
        key = title_key(art.title)
        current = by_title.get(key)
        if current is None or is_more_reliable(art, current):
            by_title[key] = art

    return list(by_title.values())


def is_more_reliable(candidate: Article, existing: Article) -> bool:
    tier = {
        "Reuters": 5,
        "Bloomberg": 5,
        "Associated Press": 5,
        "Financial Times": 4,
        "The Wall Street Journal": 4,
        "Nikkei Asia": 4,
    }
    c_score = tier.get(candidate.source, 1)
    e_score = tier.get(existing.source, 1)
    if c_score != e_score:
        return c_score > e_score
    return candidate.published_at > existing.published_at


def classify_reference(article: Article) -> str | None:
    text = f"{article.title} {article.summary}"
    for pattern, ref_type in REFERENCE_PATTERNS:
        if pattern.search(text):
            return ref_type
    return None


def classify_main(article: Article) -> MainCandidate | None:
    text = f"{article.title} {article.summary}".lower()
    hits = [(kw, wt) for kw, wt in MAIN_KEYWORD_WEIGHTS.items() if kw in text]
    if not hits:
        return None

    score = sum(weight for _, weight in hits)
    if score >= 6:
        importance = "high"
    elif score >= 3:
        importance = "medium"
    else:
        importance = "low"

    top_terms = ", ".join([kw for kw, _ in sorted(hits, key=lambda x: -x[1])[:3]])
    reason = f"Matched topic keywords: {top_terms}."
    return MainCandidate(article=article, importance=importance, reason=reason)


def rank_main(items: list[MainCandidate]) -> list[MainCandidate]:
    rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(items, key=lambda x: (rank[x.importance], -x.article.published_at.timestamp()))


def rank_reference(items: list[ReferenceCandidate]) -> list[ReferenceCandidate]:
    return sorted(items, key=lambda x: -x.article.published_at.timestamp())


def one_line_summary(article: Article) -> str:
    if article.summary:
        summary = article.summary.strip()
    else:
        summary = article.title
    return summary[:220].rstrip(" .")


def category_label(article: Article) -> str:
    if article.source and article.source != "Unknown":
        return article.source
    host = urlparse(article.link).netloc.replace("www.", "")
    return host or "General"


def render(main_items: list[MainCandidate], ref_items: list[ReferenceCandidate]) -> str:
    lines: list[str] = [
        "# Daily News Candidates",
        "",
        "## Main News Candidates",
        "",
    ]

    if not main_items:
        lines.append("No main news candidates found.")
    else:
        for idx, item in enumerate(main_items, start=1):
            article = item.article
            lines.extend(
                [
                    f"{idx}. [{category_label(article)}] {article.title}",
                    f"- Importance: {item.importance}",
                    f"- Reason: {item.reason}",
                    f"- 1-line summary: {one_line_summary(article)}",
                    f"- Link: {article.link}",
                    "",
                ]
            )

    lines.extend(["## Reference News", ""])

    if not ref_items:
        lines.append("No reference news found.")
    else:
        for idx, item in enumerate(ref_items, start=1):
            article = item.article
            lines.extend(
                [
                    f"{idx}. [{category_label(article)}] {article.title}",
                    f"- Type: {item.ref_type}",
                    f"- 1-line summary: {one_line_summary(article)}",
                    f"- Link: {article.link}",
                    "",
                ]
            )

    return "\n".join(lines).rstrip() + "\n"


def load_seed_articles() -> list[Article]:
    out: list[Article] = []
    for row in SEED_ARTICLES:
        out.append(
            Article(
                title=row["title"],
                link=row["link"],
                source=row["source"],
                summary=row["summary"],
                published_at=datetime.fromisoformat(row["published_at"]).astimezone(timezone.utc),
            )
        )
    return out


def main() -> int:
    args = parse_args()
    load_dotenv()

    fetched: list[Article] = []
    for feed in RSS_FEEDS:
        try:
            fetched.extend(fetch_feed(feed))
        except Exception:
            continue

    if not fetched:
        fetched = load_seed_articles()

    deduped = deduplicate(fetched)

    main_candidates: list[MainCandidate] = []
    reference_candidates: list[ReferenceCandidate] = []

    for article in deduped:
        ref_type = classify_reference(article)
        if ref_type:
            reference_candidates.append(ReferenceCandidate(article=article, ref_type=ref_type))
            continue

        main_item = classify_main(article)
        if main_item:
            main_candidates.append(main_item)

    ranked_main = rank_main(main_candidates)[:MAX_MAIN]
    ranked_reference = rank_reference(reference_candidates)[:MAX_REFERENCE]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(render(ranked_main, ranked_reference), encoding="utf-8")

    print(f"Generated: {OUTPUT_PATH}")
    print(f"Main candidates: {len(ranked_main)}")
    print(f"Reference news: {len(ranked_reference)}")

    if args.send_telegram:
        sent_count = send_markdown_to_telegram(OUTPUT_PATH)
        if sent_count > 0:
            print(f"Telegram delivery completed: {sent_count} message(s) sent.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
