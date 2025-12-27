"""
Adaptive Crawler - Intelligent crawling with automatic stopping
"""
import asyncio
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

from crawl4ai import AsyncWebCrawler, AdaptiveCrawler as Crawl4AIAdaptiveCrawler
from crawl4ai import AdaptiveConfig as Crawl4AIAdaptiveConfig
from crawl4ai import BrowserConfig

import sys
sys.path.append('..')
from config.settings import (
    AdaptiveConfig,
    CrawlerConfig,
    INDIA_NEWS_QUERIES,
    RELEVANCE_KEYWORDS,
)
from .core_engine import CrawlResult

logger = logging.getLogger(__name__)

@dataclass
class AdaptiveCrawlMetrics:
    """Metrics from adaptive crawl"""
    pages_crawled: int = 0
    confidence_score: float = 0.0
    coverage_score: float = 0.0
    consistency_score: float = 0.0
    saturation_score: float = 0.0
    query: str = ""
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    stopped_reason: str = ""

@dataclass
class AdaptiveCrawlResult:
    """Complete result from adaptive crawl"""
    query: str
    start_url: str
    metrics: AdaptiveCrawlMetrics
    results: List[CrawlResult]
    relevant_content: List[Dict[str, Any]]
    
class AdaptiveNewsCrawler:
    """
    Adaptive crawler that knows when to stop
    
    Uses information foraging theory to determine when sufficient
    information has been gathered for a query.
    
    Features:
    - Automatic stopping based on information gain
    - Coverage, consistency, saturation metrics
    - Query-based relevance
    - State persistence and resumption
    - Knowledge base export
    """
    
    def __init__(
        self,
        config: Optional[AdaptiveConfig] = None,
        browser_headless: bool = True,
    ):
        self.config = config or AdaptiveConfig()
        self.browser_headless = browser_headless
        self._crawler: Optional[AsyncWebCrawler] = None
        self._adaptive: Optional[Crawl4AIAdaptiveCrawler] = None
        self._browser_config = BrowserConfig(
            headless=browser_headless,
            text_mode=True,
        )
        
    async def __aenter__(self):
        """Async context manager entry"""
        self._crawler = AsyncWebCrawler(config=self._browser_config)
        await self._crawler.__aenter__()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self._crawler:
            await self._crawler.__aexit__(exc_type, exc_val, exc_tb)
            
    def _build_adaptive_config(self) -> Crawl4AIAdaptiveConfig:
        """Build Crawl4AI adaptive configuration"""
        return Crawl4AIAdaptiveConfig(
            confidence_threshold=self.config.confidence_threshold,
            max_pages=self.config.max_pages,
            top_k_links=self.config.top_k_links,
            min_gain_threshold=self.config.min_gain_threshold,
            strategy=self.config.strategy,
            save_state=self.config.save_state,
            state_path=self.config.state_path,
        )
        
    def _process_result(self, result: Any) -> CrawlResult:
        """Convert Crawl4AI result to CrawlResult"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(result.url)
            domain = parsed.netloc
            
            content = ""
            if hasattr(result, 'markdown'):
                if hasattr(result.markdown, 'raw_markdown'):
                    content = result.markdown.raw_markdown
                else:
                    content = str(result.markdown)
                    
            return CrawlResult(
                url=result.url,
                title=result.metadata.get("title", "") if hasattr(result, 'metadata') else "",
                content=content,
                markdown=content,
                metadata=result.metadata if hasattr(result, 'metadata') else {},
                depth=result.metadata.get("depth", 0) if hasattr(result, 'metadata') else 0,
                score=result.metadata.get("score", 0.0) if hasattr(result, 'metadata') else 0.0,
                crawled_at=datetime.now(),
                success=result.success if hasattr(result, 'success') else True,
                source_domain=domain,
            )
        except Exception as e:
            logger.error(f"Error processing result: {e}")
            return CrawlResult(
                url=str(result.url) if hasattr(result, 'url') else "unknown",
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
            
    async def crawl(
        self,
        start_url: str,
        query: str,
        resume_from: Optional[str] = None,
    ) -> AdaptiveCrawlResult:
        """
        Perform adaptive crawl that stops when enough info is gathered
        
        Args:
            start_url: URL to start crawling from
            query: The information query to satisfy
            resume_from: Path to resume from saved state
            
        Returns:
            AdaptiveCrawlResult with metrics and content
        """
        if not self._crawler:
            raise RuntimeError("Crawler not initialized. Use 'async with' context manager.")
            
        logger.info(f"Starting adaptive crawl: {query}")
        logger.info(f"Start URL: {start_url}")
        
        metrics = AdaptiveCrawlMetrics(query=query)
        
        adaptive_config = self._build_adaptive_config()
        adaptive = Crawl4AIAdaptiveCrawler(self._crawler, adaptive_config)
        
        try:
            result = await adaptive.digest(
                start_url=start_url,
                query=query,
                resume_from=resume_from,
            )
            
            # Get statistics
            adaptive.print_stats()
            
            # Update metrics
            if hasattr(result, 'metrics'):
                metrics.confidence_score = result.metrics.get('confidence', 0.0)
                metrics.coverage_score = result.metrics.get('coverage', 0.0)
                metrics.consistency_score = result.metrics.get('consistency', 0.0)
                metrics.saturation_score = result.metrics.get('saturation', 0.0)
                metrics.pages_crawled = result.metrics.get('pages_crawled', 0)
                
            metrics.end_time = datetime.now()
            
            # Get relevant content
            relevant_content = adaptive.get_relevant_content(top_k=10)
            
            # Process results
            processed_results = []
            if hasattr(adaptive, '_pages'):
                for page in adaptive._pages.values():
                    processed_results.append(self._process_result(page))
                    
            return AdaptiveCrawlResult(
                query=query,
                start_url=start_url,
                metrics=metrics,
                results=processed_results,
                relevant_content=relevant_content,
            )
            
        except Exception as e:
            logger.error(f"Adaptive crawl error: {e}")
            metrics.end_time = datetime.now()
            metrics.stopped_reason = str(e)
            
            return AdaptiveCrawlResult(
                query=query,
                start_url=start_url,
                metrics=metrics,
                results=[],
                relevant_content=[],
            )
            
    async def crawl_multiple_queries(
        self,
        start_url: str,
        queries: List[str],
        export_path: Optional[str] = None,
    ) -> List[AdaptiveCrawlResult]:
        """
        Crawl for multiple queries, building a knowledge base
        
        Args:
            start_url: Starting URL
            queries: List of queries to satisfy
            export_path: Path to export combined knowledge base
            
        Returns:
            List of AdaptiveCrawlResult for each query
        """
        results = []
        
        for query in queries:
            logger.info(f"Processing query {len(results)+1}/{len(queries)}: {query}")
            result = await self.crawl(start_url, query)
            results.append(result)
            
            # Small delay between queries
            await asyncio.sleep(1)
            
        if export_path:
            # Export combined knowledge base
            await self._export_knowledge_base(results, export_path)
            
        return results
        
    async def crawl_india_news(
        self,
        start_urls: Optional[List[str]] = None,
        queries: Optional[List[str]] = None,
        max_queries: int = 5,
    ) -> List[AdaptiveCrawlResult]:
        """
        Specialized method for crawling India news
        
        Args:
            start_urls: Starting URLs (uses defaults if None)
            queries: News queries (uses defaults if None)
            max_queries: Maximum number of queries to process
            
        Returns:
            List of AdaptiveCrawlResult
        """
        from config.settings import SEED_URLS
        
        start_urls = start_urls or [
            SEED_URLS["national_news"][0],  # Times of India
            SEED_URLS["national_news"][3],  # NDTV
        ]
        
        queries = (queries or INDIA_NEWS_QUERIES)[:max_queries]
        
        all_results = []
        
        for url in start_urls:
            logger.info(f"Crawling from: {url}")
            results = await self.crawl_multiple_queries(url, queries)
            all_results.extend(results)
            
        return all_results
        
    async def _export_knowledge_base(
        self,
        results: List[AdaptiveCrawlResult],
        path: str,
    ):
        """Export results to knowledge base file"""
        import json
        
        knowledge = {
            "exported_at": datetime.now().isoformat(),
            "total_queries": len(results),
            "total_pages": sum(len(r.results) for r in results),
            "queries": [],
        }
        
        for result in results:
            query_data = {
                "query": result.query,
                "start_url": result.start_url,
                "metrics": {
                    "pages_crawled": result.metrics.pages_crawled,
                    "confidence": result.metrics.confidence_score,
                    "coverage": result.metrics.coverage_score,
                },
                "relevant_content": result.relevant_content[:5],  # Top 5
                "pages": [
                    {
                        "url": r.url,
                        "title": r.title,
                        "score": r.score,
                    }
                    for r in result.results[:10]  # Top 10 pages
                ],
            }
            knowledge["queries"].append(query_data)
            
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(knowledge, f, indent=2, ensure_ascii=False)
            
        logger.info(f"Knowledge base exported to: {path}")


class AdaptiveResearchCrawler:
    """
    Research-focused adaptive crawler for building comprehensive knowledge
    """
    
    def __init__(
        self,
        confidence_threshold: float = 0.8,
        max_pages_per_query: int = 30,
    ):
        self.config = AdaptiveConfig(
            confidence_threshold=confidence_threshold,
            max_pages=max_pages_per_query,
            save_state=True,
        )
        
    async def research_topic(
        self,
        topic: str,
        seed_urls: List[str],
        sub_queries: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Research a topic across multiple sources
        
        Args:
            topic: Main research topic
            seed_urls: Starting URLs for research
            sub_queries: Additional sub-queries to explore
            
        Returns:
            Research results with combined knowledge
        """
        # Generate sub-queries if not provided
        if not sub_queries:
            sub_queries = [
                f"{topic} latest news",
                f"{topic} updates",
                f"{topic} analysis",
                f"{topic} developments",
            ]
            
        async with AdaptiveNewsCrawler(self.config) as crawler:
            all_results = []
            
            for url in seed_urls:
                for query in sub_queries:
                    result = await crawler.crawl(url, query)
                    all_results.append(result)
                    
        # Aggregate findings
        return {
            "topic": topic,
            "sources_crawled": len(seed_urls),
            "queries_processed": len(sub_queries) * len(seed_urls),
            "total_pages": sum(len(r.results) for r in all_results),
            "average_confidence": sum(r.metrics.confidence_score for r in all_results) / len(all_results) if all_results else 0,
            "top_content": self._aggregate_top_content(all_results),
        }
        
    def _aggregate_top_content(
        self,
        results: List[AdaptiveCrawlResult],
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        """Aggregate and rank top content across all results"""
        all_content = []
        
        for result in results:
            for content in result.relevant_content:
                content["query"] = result.query
                all_content.append(content)
                
        # Sort by score and deduplicate
        all_content.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        seen_urls = set()
        unique_content = []
        for content in all_content:
            url = content.get("url", "")
            if url not in seen_urls:
                seen_urls.add(url)
                unique_content.append(content)
                
        return unique_content[:top_k]


# Convenience function
async def adaptive_crawl_india_news(
    query: str = "latest India news today",
    max_pages: int = 30,
    confidence: float = 0.8,
) -> AdaptiveCrawlResult:
    """
    Quick function for adaptive India news crawl
    
    Args:
        query: News query
        max_pages: Maximum pages to crawl
        confidence: Confidence threshold to stop
        
    Returns:
        AdaptiveCrawlResult
    """
    config = AdaptiveConfig(
        confidence_threshold=confidence,
        max_pages=max_pages,
    )
    
    async with AdaptiveNewsCrawler(config) as crawler:
        return await crawler.crawl(
            start_url="https://timesofindia.indiatimes.com/",
            query=query,
        )
