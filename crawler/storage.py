"""
Storage & Output Module - Handles persistence and export
"""
import json
import sqlite3
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any, Iterator
from dataclasses import asdict
from datetime import datetime
from contextlib import contextmanager

import sys
sys.path.append('..')
from config.settings import StorageConfig
from .core_engine import CrawlResult

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
    Export results to Markdown format for RAG pipelines
    """
    
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def _sanitize_filename(self, title: str) -> str:
        """Create safe filename from title"""
        # Remove invalid characters
        safe = "".join(c if c.isalnum() or c in ' -_' else '_' for c in title)
        safe = safe[:100].strip()
        return safe or "untitled"
        
    def export(self, result: CrawlResult, include_metadata: bool = True) -> str:
        """Export single result to markdown file"""
        filename = f"{self._sanitize_filename(result.title)}_{result.crawled_at.strftime('%Y%m%d_%H%M%S')}.md"
        filepath = self.output_dir / filename
        
        content = []
        
        # Front matter
        if include_metadata:
            content.append("---")
            content.append(f"title: {result.title}")
            content.append(f"url: {result.url}")
            content.append(f"source: {result.source_domain}")
            content.append(f"crawled_at: {result.crawled_at.isoformat()}")
            content.append(f"relevance_score: {result.score:.2f}")
            if result.language:
                content.append(f"language: {result.language}")
            content.append("---\n")
            
        # Title
        content.append(f"# {result.title}\n")
        
        # Source info
        content.append(f"**Source:** [{result.source_domain}]({result.url})")
        content.append(f"**Crawled:** {result.crawled_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # Main content
        content.append(result.markdown or result.content)
        
        # Write file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
            
        logger.debug(f"Exported: {filepath}")
        return str(filepath)
        
    def export_many(self, results: List[CrawlResult]) -> List[str]:
        """Export multiple results"""
        return [self.export(r) for r in results if r.success]
        
    def export_combined(
        self,
        results: List[CrawlResult],
        output_name: str = "combined_news.md",
    ) -> str:
        """Export all results to single combined file"""
        filepath = self.output_dir / output_name
        
        content = []
        content.append("# India News Compilation\n")
        content.append(f"Generated: {datetime.now().isoformat()}")
        content.append(f"Total Articles: {len(results)}\n")
        content.append("---\n")
        
        for i, result in enumerate(results, 1):
            if not result.success:
                continue
                
            content.append(f"## {i}. {result.title}\n")
            content.append(f"**Source:** [{result.source_domain}]({result.url})")
            content.append(f"**Score:** {result.score:.2f}\n")
            
            # Truncate content for combined file
            article_content = result.markdown or result.content
            if len(article_content) > 2000:
                article_content = article_content[:2000] + "\n\n*[Content truncated...]*"
            content.append(article_content)
            content.append("\n---\n")
            
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
            
        logger.info(f"Combined export: {filepath}")
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
    Unified storage manager combining all storage backends
    """
    
    def __init__(self, config: Optional[StorageConfig] = None):
        self.config = config or StorageConfig()
        
        # Initialize components
        self.deduplicator = ContentDeduplicator() if self.config.enable_deduplication else None
        self.db = SQLiteStorage(self.config.database_path)
        self.jsonl_path = Path(self.config.output_dir) / "crawl_output.jsonl"
        self.markdown_exporter = MarkdownExporter(
            str(Path(self.config.output_dir) / "markdown")
        )
        
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._stats = {"stored": 0, "duplicates": 0, "errors": 0}
        
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
    ) -> int:
        """Store batch of results"""
        stored = 0
        
        for result in results:
            if self.store(result):
                stored += 1
                
        if export_combined_markdown:
            successful = [r for r in results if r.success]
            if successful:
                self.markdown_exporter.export_combined(
                    successful,
                    f"news_batch_{self._session_id}.md"
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
        
    def export_for_rag(self, output_path: str, min_score: float = 0.5):
        """Export data in format suitable for RAG pipelines"""
        articles = self.db.get_recent(limit=10000, min_score=min_score)
        
        rag_data = []
        for article in articles:
            rag_data.append({
                "id": article["url_hash"] if "url_hash" in article else hashlib.sha256(article["url"].encode()).hexdigest()[:16],
                "text": article["content"],
                "metadata": {
                    "title": article["title"],
                    "url": article["url"],
                    "source": article["source_domain"],
                    "date": article["crawled_at"],
                    "score": article["score"],
                }
            })
            
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(rag_data, f, indent=2, ensure_ascii=False)
            
        logger.info(f"Exported {len(rag_data)} articles for RAG to {output_path}")
