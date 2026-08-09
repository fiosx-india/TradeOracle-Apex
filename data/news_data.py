"""Optional read-only news gateway for Apex research context."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

try:
    from newsapi import NewsApiClient
except ImportError:
    NewsApiClient = None

_POSITIVE = {"beat", "beats", "surge", "growth", "profit", "upgrade", "order",
             "wins", "award", "strong", "record", "buyback", "dividend",
             "acquisition", "approval", "approved"}
_NEGATIVE = {"miss", "loss", "fall", "drop", "downgrade", "fraud", "probe",
             "investigation", "debt", "default", "warning", "weak", "delay",
             "lawsuit", "ban"}
_EVENTS = {
    "EARNINGS": ("earnings", "results", "quarterly result", "profit", "revenue"),
    "ORDER": ("order", "contract", "deal", "wins", "award"),
    "MERGER": ("merger", "merge"),
    "ACQUISITION": ("acquisition", "acquire", "acquires"),
    "DIVIDEND": ("dividend", "payout"),
    "BUYBACK": ("buyback", "repurchase"),
    "GUIDANCE": ("guidance", "outlook", "forecast"),
}


def _secret(name: str) -> str:
    try:
        import streamlit as st
        value = st.secrets.get(name)
        if value is not None:
            return str(value)
    except Exception:
        pass
    return os.getenv(name, "")


class NewsData:
    name = "NewsData"
    version = "1.0.0"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or _secret("NEWSAPI_KEY")
        self.client = NewsApiClient(api_key=self.api_key) if self.api_key and NewsApiClient else None

    @property
    def configured(self) -> bool:
        return self.client is not None

    @staticmethod
    def _event(text: str) -> str:
        low = text.lower()
        for event, keys in _EVENTS.items():
            if any(k in low for k in keys):
                return event
        return "OTHER"

    @staticmethod
    def _sentiment(text: str) -> float:
        words = {w.strip(".,:;!?()[]{}\"'").lower() for w in text.split()}
        p = len(words & _POSITIVE)
        n = len(words & _NEGATIVE)
        return 0.0 if p + n == 0 else max(-1.0, min(1.0, (p - n) / (p + n)))

    def fetch(self, symbol: str = "", limit: int = 50, **kwargs: Any) -> dict[str, Any]:
        if not self.configured:
            return {
                "records": [],
                "events": [],
                "sentiment_scores": [],
                "quality": {"status": "UNCONFIGURED", "count": 0},
                "source": None,
            }

        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=24)
        response = self.client.get_everything(
            q=symbol or "Indian stock market",
            language="en",
            from_param=start,
            to=end,
            sort_by="publishedAt",
            page_size=min(max(int(limit), 1), 100),
        )
        articles = response.get("articles", []) if isinstance(response, dict) else []
        records = []
        for article in articles:
            title = str(article.get("title") or "").strip()
            if not title or title == "[Removed]":
                continue
            published = article.get("publishedAt")
            if not published:
                continue
            text = f"{title} {article.get('description') or ''}".strip()
            event = self._event(text)
            records.append({
                "symbol": symbol,
                "timestamp": published,
                "headline": title,
                "text": text,
                "url": str(article.get("url") or ""),
                "source": str((article.get("source") or {}).get("name") or ""),
                "sentiment": round(self._sentiment(text), 6),
                "impact_score": round(self._sentiment(text), 6),
                "event_type": event,
                "event_confidence": 0.45 if event != "OTHER" else 0.0,
                "event_source": "news_heuristic",
                "data_type": "news",
            })
        records = records[-max(1, int(limit)):]
        return {
            "records": records,
            "events": [r for r in records if r["event_type"] != "OTHER"],
            "sentiment_scores": [r["sentiment"] for r in records],
            "quality": {"status": "OK" if records else "EMPTY", "count": len(records)},
            "source": "newsapi",
        }

    def health(self) -> dict[str, Any]:
        return {"engine": self.name, "configured": self.configured, "read_only": True}
