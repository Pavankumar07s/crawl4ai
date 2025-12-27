"""
Core Crawler Engine - Wraps Crawl4AI with production features
"""
import asyncio
import random
import logging
from typing import List, Optional, Dict, Any, AsyncIterator
from dataclasses import dataclass
from datetime import datetime

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
    ProxyConfig as Crawl4AIProxyConfig,
)
from crawl4ai.deep_crawling import (
    BFSDeepCrawlStrategy,
    DFSDeepCrawlStrategy,
    BestFirstCrawlingStrategy,
)
from crawl4ai.deep_crawling.filters import (
    FilterChain,
    URLPatternFilter,
    DomainFilter,
    ContentTypeFilter,
    ContentRelevanceFilter,
)
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from crawl4ai.proxy_strategy import RoundRobinProxyStrategy

import sys
sys.path.append('..')
from config.settings import (
    CrawlerConfig,
    CrawlStrategy,
    ProxyConfig,
    URL_PATTERNS,
    RELEVANCE_KEYWORDS,
)

logger = logging.getLogger(__name__)

@dataclass
class CrawlResult:
    """Standardized crawl result"""
    url: str
    title: str
    content: str
    markdown: str
    metadata: Dict[str, Any]
    depth: int
    score: float
    crawled_at: datetime
    success: bool
    error: Optional[str] = None
    language: Optional[str] = None
    source_domain: Optional[str] = None

class CoreCrawlerEngine:
    """
    Production-grade crawler engine wrapping Crawl4AI
    
    Features:
    - Multiple crawling strategies (BFS, DFS, BestFirst)
    - URL filtering and relevance scoring
    - Rate limiting and politeness delays
    - Proxy rotation support
    - Streaming results
    - Error handling and retry logic
    """
    
    def __init__(
        self,
        config: CrawlerConfig,
        proxy_config: Optional[ProxyConfig] = None,
        keywords: Optional[List[str]] = None,
    ):
        self.config = config
        self.proxy_config = proxy_config
        self.keywords = keywords or RELEVANCE_KEYWORDS
        self._crawler: Optional[AsyncWebCrawler] = None
        self._browser_config: Optional[BrowserConfig] = None
        self._proxy_strategy: Optional[RoundRobinProxyStrategy] = None
        
        self._setup_browser_config()
        self._setup_proxy_strategy()
        
    def _setup_browser_config(self):
        """Configure browser settings"""
        self._browser_config = BrowserConfig(
            browser_type=self.config.browser_type,
            headless=self.config.headless,
            text_mode=self.config.text_mode,
            verbose=False,
        )
        
    def _setup_proxy_strategy(self):
        """Setup proxy rotation if configured"""
        if self.proxy_config and self.proxy_config.enabled and self.proxy_config.proxies:
            proxies = [
                Crawl4AIProxyConfig.from_string(p) 
                for p in self.proxy_config.proxies
            ]
            if self.proxy_config.rotation_enabled:
                self._proxy_strategy = RoundRobinProxyStrategy(proxies)
            logger.info(f"Configured {len(proxies)} proxies for rotation")
            
    def _build_filter_chain(
        self,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        allowed_domains: Optional[List[str]] = None,
        blocked_domains: Optional[List[str]] = None,
        relevance_query: Optional[str] = None,
    ) -> FilterChain:
        """Build filter chain for URL filtering"""
        filters = []
        
        # URL pattern filter
        patterns = include_patterns or URL_PATTERNS.get("include", [])
        if patterns:
            filters.append(URLPatternFilter(patterns=patterns))
            
        # Domain filter
        if allowed_domains or blocked_domains:
            filters.append(DomainFilter(
                allowed_domains=allowed_domains or [],
                blocked_domains=blocked_domains or URL_PATTERNS.get("exclude", [])
            ))
            
        # Content type filter - only HTML
        filters.append(ContentTypeFilter(allowed_types=["text/html"]))
        
        # Content relevance filter
        if relevance_query:
            filters.append(ContentRelevanceFilter(
                query=relevance_query,
                threshold=self.config.score_threshold
            ))
            
        return FilterChain(filters) if filters else FilterChain([])
    
    def _build_scorer(self, keywords: Optional[List[str]] = None) -> KeywordRelevanceScorer:
        """Build keyword relevance scorer"""
        return KeywordRelevanceScorer(
            keywords=keywords or self.keywords,
            weight=0.7
        )
        
    def _get_crawl_strategy(
        self,
        filter_chain: FilterChain,
        scorer: KeywordRelevanceScorer,
    ):
        """Get appropriate crawl strategy based on config"""
        common_params = {
            "max_depth": self.config.max_depth,
            "include_external": False,
            "max_pages": self.config.max_pages,
            "filter_chain": filter_chain,
        }
        
        if self.config.strategy == CrawlStrategy.BFS:
            return BFSDeepCrawlStrategy(
                **common_params,
                score_threshold=self.config.score_threshold,
                url_scorer=scorer,
            )
        elif self.config.strategy == CrawlStrategy.DFS:
            return DFSDeepCrawlStrategy(
                **common_params,
                score_threshold=self.config.score_threshold,
                url_scorer=scorer,
            )
        elif self.config.strategy == CrawlStrategy.BEST_FIRST:
            return BestFirstCrawlingStrategy(
                **common_params,
                url_scorer=scorer,
            )
        else:
            # Default to BestFirst for news crawling
            return BestFirstCrawlingStrategy(
                **common_params,
                url_scorer=scorer,
            )
            
    def _build_run_config(
        self,
        deep_crawl_strategy,
        stream: bool = True,
    ) -> CrawlerRunConfig:
        """Build crawler run configuration"""
        config_params = {
            "deep_crawl_strategy": deep_crawl_strategy,
            "scraping_strategy": LXMLWebScrapingStrategy(),
            "stream": stream,
            "verbose": False,
            "only_text": self.config.only_text,
            "word_count_threshold": self.config.word_count_threshold,
            "cache_mode": CacheMode.ENABLED if self.config.enable_cache else CacheMode.BYPASS,
        }
        
        # Add proxy rotation if configured
        if self._proxy_strategy:
            config_params["proxy_rotation_strategy"] = self._proxy_strategy
            
        return CrawlerRunConfig(**config_params)
    
    async def __aenter__(self):
        """Async context manager entry"""
        self._crawler = AsyncWebCrawler(config=self._browser_config)
        await self._crawler.__aenter__()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self._crawler:
            await self._crawler.__aexit__(exc_type, exc_val, exc_tb)
            
    async def _apply_politeness_delay(self):
        """Apply random delay for politeness"""
        delay = random.uniform(
            self.config.request_delay_min,
            self.config.request_delay_max
        )
        await asyncio.sleep(delay)
        
    def _process_result(self, result) -> CrawlResult:
        """Convert Crawl4AI result to standardized format"""
        try:
            # Extract domain from URL
            from urllib.parse import urlparse
            parsed = urlparse(result.url)
            domain = parsed.netloc
            
            return CrawlResult(
                url=result.url,
                title=result.metadata.get("title", ""),
                content=result.markdown.raw_markdown if hasattr(result.markdown, 'raw_markdown') else str(result.markdown),
                markdown=result.markdown.raw_markdown if hasattr(result.markdown, 'raw_markdown') else str(result.markdown),
                metadata=result.metadata,
                depth=result.metadata.get("depth", 0),
                score=result.metadata.get("score", 0.0),
                crawled_at=datetime.now(),
                success=result.success,
                error=result.error_message if hasattr(result, 'error_message') else None,
                source_domain=domain,
            )
        except Exception as e:
            logger.error(f"Error processing result: {e}")
            return CrawlResult(
                url=result.url if hasattr(result, 'url') else "unknown",
                title="",
                content="",
                markdown="",
                metadata={},
                depth=0,
                score=0.0,
                crawled_at=datetime.now(),
                success=False,
                error=str(e),
            )
            
    async def crawl_deep(
        self,
        start_url: str,
        keywords: Optional[List[str]] = None,
        include_patterns: Optional[List[str]] = None,
        relevance_query: Optional[str] = None,
        stream: bool = True,
    ) -> AsyncIterator[CrawlResult]:
        """
        Perform deep crawl from a starting URL
        
        Args:
            start_url: URL to start crawling from
            keywords: Keywords for relevance scoring
            include_patterns: URL patterns to include
            relevance_query: Query for content relevance filtering
            stream: Whether to stream results
            
        Yields:
            CrawlResult objects as they are discovered
        """
        if not self._crawler:
            raise RuntimeError("Crawler not initialized. Use 'async with' context manager.")
            
        logger.info(f"Starting deep crawl from: {start_url}")
        
        # Build components
        filter_chain = self._build_filter_chain(
            include_patterns=include_patterns,
            relevance_query=relevance_query,
        )
        scorer = self._build_scorer(keywords)
        strategy = self._get_crawl_strategy(filter_chain, scorer)
        run_config = self._build_run_config(strategy, stream=stream)
        
        try:
            if stream:
                # Streaming mode - yield results as they come
                async for result in await self._crawler.arun(start_url, config=run_config):
                    await self._apply_politeness_delay()
                    yield self._process_result(result)
            else:
                # Batch mode - get all results then yield
                results = await self._crawler.arun(start_url, config=run_config)
                for result in results:
                    yield self._process_result(result)
                    
        except Exception as e:
            logger.error(f"Crawl error: {e}")
            yield CrawlResult(
                url=start_url,
                title="",
                content="",
                markdown="",
                metadata={"error": str(e)},
                depth=0,
                score=0.0,
                crawled_at=datetime.now(),
                success=False,
                error=str(e),
            )
            
    async def crawl_urls(
        self,
        urls: List[str],
        stream: bool = True,
    ) -> AsyncIterator[CrawlResult]:
        """
        Crawl a list of specific URLs
        
        Args:
            urls: List of URLs to crawl
            stream: Whether to stream results
            
        Yields:
            CrawlResult objects
        """
        if not self._crawler:
            raise RuntimeError("Crawler not initialized. Use 'async with' context manager.")
            
        logger.info(f"Crawling {len(urls)} URLs")
        
        run_config = CrawlerRunConfig(
            scraping_strategy=LXMLWebScrapingStrategy(),
            stream=stream,
            verbose=False,
            only_text=self.config.only_text,
            word_count_threshold=self.config.word_count_threshold,
            cache_mode=CacheMode.ENABLED if self.config.enable_cache else CacheMode.BYPASS,
        )
        
        if self._proxy_strategy:
            run_config.proxy_rotation_strategy = self._proxy_strategy
            
        try:
            if stream:
                async for result in await self._crawler.arun_many(urls, config=run_config):
                    await self._apply_politeness_delay()
                    yield self._process_result(result)
            else:
                results = await self._crawler.arun_many(urls, config=run_config)
                for result in results:
                    yield self._process_result(result)
                    
        except Exception as e:
            logger.error(f"Batch crawl error: {e}")

    async def crawl_single(self, url: str) -> CrawlResult:
        """
        Crawl a single URL
        
        Args:
            url: URL to crawl
            
        Returns:
            CrawlResult object
        """
        if not self._crawler:
            raise RuntimeError("Crawler not initialized. Use 'async with' context manager.")
            
        run_config = CrawlerRunConfig(
            scraping_strategy=LXMLWebScrapingStrategy(),
            stream=False,
            verbose=False,
            only_text=self.config.only_text,
            word_count_threshold=self.config.word_count_threshold,
        )
        
        try:
            result = await self._crawler.arun(url, config=run_config)
            if isinstance(result, list):
                result = result[0] if result else None
            if result:
                return self._process_result(result)
            else:
                return CrawlResult(
                    url=url,
                    title="",
                    content="",
                    markdown="",
                    metadata={},
                    depth=0,
                    score=0.0,
                    crawled_at=datetime.now(),
                    success=False,
                    error="No result returned",
                )
        except Exception as e:
            logger.error(f"Single crawl error: {e}")
            return CrawlResult(
                url=url,
                title="",
                content="",
                markdown="",
                metadata={"error": str(e)},
                depth=0,
                score=0.0,
                crawled_at=datetime.now(),
                success=False,
                error=str(e),
            )


# Factory function for easy instantiation
def create_crawler(
    strategy: CrawlStrategy = CrawlStrategy.BEST_FIRST,
    max_pages: int = 500,
    max_depth: int = 3,
    headless: bool = True,
    proxies: Optional[List[str]] = None,
) -> CoreCrawlerEngine:
    """
    Factory function to create a crawler with common settings
    
    Args:
        strategy: Crawling strategy to use
        max_pages: Maximum pages to crawl
        max_depth: Maximum depth to crawl
        headless: Run browser in headless mode
        proxies: List of proxy strings
        
    Returns:
        Configured CoreCrawlerEngine instance
    """
    crawler_config = CrawlerConfig(
        strategy=strategy,
        max_pages=max_pages,
        max_depth=max_depth,
        headless=headless,
    )
    
    proxy_config = None
    if proxies:
        proxy_config = ProxyConfig(
            enabled=True,
            rotation_enabled=True,
            proxies=proxies,
        )
        
    return CoreCrawlerEngine(
        config=crawler_config,
        proxy_config=proxy_config,
    )
