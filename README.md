# India News & Social Feed Web Crawler

A **production-ready** web crawler and content extractor focused on India news, built with [Crawl4AI](https://docs.crawl4ai.com/).

## Features

- **URL Seeding** - Intelligent URL discovery from sitemaps and Common Crawl
- **Adaptive Crawling** - Stops automatically when enough information is gathered  
- **Deep Crawling** - BFS/DFS/BestFirst strategies with relevance scoring
- **Multi-Language Support** - English, Hindi, Marathi, Bengali, Tamil, and more
- **Content Deduplication** - Hash-based duplicate detection
- **Storage Options** - SQLite database, JSONL streaming, Markdown export
- **Rate Limiting** - Respectful crawling with configurable delays
- **Proxy Support** - Rotation strategies for large-scale crawling

## Project Structure

```
crawl4ai/
├── config/
│   ├── __init__.py
│   └── settings.py          # All configurations
├── crawler/
│   ├── __init__.py
│   ├── core_engine.py       # Main crawler engine
│   ├── url_seeder.py        # URL discovery
│   ├── adaptive_crawler.py  # Adaptive crawling
│   ├── source_manager.py    # News source management
│   └── storage.py           # Data persistence
├── utils/
│   ├── __init__.py
│   └── monitoring.py        # Logging & metrics
├── main.py                  # Main orchestrator
├── examples.py              # Usage examples
└── requirements.txt
```

## Quick Start

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Install Crawl4AI
pip install crawl4ai

# Setup browser (if needed)
crawl4ai-setup
```

### Basic Usage

```python
import asyncio
from main import IndiaNewsCrawler
from config import get_default_config

async def main():
    # Create crawler with default config
    crawler = IndiaNewsCrawler(get_default_config())
    
    # Run seed-and-crawl pipeline
    results = await crawler.run_seed_and_crawl(max_urls=100)
    
    print(f"Crawled {len(results)} articles")
    
asyncio.run(main())
```

### CLI Usage

```bash
# Seed and crawl (default) with output
python main.py --mode seed --max-urls 100 --export markdown/json

# Deep crawl from seed URLs
python main.py --mode deep --max-urls 500

# Adaptive crawl with query satisfaction
python main.py --mode adaptive

# Continuous monitoring
python main.py --mode continuous

# Development mode (smaller limits)
python main.py --mode seed --dev

# Export results
python main.py --mode seed --export rag
```

## Crawling Modes

### 1. Seed and Crawl
Discovers URLs first, then crawls them:
```python
results = await crawler.run_seed_and_crawl(
    max_urls=200,
    categories=["national_news", "tech_news"]
)
```

### 2. Deep Crawl
Follows links from seed URLs:
```python
results = await crawler.run_deep_crawl(
    start_urls=["https://timesofindia.indiatimes.com/"],
    max_pages=500
)
```

### 3. Adaptive Crawl
Stops when enough information is gathered:
```python
result = await crawler.run_adaptive(
    queries=["India economy news", "India politics updates"],
    confidence=0.8
)
```

### 4. Continuous Mode
Runs periodically for monitoring:
```python
await crawler.run_continuous(
    interval_minutes=30,
    max_iterations=None  # Run forever
)
```

## Configuration

### Crawler Config
```python
from config import CrawlerConfig, CrawlStrategy

config = CrawlerConfig(
    max_depth=3,
    max_pages=500,
    strategy=CrawlStrategy.BEST_FIRST,
    headless=True,
    request_delay_min=1.0,
    request_delay_max=3.0,
)
```

### Adaptive Config
```python
from config import AdaptiveConfig

config = AdaptiveConfig(
    confidence_threshold=0.8,  # Stop at 80% confidence
    max_pages=30,
    min_gain_threshold=0.05,
)
```

### URL Seeding Config
```python
from config import URLSeedingConfig

config = URLSeedingConfig(
    source="sitemap+cc",  # Use both sitemap and Common Crawl
    extract_head=True,
    scoring_method="bm25",
    score_threshold=0.3,
)
```

##  Supported News Sources

### National (English)
- Times of India
- Hindustan Times  
- Indian Express
- NDTV
- The Hindu
- Economic Times
- Mint

### Regional (Hindi)
- Dainik Bhaskar
- Dainik Jagran
- Amar Ujala
- Navbharat Times

### Tech
- TechCrunch India
- YourStory
- Inc42

### Social
- Reddit r/india

## Output Formats

### JSONL (Streaming)
```json
{"url": "...", "title": "...", "content": "...", "score": 0.85}
```

### SQLite Database
- Full-text search
- Deduplication
- Query by source, date, score

### Markdown (RAG-ready)
```markdown
---
title: Article Title
url: https://...
source: timesofindia.com
---
# Article Title
Content here...
```

## 🔧 Advanced Usage

### Custom Source Manager
```python
from crawler import NewsSourceManager, NewsSource, SourceCategory
from config import Language

manager = NewsSourceManager()

# Add custom source
manager.add_source("my_source", NewsSource(
    url="https://mynews.com",
    name="My News",
    domain="mynews.com",
    category=SourceCategory.NATIONAL,
    language=Language.ENGLISH,
    priority=8,
))

# Get high-priority sources
urls = manager.get_urls(min_priority=7)
```

### Proxy Rotation
```python
from config import ProxyConfig

proxy_config = ProxyConfig(
    enabled=True,
    rotation_enabled=True,
    proxies=[
        "http://user:pass@proxy1:8080",
        "http://user:pass@proxy2:8080",
    ]
)
```

### Export for RAG
```python
# Export to RAG-compatible format
crawler.storage.export_for_rag("./output/rag_data.json")
```

## Monitoring

```python
from utils import MetricsCollector, setup_logging

# Setup logging
setup_logging(log_level="INFO", log_file="./logs/crawler.log")

# Collect metrics
metrics = MetricsCollector()
metrics.start_session()
# ... crawl ...
metrics.end_session()
metrics.print_summary()
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Main Orchestrator                     │
├─────────────────────────────────────────────────────────┤
│  URL Seeder  │  Core Crawler  │  Adaptive Crawler       │
├─────────────────────────────────────────────────────────┤
│  Source Manager  │  Storage Manager  │  Monitoring      │
├─────────────────────────────────────────────────────────┤
│                     Crawl4AI Engine                      │
└─────────────────────────────────────────────────────────┘
```
```
┌─────────────────────────────────────────────────────────────┐
│                    CRAWLING PIPELINE                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. URL DISCOVERY (RSS Mode - Default)                      │
│     ├── 31 Direct RSS feeds from Indian news sites          │
│     ├── Times of India, Hindustan Times, NDTV, etc.         │
│     ├── TechCrunch India, YourStory, Inc42, Entrackr        │
│     └── Returns 600+ articles with direct URLs              │
│                                                             │
│  2. DEDUPLICATION                                           │
│     ├── Check SQLite for existing URLs                      │
│     └── Skip already crawled articles                       │
│                                                             │
│  3. ADAPTIVE CRAWLING                                       │
│     ├── BestFirstCrawlingStrategy (news-optimized)          │
│     ├── KeywordRelevanceScorer for India news               │
│     └── Content filtering and validation                    │
│                                                             │
│  4. STORAGE                                                 │
│     ├── SQLite: Full article storage (title, content, etc.) │
│     ├── JSONL: Streaming output for large crawls            │
│     └── Markdown: Optional export                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```
## License

MIT License

## Acknowledgments

Built with [Crawl4AI](https://github.com/unclecode/crawl4ai) - the #1 open-source LLM-friendly web crawler.
