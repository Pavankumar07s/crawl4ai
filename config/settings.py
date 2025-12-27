"""
Production Configuration Settings for India News Crawler
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum

class CrawlStrategy(Enum):
    """Crawling strategy options"""
    BFS = "bfs"
    DFS = "dfs"
    BEST_FIRST = "best_first"
    ADAPTIVE = "adaptive"

class Language(Enum):
    """Supported Indian languages"""
    ENGLISH = "en"
    HINDI = "hi"
    MARATHI = "mr"
    BENGALI = "bn"
    TAMIL = "ta"
    TELUGU = "te"
    KANNADA = "kn"
    GUJARATI = "gu"
    PUNJABI = "pa"
    MALAYALAM = "ml"

@dataclass
class CrawlerConfig:
    """Core crawler configuration"""
    # Crawl limits
    max_depth: int = 3
    max_pages: int = 500
    confidence_threshold: float = 0.8
    score_threshold: float = 0.3
    min_gain_threshold: float = 0.05
    top_k_links: int = 10
    
    # Timing & Rate limiting
    request_delay_min: float = 1.0
    request_delay_max: float = 3.0
    hits_per_second: int = 5
    concurrent_requests: int = 10
    
    # Browser settings
    headless: bool = True
    browser_type: str = "chromium"  # chromium, firefox, webkit
    text_mode: bool = True
    
    # Content settings
    word_count_threshold: int = 200
    only_text: bool = True
    
    # Cache settings
    enable_cache: bool = True
    cache_ttl_hours: int = 24
    
    # Strategy
    strategy: CrawlStrategy = CrawlStrategy.BEST_FIRST

@dataclass  
class AdaptiveConfig:
    """Adaptive crawling configuration"""
    confidence_threshold: float = 0.8
    max_pages: int = 30
    top_k_links: int = 5
    min_gain_threshold: float = 0.1
    strategy: str = "statistical"  # statistical or embedding
    save_state: bool = True
    state_path: str = "./crawl_state.json"

@dataclass
class URLSeedingConfig:
    """URL seeding configuration"""
    source: str = "sitemap+cc"  # sitemap, cc, sitemap+cc
    extract_head: bool = True
    live_check: bool = False
    max_urls: int = 1000
    concurrency: int = 20
    hits_per_sec: int = 10
    scoring_method: str = "bm25"
    score_threshold: float = 0.3
    filter_nonsense_urls: bool = True

@dataclass
class ProxyConfig:
    """Proxy configuration for rate limiting evasion"""
    enabled: bool = False
    rotation_enabled: bool = True
    proxies: List[str] = field(default_factory=list)
    # Format: "ip:port:user:pass" or "http://user:pass@ip:port"

@dataclass
class StorageConfig:
    """Storage configuration"""
    output_dir: str = "./output"
    output_format: str = "jsonl"  # json, jsonl, markdown
    database_path: str = "./data/crawler.db"
    enable_deduplication: bool = True

@dataclass
class MonitoringConfig:
    """Monitoring and alerting configuration"""
    enable_logging: bool = True
    log_level: str = "INFO"
    log_file: str = "./logs/crawler.log"
    enable_metrics: bool = True
    metrics_port: int = 9090

# =============================================================================
# INDIA NEWS SPECIFIC CONFIGURATION
# =============================================================================

# News queries for adaptive crawling
INDIA_NEWS_QUERIES = [
    "latest India news today",
    "India breaking news",
    "Indian politics news",
    "India economy business news",
    "India state government news",
    "India international relations news",
    "India technology startup news",
    "India sports cricket news",
    "India weather climate news",
    "India infrastructure development news",
]

# State-specific queries
INDIA_STATE_QUERIES = {
    "Maharashtra": ["Maharashtra news", "Mumbai news", "Pune news"],
    "Delhi": ["Delhi news", "New Delhi government news"],
    "Karnataka": ["Karnataka news", "Bangalore news", "Bengaluru tech news"],
    "Tamil Nadu": ["Tamil Nadu news", "Chennai news"],
    "West Bengal": ["West Bengal news", "Kolkata news"],
    "Gujarat": ["Gujarat news", "Ahmedabad news"],
    "Uttar Pradesh": ["UP news", "Lucknow news", "Uttar Pradesh news"],
    "Rajasthan": ["Rajasthan news", "Jaipur news"],
    "Kerala": ["Kerala news", "Kochi news", "Thiruvananthapuram news"],
    "Telangana": ["Telangana news", "Hyderabad news"],
}

# Seed URLs for news sources
SEED_URLS = {
    "news_aggregators": [
        "https://news.google.com/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRFZxYUdjU0FtVnVHZ0pKVGlnQVAB?hl=en-IN&gl=IN",
        "https://www.google.com/search?q=india+news&tbm=nws",
    ],
    "national_news": [
        "https://timesofindia.indiatimes.com/",
        "https://www.hindustantimes.com/",
        "https://indianexpress.com/",
        "https://www.ndtv.com/",
        "https://www.thehindu.com/",
        "https://www.livemint.com/",
        "https://economictimes.indiatimes.com/",
        "https://www.business-standard.com/",
        "https://www.moneycontrol.com/news/",
        "https://www.firstpost.com/",
        "https://www.news18.com/",
        "https://www.republicworld.com/",
        "https://www.indiatoday.in/",
        "https://scroll.in/",
        "https://thewire.in/",
    ],
    "regional_hindi": [
        "https://www.bhaskar.com/",
        "https://www.jagran.com/",
        "https://www.amarujala.com/",
        "https://navbharattimes.indiatimes.com/",
        "https://www.livehindustan.com/",
    ],
    "regional_marathi": [
        "https://www.loksatta.com/",
        "https://www.esakal.com/",
        "https://maharashtratimes.com/",
    ],
    "regional_bengali": [
        "https://www.anandabazar.com/",
        "https://eisamay.com/",
    ],
    "regional_tamil": [
        "https://www.dinamalar.com/",
        "https://www.dinamani.com/",
    ],
    "tech_news": [
        "https://techcrunch.com/tag/india/",
        "https://yourstory.com/",
        "https://inc42.com/",
        "https://entrackr.com/",
    ],
    "social_forums": [
        "https://www.reddit.com/r/india/",
        "https://www.reddit.com/r/IndiaSpeaks/",
        "https://www.reddit.com/r/IndianStockMarket/",
    ],
}

# URL patterns to include/exclude
URL_PATTERNS = {
    "include": [
        "*news*",
        "*article*",
        "*story*",
        "*latest*",
        "*breaking*",
        "*india*",
        "*politics*",
        "*economy*",
        "*business*",
        "*tech*",
        "*sports*",
    ],
    "exclude": [
        "*login*",
        "*signin*",
        "*signup*",
        "*register*",
        "*cart*",
        "*checkout*",
        "*advertisement*",
        "*ad/*",
        "*ads/*",
        "*sponsor*",
        "*subscription*",
        "*premium*",
        "*video*",
        "*gallery*",
        "*photos*",
        "*quiz*",
        "*poll*",
        "*horoscope*",
        "*astrology*",
        "*games*",
    ],
}

# Keywords for relevance scoring
RELEVANCE_KEYWORDS = [
    "india", "indian", "delhi", "mumbai", "bangalore", "chennai", "kolkata",
    "government", "minister", "parliament", "lok sabha", "rajya sabha",
    "modi", "congress", "bjp", "aap", "election", "vote",
    "economy", "gdp", "rupee", "rbi", "stock", "sensex", "nifty",
    "startup", "tech", "it", "software", "digital",
    "cricket", "sports", "olympics",
    "supreme court", "high court", "law", "legislation",
    "development", "infrastructure", "railway", "metro", "highway",
    "education", "university", "iit", "iim",
    "health", "covid", "vaccine", "hospital",
    "weather", "monsoon", "flood", "drought", "climate",
]

# Content type mappings
CONTENT_TYPES = {
    "news_article": ["article", "news", "story", "report"],
    "opinion": ["opinion", "editorial", "column", "analysis"],
    "press_release": ["press release", "pr", "announcement"],
    "interview": ["interview", "qa", "conversation"],
    "report": ["report", "study", "research", "survey"],
}

@dataclass
class IndiaNewsCrawlerConfig:
    """Complete configuration for India News Crawler"""
    crawler: CrawlerConfig = field(default_factory=CrawlerConfig)
    adaptive: AdaptiveConfig = field(default_factory=AdaptiveConfig)
    seeding: URLSeedingConfig = field(default_factory=URLSeedingConfig)
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    
    # India-specific settings
    languages: List[Language] = field(default_factory=lambda: [Language.ENGLISH, Language.HINDI])
    queries: List[str] = field(default_factory=lambda: INDIA_NEWS_QUERIES)
    seed_urls: Dict[str, List[str]] = field(default_factory=lambda: SEED_URLS)
    url_patterns: Dict[str, List[str]] = field(default_factory=lambda: URL_PATTERNS)
    relevance_keywords: List[str] = field(default_factory=lambda: RELEVANCE_KEYWORDS)

def get_default_config() -> IndiaNewsCrawlerConfig:
    """Get default production configuration"""
    return IndiaNewsCrawlerConfig()

def get_development_config() -> IndiaNewsCrawlerConfig:
    """Get development/testing configuration"""
    config = IndiaNewsCrawlerConfig()
    config.crawler.max_pages = 50
    config.crawler.max_depth = 2
    config.crawler.headless = False
    config.adaptive.max_pages = 10
    config.seeding.max_urls = 100
    config.monitoring.log_level = "DEBUG"
    return config
