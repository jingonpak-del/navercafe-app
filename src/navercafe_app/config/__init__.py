"""Configuration loaders for daily Naver Cafe crawler targets."""

from .targets import BoardTarget, CrawlDefaults, CafeTarget, CrawlTargets, load_targets

__all__ = ["BoardTarget", "CafeTarget", "CrawlDefaults", "CrawlTargets", "load_targets"]
