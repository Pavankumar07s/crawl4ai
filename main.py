"""
Main Orchestrator - Production-grade India News Crawler
"""
import asyncio
import logging
import signal
import sys
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    IndiaNewsCrawlerConfig,
    get_default_config,
    get_development_config,
    CrawlStrategy,
    INDIA_NEWS_QUERIES,
    INDIA_STATE_QUERIES,
)

# Suppress the ContextVar cross-context reset error from crawl4ai
# This is a known issue when async generators are closed across different contexts
import warnings
import logging

# Filter out the specific asyncio "Task exception was never retrieved" for ContextVar
class _ContextVarFilter(logging.Filter):
    def filter(self, record):
        if "ContextVar" in str(record.msg) and "different Context" in str(record.msg):
            return False
        return True

logging.getLogger("asyncio").addFilter(_ContextVarFilter())

# Import crawler components lazily (module-level import kept for typing/runtime use)
from crawler import (
    CoreCrawlerEngine,
    URLSeeder,
    AdaptiveNewsCrawler,
    NewsSourceManager,
    StorageManager,
    CrawlResult,
    DiscoveredURL,
    SourceCategory,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('crawler.log'),
    ]
)
logger = logging.getLogger(__name__)


class CrawlMode(Enum):
    """Crawling modes"""
    SEED_AND_CRAWL = "seed_and_crawl"  # Discover URLs then crawl
    DEEP_CRAWL = "deep_crawl"          # Deep crawl from seeds
    ADAPTIVE = "adaptive"              # Adaptive query-based
    CONTINUOUS = "continuous"          # Continuous monitoring


@dataclass
class CrawlSession:
    """Represents a crawl session"""
    session_id: str
    mode: CrawlMode
    start_time: datetime
    end_time: Optional[datetime] = None
    total_urls: int = 0
    successful: int = 0
    failed: int = 0
    duplicates: int = 0
    status: str = "running"
    errors: List[str] = field(default_factory=list)


class IndiaNewsCrawler:
    """
    Main orchestrator for India News Crawler
    
    Combines all components into a production-ready system:
    - URL Seeding for discovery
    - Deep/Adaptive crawling
    - Content storage and export
    - Monitoring and logging
    """
    
    def __init__(self, config: Optional[IndiaNewsCrawlerConfig] = None):
        self.config = config or get_default_config()
        
        # Initialize components
        self.source_manager = NewsSourceManager()
        self.storage = StorageManager(self.config.storage)
        
        # Session tracking
        self._current_session: Optional[CrawlSession] = None
        self._shutdown_requested = False
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        
    def _handle_shutdown(self, signum, frame):
        """Handle graceful shutdown"""
        logger.info("Shutdown requested...")
        self._shutdown_requested = True
        
    def _create_session(self, mode: CrawlMode) -> CrawlSession:
        """Create new crawl session"""
        session = CrawlSession(
            session_id=datetime.now().strftime("%Y%m%d_%H%M%S"),
            mode=mode,
            start_time=datetime.now(),
        )
        self._current_session = session
        logger.info(f"Started session: {session.session_id} (mode: {mode.value})")
        return session
        
    def _end_session(self):
        """End current session"""
        if self._current_session:
            self._current_session.end_time = datetime.now()
            self._current_session.status = "completed"
            
            duration = self._current_session.end_time - self._current_session.start_time
            logger.info(
                f"Session {self._current_session.session_id} completed: "
                f"{self._current_session.successful} successful, "
                f"{self._current_session.failed} failed, "
                f"{self._current_session.duplicates} duplicates, "
                f"duration: {duration}"
            )
            
    async def discover_urls(
        self,
        categories: Optional[List[str]] = None,
        queries: Optional[List[str]] = None,
        max_urls: int = 500,
        include_google_news: bool = True,
    ) -> List[DiscoveredURL]:
        """
        Phase 1: Discover URLs using Google News, URL seeding, and sitemaps
        
        Args:
            categories: Source categories to use
            queries: News queries for relevance
            max_urls: Maximum URLs to discover
            include_google_news: Whether to include Google News RSS feeds
            
        Returns:
            List of discovered URLs sorted by relevance
        """
        logger.info(f"Starting URL discovery (max: {max_urls}, google_news: {include_google_news})")
        
        categories = categories or ["national_news", "tech_news"]
        queries = queries or INDIA_NEWS_QUERIES[:5]
        
        all_urls = []
        
        async with URLSeeder(self.config.seeding) as seeder:
            # Discover India news (now includes Google News by default)
            urls = await seeder.discover_india_news(
                queries=queries,
                categories=categories,
                max_urls_per_source=max_urls // len(categories),
                include_google_news=include_google_news,
            )
            all_urls.extend(urls)
            
        # Filter out already crawled URLs
        filtered = []
        for url in all_urls:
            if not self.storage.url_exists(url.url):
                filtered.append(url)
            else:
                logger.debug(f"Skipping already crawled: {url.url}")
                
        logger.info(f"Discovered {len(all_urls)} URLs, {len(filtered)} new")
        return filtered[:max_urls]
    
    async def discover_from_rss(
        self,
        rss_feeds: Optional[List[str]] = None,
        max_urls: int = 100,
    ) -> List[DiscoveredURL]:
        """
        Discover news URLs from direct news website RSS feeds.
        This is the most reliable method - URLs are direct article links.
        
        Args:
            rss_feeds: List of RSS feed URLs (defaults to NEWS_RSS_FEEDS)
            max_urls: Maximum URLs to return
            
        Returns:
            List of discovered URLs
        """
        logger.info(f"Discovering from direct RSS feeds (max: {max_urls})")
        
        async with URLSeeder(self.config.seeding) as seeder:
            urls = await seeder.discover_from_direct_rss(
                rss_feeds=rss_feeds,
                max_urls=max_urls,
            )
        
        # Filter out already crawled URLs
        filtered = [u for u in urls if not self.storage.url_exists(u.url)]
        logger.info(f"Found {len(urls)} URLs from RSS, {len(filtered)} new")
        return filtered
    
    async def discover_google_news(
        self,
        queries: Optional[List[str]] = None,
        max_urls: int = 100,
    ) -> List[DiscoveredURL]:
        """
        Discover news URLs from Google News RSS feeds only
        
        Args:
            queries: Search queries (defaults to India news queries)
            max_urls: Maximum URLs to return
            
        Returns:
            List of discovered URLs from Google News
        """
        logger.info(f"Discovering from Google News RSS (max: {max_urls})")
        
        queries = queries or [
            "India news",
            "India breaking news", 
            "India politics",
            "India economy",
            "Indian government",
        ]
        
        async with URLSeeder(self.config.seeding) as seeder:
            urls = await seeder.discover_from_google_news(
                queries=queries,
                max_urls=max_urls,
                resolve_redirects=True,
            )
        
        # Filter out already crawled URLs
        filtered = [u for u in urls if not self.storage.url_exists(u.url)]
        logger.info(f"Found {len(urls)} URLs from Google News, {len(filtered)} new")
        return filtered
        
    async def crawl_discovered_urls(
        self,
        urls: List[DiscoveredURL],
        stream: bool = True,
    ) -> List[CrawlResult]:
        """
        Phase 2: Crawl discovered URLs
        
        Args:
            urls: URLs to crawl (from discovery phase)
            stream: Stream results as they come
            
        Returns:
            List of crawl results
        """
        if not urls:
            logger.warning("No URLs to crawl")
            return []
            
        logger.info(f"Crawling {len(urls)} URLs")
        
        results = []
        url_strings = [u.url for u in urls]
        
        # Ensure we have a session
        if not self._current_session:
            self._create_session(CrawlMode.SEED_AND_CRAWL)
        
        from crawler.core_engine import CoreCrawlerEngine
        engine = CoreCrawlerEngine(
            config=self.config.crawler,
            proxy_config=self.config.proxy if self.config.proxy.enabled else None,
        )
        
        async with engine as crawler:
            async for result in crawler.crawl_urls(url_strings, stream=stream):
                if self._shutdown_requested:
                    logger.info("Shutdown requested, stopping crawl")
                    break
                    
                results.append(result)
                
                # Store result
                if result.success:
                    stored = self.storage.store(result)
                    if stored:
                        if self._current_session:
                            self._current_session.successful += 1
                        logger.info(f"✓ Crawled: {result.title[:50]}... (score: {result.score:.2f})")
                    else:
                        if self._current_session:
                            self._current_session.duplicates += 1
                else:
                    if self._current_session:
                        self._current_session.failed += 1
                    logger.warning(f"✗ Failed: {result.url} - {result.error}")
                
                if self._current_session:
                    self._current_session.total_urls += 1
                
        return results
        
    async def deep_crawl(
        self,
        start_urls: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        max_pages: Optional[int] = None,
    ) -> List[CrawlResult]:
        """
        Deep crawl mode - follow links from seed URLs
        
        Args:
            start_urls: Starting URLs (uses config if None)
            keywords: Keywords for relevance scoring
            max_pages: Maximum pages to crawl
            
        Returns:
            List of crawl results
        """
        start_urls = start_urls or self.source_manager.get_urls(
            categories=[SourceCategory.NATIONAL],
            min_priority=8,
        )[:3]
        
        max_pages = max_pages or self.config.crawler.max_pages
        
        logger.info(f"Starting deep crawl from {len(start_urls)} seeds")
        
        results = []
        
        engine = CoreCrawlerEngine(
            config=self.config.crawler,
            proxy_config=self.config.proxy if self.config.proxy.enabled else None,
            keywords=keywords,
        )
        
        async with engine as crawler:
            for start_url in start_urls:
                if self._shutdown_requested:
                    break
                
                # Check if we've already hit the global limit
                if len(results) >= max_pages:
                    logger.info(f"Max pages reached ({len(results)}/{max_pages}), skipping remaining seeds")
                    break
                    
                logger.info(f"Deep crawling: {start_url}")
                
                async for result in crawler.crawl_deep(
                    start_url=start_url,
                    keywords=keywords,
                    relevance_query="India news",
                    stream=True,
                ):
                    if self._shutdown_requested:
                        break
                        
                    results.append(result)
                    
                    if result.success:
                        stored = self.storage.store(result)
                        if stored:
                            self._current_session.successful += 1
                            logger.info(f"✓ [{result.depth}] {result.title[:50]}...")
                        else:
                            self._current_session.duplicates += 1
                    else:
                        self._current_session.failed += 1
                        
                    self._current_session.total_urls += 1
                    
                    if len(results) >= max_pages:
                        logger.info(f"Max pages reached ({len(results)}/{max_pages})")
                        break
                        
        return results
        
    async def adaptive_crawl(
        self,
        queries: Optional[List[str]] = None,
        start_urls: Optional[List[str]] = None,
        confidence_threshold: float = 0.8,
    ) -> Dict[str, Any]:
        """
        Adaptive crawl mode - stops when enough info gathered
        
        Args:
            queries: Queries to satisfy
            start_urls: Starting URLs
            confidence_threshold: Confidence level to reach
            
        Returns:
            Dictionary with results and metrics
        """
        queries = queries or INDIA_NEWS_QUERIES[:5]
        start_urls = start_urls or [
            "https://timesofindia.indiatimes.com/",
            "https://www.ndtv.com/",
        ]
        
        logger.info(f"Starting adaptive crawl with {len(queries)} queries")
        
        from crawler import AdaptiveNewsCrawler
        from config import AdaptiveConfig
        
        adaptive_config = AdaptiveConfig(
            confidence_threshold=confidence_threshold,
            max_pages=self.config.adaptive.max_pages,
        )
        
        all_results = []
        total_metrics = {
            "queries_processed": 0,
            "total_pages": 0,
            "avg_confidence": 0,
        }
        
        async with AdaptiveNewsCrawler(adaptive_config) as crawler:
            for url in start_urls:
                if self._shutdown_requested:
                    break
                    
                for query in queries:
                    if self._shutdown_requested:
                        break
                        
                    logger.info(f"Adaptive crawl: {query}")
                    
                    result = await crawler.crawl(url, query)
                    all_results.append(result)
                    
                    # Store results
                    for r in result.results:
                        if r.success:
                            self.storage.store(r)
                            self._current_session.successful += 1
                        else:
                            self._current_session.failed += 1
                        self._current_session.total_urls += 1
                        
                    total_metrics["queries_processed"] += 1
                    total_metrics["total_pages"] += len(result.results)
                    total_metrics["avg_confidence"] += result.metrics.confidence_score
                    
                    logger.info(
                        f"Query complete: {result.metrics.pages_crawled} pages, "
                        f"confidence: {result.metrics.confidence_score:.2f}"
                    )
                    
        if total_metrics["queries_processed"] > 0:
            total_metrics["avg_confidence"] /= total_metrics["queries_processed"]
            
        return {
            "results": all_results,
            "metrics": total_metrics,
        }
        
    async def run_seed_and_crawl(
        self,
        max_urls: int = 200,
        categories: Optional[List[str]] = None,
        include_google_news: bool = True,
    ) -> List[CrawlResult]:
        """
        Complete seed-and-crawl pipeline with Google News support
        
        Args:
            max_urls: Maximum URLs to process
            categories: Source categories
            include_google_news: Whether to include Google News RSS feeds
            
        Returns:
            List of crawl results
        """
        session = self._create_session(CrawlMode.SEED_AND_CRAWL)
        
        try:
            # Phase 1: Discover (now includes Google News)
            discovered = await self.discover_urls(
                categories=categories,
                max_urls=max_urls,
                include_google_news=include_google_news,
            )
            
            # Phase 2: Crawl
            results = await self.crawl_discovered_urls(discovered)
            
            return results
            
        except Exception as e:
            logger.error(f"Error in seed-and-crawl: {e}")
            session.errors.append(str(e))
            return []
            
        finally:
            self._end_session()
            
    async def run_deep_crawl(
        self,
        start_urls: Optional[List[str]] = None,
        max_pages: int = 500,
    ) -> List[CrawlResult]:
        """
        Complete deep crawl pipeline
        
        Args:
            start_urls: Starting URLs
            max_pages: Maximum pages
            
        Returns:
            List of crawl results
        """
        session = self._create_session(CrawlMode.DEEP_CRAWL)
        
        try:
            return await self.deep_crawl(
                start_urls=start_urls,
                max_pages=max_pages,
            )
            
        except Exception as e:
            logger.error(f"Error in deep crawl: {e}")
            session.errors.append(str(e))
            return []
            
        finally:
            self._end_session()
            
    async def run_adaptive(
        self,
        queries: Optional[List[str]] = None,
        confidence: float = 0.8,
    ) -> Dict[str, Any]:
        """
        Complete adaptive crawl pipeline
        
        Args:
            queries: Queries to satisfy
            confidence: Target confidence
            
        Returns:
            Results dictionary
        """
        session = self._create_session(CrawlMode.ADAPTIVE)
        
        try:
            return await self.adaptive_crawl(
                queries=queries,
                confidence_threshold=confidence,
            )
            
        except Exception as e:
            logger.error(f"Error in adaptive crawl: {e}")
            session.errors.append(str(e))
            return {"results": [], "metrics": {}}
            
        finally:
            self._end_session()
            
    async def run_continuous(
        self,
        interval_minutes: int = 30,
        max_iterations: Optional[int] = None,
    ):
        """
        Continuous crawling mode
        
        Args:
            interval_minutes: Minutes between crawl cycles
            max_iterations: Maximum iterations (None for infinite)
        """
        session = self._create_session(CrawlMode.CONTINUOUS)
        iteration = 0
        
        try:
            while not self._shutdown_requested:
                if max_iterations and iteration >= max_iterations:
                    break
                    
                iteration += 1
                logger.info(f"=== Continuous crawl iteration {iteration} ===")
                
                # Run seed and crawl
                await self.run_seed_and_crawl(max_urls=100)
                
                if self._shutdown_requested:
                    break
                    
                # Wait for next cycle
                logger.info(f"Waiting {interval_minutes} minutes for next cycle...")
                await asyncio.sleep(interval_minutes * 60)
                
        except Exception as e:
            logger.error(f"Error in continuous mode: {e}")
            session.errors.append(str(e))
            
        finally:
            self._end_session()
            
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        storage_stats = self.storage.get_stats()
        
        return {
            "current_session": {
                "id": self._current_session.session_id if self._current_session else None,
                "status": self._current_session.status if self._current_session else None,
                "successful": self._current_session.successful if self._current_session else 0,
                "failed": self._current_session.failed if self._current_session else 0,
            },
            "storage": storage_stats,
            "sources": {
                "total": len(self.source_manager.sources),
                "enabled": len(self.source_manager.get_all_sources()),
            },
        }
        
    def export_results(self, format: str = "rag", limit: int = 100):
        """
        Export results in specified format
        
        Args:
            format: Output format (rag, json, jsonl, markdown)
            limit: Number of recent articles to export
        """
        if format == "rag":
            self.storage.export_for_rag("./output/rag_export.json", min_score=0.0)
            logger.info("RAG export complete at: ./output/rag_export.json")
        elif format == "json":
            articles = self.storage.get_recent_articles(limit=limit, min_score=0.0)
            if articles:
                # Export to JSON file (array format)
                import json
                from datetime import datetime
                json_file = Path("./output") / f"exported_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                json_file.parent.mkdir(parents=True, exist_ok=True)
                
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(articles, f, indent=2, ensure_ascii=False)
                
                logger.info(f"Exported {len(articles)} articles to: {json_file}")
            else:
                logger.warning("No articles to export")
        elif format == "jsonl":
            articles = self.storage.get_recent_articles(limit=limit, min_score=0.0)
            if articles:
                # Export to JSONL file
                import json
                from datetime import datetime
                jsonl_file = Path("./output") / f"exported_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
                jsonl_file.parent.mkdir(parents=True, exist_ok=True)
                
                with open(jsonl_file, 'w', encoding='utf-8') as f:
                    for article in articles:
                        f.write(json.dumps(article, ensure_ascii=False) + '\n')
                
                logger.info(f"Exported {len(articles)} articles to: {jsonl_file}")
            else:
                logger.warning("No articles to export")
        elif format == "markdown":
            articles = self.storage.get_recent_articles(limit=limit, min_score=0.0)
            if articles:
                # Convert dict articles to CrawlResult objects for export
                from datetime import datetime
                crawl_results = []
                for article in articles:
                    result = CrawlResult(
                        url=article.get("url", ""),
                        title=article.get("title", ""),
                        content=article.get("content", ""),
                        markdown=article.get("markdown", ""),
                        metadata=article.get("metadata", {}),
                        depth=0,
                        score=article.get("score", 0.0),
                        crawled_at=datetime.now(),
                        success=True,
                        source_domain=article.get("source_domain", ""),
                    )
                    crawl_results.append(result)
                
                # Export combined markdown file
                self.storage.markdown_exporter.export_combined(
                    crawl_results,
                    f"exported_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
                )
                logger.info(f"Exported {len(articles)} articles to: {self.storage.markdown_exporter.output_dir}")
            else:
                logger.warning("No articles to export")


# CLI entry point
async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="India News Crawler")
    parser.add_argument(
        "--mode",
        choices=["seed", "rss", "google-news", "deep", "adaptive", "continuous"],
        default="rss",
        help="Crawling mode: rss (recommended - direct RSS feeds), seed (sitemaps), google-news, deep, adaptive, continuous"
    )
    parser.add_argument(
        "--max-urls",
        type=int,
        default=100,
        help="Maximum URLs to crawl"
    )
    parser.add_argument(
        "--no-google-news",
        action="store_true",
        help="Disable Google News in seed mode"
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Use development config"
    )
    parser.add_argument(
        "--export",
        choices=["rag", "json", "jsonl", "markdown"],
        help="Export format after crawling"
    )
    
    args = parser.parse_args()
    
    # Get config
    config = get_development_config() if args.dev else get_default_config()
    
    # Create crawler
    crawler = IndiaNewsCrawler(config)
    
    include_google = not args.no_google_news
    google_status = "enabled" if include_google else "disabled"
    
    print(f"""
╔═══════════════════════════════════════════════════════════╗
║          🇮🇳 INDIA NEWS CRAWLER - Production Ready 🇮🇳      ║
╠═══════════════════════════════════════════════════════════╣
║  Mode: {args.mode:<50} ║
║  Max URLs: {args.max_urls:<46} ║
║  Google News: {google_status:<43} ║
║  Config: {'Development' if args.dev else 'Production':<47} ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Run appropriate mode
    if args.mode == "seed":
        results = await crawler.run_seed_and_crawl(
            max_urls=args.max_urls,
            include_google_news=include_google
        )
        print(f"\n✓ Completed: {len(results)} articles crawled")
    
    elif args.mode == "rss":
        # Direct RSS feeds mode (most reliable)
        urls = await crawler.discover_from_rss(max_urls=args.max_urls)
        if urls:
            results = await crawler.crawl_discovered_urls(urls)
            print(f"\n✓ Completed: {len(results)} articles crawled from RSS feeds")
        else:
            print("\n⚠ No new URLs found from RSS feeds")
            results = []
    
    elif args.mode == "google-news":
        # Google News only mode (may have redirect issues)
        urls = await crawler.discover_google_news(max_urls=args.max_urls)
        if urls:
            results = await crawler.crawl_discovered_urls(urls)
            print(f"\n✓ Completed: {len(results)} articles crawled from Google News")
        else:
            print("\n⚠ No new URLs found from Google News")
            results = []
        
    elif args.mode == "deep":
        results = await crawler.run_deep_crawl(max_pages=args.max_urls)
        print(f"\n✓ Completed: {len(results)} articles crawled")
        
    elif args.mode == "adaptive":
        result = await crawler.run_adaptive()
        print(f"\n✓ Completed: {result['metrics']['total_pages']} pages, "
              f"avg confidence: {result['metrics']['avg_confidence']:.2f}")
        
    elif args.mode == "continuous":
        await crawler.run_continuous(interval_minutes=30)
        
    # Export if requested
    if args.export:
        crawler.export_results(format=args.export)
        
    # Print stats
    stats = crawler.get_stats()
    print(f"\n📊 Stats: {stats['storage']['database']['total_articles']} total articles in database")


if __name__ == "__main__":
    asyncio.run(main())
