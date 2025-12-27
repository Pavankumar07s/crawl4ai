"""
URL Seeding Module - Intelligent URL discovery for India News
Uses sitemap parsing, Direct RSS feeds, and optional Crawl4AI AsyncUrlSeeder
"""
import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs, unquote
import warnings
import base64

# Suppress the GeneratorExit warnings from pyee
warnings.filterwarnings("ignore", message="coroutine.*ignored GeneratorExit")

import aiohttp

import sys
sys.path.append('..')
from config.settings import (
    URLSeedingConfig,
    SEED_URLS,
    INDIA_NEWS_QUERIES,
    INDIA_STATE_QUERIES,
    RELEVANCE_KEYWORDS,
    NEWS_RSS_FEEDS,
)

# Import Google News RSS feeds
try:
    from config.settings import GOOGLE_NEWS_RSS_FEEDS
except ImportError:
    GOOGLE_NEWS_RSS_FEEDS = []

logger = logging.getLogger(__name__)

# Try to import AsyncUrlSeeder, but have a fallback to our own implementation
HAS_URL_SEEDER = False
AsyncUrlSeeder = None
SeedingConfig = None

# Disable AsyncUrlSeeder by default due to cleanup issues
# Set USE_ASYNC_URL_SEEDER=True in environment to enable it
import os
if os.environ.get("USE_ASYNC_URL_SEEDER", "").lower() == "true":
    try:
        from crawl4ai import AsyncUrlSeeder as _AsyncUrlSeeder, SeedingConfig as _SeedingConfig
        AsyncUrlSeeder = _AsyncUrlSeeder
        SeedingConfig = _SeedingConfig
        HAS_URL_SEEDER = True
        logger.info("AsyncUrlSeeder enabled via environment variable")
    except ImportError:
        pass

if not HAS_URL_SEEDER:
    logger.info("Using built-in sitemap-based URL discovery (stable)")

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
        self._seeder = None
        self._use_fallback = not HAS_URL_SEEDER
        
    async def __aenter__(self):
        """Async context manager entry"""
        if HAS_URL_SEEDER and not self._use_fallback:
            try:
                self._seeder = AsyncUrlSeeder()
                await self._seeder.__aenter__()
            except Exception as e:
                logger.warning(f"Failed to initialize AsyncUrlSeeder: {e}, using fallback")
                self._use_fallback = True
                self._seeder = None
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with proper cleanup"""
        if self._seeder:
            try:
                # Give pending tasks a moment to complete
                await asyncio.sleep(0.1)
                await self._seeder.__aexit__(exc_type, exc_val, exc_tb)
            except Exception as e:
                logger.debug(f"Cleanup warning (can be ignored): {e}")
            finally:
                self._seeder = None
            
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
    
    # =========================================================================
    # Fallback Sitemap-based URL Discovery (stable, no cleanup issues)
    # =========================================================================
    
    async def _fetch_sitemap(self, url: str, timeout: int = 30) -> Optional[str]:
        """Fetch sitemap XML content"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"User-Agent": "Mozilla/5.0 (compatible; NewsCrawler/1.0)"}
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status == 200:
                        return await resp.text()
        except Exception as e:
            logger.debug(f"Failed to fetch sitemap {url}: {e}")
        return None
    
    def _parse_sitemap_urls(self, xml_content: str, max_urls: int = 1000) -> List[Dict[str, Any]]:
        """Parse URLs from sitemap XML"""
        urls = []
        try:
            # Remove namespaces for easier parsing
            xml_content = re.sub(r'\sxmlns[^"]*"[^"]*"', '', xml_content)
            root = ET.fromstring(xml_content)
            
            # Handle sitemap index (contains links to other sitemaps)
            for sitemap in root.findall('.//sitemap'):
                loc = sitemap.find('loc')
                if loc is not None and loc.text:
                    urls.append({
                        "url": loc.text.strip(),
                        "type": "sitemap_index",
                        "lastmod": sitemap.find('lastmod').text if sitemap.find('lastmod') is not None else None
                    })
            
            # Handle regular sitemap (contains actual page URLs)
            for url_elem in root.findall('.//url'):
                loc = url_elem.find('loc')
                if loc is not None and loc.text:
                    lastmod = url_elem.find('lastmod')
                    urls.append({
                        "url": loc.text.strip(),
                        "type": "page",
                        "lastmod": lastmod.text if lastmod is not None else None
                    })
                    
                    if len(urls) >= max_urls:
                        break
                        
        except ET.ParseError as e:
            logger.debug(f"Failed to parse sitemap XML: {e}")
        
        return urls
    
    def _calculate_relevance_score(self, url: str, query: Optional[str] = None) -> float:
        """Calculate relevance score based on URL and query"""
        score = 0.0
        url_lower = url.lower()
        
        # Check for news-related patterns in URL
        news_patterns = ['/news/', '/article/', '/story/', '/post/', '/india/', '/world/', '/politics/', '/business/', '/tech/']
        for pattern in news_patterns:
            if pattern in url_lower:
                score += 0.2
                
        # Check for date patterns (likely news)
        date_pattern = r'/\d{4}/\d{2}/\d{2}/'
        if re.search(date_pattern, url):
            score += 0.3
            
        # Check query keywords in URL
        if query:
            query_words = query.lower().split()
            for word in query_words:
                if len(word) > 3 and word in url_lower:
                    score += 0.2
                    
        # Check relevance keywords from config
        for keyword in RELEVANCE_KEYWORDS:
            if keyword.lower() in url_lower:
                score += 0.1
                
        return min(score, 1.0)  # Cap at 1.0
    
    # =========================================================================
    # Direct News RSS Feed Discovery (Most Reliable Method)
    # =========================================================================
    
    async def _fetch_direct_rss(self, rss_url: str, max_items: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch and parse a direct news website RSS feed.
        Returns list of article data with direct URLs (no redirect needed).
        """
        articles = []
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/rss+xml, application/xml, text/xml, */*",
                }
                async with session.get(
                    rss_url, 
                    headers=headers, 
                    timeout=aiohttp.ClientTimeout(total=15),
                    allow_redirects=True
                ) as resp:
                    if resp.status != 200:
                        logger.debug(f"Failed to fetch RSS {rss_url}: status {resp.status}")
                        return []
                    content = await resp.text()
            
            # Parse RSS/Atom XML
            root = ET.fromstring(content)
            
            # Handle both RSS 2.0 and Atom formats
            items = root.findall('.//item')  # RSS 2.0
            if not items:
                # Try Atom format
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                items = root.findall('.//atom:entry', ns)
            
            for item in items[:max_items]:
                try:
                    # RSS 2.0 format
                    title_elem = item.find('title')
                    link_elem = item.find('link')
                    pub_date_elem = item.find('pubDate')
                    description_elem = item.find('description')
                    
                    # Atom format fallback
                    if link_elem is None or not link_elem.text:
                        ns = {'atom': 'http://www.w3.org/2005/Atom'}
                        link_elem = item.find('atom:link[@rel="alternate"]', ns)
                        if link_elem is not None:
                            link = link_elem.get('href')
                        else:
                            link_elem = item.find('link')
                            link = link_elem.get('href') if link_elem is not None else None
                    else:
                        link = link_elem.text.strip() if link_elem.text else None
                    
                    if not link:
                        continue
                    
                    # Skip non-article URLs
                    if any(skip in link.lower() for skip in ['/tag/', '/category/', '/author/', '/page/', '#']):
                        continue
                    
                    # Parse publication date
                    pub_date = None
                    if pub_date_elem is not None and pub_date_elem.text:
                        try:
                            from email.utils import parsedate_to_datetime
                            pub_date = parsedate_to_datetime(pub_date_elem.text)
                        except:
                            pass
                    
                    articles.append({
                        "url": link,
                        "title": title_elem.text.strip() if title_elem is not None and title_elem.text else None,
                        "description": description_elem.text.strip() if description_elem is not None and description_elem.text else None,
                        "published_date": pub_date,
                        "source_feed": rss_url,
                    })
                except Exception as e:
                    logger.debug(f"Failed to parse RSS item: {e}")
                    continue
                    
            if articles:
                logger.debug(f"Parsed {len(articles)} articles from {rss_url}")
            return articles
            
        except ET.ParseError as e:
            logger.debug(f"Failed to parse RSS XML from {rss_url}: {e}")
        except Exception as e:
            logger.debug(f"Failed to fetch RSS {rss_url}: {e}")
        return []
    
    async def discover_from_direct_rss(
        self,
        rss_feeds: Optional[List[str]] = None,
        max_urls: int = 100,
    ) -> List[DiscoveredURL]:
        """
        Discover news URLs from direct news website RSS feeds.
        This is the most reliable method as URLs are direct article links.
        
        Args:
            rss_feeds: List of RSS feed URLs (uses defaults if None)
            max_urls: Maximum URLs to return
            
        Returns:
            List of DiscoveredURL objects
        """
        discovered = []
        seen_urls = set()
        
        # Use provided feeds or default
        feeds = rss_feeds or NEWS_RSS_FEEDS
        
        logger.info(f"Fetching news from {len(feeds)} direct RSS feeds")
        
        # Fetch all RSS feeds concurrently
        semaphore = asyncio.Semaphore(10)
        
        async def fetch_with_limit(rss_url: str) -> List[Dict]:
            async with semaphore:
                return await self._fetch_direct_rss(rss_url, max_items=30)
        
        tasks = [fetch_with_limit(url) for url in feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_articles = []
        successful_feeds = 0
        for i, result in enumerate(results):
            if isinstance(result, list) and result:
                all_articles.extend(result)
                successful_feeds += 1
            elif isinstance(result, Exception):
                logger.debug(f"Feed {feeds[i]} failed: {result}")
        
        logger.info(f"Fetched {len(all_articles)} articles from {successful_feeds}/{len(feeds)} RSS feeds")
        
        # Process articles
        for article in all_articles:
            url = article["url"]
            
            # Skip duplicates
            if url in seen_urls:
                continue
            seen_urls.add(url)
            
            # Calculate relevance score
            score = self._calculate_relevance_score(url)
            
            # Boost score based on title keywords
            if article.get("title"):
                title_lower = article["title"].lower()
                india_keywords = ["india", "indian", "delhi", "mumbai", "bangalore", "modi", 
                                 "rupee", "sensex", "nifty", "cricket", "ipl"]
                for keyword in india_keywords:
                    if keyword in title_lower:
                        score += 0.15
                        break
            
            discovered.append(DiscoveredURL(
                url=url,
                status="valid",
                relevance_score=min(score, 1.0),
                title=article.get("title"),
                description=article.get("description"),
                published_date=article.get("published_date"),
                domain=self._extract_domain(url),
            ))
        
        # Sort by relevance and recency (handle timezone-aware vs naive datetimes)
        from datetime import timezone
        min_date = datetime.min.replace(tzinfo=timezone.utc)
        
        def get_sort_key(x):
            pub_date = x.published_date
            if pub_date is None:
                pub_date = min_date
            elif pub_date.tzinfo is None:
                pub_date = pub_date.replace(tzinfo=timezone.utc)
            return (x.relevance_score, pub_date)
        
        discovered.sort(key=get_sort_key, reverse=True)
        
        logger.info(f"Discovered {len(discovered)} unique URLs from direct RSS feeds")
        return discovered[:max_urls]
    
    # =========================================================================
    # Google News RSS Feed Discovery with Redirect Handling
    # =========================================================================
    
    async def _resolve_redirect(self, url: str, timeout: int = 15) -> Optional[str]:
        """
        Follow redirects to get the final URL.
        Google News URLs redirect to the actual article.
        """
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                # Allow redirects and get final URL
                async with session.get(
                    url, 
                    headers=headers, 
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    allow_redirects=True
                ) as resp:
                    return str(resp.url)
        except Exception as e:
            logger.debug(f"Failed to resolve redirect for {url}: {e}")
            return None
    
    def _decode_google_news_url(self, google_url: str) -> Optional[str]:
        """
        Decode Google News article URL to get the actual article URL.
        Google News uses encoded URLs in their links.
        """
        try:
            parsed = urlparse(google_url)
            
            # Handle news.google.com/articles format
            if "news.google.com" in parsed.netloc:
                # Try to extract from path
                if "/articles/" in parsed.path:
                    # The URL after /articles/ is base64 encoded
                    path_parts = parsed.path.split("/articles/")
                    if len(path_parts) > 1:
                        encoded = path_parts[1].split("?")[0]
                        # This is a Google-specific encoding, need to follow redirect
                        return google_url  # Will be resolved via redirect
                
                # Try query parameters
                query_params = parse_qs(parsed.query)
                if 'url' in query_params:
                    return unquote(query_params['url'][0])
            
            # Handle google.com/url redirect format
            if "google.com/url" in google_url:
                query_params = parse_qs(parsed.query)
                if 'url' in query_params:
                    return unquote(query_params['url'][0])
                if 'q' in query_params:
                    return unquote(query_params['q'][0])
            
            return google_url
        except Exception as e:
            logger.debug(f"Failed to decode Google URL {google_url}: {e}")
            return google_url
    
    async def _fetch_google_news_rss(self, rss_url: str, max_items: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch and parse Google News RSS feed.
        Returns list of article data with resolved URLs.
        """
        articles = []
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                async with session.get(
                    rss_url, 
                    headers=headers, 
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status != 200:
                        logger.debug(f"Failed to fetch RSS {rss_url}: status {resp.status}")
                        return []
                    content = await resp.text()
            
            # Parse RSS XML
            root = ET.fromstring(content)
            
            # Find all items
            items = root.findall('.//item')
            
            for item in items[:max_items]:
                try:
                    title_elem = item.find('title')
                    link_elem = item.find('link')
                    pub_date_elem = item.find('pubDate')
                    description_elem = item.find('description')
                    source_elem = item.find('source')
                    
                    if link_elem is None or not link_elem.text:
                        continue
                    
                    google_link = link_elem.text.strip()
                    
                    # Try to decode the Google News URL
                    decoded_url = self._decode_google_news_url(google_link)
                    
                    # Parse publication date
                    pub_date = None
                    if pub_date_elem is not None and pub_date_elem.text:
                        try:
                            # RSS date format: "Fri, 27 Dec 2024 10:30:00 GMT"
                            from email.utils import parsedate_to_datetime
                            pub_date = parsedate_to_datetime(pub_date_elem.text)
                        except:
                            pass
                    
                    articles.append({
                        "url": decoded_url or google_link,
                        "google_url": google_link,
                        "title": title_elem.text if title_elem is not None else None,
                        "description": description_elem.text if description_elem is not None else None,
                        "published_date": pub_date,
                        "source": source_elem.text if source_elem is not None else None,
                        "needs_redirect": "news.google.com" in google_link,
                    })
                except Exception as e:
                    logger.debug(f"Failed to parse RSS item: {e}")
                    continue
                    
            logger.info(f"Parsed {len(articles)} articles from Google News RSS")
            return articles
            
        except ET.ParseError as e:
            logger.debug(f"Failed to parse RSS XML: {e}")
        except Exception as e:
            logger.debug(f"Failed to fetch Google News RSS: {e}")
        return []
    
    async def discover_from_google_news(
        self,
        queries: Optional[List[str]] = None,
        max_urls: int = 100,
        resolve_redirects: bool = True,
    ) -> List[DiscoveredURL]:
        """
        Discover news URLs from Google News RSS feeds.
        
        Args:
            queries: Search queries for Google News (uses defaults if None)
            max_urls: Maximum URLs to return
            resolve_redirects: Whether to follow redirects to get actual URLs
            
        Returns:
            List of DiscoveredURL objects from Google News
        """
        discovered = []
        seen_urls = set()
        
        # Use provided queries or default RSS feeds
        rss_feeds = []
        if queries:
            for query in queries:
                # Convert query to Google News RSS URL
                query_encoded = query.replace(" ", "+")
                rss_url = f"https://news.google.com/rss/search?q={query_encoded}&hl=en-IN&gl=IN&ceid=IN:en"
                rss_feeds.append(rss_url)
        else:
            rss_feeds = GOOGLE_NEWS_RSS_FEEDS[:10]  # Use first 10 default feeds
        
        logger.info(f"Fetching news from {len(rss_feeds)} Google News RSS feeds")
        
        # Fetch all RSS feeds concurrently
        semaphore = asyncio.Semaphore(5)
        
        async def fetch_with_limit(rss_url: str) -> List[Dict]:
            async with semaphore:
                return await self._fetch_google_news_rss(rss_url, max_items=max_urls // len(rss_feeds) + 10)
        
        tasks = [fetch_with_limit(url) for url in rss_feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_articles = []
        for result in results:
            if isinstance(result, list):
                all_articles.extend(result)
        
        logger.info(f"Total articles from Google News: {len(all_articles)}")
        
        # Process articles and resolve redirects if needed
        redirect_semaphore = asyncio.Semaphore(10)
        
        async def process_article(article: Dict) -> Optional[DiscoveredURL]:
            url = article["url"]
            
            # Resolve redirect if needed
            if resolve_redirects and article.get("needs_redirect"):
                async with redirect_semaphore:
                    resolved = await self._resolve_redirect(article["google_url"])
                    if resolved and "news.google.com" not in resolved:
                        url = resolved
            
            # Skip duplicates
            if url in seen_urls:
                return None
            seen_urls.add(url)
            
            # Calculate relevance score
            score = self._calculate_relevance_score(url)
            
            # Boost score if title contains India-related keywords
            if article.get("title"):
                title_lower = article["title"].lower()
                for keyword in ["india", "indian", "delhi", "mumbai", "modi"]:
                    if keyword in title_lower:
                        score += 0.2
                        break
            
            return DiscoveredURL(
                url=url,
                status="valid",
                relevance_score=min(score, 1.0),
                title=article.get("title"),
                description=article.get("description"),
                published_date=article.get("published_date"),
                domain=self._extract_domain(url),
            )
        
        # Process articles concurrently
        process_tasks = [process_article(article) for article in all_articles]
        processed = await asyncio.gather(*process_tasks, return_exceptions=True)
        
        for result in processed:
            if isinstance(result, DiscoveredURL):
                discovered.append(result)
        
        # Sort by relevance and recency
        discovered.sort(key=lambda x: (x.relevance_score, x.published_date or datetime.min), reverse=True)
        
        logger.info(f"Discovered {len(discovered)} unique URLs from Google News")
        return discovered[:max_urls]
    
    # =========================================================================
    # Sitemap-based URL Discovery
    # =========================================================================
    
    async def _discover_from_sitemap_fallback(
        self, 
        domain: str, 
        query: Optional[str] = None,
        pattern: Optional[str] = None,
        max_urls: int = 100
    ) -> List[DiscoveredURL]:
        """Fallback URL discovery using sitemap parsing - optimized for speed"""
        discovered = []
        
        # Common sitemap locations - prioritize news sitemaps
        sitemap_paths = [
            f"https://{domain}/news-sitemap.xml",
            f"https://{domain}/post-sitemap.xml",
            f"https://{domain}/article-sitemap.xml",
            f"https://{domain}/sitemap.xml",
            f"https://{domain}/sitemap_index.xml",
        ]
        
        all_urls = []
        max_nested_sitemaps = 5  # Limit nested sitemap fetches for speed
        fetched_sitemaps = set()  # Track already fetched sitemaps
        
        async def fetch_and_parse_sitemap(url: str, depth: int = 0) -> List[Dict]:
            """Recursively fetch sitemaps up to depth 3"""
            if url in fetched_sitemaps or depth > 3 or len(all_urls) >= max_urls:
                return []
            fetched_sitemaps.add(url)
            
            content = await self._fetch_sitemap(url, timeout=10)
            if not content:
                return []
                
            entries = self._parse_sitemap_urls(content, max_urls * 3)
            if not entries:
                return []
                
            # Separate page URLs from sitemap indexes
            page_urls = [e for e in entries if e.get("type") == "page"]
            sitemap_indexes = [e for e in entries if e.get("type") == "sitemap_index"]
            
            if page_urls:
                logger.info(f"Found {len(page_urls)} page URLs in {url} (depth {depth})")
                return page_urls
            
            # If no page URLs, recursively fetch nested sitemaps
            if sitemap_indexes and depth < 3:
                # Prioritize news/article/post sitemaps and recent years
                def sitemap_priority(s):
                    url_lower = s["url"].lower()
                    if "news" in url_lower:
                        return 0
                    if "post" in url_lower or "article" in url_lower:
                        return 1
                    if "2025" in url_lower:  # Current year
                        return 2
                    if "2024" in url_lower:  # Last year
                        return 3
                    return 4
                
                sitemap_indexes.sort(key=sitemap_priority)
                
                # Try more nested sitemaps at deeper levels
                max_to_try = max_nested_sitemaps if depth == 0 else 3
                nested_results = []
                for idx, sitemap_data in enumerate(sitemap_indexes[:max_to_try]):
                    if len(all_urls) + len(nested_results) >= max_urls:
                        break
                    nested = await fetch_and_parse_sitemap(sitemap_data["url"], depth + 1)
                    nested_results.extend(nested)
                    if nested_results:  # Found some pages, can stop
                        break
                    
                return nested_results
            
            return []
        
        # Try each sitemap path
        for sitemap_url in sitemap_paths:
            if len(all_urls) >= max_urls:
                break
            
            urls = await fetch_and_parse_sitemap(sitemap_url)
            all_urls.extend(urls)
            
            if all_urls:
                logger.info(f"Found {len(all_urls)} page URLs from {domain}")
                break
        
        # Apply pattern filter if specified
        if pattern and pattern != "*":
            pattern_regex = pattern.replace("*", ".*")
            all_urls = [u for u in all_urls if re.search(pattern_regex, u["url"])]
        
        logger.debug(f"Before conversion: {len(all_urls)} URLs for {domain}")
        
        # Convert to DiscoveredURL objects with relevance scoring
        for url_data in all_urls[:max_urls]:
            url = url_data["url"]
            score = self._calculate_relevance_score(url, query)
            
            # Parse lastmod date if available
            published_date = None
            if url_data.get("lastmod"):
                try:
                    published_date = datetime.fromisoformat(url_data["lastmod"].replace("Z", "+00:00"))
                except:
                    pass
            
            discovered.append(DiscoveredURL(
                url=url,
                status="valid",
                relevance_score=score,
                domain=domain,
                published_date=published_date,
            ))
        
        # Sort by relevance
        discovered.sort(key=lambda x: x.relevance_score, reverse=True)
        
        logger.info(f"Discovered {len(discovered)} URLs from {domain} (sitemap fallback)")
        return discovered
        
    # =========================================================================
    # Main Discovery Methods
    # =========================================================================
        
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
        # Clean domain
        domain = domain.replace("https://", "").replace("http://", "").rstrip("/")
        effective_max = max_urls or self.config.max_urls
        
        # Use fallback sitemap parsing if AsyncUrlSeeder is not available
        if self._use_fallback or not self._seeder:
            return await self._discover_from_sitemap_fallback(
                domain=domain,
                query=query,
                pattern=pattern,
                max_urls=effective_max,
            )
        
        # Use AsyncUrlSeeder if available
        config = SeedingConfig(
            source=self.config.source,
            pattern=pattern or "*",
            extract_head=self.config.extract_head,
            live_check=self.config.live_check,
            max_urls=effective_max,
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
            logger.warning(f"AsyncUrlSeeder failed for {domain}: {e}, trying fallback")
            return await self._discover_from_sitemap_fallback(
                domain=domain,
                query=query,
                pattern=pattern,
                max_urls=effective_max,
            )
            
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
        # Clean domains
        clean_domains = [
            d.replace("https://", "").replace("http://", "").rstrip("/")
            for d in domains
        ]
        
        effective_max = max_urls_per_domain or self.config.max_urls
        
        # Use fallback sitemap parsing for each domain
        if self._use_fallback or not self._seeder:
            logger.info(f"Discovering URLs from {len(clean_domains)} domains (sitemap fallback)")
            processed_results = {}
            
            # Process domains concurrently with limited parallelism
            semaphore = asyncio.Semaphore(5)  # Limit concurrent requests
            
            async def discover_with_limit(domain: str) -> tuple:
                async with semaphore:
                    urls = await self._discover_from_sitemap_fallback(
                        domain=domain,
                        query=query,
                        pattern=pattern,
                        max_urls=effective_max,
                    )
                    return domain, urls
            
            tasks = [discover_with_limit(d) for d in clean_domains]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, tuple):
                    domain, urls = result
                    processed_results[domain] = urls
                    
            total = sum(len(v) for v in processed_results.values())
            logger.info(f"Discovered {total} URLs across {len(clean_domains)} domains")
            return processed_results
        
        # Use AsyncUrlSeeder if available
        config = SeedingConfig(
            source=self.config.source,
            pattern=pattern or "*",
            extract_head=self.config.extract_head,
            live_check=self.config.live_check,
            max_urls=effective_max,
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
            logger.warning(f"AsyncUrlSeeder failed: {e}, using fallback")
            # Fall back to sitemap parsing
            processed_results = {}
            for domain in clean_domains:
                urls = await self._discover_from_sitemap_fallback(
                    domain=domain,
                    query=query,
                    pattern=pattern,
                    max_urls=effective_max,
                )
                processed_results[domain] = urls
            return processed_results
            
    async def discover_india_news(
        self,
        queries: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        max_urls_per_source: int = 50,
        recent_only: bool = True,
        recent_days: int = 7,
        include_google_news: bool = True,
    ) -> List[DiscoveredURL]:
        """
        Discover India news URLs using Google News, predefined seed URLs, and sitemaps
        
        Args:
            queries: Custom queries (uses defaults if None)
            categories: Source categories to use (e.g., ["national_news", "tech_news"])
            max_urls_per_source: Max URLs per source
            recent_only: Filter for recent articles only
            recent_days: Number of days to consider as recent
            include_google_news: Whether to include Google News RSS feeds
            
        Returns:
            List of DiscoveredURL sorted by relevance
        """
        queries = queries or INDIA_NEWS_QUERIES[:5]  # Use top 5 queries
        categories = categories or ["national_news", "tech_news"]
        
        all_urls = []
        
        # 1. First, get news from Google News (highest priority - most current)
        if include_google_news:
            logger.info("Fetching latest news from Google News RSS feeds...")
            google_news_queries = [
                "India news",
                "India breaking news",
                "India politics",
                "India economy",
                "India cricket",
            ]
            google_urls = await self.discover_from_google_news(
                queries=google_news_queries,
                max_urls=max_urls_per_source * 2,  # Get more from Google News
                resolve_redirects=True,
            )
            all_urls.extend(google_urls)
            logger.info(f"Got {len(google_urls)} URLs from Google News")
        
        # 2. Then, discover from sitemap sources
        domains = []
        for category in categories:
            if category in SEED_URLS:
                for url in SEED_URLS[category]:
                    domain = self._extract_domain(url)
                    if domain:
                        domains.append(domain)
                        
        domains = list(set(domains))  # Remove duplicates
        
        for query in queries:
            logger.info(f"Discovering URLs for query: {query}")
            results = await self.discover_from_domains(
                domains=domains,
                query=query,
                pattern=None,  # Don't filter by URL pattern - rely on relevance scoring
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
            from datetime import timezone
            cutoff = datetime.now(timezone.utc) - timedelta(days=recent_days)
            filtered_urls = []
            for u in unique_urls:
                if u.published_date is None:
                    filtered_urls.append(u)  # Keep URLs without date info
                else:
                    # Make published_date timezone-aware if it isn't
                    pub_date = u.published_date
                    if pub_date.tzinfo is None:
                        pub_date = pub_date.replace(tzinfo=timezone.utc)
                    if pub_date > cutoff:
                        filtered_urls.append(u)
            unique_urls = filtered_urls
            
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
    include_google_news: bool = True,
) -> List[DiscoveredURL]:
    """
    Quick function to discover India news URLs
    
    Args:
        max_urls: Maximum total URLs to return
        categories: Source categories
        include_google_news: Whether to include Google News
        
    Returns:
        List of prioritized DiscoveredURL
    """
    async with URLSeeder() as seeder:
        urls = await seeder.discover_india_news(
            categories=categories,
            max_urls_per_source=max_urls // 5,
            include_google_news=include_google_news,
        )
        
    prioritizer = SmartURLPrioritizer()
    return prioritizer.prioritize(urls)[:max_urls]


async def seed_google_news_urls(
    queries: Optional[List[str]] = None,
    max_urls: int = 100,
) -> List[DiscoveredURL]:
    """
    Quick function to discover India news from Google News RSS
    
    Args:
        queries: Search queries for Google News
        max_urls: Maximum URLs to return
        
    Returns:
        List of DiscoveredURL from Google News
    """
    async with URLSeeder() as seeder:
        urls = await seeder.discover_from_google_news(
            queries=queries or ["India news", "India breaking news", "India politics"],
            max_urls=max_urls,
            resolve_redirects=True,
        )
    
    prioritizer = SmartURLPrioritizer()
    return prioritizer.prioritize(urls)[:max_urls]
