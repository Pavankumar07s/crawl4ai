"""
Example: Quick Start India News Crawler
========================================
Simple examples to get started with the crawler
"""
import asyncio
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))


async def example_1_simple_crawl():
    """
    Example 1: Simple news crawl from a single source
    """
    print("\n" + "="*60)
    print("Example 1: Simple News Crawl")
    print("="*60)
    
    from crawler import CoreCrawlerEngine
    from config import CrawlerConfig, CrawlStrategy
    
    # Create a simple config
    config = CrawlerConfig(
        max_depth=2,
        max_pages=10,
        headless=True,
        strategy=CrawlStrategy.BEST_FIRST,
    )
    
    engine = CoreCrawlerEngine(config=config)
    
    async with engine as crawler:
        print("🚀 Starting crawl from Times of India...")
        
        count = 0
        async for result in crawler.crawl_deep(
            start_url="https://timesofindia.indiatimes.com/",
            keywords=["india", "news", "today"],
            stream=True,
        ):
            if result.success:
                count += 1
                print(f"  [{count}] {result.title[:60]}...")
                print(f"      Score: {result.score:.2f} | Depth: {result.depth}")
                
            if count >= 5:  # Just get 5 for example
                break
                
    print(f"\n✓ Crawled {count} articles")


async def example_2_url_seeding():
    """
    Example 2: Discover URLs using URL seeding
    """
    print("\n" + "="*60)
    print("Example 2: URL Seeding Discovery")
    print("="*60)
    
    from crawler import URLSeeder
    from config import URLSeedingConfig
    
    config = URLSeedingConfig(
        source="sitemap",
        extract_head=True,
        max_urls=20,
        scoring_method="bm25",
    )
    
    async with URLSeeder(config) as seeder:
        print("🔍 Discovering news URLs...")
        
        urls = await seeder.discover_from_domain(
            domain="indianexpress.com",
            query="India news politics",
            max_urls=10,
        )
        
        print(f"\n📋 Discovered {len(urls)} URLs:")
        for i, url in enumerate(urls[:5], 1):
            print(f"  {i}. {url.title or 'No title'}")
            print(f"     URL: {url.url[:60]}...")
            print(f"     Score: {url.relevance_score:.2f}")


async def example_3_adaptive_crawl():
    """
    Example 3: Adaptive crawling that stops when enough info gathered
    """
    print("\n" + "="*60)
    print("Example 3: Adaptive Crawling")
    print("="*60)
    
    from crawler import AdaptiveNewsCrawler
    from config import AdaptiveConfig
    
    config = AdaptiveConfig(
        confidence_threshold=0.7,
        max_pages=15,
        top_k_links=3,
    )
    
    async with AdaptiveNewsCrawler(config) as crawler:
        print("🎯 Starting adaptive crawl for 'India economy news'...")
        
        result = await crawler.crawl(
            start_url="https://economictimes.indiatimes.com/",
            query="India economy GDP growth latest",
        )
        
        print(f"\n📊 Results:")
        print(f"  Pages crawled: {result.metrics.pages_crawled}")
        print(f"  Confidence: {result.metrics.confidence_score:.2f}")
        print(f"  Coverage: {result.metrics.coverage_score:.2f}")
        
        print(f"\n📄 Top relevant content:")
        for i, content in enumerate(result.relevant_content[:3], 1):
            print(f"  {i}. {content.get('url', 'N/A')[:60]}...")


async def example_4_source_management():
    """
    Example 4: Using the News Source Manager
    """
    print("\n" + "="*60)
    print("Example 4: News Source Management")
    print("="*60)
    
    from crawler import NewsSourceManager, SourceCategory
    from config import Language
    
    manager = NewsSourceManager()
    
    print("📰 Available News Sources:\n")
    
    # Get national English sources
    national = manager.get_national_english_sources()
    print(f"National English ({len(national)} sources):")
    for source in national[:3]:
        print(f"  - {source.name} ({source.domain}) [Priority: {source.priority}]")
        
    # Get Hindi sources
    hindi = manager.get_sources_by_language(Language.HINDI)
    print(f"\nHindi ({len(hindi)} sources):")
    for source in hindi[:3]:
        print(f"  - {source.name} ({source.domain})")
        
    # Get URLs for crawling
    urls = manager.get_urls(
        categories=[SourceCategory.NATIONAL, SourceCategory.BUSINESS],
        min_priority=7,
    )
    print(f"\nHigh-priority URLs for crawling: {len(urls)}")


async def example_5_full_pipeline():
    """
    Example 5: Full seed-and-crawl pipeline
    """
    print("\n" + "="*60)
    print("Example 5: Full Pipeline (Seed → Crawl → Store)")
    print("="*60)
    
    from main import IndiaNewsCrawler
    from config import get_development_config
    
    # Use development config for faster testing
    config = get_development_config()
    config.crawler.max_pages = 10
    config.seeding.max_urls = 20
    
    crawler = IndiaNewsCrawler(config)
    
    print("🚀 Running seed-and-crawl pipeline...")
    results = await crawler.run_seed_and_crawl(
        max_urls=10,
        categories=["national_news"],
    )
    
    print(f"\n✓ Pipeline complete!")
    print(f"  Total articles: {len(results)}")
    
    # Show stats
    stats = crawler.get_stats()
    print(f"  Database articles: {stats['storage']['database']['total_articles']}")


async def main():
    """Run all examples"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║          🇮🇳 INDIA NEWS CRAWLER - Examples 🇮🇳             ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Run examples (comment out ones you don't want)
    
    # Example 1: Simple crawl
    # await example_1_simple_crawl()
    
    # Example 2: URL seeding
    # await example_2_url_seeding()
    
    # Example 3: Adaptive crawl
    # await example_3_adaptive_crawl()
    
    # Example 4: Source management (no network needed)
    await example_4_source_management()
    
    # Example 5: Full pipeline
    # await example_5_full_pipeline()
    
    print("\n✨ Examples complete!")


if __name__ == "__main__":
    asyncio.run(main())
