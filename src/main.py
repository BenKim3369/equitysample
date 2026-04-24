from __future__ import annotations

import argparse
import html
import math
import os
import re
import ssl
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, Iterable, TypeVar
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import urlopen
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from news_sources.naver_client import fetch_naver_news
from notify.telegram_sender import send_markdown_to_telegram

T = TypeVar("T")

OUTPUT_PATH = Path("outputs/daily_news_candidates.md")
MAX_MAIN = 20
MAX_REFERENCE = 20
TARGET_NAVER_RATIO = 0.7
OUTPUT_NAVER_RATIO = 0.9


SEED_ARTICLES = [
    {
        "title": "Global pop group announces comeback world tour after label contract renewal",
        "link": "https://n.news.naver.com/mnews/article/015/0005277832?sid=101",
        "source": "Naver News",
        "summary": "Major artist comeback and multi-continent tour expected to lift ticketing and streaming demand.",
        "published_at": "2026-04-24T08:30:00+00:00",
    },
    {
        "title": "Streaming platform says drama series breaks OTT viewership records in Asia",
        "link": "https://m.entertain.naver.com/home/article/144/0001110995",
        "source": "Naver News",
        "summary": "Content performance improved subscription and ad-supported watch time across key markets.",
        "published_at": "2026-04-24T06:00:00+00:00",
    },
    {
        "title": "Airport authority approves temporary fuel surcharge as airlines trim routes",
        "link": "https://n.news.naver.com/mnews/article/079/0004139218?sid=104",
        "source": "Naver News",
        "summary": "Airline cancellations and surcharge updates could affect outbound tourism demand this quarter.",
        "published_at": "2026-04-23T23:00:00+00:00",
    },
    {
        "title": "Resort operator and gaming company sign strategic partnership for integrated leisure project",
        "link": "https://n.news.naver.com/mnews/article/277/0005752612?sid=101",
        "source": "Naver News",
        "summary": "Casino and hotel demand outlook improved after policy support for inbound visitors.",
        "published_at": "2026-04-23T19:00:00+00:00",
    },
    {
        "title": "Studio parent reports Q1 earnings beat with higher operating profit and revenue",
        "link": "https://n.news.naver.com/mnews/article/018/0006262823?sid=101",
        "source": "CNBC",
        "summary": "Quarterly report highlighted stronger sales and guidance raise for the full year.",
        "published_at": "2026-04-24T07:15:00+00:00",
    },
    {
        "title": "Airline files annual report and IR presentation after weaker consensus forecast",
        "link": "https://n.news.naver.com/mnews/article/015/0005277000?sid=101",
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

BLOCKED_SOURCE_PATTERNS = [
    "travel and tour world",
    "travelandtourworld",
    "thetraveler.org",
    "traveloffpath",
    "traveltourworld",
]

BLOCKED_DOMAINS = {
    "travelandtourworld.com",
    "www.travelandtourworld.com",
    "thetraveler.org",
    "www.thetraveler.org",
    "traveloffpath.com",
    "www.traveloffpath.com",
}

NAVER_NEWS_DOMAINS = {
    "n.news.naver.com",
    "news.naver.com",
    "m.entertain.naver.com",
    "entertain.naver.com",
}

KOREAN_MEDIA_DOMAINS = {
    "yna.co.kr",
    "www.yna.co.kr",
    "mk.co.kr",
    "www.mk.co.kr",
    "hankyung.com",
    "www.hankyung.com",
    "sedaily.com",
    "www.sedaily.com",
    "newsis.com",
    "www.newsis.com",
    "joongang.co.kr",
    "www.joongang.co.kr",
    "chosun.com",
    "www.chosun.com",
    "donga.com",
    "www.donga.com",
    "khan.co.kr",
    "www.khan.co.kr",
}

KOREA_RELEVANCE_KEYWORDS = {
    "korea",
    "korean",
    "seoul",
    "busan",
    "incheon",
    "jeju",
    "hyundai",
    "samsung",
    "lg",
    "kakao",
    "naver",
    "coupang",
}

TOURISM_FLOW_KEYWORDS = {"tourism", "inbound", "outbound", "korea", "japan", "china", "travel flow"}
MACRO_KEYWORDS = {"fuel surcharge", "aviation", "airline", "cancellation", "casino demand", "casino"}


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


def target_publication_window_kst(now_kst: datetime) -> tuple[datetime, datetime]:
    """
    Returns inclusive KST window.
    - Tue~Sun runs: previous day (00:00:00 ~ 23:59:59.999999)
    - Mon runs: Friday~Sunday (00:00:00 Friday ~ 23:59:59.999999 Sunday)
    """
    run_day = now_kst.date()
    if now_kst.weekday() == 0:  # Monday
        start_day = run_day - timedelta(days=3)
        end_day = run_day - timedelta(days=1)
    else:
        start_day = run_day - timedelta(days=1)
        end_day = start_day

    start_dt = datetime.combine(start_day, time.min, tzinfo=ZoneInfo("Asia/Seoul"))
    end_dt = datetime.combine(end_day, time.max, tzinfo=ZoneInfo("Asia/Seoul"))
    return start_dt, end_dt


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


def is_blocked_source(article: Article) -> bool:
    source_lower = article.source.lower()
    domain = urlparse(article.link).netloc.lower()
    if domain in BLOCKED_DOMAINS:
        return True
    return any(pattern in source_lower or pattern in domain for pattern in BLOCKED_SOURCE_PATTERNS)


def is_internationally_relevant(article: Article) -> bool:
    if article.source == "Naver News":
        return True
    text = f"{article.title} {article.summary}".lower()
    has_korean_company_relevance = any(keyword in text for keyword in KOREA_RELEVANCE_KEYWORDS)
    has_tourism_flow_relevance = any(keyword in text for keyword in TOURISM_FLOW_KEYWORDS)
    has_macro_relevance = any(keyword in text for keyword in MACRO_KEYWORDS)
    return has_korean_company_relevance or has_tourism_flow_relevance or has_macro_relevance


def is_naver_news_link(link: str) -> bool:
    domain = urlparse(link).netloc.lower()
    if domain in NAVER_NEWS_DOMAINS:
        return True
    return domain.endswith(".naver.com")


def is_korean_media_article(article: Article) -> bool:
    domain = urlparse(article.link).netloc.lower()
    source_lower = article.source.lower()
    if domain.endswith(".kr") or domain in KOREAN_MEDIA_DOMAINS:
        return True
    korean_media_source_hints = ("연합뉴스", "한국", "매일경제", "한경", "중앙", "조선", "동아", "경향")
    return any(hint in article.source for hint in korean_media_source_hints) or ".co.kr" in domain or "kore" in source_lower


def source_priority(article: Article) -> int:
    if is_naver_news_link(article.link) or article.source == "Naver News":
        return 0
    if is_korean_media_article(article):
        return 1
    return 2


def is_in_target_publication_window(article: Article, start_kst: datetime, end_kst: datetime) -> bool:
    published_kst = article.published_at.astimezone(ZoneInfo("Asia/Seoul"))
    return start_kst <= published_kst <= end_kst


def select_main_candidates_with_naver_priority(candidates: list[MainCandidate]) -> list[MainCandidate]:
    if not candidates:
        return []

    ranked_all = rank_main(candidates)
    ranked_naver = [item for item in ranked_all if item.article.source == "Naver News"]

    total = min(MAX_MAIN, len(ranked_all))
    while total > 0 and len(ranked_naver) < math.ceil(TARGET_NAVER_RATIO * total):
        total -= 1
    if total == 0:
        return []

    selected = ranked_all[:total]
    required_naver = math.ceil(TARGET_NAVER_RATIO * total)
    current_naver = sum(1 for item in selected if item.article.source == "Naver News")

    if current_naver < required_naver:
        replacements_needed = required_naver - current_naver
        selected_naver_links = {item.article.link for item in selected if item.article.source == "Naver News"}
        naver_pool = [item for item in ranked_naver if item.article.link not in selected_naver_links]

        for replacement in naver_pool[:replacements_needed]:
            for idx in range(len(selected) - 1, -1, -1):
                if selected[idx].article.source != "Naver News":
                    selected[idx] = replacement
                    break

    return rank_main(selected)


def prioritize_naver_output(items: list[T], extractor: Callable[[T], Article]) -> list[T]:
    if not items:
        return []

    naver_items = [item for item in items if is_naver_news_link(extractor(item).link)]
    non_naver_items = [item for item in items if not is_naver_news_link(extractor(item).link)]
    if not naver_items:
        return items

    required_naver = math.ceil(len(items) * OUTPUT_NAVER_RATIO)
    if len(naver_items) >= required_naver:
        allowed_non_naver = max(0, len(items) - required_naver)
        return naver_items + non_naver_items[:allowed_non_naver]

    return naver_items + non_naver_items


def is_more_reliable(candidate: Article, existing: Article) -> bool:
    candidate_priority = source_priority(candidate)
    existing_priority = source_priority(existing)
    if candidate_priority != existing_priority:
        return candidate_priority < existing_priority

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
    return sorted(
        items,
        key=lambda x: (
            source_priority(x.article),
            rank[x.importance],
            -x.article.published_at.timestamp(),
        ),
    )


def rank_reference(items: list[ReferenceCandidate]) -> list[ReferenceCandidate]:
    return sorted(items, key=lambda x: (source_priority(x.article), -x.article.published_at.timestamp()))


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
    kst_date = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%y/%m/%d")
    lines: list[str] = [f"★주요 뉴스({kst_date})", ""]

    combined_articles = [item.article for item in main_items] + [item.article for item in ref_items]

    for idx, article in enumerate(combined_articles):
        lines.append(article.title)
        lines.append(article.link)
        if idx != len(combined_articles) - 1:
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def load_seed_articles(now_kst: datetime) -> list[Article]:
    start_kst, end_kst = target_publication_window_kst(now_kst)
    seed_day = end_kst.date()
    seed_times = [
        datetime.combine(seed_day, time(8, 30), tzinfo=ZoneInfo("Asia/Seoul")),
        datetime.combine(seed_day, time(10, 0), tzinfo=ZoneInfo("Asia/Seoul")),
        datetime.combine(seed_day, time(12, 0), tzinfo=ZoneInfo("Asia/Seoul")),
        datetime.combine(seed_day, time(14, 0), tzinfo=ZoneInfo("Asia/Seoul")),
        datetime.combine(seed_day, time(16, 0), tzinfo=ZoneInfo("Asia/Seoul")),
        datetime.combine(seed_day, time(18, 0), tzinfo=ZoneInfo("Asia/Seoul")),
    ]

    out: list[Article] = []
    for idx, row in enumerate(SEED_ARTICLES):
        published_at = seed_times[idx % len(seed_times)].astimezone(timezone.utc)
        out.append(
            Article(
                title=row["title"],
                link=row["link"],
                source=row["source"],
                summary=row["summary"],
                published_at=published_at,
            )
        )
    return out


def main() -> int:
    args = parse_args()
    load_dotenv()
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    window_start_kst, window_end_kst = target_publication_window_kst(now_kst)

    fetched: list[Article] = []
    naver_items = fetch_naver_news()
    for item in naver_items:
        fetched.append(
            Article(
                title=item["title"],
                link=item["link"],
                source=item.get("source", "Naver News"),
                summary=item.get("summary", ""),
                published_at=item["published_at"],
            )
        )

    for feed in RSS_FEEDS:
        try:
            fetched.extend(fetch_feed(feed))
        except Exception:
            continue

    if not fetched:
        fetched = load_seed_articles(now_kst)

    deduped = deduplicate(fetched)

    main_candidates: list[MainCandidate] = []
    reference_candidates: list[ReferenceCandidate] = []

    for article in deduped:
        if not is_in_target_publication_window(article, window_start_kst, window_end_kst):
            continue
        if is_blocked_source(article):
            continue
        if not is_internationally_relevant(article):
            continue

        ref_type = classify_reference(article)
        if ref_type:
            reference_candidates.append(ReferenceCandidate(article=article, ref_type=ref_type))
            continue

        main_item = classify_main(article)
        if main_item:
            main_candidates.append(main_item)

    ranked_main = select_main_candidates_with_naver_priority(main_candidates)
    ranked_reference = rank_reference(reference_candidates)[:MAX_REFERENCE]

    ranked_main = prioritize_naver_output(ranked_main, lambda x: x.article)
    ranked_reference = prioritize_naver_output(ranked_reference, lambda x: x.article)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(render(ranked_main, ranked_reference), encoding="utf-8")

    print(f"Generated: {OUTPUT_PATH}")
    print(
        "Publication window (KST): "
        f"{window_start_kst.strftime('%Y-%m-%d %H:%M:%S')} ~ {window_end_kst.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    print(f"Main candidates: {len(ranked_main)}")
    print(f"Reference news: {len(ranked_reference)}")

    if args.send_telegram:
        sent_count = send_markdown_to_telegram(OUTPUT_PATH)
        if sent_count > 0:
            print(f"Telegram delivery completed: {sent_count} message(s) sent.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
