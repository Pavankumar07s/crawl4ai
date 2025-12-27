"""Crawler module initialization"""
from .core_engine import (
    CoreCrawlerEngine,
    CrawlResult,
    create_crawler,
)
from .url_seeder import (
    URLSeeder,
    DiscoveredURL,
    SmartURLPrioritizer,
    seed_india_news_urls,
)
from .adaptive_crawler import (
    AdaptiveNewsCrawler,
    AdaptiveCrawlResult,
    AdaptiveCrawlMetrics,
    AdaptiveResearchCrawler,
    adaptive_crawl_india_news,
)
from .source_manager import (
    NewsSourceManager,
    NewsSource,
    SourceCategory,
    SourceReliability,
    NEWS_SOURCES,
    get_top_news_sources,
    get_india_news_urls,
    get_multilingual_sources,
)
from .storage import (
    StorageManager,
    SQLiteStorage,
    JSONLinesStorage,
    MarkdownExporter,
    ContentDeduplicator,
)

__all__ = [
    # Core engine
    "CoreCrawlerEngine",
    "CrawlResult",
    "create_crawler",
    
    # URL seeding
    "URLSeeder",
    "DiscoveredURL",
    "SmartURLPrioritizer",
    "seed_india_news_urls",
    
    # Adaptive crawling
    "AdaptiveNewsCrawler",
    "AdaptiveCrawlResult",
    "AdaptiveCrawlMetrics",
    "AdaptiveResearchCrawler",
    "adaptive_crawl_india_news",
    
    # Source management
    "NewsSourceManager",
    "NewsSource",
    "SourceCategory",
    "SourceReliability",
    "NEWS_SOURCES",
    "get_top_news_sources",
    "get_india_news_urls",
    "get_multilingual_sources",
    
    # Storage
    "StorageManager",
    "SQLiteStorage",
    "JSONLinesStorage",
    "MarkdownExporter",
    "ContentDeduplicator",
]
