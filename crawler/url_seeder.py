"""
URL Seeding Module - Intelligent URL discovery for India News
"""
import asyncio
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import urlparse

from crawl4ai import AsyncUrlSeeder, SeedingConfig

import sys
sys.path.append('..')
from config.settings import (
    URLSeedingConfig,
    SEED_URLS,
    INDIA_NEWS_QUERIES,
    INDIA_STATE_QUERIES,
    RELEVANCE_KEYWORDS,
)

logger = logging.getLogger(__name__)

@dataclass
class DiscoveredURL:
    """Represents a discovered URL with metadata"""
    url: str
    status: str  # valid, not_valid, unknown
    relevance_score: float
    title: Optional[str] = None
    description: Optional[str] = None
    language: Optional[str] = None
    published_date: Optional[datetime] = None
    domain: Optional[str] = None
    head_data: Dict[str, Any] = field(default_factory=dict)
    discovered_at: datetime = field(default_factory=datetime.now)

class URLSeeder:
    """
    Intelligent URL discovery and seeding for news crawling
    
    Features:
    - Sitemap-based discovery
    - Common Crawl index discovery
    - BM25 relevance scoring
    - Metadata extraction
    - Multi-domain support
    - Smart filtering
    """
    
    def __init__(self, config: Optional[URLSeedingConfig] = None):
        self.config = config or URLSeedingConfig()
        self._seeder: Optional[AsyncUrlSeeder] = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        self._seeder = AsyncUrlSeeder()
        await self._seeder.__aenter__()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self._seeder:
            await self._seeder.__aexit__(exc_type, exc_val, exc_tb)
            
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL"""
        try:
            parsed = urlparse(url)
            return parsed.netloc
        except:
            return ""
            
    def _process_url_data(self, url_data: Dict[str, Any], query: Optional[str] = None) -> DiscoveredURL:
        """Process raw URL data into DiscoveredURL"""
        head_data = url_data.get("head_data", {}) or {}
        meta = head_data.get("meta", {}) or {}
        
        # Extract publication date from various sources
        published_date = None
        for jsonld in head_data.get("jsonld", []) or []:
            if isinstance(jsonld, dict) and "datePublished" in jsonld:
                try:
                    date_str = jsonld["datePublished"]
                    published_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except:
                    pass
                break
                
        # Detect language from metadata
        language = head_data.get("lang") or meta.get("og:locale", "").split("_")[0] or None
        
        return DiscoveredURL(
            url=url_data.get("url", ""),
            status=url_data.get("status", "unknown"),
            relevance_score=url_data.get("relevance_score", 0.0),
            title=head_data.get("title"),
            description=meta.get("description") or meta.get("og:description"),
            language=language,
            published_date=published_date,
            domain=self._extract_domain(url_data.get("url", "")),
            head_data=head_data,
        )
        
    async def discover_from_domain(
        self,
        domain: str,
        query: Optional[str] = None,
        pattern: Optional[str] = None,
        max_urls: Optional[int] = None,
    ) -> List[DiscoveredURL]:
        """
        Discover URLs from a single domain
        
        Args:
            domain: Domain to discover URLs from (without protocol)
            query: Search query for relevance scoring
            pattern: URL pattern to filter (e.g., "*/news/*")
            max_urls: Maximum URLs to return
            
        Returns:
            List of DiscoveredURL objects sorted by relevance
        """
        if not self._seeder:
            raise RuntimeError("Seeder not initialized. Use 'async with' context manager.")
            
        # Clean domain
        domain = domain.replace("https://", "").replace("http://", "").rstrip("/")
        
        config = SeedingConfig(
            source=self.config.source,
            pattern=pattern or "*",
            extract_head=self.config.extract_head,
            live_check=self.config.live_check,
            max_urls=max_urls or self.config.max_urls,
            concurrency=self.config.concurrency,
            hits_per_sec=self.config.hits_per_sec,
            query=query,
            scoring_method=self.config.scoring_method if query else None,
            score_threshold=self.config.score_threshold if query else None,
            filter_nonsense_urls=self.config.filter_nonsense_urls,
        )
        
        logger.info(f"Discovering URLs from: {domain} (query: {query})")
        
        try:
            urls = await self._seeder.urls(domain, config)
            
            discovered = [self._process_url_data(u, query) for u in urls]
            
            # Filter out invalid URLs
            discovered = [u for u in discovered if u.url and u.status != "not_valid"]
            
            # Sort by relevance
            discovered.sort(key=lambda x: x.relevance_score, reverse=True)
            
            logger.info(f"Discovered {len(discovered)} URLs from {domain}")
            return discovered
            
        except Exception as e:
            logger.error(f"Error discovering URLs from {domain}: {e}")
            return []
            
    async def discover_from_domains(
        self,
        domains: List[str],
        query: Optional[str] = None,
        pattern: Optional[str] = None,
        max_urls_per_domain: Optional[int] = None,
    ) -> Dict[str, List[DiscoveredURL]]:
        """
        Discover URLs from multiple domains in parallel
        
        Args:
            domains: List of domains to discover from
            query: Search query for relevance scoring
            pattern: URL pattern to filter
            max_urls_per_domain: Max URLs per domain
            
        Returns:
            Dictionary mapping domain to list of DiscoveredURL
        """
        if not self._seeder:
            raise RuntimeError("Seeder not initialized. Use 'async with' context manager.")
            
        # Clean domains
        clean_domains = [
            d.replace("https://", "").replace("http://", "").rstrip("/")
            for d in domains
        ]
        
        config = SeedingConfig(
            source=self.config.source,
            pattern=pattern or "*",
            extract_head=self.config.extract_head,
            live_check=self.config.live_check,
            max_urls=max_urls_per_domain or self.config.max_urls,
            concurrency=self.config.concurrency,
            hits_per_sec=self.config.hits_per_sec,
            query=query,
            scoring_method=self.config.scoring_method if query else None,
            score_threshold=self.config.score_threshold if query else None,
            filter_nonsense_urls=self.config.filter_nonsense_urls,
        )
        
        logger.info(f"Discovering URLs from {len(clean_domains)} domains")
        
        try:
            results = await self._seeder.many_urls(clean_domains, config)
            
            processed_results = {}
            for domain, urls in results.items():
                discovered = [self._process_url_data(u, query) for u in urls]
                discovered = [u for u in discovered if u.url and u.status != "not_valid"]
                discovered.sort(key=lambda x: x.relevance_score, reverse=True)
                processed_results[domain] = discovered
                
            total = sum(len(v) for v in processed_results.values())
            logger.info(f"Discovered {total} URLs across {len(clean_domains)} domains")
            return processed_results
            
        except Exception as e:
            logger.error(f"Error discovering URLs from multiple domains: {e}")
            return {}
            
    async def discover_india_news(
        self,
        queries: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        max_urls_per_source: int = 50,
        recent_only: bool = True,
        recent_days: int = 7,
    ) -> List[DiscoveredURL]:
        """
        Discover India news URLs using predefined seed URLs and queries
        
        Args:
            queries: Custom queries (uses defaults if None)
            categories: Source categories to use (e.g., ["national_news", "tech_news"])
            max_urls_per_source: Max URLs per source
            recent_only: Filter for recent articles only
            recent_days: Number of days to consider as recent
            
        Returns:
            List of DiscoveredURL sorted by relevance
        """
        queries = queries or INDIA_NEWS_QUERIES[:3]  # Use top 3 queries
        categories = categories or ["national_news", "regional_hindi"]
        
        # Collect domains from specified categories
        domains = []
        for category in categories:
            if category in SEED_URLS:
                for url in SEED_URLS[category]:
                    domain = self._extract_domain(url)
                    if domain:
                        domains.append(domain)
                        
        domains = list(set(domains))  # Remove duplicates
        
        all_urls = []
        
        for query in queries:
            logger.info(f"Discovering URLs for query: {query}")
            results = await self.discover_from_domains(
                domains=domains,
                query=query,
                pattern="*news*",
                max_urls_per_domain=max_urls_per_source // len(queries),
            )
            
            for domain_urls in results.values():
                all_urls.extend(domain_urls)
                
        # Remove duplicates based on URL
        seen_urls = set()
        unique_urls = []
        for url in all_urls:
            if url.url not in seen_urls:
                seen_urls.add(url.url)
                unique_urls.append(url)
                
        # Filter for recent articles if requested
        if recent_only:
            cutoff = datetime.now() - timedelta(days=recent_days)
            unique_urls = [
                u for u in unique_urls
                if u.published_date is None or u.published_date > cutoff
            ]
            
        # Sort by relevance
        unique_urls.sort(key=lambda x: x.relevance_score, reverse=True)
        
        logger.info(f"Total unique India news URLs discovered: {len(unique_urls)}")
        return unique_urls
        
    async def discover_state_news(
        self,
        states: Optional[List[str]] = None,
        max_urls_per_state: int = 30,
    ) -> Dict[str, List[DiscoveredURL]]:
        """
        Discover news URLs for specific Indian states
        
        Args:
            states: List of state names (uses all if None)
            max_urls_per_state: Max URLs per state
            
        Returns:
            Dictionary mapping state to list of DiscoveredURL
        """
        states = states or list(INDIA_STATE_QUERIES.keys())
        
        # Get news domains
        domains = []
        for category in ["national_news", "regional_hindi", "regional_marathi"]:
            if category in SEED_URLS:
                for url in SEED_URLS[category]:
                    domain = self._extract_domain(url)
                    if domain:
                        domains.append(domain)
        domains = list(set(domains))
        
        state_results = {}
        
        for state in states:
            queries = INDIA_STATE_QUERIES.get(state, [f"{state} news"])
            
            state_urls = []
            for query in queries[:2]:  # Use first 2 queries per state
                results = await self.discover_from_domains(
                    domains=domains,
                    query=query,
                    max_urls_per_domain=max_urls_per_state // (len(queries) * len(domains)),
                )
                
                for domain_urls in results.values():
                    state_urls.extend(domain_urls)
                    
            # Deduplicate
            seen = set()
            unique = []
            for url in state_urls:
                if url.url not in seen:
                    seen.add(url.url)
                    unique.append(url)
                    
            unique.sort(key=lambda x: x.relevance_score, reverse=True)
            state_results[state] = unique[:max_urls_per_state]
            
            logger.info(f"Discovered {len(state_results[state])} URLs for {state}")
            
        return state_results


class SmartURLPrioritizer:
    """
    Intelligent URL prioritization for optimal crawling order
    """
    
    def __init__(self, keywords: Optional[List[str]] = None):
        self.keywords = keywords or RELEVANCE_KEYWORDS
        
    def calculate_priority(self, url: DiscoveredURL) -> float:
        """Calculate priority score for a URL"""
        score = url.relevance_score
        
        # Boost for recent content
        if url.published_date:
            days_old = (datetime.now() - url.published_date).days
            if days_old < 1:
                score *= 1.5
            elif days_old < 3:
                score *= 1.3
            elif days_old < 7:
                score *= 1.1
                
        # Boost for keyword matches in title
        if url.title:
            title_lower = url.title.lower()
            keyword_matches = sum(1 for k in self.keywords if k.lower() in title_lower)
            score *= (1 + keyword_matches * 0.1)
            
        # Penalize very old content
        if url.published_date:
            days_old = (datetime.now() - url.published_date).days
            if days_old > 30:
                score *= 0.5
                
        return score
        
    def prioritize(self, urls: List[DiscoveredURL]) -> List[DiscoveredURL]:
        """Sort URLs by calculated priority"""
        for url in urls:
            url.relevance_score = self.calculate_priority(url)
        return sorted(urls, key=lambda x: x.relevance_score, reverse=True)


# Convenience function
async def seed_india_news_urls(
    max_urls: int = 100,
    categories: Optional[List[str]] = None,
) -> List[DiscoveredURL]:
    """
    Quick function to discover India news URLs
    
    Args:
        max_urls: Maximum total URLs to return
        categories: Source categories
        
    Returns:
        List of prioritized DiscoveredURL
    """
    async with URLSeeder() as seeder:
        urls = await seeder.discover_india_news(
            categories=categories,
            max_urls_per_source=max_urls // 5,
        )
        
    prioritizer = SmartURLPrioritizer()
    return prioritizer.prioritize(urls)[:max_urls]
