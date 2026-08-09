"""Optional live news gateway for TradeOracle Apex."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

try:
    from newsapi import NewsApiClient
except ImportError:  # pragma: no cover
    NewsApiClient = None

POSITIVE_TERMS = {"beat", "beats", "surge", "surges", "growth", "profit", "profits",
                  "upgrade", "upgraded", "order", "orders", "wins", "award", "strong",
                  "record", "buyback", "dividend", "acquisition", "approval", "approved"}
NEGATIVE_TERMS = {"miss", "misses", "loss", "losses", "fall", "falls", "drop", "drops",
                  "downgrade", "downgraded", "fraud", "probe", "investigation", "debt",
                  "default", "warning", "weak", "delay", "delayed", "lawsuit", "ban"}
EVENT_KEYWORDS = {
    "EARNINGS": ("earnings", "results", "quarterly result", "profit", "revenue"),
    "ORDER": ("order", "contract", "deal", "wins", "award"),
    "MERGER": ("merger", "merge"),
    "ACQUISITION": ("acquisition", "acquire", "acquires"),
    "DIVIDEND": ("dividend", "payout"),
    "BUYBACK": ("buyback", "share repurchase", "repurchase"),
    "GUIDANCE": ("guidance", "outlook", "forecast"),
}


def _secret(name: str, default: str = "") -> str:
    try:
        import streamlit as st
        value = st.secrets.get(name)
        if value is not None:
            return str(value)
    except Exception:
        pass
    return os.getenv(name, default)


def _parse_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class NewsData:
    """Normalize recent news into Apex research context.

    Sentiment and event labels are explicitly marked as heuristic.
    """

    name = "NewsData"
    version = "1.0.0"
    capabilities = ["NEWS_DATA", "EVENT_DATA"]

    def __init__(self, api_key: Optional[str] = None, language: str = "en") -> None:
        self.api_key = api_key or _secret("NEWSAPI_KEY")
        self.language = language
        self.client = (
            NewsApiClient(api_key=self.api_key)
            if self.api_key and NewsApiClient
            else None
        )

    @property
    def configured(self) -> bool:
        return self.client is not None

    @staticmethod
    def _sentiment(text: str) -> float:
        words = {word.strip(".,:;!?()[]{}\"'").lower() for word in text.split()}
        positive = len(words.intersection(POSITIVE_TERMS))
        negative = len(words.intersection(NEGATIVE_TERMS))
        total = positive + negative
        if total == 0:
            return 0.0
        return max(-1.0, min(1.0, (positive - negative) / total))

    @staticmethod
    def _event_type(text: str) -> str:
        lowered = text.lower()
        for event_type, keywords in EVENT_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                return event_type
        return "OTHER"

    def _normalize(self, article: dict[str, Any], symbol: str) -> Optional[dict[str, Any]]:
        if not isinstance(article, dict):
            return None
        title = str(article.get("title") or "").strip()
        if not title or title == "[Removed]":
            return None
        published = _parse_time(article.get("publishedAt"))
        if published is None:
            return None

        description = str(article.get("description") or "").strip()
        text = f"{title} {description}".strip()
        sentiment = self._sentiment(text)
        event_type = self._event_type(text)
        source = article.get("source") or {}
        source_name = source.get("name") if isinstance(source, dict) else str(source)

        return {
            "symbol": symbol,
            "timestamp": published.isoformat(),
            "headline": title,
            "text": text,
            "description": description,
            "url": str(article.get("url") or ""),
            "source": str(source_name or ""),
            "sentiment": round(sentiment, 6),
            "impact_score": round(sentiment, 6),
            "event_type": event_type,
            "event_confidence": 0.45 if event_type != "OTHER" else 0.0,
            "event_source": "news_heuristic",
            "data_type": "news",
            "live": True,
        }

    def fetch(
        self,
        symbol: Optional[str] = None,
        start: Any = None,
        end: Any = None,
        limit: Optional[int] = 50,
        query: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not self.configured:
            return {
                "records": [],
                "events": [],
                "sentiment_scores": [],
                "quality": {"status": "UNCONFIGURED", "count": 0},
                "source": None,
            }

        now = datetime.now(timezone.utc)
        end_dt = _parse_time(end) or now
        start_dt = _parse_time(start) or (end_dt - timedelta(hours=24))
        search = query or symbol or "Indian stock market"

        response = self.client.get_everything(
            q=search,
            language=self.language,
            from_param=start_dt,
            to=end_dt,
            sort_by="publishedAt",
            page_size=min(max(int(limit or 50), 1), 100),
        )
        articles = response.get("articles", []) if isinstance(response, dict) else []

        records = [
            row for row in (
                self._normalize(article, symbol or "") for article in articles
            ) if row
        ]
        records.sort(key=lambda row: row["timestamp"])
        if limit:
            records = records[-max(1, int(limit)):]

        events = [dict(row) for row in records if row.get("event_type") != "OTHER"]
        sentiments = [float(row["sentiment"]) for row in records]

        return {
            "records": records,
            "events": events,
            "sentiment_scores": sentiments,
            "quality": {
                "status": "OK" if records else "EMPTY",
                "count": len(records),
                "source": "newsapi",
                "window_start": start_dt.isoformat(),
                "window_end": end_dt.isoformat(),
            },
            "source": "newsapi",
        }

    def health(self) -> dict[str, Any]:
        return {
            "engine": self.name,
            "version": self.version,
            "configured": self.configured,
            "provider": "newsapi" if self.configured else None,
            "read_only": True,
        }
