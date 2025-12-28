"""
Storage & Output Module - Handles persistence and export
"""
import json
import sqlite3
import hashlib
import logging
import re
from pathlib import Path
from typing import List, Dict, Optional, Any, Iterator, Tuple
from dataclasses import asdict
from datetime import datetime
from contextlib import contextmanager

import sys
sys.path.append('..')
from config.settings import StorageConfig
from .core_engine import CrawlResult
from utils.content_cleaner import ContentCleaner, ContentDeduplicatorV2

logger = logging.getLogger(__name__)


class ContentDeduplicator:
    """
    Deduplicates content using hash-based approach
    """
    
    def __init__(self):
        self._seen_hashes: set = set()
        self._url_hashes: Dict[str, str] = {}
        
    def _compute_hash(self, content: str) -> str:
        """Compute content hash"""
        # Normalize content
        normalized = ' '.join(content.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]
        
    def is_duplicate(self, content: str, url: str) -> bool:
        """Check if content is duplicate"""
        content_hash = self._compute_hash(content)
        
        # Check exact content match
        if content_hash in self._seen_hashes:
            return True
            
        # Check URL
        if url in self._url_hashes:
            return True
            
        return False
        
    def add(self, content: str, url: str):
        """Add content to seen set"""
        content_hash = self._compute_hash(content)
        self._seen_hashes.add(content_hash)
        self._url_hashes[url] = content_hash
        
    def clear(self):
        """Clear all seen content"""
        self._seen_hashes.clear()
        self._url_hashes.clear()


class JSONLinesStorage:
    """
    JSONL file storage for streaming output
    """
    
    def __init__(self, output_path: str):
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = None
        
    def __enter__(self):
        self._file = open(self.output_path, 'a', encoding='utf-8')
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._file:
            self._file.close()
            
    def write(self, result: CrawlResult):
        """Write a single result"""
        if self._file:
            data = {
                "url": result.url,
                "title": result.title,
                "content": result.content,
                "metadata": result.metadata,
                "score": result.score,
                "depth": result.depth,
                "crawled_at": result.crawled_at.isoformat(),
                "source_domain": result.source_domain,
                "language": result.language,
            }
            self._file.write(json.dumps(data, ensure_ascii=False) + '\n')
            self._file.flush()
            
    def write_many(self, results: List[CrawlResult]):
        """Write multiple results"""
        for result in results:
            self.write(result)
            
    @staticmethod
    def read(path: str) -> Iterator[Dict[str, Any]]:
        """Read JSONL file as iterator"""
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)


class MarkdownExporter:
    """
    Export results to Markdown format for RAG pipelines.
    
    Features:
    - Content cleaning (removes navigation, menus, HTML noise)
    - URL quality filtering (filters out homepages, tag pages)
    - Smart content extraction (extracts actual article text)
    - Improved relevance scoring
    - Deduplication
    """
    
    def __init__(self, output_dir: str, max_article_words: int = 500):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_article_words = max_article_words
        self.content_cleaner = ContentCleaner()
        self.deduplicator = ContentDeduplicatorV2()
        
    def _sanitize_filename(self, title: str) -> str:
        """Create safe filename from title"""
        # Remove invalid characters
        safe = "".join(c if c.isalnum() or c in ' -_' else '_' for c in title)
        safe = safe[:100].strip()
        return safe or "untitled"
    
    def _is_quality_article(self, result: CrawlResult) -> Tuple[bool, float, str]:
        """
        Check if result is a quality article worth exporting.
        
        Returns:
            Tuple of (is_quality, adjusted_score, reason)
        """
        # Check URL quality
        if not self.content_cleaner.is_article_url(result.url):
            return False, 0.0, "Non-article URL (homepage/tag/category page)"
        
        # Check title quality  
        if not self.content_cleaner.is_article_title(result.title):
            return False, 0.0, "Non-article title (listing/category page)"
        
        # Check for duplicates
        content = result.markdown or result.content
        if self.deduplicator.is_duplicate(result.url, result.title, content):
            return False, 0.0, "Duplicate content"
        
        # Calculate quality score
        is_quality, score = self.content_cleaner.is_quality_content(
            content, result.title, result.url, min_score=0.3
        )
        
        if not is_quality:
            return False, score, f"Low quality score ({score:.2f})"
        
        return True, score, "Quality article"
        
    def export(self, result: CrawlResult, include_metadata: bool = True) -> Optional[str]:
        """Export single result to markdown file"""
        # Quality check
        is_quality, score, reason = self._is_quality_article(result)
        if not is_quality:
            logger.debug(f"Skipping {result.url}: {reason}")
            return None
        
        # Mark as seen
        content = result.markdown or result.content
        self.deduplicator.add(result.url, result.title, content)
        
        filename = f"{self._sanitize_filename(result.title)}_{result.crawled_at.strftime('%Y%m%d_%H%M%S')}.md"
        filepath = self.output_dir / filename
        
        # Clean and extract content
        cleaned_content = self.content_cleaner.extract_article_content(
            content, max_words=self.max_article_words
        )
        
        output = []
        
        # Front matter
        if include_metadata:
            output.append("---")
            output.append(f"title: {result.title}")
            output.append(f"url: {result.url}")
            output.append(f"source: {result.source_domain}")
            output.append(f"crawled_at: {result.crawled_at.isoformat()}")
            output.append(f"relevance_score: {score:.2f}")
            if result.language:
                output.append(f"language: {result.language}")
            output.append("---\n")
            
        # Title
        output.append(f"# {result.title}\n")
        
        # Source info
        output.append(f"**Source:** [{result.source_domain}]({result.url})")
        output.append(f"**Crawled:** {result.crawled_at.strftime('%Y-%m-%d %H:%M:%S')}")
        output.append(f"**Quality Score:** {score:.2f}\n")
        
        # Main content
        output.append(cleaned_content if cleaned_content else "*[No article content extracted]*")
        
        # Write file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(output))
            
        logger.debug(f"Exported: {filepath}")
        return str(filepath)
        
    def export_many(self, results: List[CrawlResult]) -> List[str]:
        """Export multiple results"""
        exported = []
        for r in results:
            if r.success:
                path = self.export(r)
                if path:
                    exported.append(path)
        return exported
        
    def export_combined(
        self,
        results: List[CrawlResult],
        output_name: str = "combined_news.md",
        min_quality_score: float = 0.3,
        max_articles: int = 100,
    ) -> str:
        """
        Export all results to single combined file with quality filtering.
        
        Args:
            results: List of crawl results
            output_name: Output filename
            min_quality_score: Minimum quality score to include
            max_articles: Maximum number of articles to include
        """
        filepath = self.output_dir / output_name
        
        # Reset deduplicator for this export
        self.deduplicator.clear()
        
        # Filter and score articles
        quality_articles = []
        skipped_stats = {"non_article_url": 0, "non_article_title": 0, "duplicate": 0, "low_quality": 0, "no_content": 0}
        
        for result in results:
            if not result.success:
                continue
            
            # Check URL quality
            if not self.content_cleaner.is_article_url(result.url):
                skipped_stats["non_article_url"] += 1
                continue
            
            # Check title quality
            if not self.content_cleaner.is_article_title(result.title):
                skipped_stats["non_article_title"] += 1
                continue
            
            content = result.markdown or result.content
            
            # Check for duplicates
            if self.deduplicator.is_duplicate(result.url, result.title, content):
                skipped_stats["duplicate"] += 1
                continue
            
            # Calculate quality score
            is_quality, score = self.content_cleaner.is_quality_content(
                content, result.title, result.url, min_score=min_quality_score
            )
            
            if not is_quality:
                skipped_stats["low_quality"] += 1
                continue
            
            # Extract and clean content
            cleaned_content = self.content_cleaner.extract_article_content(
                content, max_words=self.max_article_words
            )
            
            if not cleaned_content or len(cleaned_content.strip()) < 100:
                skipped_stats["no_content"] += 1
                continue
            
            # Mark as seen
            self.deduplicator.add(result.url, result.title, content)
            
            quality_articles.append({
                "result": result,
                "score": score,
                "content": cleaned_content
            })
        
        # Sort by score (highest first) and limit
        quality_articles.sort(key=lambda x: x["score"], reverse=True)
        quality_articles = quality_articles[:max_articles]
        
        # Build output
        output = []
        output.append("# India News Compilation\n")
        output.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        output.append(f"**Quality Articles:** {len(quality_articles)}")
        output.append(f"**Total Processed:** {len(results)}")
        output.append(f"**Filtering Summary:**")
        output.append(f"  - Non-article URLs (homepages/tags): {skipped_stats['non_article_url']}")
        output.append(f"  - Non-article titles: {skipped_stats['non_article_title']}")
        output.append(f"  - Duplicates removed: {skipped_stats['duplicate']}")
        output.append(f"  - Low quality score: {skipped_stats['low_quality']}")
        output.append(f"  - No content extracted: {skipped_stats['no_content']}")
        output.append("\n---\n")
        
        for i, article in enumerate(quality_articles, 1):
            result = article["result"]
            score = article["score"]
            cleaned_content = article["content"]
            
            output.append(f"## {i}. {result.title}\n")
            output.append(f"**Source:** [{result.source_domain}]({result.url})")
            output.append(f"**Quality Score:** {score:.2f}")
            output.append(f"**Crawled:** {result.crawled_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
            output.append(cleaned_content)
            output.append("\n---\n")
        
        # Write file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(output))
        
        logger.info(f"Combined export: {filepath} ({len(quality_articles)} quality articles)")
        return str(filepath)


class SQLiteStorage:
    """
    SQLite database storage for structured data
    """
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        
    def _init_db(self):
        """Initialize database schema"""
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    url_hash TEXT NOT NULL,
                    title TEXT,
                    content TEXT,
                    markdown TEXT,
                    source_domain TEXT,
                    language TEXT,
                    score REAL,
                    depth INTEGER,
                    crawled_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata JSON
                );
                
                CREATE INDEX IF NOT EXISTS idx_url_hash ON articles(url_hash);
                CREATE INDEX IF NOT EXISTS idx_source ON articles(source_domain);
                CREATE INDEX IF NOT EXISTS idx_crawled ON articles(crawled_at);
                CREATE INDEX IF NOT EXISTS idx_score ON articles(score);
                
                CREATE TABLE IF NOT EXISTS crawl_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    start_time TIMESTAMP,
                    end_time TIMESTAMP,
                    total_urls INTEGER,
                    successful INTEGER,
                    failed INTEGER,
                    config JSON
                );
                
                CREATE TABLE IF NOT EXISTS url_frontier (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    priority REAL,
                    status TEXT DEFAULT 'pending',
                    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    crawled_at TIMESTAMP
                );
            """)
            
    @contextmanager
    def _get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
            
    def _url_hash(self, url: str) -> str:
        """Create URL hash"""
        return hashlib.sha256(url.encode()).hexdigest()[:16]
        
    def store(self, result: CrawlResult) -> bool:
        """Store a single crawl result"""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO articles 
                    (url, url_hash, title, content, markdown, source_domain, 
                     language, score, depth, crawled_at, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    result.url,
                    self._url_hash(result.url),
                    result.title,
                    result.content,
                    result.markdown,
                    result.source_domain,
                    result.language,
                    result.score,
                    result.depth,
                    result.crawled_at.isoformat(),
                    json.dumps(result.metadata, ensure_ascii=False),
                ))
            return True
        except Exception as e:
            logger.error(f"Error storing result: {e}")
            return False
            
    def store_many(self, results: List[CrawlResult]) -> int:
        """Store multiple results, return count of successful"""
        count = 0
        for result in results:
            if self.store(result):
                count += 1
        return count
        
    def exists(self, url: str) -> bool:
        """Check if URL already exists"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM articles WHERE url_hash = ?",
                (self._url_hash(url),)
            )
            return cursor.fetchone() is not None
            
    def get_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Get article by URL"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM articles WHERE url_hash = ?",
                (self._url_hash(url),)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
            
    def get_recent(
        self,
        limit: int = 100,
        source: Optional[str] = None,
        min_score: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Get recent articles"""
        query = "SELECT * FROM articles"
        conditions = []
        params = []
        
        if source:
            conditions.append("source_domain = ?")
            params.append(source)
            
        if min_score is not None:
            conditions.append("score >= ?")
            params.append(min_score)
            
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        query += " ORDER BY crawled_at DESC LIMIT ?"
        params.append(limit)
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
            
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        with self._get_connection() as conn:
            stats = {}
            
            cursor = conn.execute("SELECT COUNT(*) FROM articles")
            stats["total_articles"] = cursor.fetchone()[0]
            
            cursor = conn.execute(
                "SELECT source_domain, COUNT(*) as count FROM articles GROUP BY source_domain ORDER BY count DESC LIMIT 10"
            )
            stats["top_sources"] = [dict(row) for row in cursor.fetchall()]
            
            cursor = conn.execute("SELECT AVG(score) FROM articles")
            stats["avg_score"] = cursor.fetchone()[0]
            
            cursor = conn.execute(
                "SELECT MIN(crawled_at), MAX(crawled_at) FROM articles"
            )
            row = cursor.fetchone()
            stats["date_range"] = {"min": row[0], "max": row[1]}
            
            return stats
            
    def add_to_frontier(self, urls: List[str], priorities: Optional[List[float]] = None):
        """Add URLs to crawl frontier"""
        if priorities is None:
            priorities = [0.5] * len(urls)
            
        with self._get_connection() as conn:
            for url, priority in zip(urls, priorities):
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO url_frontier (url, priority) VALUES (?, ?)",
                        (url, priority)
                    )
                except Exception:
                    pass
                    
    def get_frontier_urls(self, limit: int = 100) -> List[str]:
        """Get pending URLs from frontier"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """SELECT url FROM url_frontier 
                   WHERE status = 'pending' 
                   ORDER BY priority DESC LIMIT ?""",
                (limit,)
            )
            return [row[0] for row in cursor.fetchall()]
            
    def mark_url_crawled(self, url: str):
        """Mark URL as crawled in frontier"""
        with self._get_connection() as conn:
            conn.execute(
                """UPDATE url_frontier 
                   SET status = 'crawled', crawled_at = CURRENT_TIMESTAMP 
                   WHERE url = ?""",
                (url,)
            )


class StorageManager:
    """
    Unified storage manager combining all storage backends.
    
    Features:
    - Content deduplication
    - Quality-based filtering
    - Multiple export formats (JSONL, Markdown, RAG)
    """
    
    def __init__(self, config: Optional[StorageConfig] = None):
        self.config = config or StorageConfig()
        
        # Initialize components
        self.deduplicator = ContentDeduplicator() if self.config.enable_deduplication else None
        self.db = SQLiteStorage(self.config.database_path)
        self.jsonl_path = Path(self.config.output_dir) / "crawl_output.jsonl"
        self.markdown_exporter = MarkdownExporter(
            str(Path(self.config.output_dir) / "markdown"),
            max_article_words=500
        )
        self.content_cleaner = ContentCleaner()
        
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._stats = {"stored": 0, "duplicates": 0, "errors": 0, "filtered": 0}
        
    def store(self, result: CrawlResult, export_markdown: bool = False) -> bool:
        """
        Store a crawl result
        
        Args:
            result: CrawlResult to store
            export_markdown: Also export to markdown file
            
        Returns:
            True if stored successfully
        """
        if not result.success:
            self._stats["errors"] += 1
            return False
            
        # Check for duplicates
        if self.deduplicator:
            if self.deduplicator.is_duplicate(result.content, result.url):
                self._stats["duplicates"] += 1
                logger.debug(f"Duplicate content: {result.url}")
                return False
            self.deduplicator.add(result.content, result.url)
            
        # Store in database
        if not self.db.store(result):
            self._stats["errors"] += 1
            return False
            
        # Export to markdown if requested
        if export_markdown:
            self.markdown_exporter.export(result)
            
        self._stats["stored"] += 1
        return True
        
    def store_streaming(self, result: CrawlResult):
        """Store with streaming output to JSONL"""
        if not result.success:
            return
            
        if self.deduplicator and self.deduplicator.is_duplicate(result.content, result.url):
            return
            
        if self.deduplicator:
            self.deduplicator.add(result.content, result.url)
            
        # Append to JSONL
        with JSONLinesStorage(str(self.jsonl_path)) as storage:
            storage.write(result)
            
        self._stats["stored"] += 1
        
    def store_batch(
        self,
        results: List[CrawlResult],
        export_combined_markdown: bool = True,
        min_quality_score: float = 0.3,
    ) -> int:
        """Store batch of results with quality filtering"""
        stored = 0
        
        for result in results:
            if self.store(result):
                stored += 1
                
        if export_combined_markdown:
            successful = [r for r in results if r.success]
            if successful:
                self.markdown_exporter.export_combined(
                    successful,
                    f"news_batch_{self._session_id}.md",
                    min_quality_score=min_quality_score,
                )
                
        return stored
        
    def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics"""
        db_stats = self.db.get_stats()
        return {
            **self._stats,
            "database": db_stats,
        }
        
    def url_exists(self, url: str) -> bool:
        """Check if URL already crawled"""
        return self.db.exists(url)
        
    def get_recent_articles(
        self,
        limit: int = 100,
        min_score: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """Get recent high-quality articles"""
        return self.db.get_recent(limit=limit, min_score=min_score)
        
    def export_for_rag(
        self,
        output_path: str,
        min_score: float = 0.3,
        clean_content: bool = True,
    ):
        """
        Export data in format suitable for RAG pipelines.
        
        Args:
            output_path: Path to output JSON file
            min_score: Minimum quality score
            clean_content: Whether to clean content before export
        """
        articles = self.db.get_recent(limit=10000, min_score=min_score)
        
        rag_data = []
        dedup = ContentDeduplicatorV2()
        
        for article in articles:
            url = article["url"]
            title = article["title"]
            content = article["content"] or article["markdown"] or ""
            
            # Skip non-article URLs
            if not self.content_cleaner.is_article_url(url):
                continue
            
            # Skip non-article titles
            if not self.content_cleaner.is_article_title(title):
                continue
            
            # Skip duplicates
            if dedup.is_duplicate(url, title, content):
                continue
            dedup.add(url, title, content)
            
            # Clean content if requested
            if clean_content:
                cleaned_content = self.content_cleaner.extract_article_content(
                    content, max_words=500
                )
                if not cleaned_content or len(cleaned_content.strip()) < 100:
                    continue
            else:
                cleaned_content = content
            
            # Calculate quality score
            _, quality_score = self.content_cleaner.is_quality_content(
                content, title, url
            )
            
            rag_data.append({
                "id": article["url_hash"] if "url_hash" in article else hashlib.sha256(url.encode()).hexdigest()[:16],
                "text": cleaned_content,
                "metadata": {
                    "title": title,
                    "url": url,
                    "source": article["source_domain"],
                    "date": article["crawled_at"],
                    "original_score": article["score"],
                    "quality_score": quality_score,
                }
            })
        
        # Sort by quality score
        rag_data.sort(key=lambda x: x["metadata"]["quality_score"], reverse=True)
            
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(rag_data, f, indent=2, ensure_ascii=False)
            
        logger.info(f"Exported {len(rag_data)} quality articles for RAG to {output_path}")
    
    def export_markdown_report(
        self,
        output_name: str = None,
        min_quality_score: float = 0.3,
        max_articles: int = 100,
    ) -> str:
        """
        Generate a quality markdown report from stored articles.
        
        Args:
            output_name: Output filename (auto-generated if None)
            min_quality_score: Minimum quality score to include
            max_articles: Maximum number of articles
            
        Returns:
            Path to generated file
        """
        if output_name is None:
            output_name = f"exported_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        
        # Get all articles from database
        articles = self.db.get_recent(limit=10000)
        
        # Convert to CrawlResult objects for the exporter
        results = []
        for article in articles:
            result = CrawlResult(
                url=article["url"],
                title=article["title"],
                content=article["content"] or "",
                markdown=article["markdown"] or "",
                metadata=json.loads(article["metadata"]) if article["metadata"] else {},
                depth=article["depth"] or 0,
                score=article["score"] or 0.0,
                crawled_at=datetime.fromisoformat(article["crawled_at"]) if article["crawled_at"] else datetime.now(),
                success=True,
                source_domain=article["source_domain"],
                language=article["language"],
            )
            results.append(result)
        
        return self.markdown_exporter.export_combined(
            results,
            output_name=output_name,
            min_quality_score=min_quality_score,
            max_articles=max_articles,
        )

