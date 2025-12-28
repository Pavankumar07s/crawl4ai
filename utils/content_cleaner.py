"""
Content Cleaner Utility - Cleans HTML noise and extracts quality article content
"""
import re
import logging
from typing import List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ContentCleaner:
    """
    Cleans raw markdown/HTML content to extract actual article text.
    Removes navigation menus, headers, footers, and UI noise.
    """
    
    # Patterns that indicate navigation/UI elements (to remove)
    NOISE_PATTERNS = [
        # Navigation menus
        r'\*\s*\[(?:Home|News|Markets|Premium|Companies|Money|Technology|Sports|Entertainment|Lifestyle|Opinion|Videos|Photos|More)\].*?\n',
        r'\[(?:Sign in|Sign Out|Subscribe|Login|Register|My Account)\].*?\n',
        r'(?:e-paper|ePaper)\s*\[.*?\]',
        
        # Language selectors
        r'(?:English|Hindi|हिंदी|Tamil|Telugu|Bengali|Marathi|Gujarati)\s*\n\s*\*\s*(?:English|Hindi|हिंदी)',
        
        # Social media links
        r'\[(?:Facebook|Twitter|LinkedIn|Instagram|YouTube|WhatsApp|Telegram|Share)\].*?\n',
        r'(?:Share|Follow us).*?(?:Facebook|Twitter|LinkedIn).*?\n',
        
        # Repeated link patterns (menus)
        r'(?:\*\s*\[.*?\]\(javascript:.*?\)\s*\n){3,}',
        r'(?:\*\s*\[.*?\]\(JavaScript:.*?\)\s*\n){3,}',
        
        # Footer/copyright
        r'©.*?(?:All Rights Reserved|Copyright).*?\n',
        r'(?:About Us|Contact Us|Privacy Policy|Terms of Service|Advertise).*?\n',
        
        # Cookie/subscription notices
        r'(?:Accept Cookies|Cookie Policy|Newsletter|Subscribe to).*?\n',
        
        # Image placeholders with just alt text
        r'!\[(?:mint|logo|icon|banner|ad|advertisement).*?\]\(.*?\)',
        
        # Inline navigation text
        r'\[(?:Read More|Load More|View All|See More|Click Here)\].*?\n',
        
        # Common news site navigation
        r'(?:Latest News|Trending|Popular|Most Read|Related Articles|Also Read):?\s*(?:\n\s*\*.*?)+',
        
        # Date/time patterns with navigation context
        r'(?:Saturday|Sunday|Monday|Tuesday|Wednesday|Thursday|Friday),\s*\d{1,2}\s+\w+\s+\d{4}\s*\n(?:\[.*?\]\n)+',
        
        # Stock ticker noise
        r'Stocks\s*\nMutual Funds\s*\nNews',
        
        # Empty list items
        r'\*\s*\n(?:\*\s*\n)+',
        
        # Markdown artifacts
        r'\[]\(javascript:void\(0\)\)',
        r'\[S\]\s*\n',
    ]
    
    # URL patterns that indicate non-article pages
    NON_ARTICLE_URL_PATTERNS = [
        r'^https?://[^/]+/?$',  # Homepage only
        r'/tag/',  # Tag pages
        r'/tags/',
        r'/category/',
        r'/categories/',
        r'/topics?/',
        r'/author/',
        r'/authors/',
        r'/page/\d+',  # Pagination
        r'/search\?',  # Search results
        r'/archive/',
        r'/company-results/?$',  # Listing pages
        r'/people/?$',
        r'/start-ups/?$',
        r'/latest-news/?$',
        r'/breaking-news/?$',
        r'/photos?/?$',
        r'/videos?/?$',
        r'/gallery/',
        r'/slideshow/',
        r'/live-blog/',
        r'/live-updates/?$',
        r'#[^/]*$',  # Anchor-only URLs
        r'\?.*utm_',  # Tracking URLs without path
    ]
    
    # Title patterns that indicate non-article pages
    NON_ARTICLE_TITLE_PATTERNS = [
        r'^Company (?:Results|Quarterly Results|Financial Results)',
        r'^People in Companies',
        r'^Startup News:',
        r'^Latest (?:News|Headlines)',
        r'^Breaking News',
        r'^(?:Home|Homepage)\s*[-|]',
        r'^404\s',
        r'^Page Not Found',
        r'^Error',
        r'^Search Results',
        r'^Tag:',
        r'^Category:',
        r'^Archive',
    ]
    
    def __init__(self, min_content_length: int = 200, max_content_length: int = 5000):
        """
        Initialize content cleaner.
        
        Args:
            min_content_length: Minimum characters for valid content
            max_content_length: Maximum characters to keep (smart truncation)
        """
        self.min_content_length = min_content_length
        self.max_content_length = max_content_length
        self._compiled_noise_patterns = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in self.NOISE_PATTERNS]
        self._compiled_url_patterns = [re.compile(p, re.IGNORECASE) for p in self.NON_ARTICLE_URL_PATTERNS]
        self._compiled_title_patterns = [re.compile(p, re.IGNORECASE) for p in self.NON_ARTICLE_TITLE_PATTERNS]
    
    def is_article_url(self, url: str) -> bool:
        """
        Check if URL is likely an actual article (not homepage/tag/category).
        
        Args:
            url: URL to check
            
        Returns:
            True if URL appears to be an article page
        """
        for pattern in self._compiled_url_patterns:
            if pattern.search(url):
                return False
        
        # Additional heuristics
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        
        # Homepage check
        if not path or path in ['index.html', 'index.php']:
            return False
        
        # Path should have some depth for articles
        path_segments = [s for s in path.split('/') if s]
        if len(path_segments) < 1:
            return False
        
        # Article URLs often have dates or slugs
        has_date_pattern = bool(re.search(r'\d{4}[/-]\d{2}[/-]\d{2}|\d{8,}', path))
        has_slug = bool(re.search(r'[a-z]+-[a-z]+-[a-z]+', path.lower()))
        has_article_id = bool(re.search(r'article|story|news|post', path.lower()))
        
        # Either has date, has slug pattern, or has article indicator
        return has_date_pattern or has_slug or has_article_id or len(path_segments) >= 2
    
    def is_article_title(self, title: str) -> bool:
        """
        Check if title indicates an actual article (not a listing page).
        
        Args:
            title: Page title to check
            
        Returns:
            True if title appears to be from an article
        """
        if not title or len(title.strip()) < 10:
            return False
        
        for pattern in self._compiled_title_patterns:
            if pattern.search(title):
                return False
        
        return True
    
    def clean_content(self, content: str) -> str:
        """
        Remove HTML/navigation noise from content.
        
        Args:
            content: Raw markdown content
            
        Returns:
            Cleaned content
        """
        if not content:
            return ""
        
        cleaned = content
        
        # Apply noise removal patterns
        for pattern in self._compiled_noise_patterns:
            cleaned = pattern.sub('', cleaned)
        
        # Remove excessive whitespace
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        cleaned = re.sub(r'[ \t]+', ' ', cleaned)
        
        # Remove lines that are just links or markdown artifacts
        lines = cleaned.split('\n')
        filtered_lines = []
        
        for line in lines:
            stripped = line.strip()
            
            # Skip empty lines (keep one)
            if not stripped:
                if filtered_lines and filtered_lines[-1].strip():
                    filtered_lines.append('')
                continue
            
            # Skip lines that are just markdown link syntax
            if re.match(r'^\[.*?\]\(.*?\)$', stripped):
                continue
            
            # Skip very short lines that look like navigation
            if len(stripped) < 20 and re.match(r'^[\*\-]\s*\[', stripped):
                continue
            
            # Skip lines with only special characters
            if re.match(r'^[\*\-_\[\]\(\)#\s]+$', stripped):
                continue
            
            filtered_lines.append(line)
        
        cleaned = '\n'.join(filtered_lines)
        
        # Final cleanup
        cleaned = cleaned.strip()
        
        return cleaned
    
    def extract_article_content(self, content: str, max_words: int = 500) -> str:
        """
        Extract the main article content, limited to specified word count.
        
        Args:
            content: Cleaned markdown content
            max_words: Maximum words to extract
            
        Returns:
            Extracted article content
        """
        if not content:
            return ""
        
        # First clean the content
        cleaned = self.clean_content(content)
        
        if not cleaned:
            return ""
        
        # Split into paragraphs
        paragraphs = [p.strip() for p in cleaned.split('\n\n') if p.strip()]
        
        # Filter out non-content paragraphs
        content_paragraphs = []
        for p in paragraphs:
            # Skip very short paragraphs
            if len(p) < 50:
                continue
            
            # Skip paragraphs that look like navigation
            if p.startswith('*') and p.count('*') > 3:
                continue
            
            # Skip paragraphs with too many links
            link_count = len(re.findall(r'\[.*?\]\(.*?\)', p))
            word_count = len(p.split())
            if word_count > 0 and link_count / word_count > 0.3:
                continue
            
            content_paragraphs.append(p)
        
        if not content_paragraphs:
            return ""
        
        # Build content up to max words
        result_paragraphs = []
        current_words = 0
        
        for p in content_paragraphs:
            p_words = len(p.split())
            if current_words + p_words > max_words and result_paragraphs:
                break
            result_paragraphs.append(p)
            current_words += p_words
        
        return '\n\n'.join(result_paragraphs)
    
    def calculate_content_quality_score(self, content: str, title: str, url: str) -> float:
        """
        Calculate a quality score for the content.
        
        Args:
            content: Article content
            title: Article title
            url: Article URL
            
        Returns:
            Quality score between 0.0 and 1.0
        """
        score = 0.0
        
        # URL quality (0-0.2)
        if self.is_article_url(url):
            score += 0.2
        
        # Title quality (0-0.2)
        if self.is_article_title(title):
            title_length_score = min(len(title) / 100, 1.0) * 0.1
            score += 0.1 + title_length_score
        
        # Content length (0-0.3)
        cleaned = self.clean_content(content)
        word_count = len(cleaned.split())
        
        if word_count >= 300:
            score += 0.3
        elif word_count >= 150:
            score += 0.2
        elif word_count >= 50:
            score += 0.1
        
        # Content quality indicators (0-0.3)
        if cleaned:
            # Paragraph structure
            paragraphs = [p for p in cleaned.split('\n\n') if len(p.strip()) > 50]
            if len(paragraphs) >= 3:
                score += 0.1
            
            # Link-to-text ratio (fewer links = better)
            link_count = len(re.findall(r'\[.*?\]\(.*?\)', cleaned))
            if word_count > 0:
                link_ratio = link_count / word_count
                if link_ratio < 0.05:
                    score += 0.1
                elif link_ratio < 0.1:
                    score += 0.05
            
            # Sentence structure (periods, question marks)
            sentence_endings = len(re.findall(r'[.!?]', cleaned))
            if sentence_endings >= 5:
                score += 0.1
        
        return min(score, 1.0)
    
    def is_quality_content(
        self,
        content: str,
        title: str,
        url: str,
        min_score: float = 0.4
    ) -> Tuple[bool, float]:
        """
        Check if content meets quality threshold.
        
        Args:
            content: Article content
            title: Article title
            url: Article URL
            min_score: Minimum quality score
            
        Returns:
            Tuple of (is_quality, score)
        """
        score = self.calculate_content_quality_score(content, title, url)
        return score >= min_score, score


class ContentDeduplicatorV2:
    """
    Improved content deduplication using multiple strategies.
    """
    
    def __init__(self, similarity_threshold: float = 0.8):
        self.similarity_threshold = similarity_threshold
        self._seen_urls: set = set()
        self._seen_titles: set = set()
        self._content_hashes: set = set()
        self._title_hashes: dict = {}
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison"""
        # Lowercase, remove extra spaces
        normalized = ' '.join(text.lower().split())
        # Remove punctuation
        normalized = re.sub(r'[^\w\s]', '', normalized)
        return normalized
    
    def _compute_hash(self, text: str) -> str:
        """Compute hash of normalized text"""
        import hashlib
        normalized = self._normalize_text(text)
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]
    
    def _get_title_key(self, title: str) -> str:
        """Extract key words from title for fuzzy matching"""
        normalized = self._normalize_text(title)
        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
                      'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
                      'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
                      'should', 'may', 'might', 'must', 'shall', 'can', 'that', 'this',
                      'these', 'those', 'it', 'its', 'as', 'into', 'than', 'new', 'says'}
        
        # Get significant words (length > 3 and not stop words)
        words = [w for w in normalized.split() if len(w) > 3 and w not in stop_words]
        # Sort for consistency
        words.sort()
        return ' '.join(words[:6])  # Top 6 significant words
    
    def _jaccard_similarity(self, set1: set, set2: set) -> float:
        """Calculate Jaccard similarity between two sets"""
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0
    
    def is_duplicate(self, url: str, title: str, content: str) -> bool:
        """
        Check if content is duplicate.
        
        Args:
            url: Article URL
            title: Article title
            content: Article content
            
        Returns:
            True if duplicate
        """
        # Exact URL match
        if url in self._seen_urls:
            return True
        
        # Title similarity check - use word set comparison
        title_key = self._get_title_key(title)
        if title_key:
            title_words = set(title_key.split())
            for seen_key in self._title_hashes:
                seen_words = set(seen_key.split())
                similarity = self._jaccard_similarity(title_words, seen_words)
                if similarity > 0.7:  # 70% word overlap
                    return True
        
        # Content hash check
        if content:
            content_hash = self._compute_hash(content[:1000])  # First 1000 chars
            if content_hash in self._content_hashes:
                return True
        
        return False
    
    def add(self, url: str, title: str, content: str):
        """Add content to seen set"""
        self._seen_urls.add(url)
        
        title_key = self._get_title_key(title)
        if title_key:
            self._title_hashes[title_key] = url
        
        if content:
            content_hash = self._compute_hash(content[:1000])
            self._content_hashes.add(content_hash)
    
    def clear(self):
        """Clear all seen content"""
        self._seen_urls.clear()
        self._seen_titles.clear()
        self._content_hashes.clear()
        self._title_hashes.clear()
