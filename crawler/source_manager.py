"""
News Source Manager - Manages multiple news sources and categories
"""
import logging
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse

import sys
sys.path.append('..')
from config.settings import SEED_URLS, Language

logger = logging.getLogger(__name__)

class SourceCategory(Enum):
    """News source categories"""
    NATIONAL = "national_news"
    REGIONAL_HINDI = "regional_hindi"
    REGIONAL_MARATHI = "regional_marathi"
    REGIONAL_BENGALI = "regional_bengali"
    REGIONAL_TAMIL = "regional_tamil"
    TECH = "tech_news"
    BUSINESS = "business_news"
    AGGREGATOR = "news_aggregators"
    SOCIAL = "social_forums"

class SourceReliability(Enum):
    """Source reliability ratings"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"

@dataclass
class NewsSource:
    """Represents a news source"""
    url: str
    name: str
    domain: str
    category: SourceCategory
    language: Language
    reliability: SourceReliability = SourceReliability.UNKNOWN
    rate_limit: float = 1.0  # Seconds between requests
    enabled: bool = True
    priority: int = 5  # 1-10, higher = more important
    requires_js: bool = False
    has_sitemap: bool = True
    sitemap_url: Optional[str] = None
    
    def __post_init__(self):
        """Extract domain from URL if not provided"""
        if not self.domain:
            parsed = urlparse(self.url)
            self.domain = parsed.netloc

# Pre-configured news sources
NEWS_SOURCES: Dict[str, NewsSource] = {
    # National English News
    "times_of_india": NewsSource(
        url="https://timesofindia.indiatimes.com/",
        name="Times of India",
        domain="timesofindia.indiatimes.com",
        category=SourceCategory.NATIONAL,
        language=Language.ENGLISH,
        reliability=SourceReliability.HIGH,
        priority=9,
        has_sitemap=True,
    ),
    "hindustan_times": NewsSource(
        url="https://www.hindustantimes.com/",
        name="Hindustan Times",
        domain="hindustantimes.com",
        category=SourceCategory.NATIONAL,
        language=Language.ENGLISH,
        reliability=SourceReliability.HIGH,
        priority=9,
    ),
    "indian_express": NewsSource(
        url="https://indianexpress.com/",
        name="Indian Express",
        domain="indianexpress.com",
        category=SourceCategory.NATIONAL,
        language=Language.ENGLISH,
        reliability=SourceReliability.HIGH,
        priority=9,
    ),
    "ndtv": NewsSource(
        url="https://www.ndtv.com/",
        name="NDTV",
        domain="ndtv.com",
        category=SourceCategory.NATIONAL,
        language=Language.ENGLISH,
        reliability=SourceReliability.HIGH,
        priority=8,
        requires_js=True,
    ),
    "the_hindu": NewsSource(
        url="https://www.thehindu.com/",
        name="The Hindu",
        domain="thehindu.com",
        category=SourceCategory.NATIONAL,
        language=Language.ENGLISH,
        reliability=SourceReliability.HIGH,
        priority=9,
    ),
    "livemint": NewsSource(
        url="https://www.livemint.com/",
        name="Mint",
        domain="livemint.com",
        category=SourceCategory.BUSINESS,
        language=Language.ENGLISH,
        reliability=SourceReliability.HIGH,
        priority=8,
    ),
    "economic_times": NewsSource(
        url="https://economictimes.indiatimes.com/",
        name="Economic Times",
        domain="economictimes.indiatimes.com",
        category=SourceCategory.BUSINESS,
        language=Language.ENGLISH,
        reliability=SourceReliability.HIGH,
        priority=8,
    ),
    "business_standard": NewsSource(
        url="https://www.business-standard.com/",
        name="Business Standard",
        domain="business-standard.com",
        category=SourceCategory.BUSINESS,
        language=Language.ENGLISH,
        reliability=SourceReliability.HIGH,
        priority=7,
    ),
    "scroll": NewsSource(
        url="https://scroll.in/",
        name="Scroll.in",
        domain="scroll.in",
        category=SourceCategory.NATIONAL,
        language=Language.ENGLISH,
        reliability=SourceReliability.MEDIUM,
        priority=6,
    ),
    "the_wire": NewsSource(
        url="https://thewire.in/",
        name="The Wire",
        domain="thewire.in",
        category=SourceCategory.NATIONAL,
        language=Language.ENGLISH,
        reliability=SourceReliability.MEDIUM,
        priority=6,
    ),
    
    # Hindi News
    "dainik_bhaskar": NewsSource(
        url="https://www.bhaskar.com/",
        name="Dainik Bhaskar",
        domain="bhaskar.com",
        category=SourceCategory.REGIONAL_HINDI,
        language=Language.HINDI,
        reliability=SourceReliability.HIGH,
        priority=8,
    ),
    "dainik_jagran": NewsSource(
        url="https://www.jagran.com/",
        name="Dainik Jagran",
        domain="jagran.com",
        category=SourceCategory.REGIONAL_HINDI,
        language=Language.HINDI,
        reliability=SourceReliability.HIGH,
        priority=8,
    ),
    "amar_ujala": NewsSource(
        url="https://www.amarujala.com/",
        name="Amar Ujala",
        domain="amarujala.com",
        category=SourceCategory.REGIONAL_HINDI,
        language=Language.HINDI,
        reliability=SourceReliability.HIGH,
        priority=7,
    ),
    "navbharat_times": NewsSource(
        url="https://navbharattimes.indiatimes.com/",
        name="Navbharat Times",
        domain="navbharattimes.indiatimes.com",
        category=SourceCategory.REGIONAL_HINDI,
        language=Language.HINDI,
        reliability=SourceReliability.HIGH,
        priority=7,
    ),
    
    # Marathi News
    "loksatta": NewsSource(
        url="https://www.loksatta.com/",
        name="Loksatta",
        domain="loksatta.com",
        category=SourceCategory.REGIONAL_MARATHI,
        language=Language.MARATHI,
        reliability=SourceReliability.HIGH,
        priority=7,
    ),
    "maharashtra_times": NewsSource(
        url="https://maharashtratimes.com/",
        name="Maharashtra Times",
        domain="maharashtratimes.com",
        category=SourceCategory.REGIONAL_MARATHI,
        language=Language.MARATHI,
        reliability=SourceReliability.HIGH,
        priority=7,
    ),
    
    # Tech News
    "techcrunch_india": NewsSource(
        url="https://techcrunch.com/tag/india/",
        name="TechCrunch India",
        domain="techcrunch.com",
        category=SourceCategory.TECH,
        language=Language.ENGLISH,
        reliability=SourceReliability.HIGH,
        priority=7,
    ),
    "yourstory": NewsSource(
        url="https://yourstory.com/",
        name="YourStory",
        domain="yourstory.com",
        category=SourceCategory.TECH,
        language=Language.ENGLISH,
        reliability=SourceReliability.MEDIUM,
        priority=6,
    ),
    "inc42": NewsSource(
        url="https://inc42.com/",
        name="Inc42",
        domain="inc42.com",
        category=SourceCategory.TECH,
        language=Language.ENGLISH,
        reliability=SourceReliability.MEDIUM,
        priority=6,
    ),
    
    # Social/Forums
    "reddit_india": NewsSource(
        url="https://www.reddit.com/r/india/",
        name="Reddit r/india",
        domain="reddit.com",
        category=SourceCategory.SOCIAL,
        language=Language.ENGLISH,
        reliability=SourceReliability.LOW,
        priority=4,
        requires_js=True,
        has_sitemap=False,
    ),
}

class NewsSourceManager:
    """
    Manages news sources for crawling
    
    Features:
    - Source categorization
    - Language filtering
    - Priority-based selection
    - Rate limit tracking
    - Source health monitoring
    """
    
    def __init__(self, sources: Optional[Dict[str, NewsSource]] = None):
        self.sources = sources or NEWS_SOURCES.copy()
        self._disabled_sources: Set[str] = set()
        self._source_health: Dict[str, float] = {}  # 0.0 to 1.0
        
    def get_source(self, source_id: str) -> Optional[NewsSource]:
        """Get a specific source by ID"""
        return self.sources.get(source_id)
        
    def get_all_sources(self) -> List[NewsSource]:
        """Get all enabled sources"""
        return [
            s for s in self.sources.values()
            if s.enabled and s.domain not in self._disabled_sources
        ]
        
    def get_sources_by_category(
        self,
        category: SourceCategory,
    ) -> List[NewsSource]:
        """Get sources by category"""
        return [
            s for s in self.get_all_sources()
            if s.category == category
        ]
        
    def get_sources_by_language(
        self,
        language: Language,
    ) -> List[NewsSource]:
        """Get sources by language"""
        return [
            s for s in self.get_all_sources()
            if s.language == language
        ]
        
    def get_sources_by_reliability(
        self,
        min_reliability: SourceReliability = SourceReliability.MEDIUM,
    ) -> List[NewsSource]:
        """Get sources with minimum reliability"""
        reliability_order = {
            SourceReliability.HIGH: 3,
            SourceReliability.MEDIUM: 2,
            SourceReliability.LOW: 1,
            SourceReliability.UNKNOWN: 0,
        }
        min_level = reliability_order[min_reliability]
        
        return [
            s for s in self.get_all_sources()
            if reliability_order[s.reliability] >= min_level
        ]
        
    def get_prioritized_sources(
        self,
        min_priority: int = 5,
        limit: Optional[int] = None,
    ) -> List[NewsSource]:
        """Get sources sorted by priority"""
        sources = [
            s for s in self.get_all_sources()
            if s.priority >= min_priority
        ]
        sources.sort(key=lambda x: x.priority, reverse=True)
        
        if limit:
            return sources[:limit]
        return sources
        
    def get_national_english_sources(self) -> List[NewsSource]:
        """Get high-priority national English news sources"""
        return [
            s for s in self.get_all_sources()
            if s.category == SourceCategory.NATIONAL
            and s.language == Language.ENGLISH
            and s.priority >= 7
        ]
        
    def get_regional_sources(
        self,
        languages: Optional[List[Language]] = None,
    ) -> List[NewsSource]:
        """Get regional language sources"""
        regional_categories = {
            SourceCategory.REGIONAL_HINDI,
            SourceCategory.REGIONAL_MARATHI,
            SourceCategory.REGIONAL_BENGALI,
            SourceCategory.REGIONAL_TAMIL,
        }
        
        sources = [
            s for s in self.get_all_sources()
            if s.category in regional_categories
        ]
        
        if languages:
            sources = [s for s in sources if s.language in languages]
            
        return sources
        
    def disable_source(self, source_id: str):
        """Temporarily disable a source"""
        if source_id in self.sources:
            self._disabled_sources.add(self.sources[source_id].domain)
            logger.info(f"Disabled source: {source_id}")
            
    def enable_source(self, source_id: str):
        """Re-enable a source"""
        if source_id in self.sources:
            self._disabled_sources.discard(self.sources[source_id].domain)
            logger.info(f"Enabled source: {source_id}")
            
    def update_health(self, source_id: str, success: bool):
        """Update source health based on crawl success"""
        if source_id not in self._source_health:
            self._source_health[source_id] = 1.0
            
        current = self._source_health[source_id]
        # Exponential moving average
        if success:
            self._source_health[source_id] = current * 0.9 + 0.1
        else:
            self._source_health[source_id] = current * 0.9
            
        # Auto-disable unhealthy sources
        if self._source_health[source_id] < 0.3:
            self.disable_source(source_id)
            logger.warning(f"Auto-disabled unhealthy source: {source_id}")
            
    def get_urls(
        self,
        categories: Optional[List[SourceCategory]] = None,
        languages: Optional[List[Language]] = None,
        min_priority: int = 5,
    ) -> List[str]:
        """Get URLs matching criteria"""
        sources = self.get_all_sources()
        
        if categories:
            sources = [s for s in sources if s.category in categories]
            
        if languages:
            sources = [s for s in sources if s.language in languages]
            
        sources = [s for s in sources if s.priority >= min_priority]
        
        return [s.url for s in sources]
        
    def get_domains(
        self,
        categories: Optional[List[SourceCategory]] = None,
        languages: Optional[List[Language]] = None,
    ) -> List[str]:
        """Get domains matching criteria"""
        sources = self.get_all_sources()
        
        if categories:
            sources = [s for s in sources if s.category in categories]
            
        if languages:
            sources = [s for s in sources if s.language in languages]
            
        return [s.domain for s in sources]
        
    def add_source(self, source_id: str, source: NewsSource):
        """Add a new source"""
        self.sources[source_id] = source
        logger.info(f"Added source: {source_id}")
        
    def get_crawl_config(self, source_id: str) -> Dict[str, any]:
        """Get recommended crawl config for a source"""
        source = self.sources.get(source_id)
        if not source:
            return {}
            
        return {
            "rate_limit": source.rate_limit,
            "requires_js": source.requires_js,
            "has_sitemap": source.has_sitemap,
            "sitemap_url": source.sitemap_url,
            "language": source.language.value,
        }
        
    def to_dict(self) -> Dict[str, Dict]:
        """Export sources to dictionary"""
        return {
            source_id: {
                "url": source.url,
                "name": source.name,
                "domain": source.domain,
                "category": source.category.value,
                "language": source.language.value,
                "reliability": source.reliability.value,
                "priority": source.priority,
                "enabled": source.enabled and source.domain not in self._disabled_sources,
            }
            for source_id, source in self.sources.items()
        }


# Convenience functions
def get_top_news_sources(limit: int = 10) -> List[NewsSource]:
    """Get top priority news sources"""
    manager = NewsSourceManager()
    return manager.get_prioritized_sources(min_priority=7, limit=limit)

def get_india_news_urls() -> List[str]:
    """Get all India news URLs"""
    manager = NewsSourceManager()
    return manager.get_urls(
        categories=[SourceCategory.NATIONAL, SourceCategory.BUSINESS],
        languages=[Language.ENGLISH],
        min_priority=6,
    )

def get_multilingual_sources() -> Dict[str, List[NewsSource]]:
    """Get sources grouped by language"""
    manager = NewsSourceManager()
    return {
        "english": manager.get_sources_by_language(Language.ENGLISH),
        "hindi": manager.get_sources_by_language(Language.HINDI),
        "marathi": manager.get_sources_by_language(Language.MARATHI),
    }
