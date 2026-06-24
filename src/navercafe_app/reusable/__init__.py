"""Reusable extraction modules for future Naver Cafe automation builds."""

from .comment_master import (
    ArticleFilter,
    CafeBoardTarget,
    NewPost,
    NewPostTracker,
    WorkDatabase,
    article_list_v3_url,
    article_timestamp,
    cafe_gate_info_url,
    filter_articles,
    load_comment_bank,
    normalize_cafe_slug,
    parse_cafe_board_targets,
    select_comment_for_article,
)

__all__ = [
    "ArticleFilter",
    "CafeBoardTarget",
    "NewPost",
    "NewPostTracker",
    "WorkDatabase",
    "article_list_v3_url",
    "article_timestamp",
    "cafe_gate_info_url",
    "filter_articles",
    "load_comment_bank",
    "normalize_cafe_slug",
    "parse_cafe_board_targets",
    "select_comment_for_article",
]
