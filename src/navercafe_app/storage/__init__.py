"""Storage backends for Naver Cafe crawler results."""

from .sqlite_store import CrawlRunSummary, SQLiteStore

__all__ = ["CrawlRunSummary", "SQLiteStore"]
