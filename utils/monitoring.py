"""
Monitoring & Logging Utilities
"""
import logging
import time
import functools
import traceback
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
from pathlib import Path

# Create logs directory
Path("./logs").mkdir(exist_ok=True)


def setup_logging(
    log_level: str = "INFO",
    log_file: str = "./logs/crawler.log",
    console: bool = True,
):
    """
    Setup production logging configuration
    
    Args:
        log_level: Logging level
        log_file: Path to log file
        console: Enable console output
    """
    handlers = []
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8',
    ) if hasattr(logging, 'handlers') else logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)s | %(name)s | %(message)s'
    ))
    handlers.append(file_handler)
    
    # Console handler
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, log_level))
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%H:%M:%S'
        ))
        handlers.append(console_handler)
        
    # Configure root logger
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=handlers,
    )
    
    # Reduce noise from libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)


@dataclass
class CrawlMetrics:
    """Metrics for crawl operations"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_bytes: int = 0
    total_time_seconds: float = 0.0
    urls_per_second: float = 0.0
    errors_by_type: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    latencies: list = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests
        
    @property
    def avg_latency(self) -> float:
        if not self.latencies:
            return 0.0
        return sum(self.latencies) / len(self.latencies)
        
    @property
    def p95_latency(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_lat = sorted(self.latencies)
        idx = int(len(sorted_lat) * 0.95)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]


class MetricsCollector:
    """
    Collects and aggregates crawl metrics
    """
    
    def __init__(self):
        self.metrics = CrawlMetrics()
        self._start_time: Optional[float] = None
        self._request_times: Dict[str, float] = {}
        
    def start_session(self):
        """Start a new metrics session"""
        self._start_time = time.time()
        self.metrics = CrawlMetrics()
        
    def record_request_start(self, url: str):
        """Record start of a request"""
        self._request_times[url] = time.time()
        
    def record_request_end(
        self,
        url: str,
        success: bool,
        bytes_received: int = 0,
        error_type: Optional[str] = None,
    ):
        """Record end of a request"""
        self.metrics.total_requests += 1
        
        if success:
            self.metrics.successful_requests += 1
        else:
            self.metrics.failed_requests += 1
            if error_type:
                self.metrics.errors_by_type[error_type] += 1
                
        self.metrics.total_bytes += bytes_received
        
        # Calculate latency
        if url in self._request_times:
            latency = time.time() - self._request_times[url]
            self.metrics.latencies.append(latency)
            del self._request_times[url]
            
    def end_session(self):
        """End metrics session and calculate final stats"""
        if self._start_time:
            self.metrics.total_time_seconds = time.time() - self._start_time
            if self.metrics.total_time_seconds > 0:
                self.metrics.urls_per_second = (
                    self.metrics.total_requests / self.metrics.total_time_seconds
                )
                
    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary"""
        return {
            "total_requests": self.metrics.total_requests,
            "successful": self.metrics.successful_requests,
            "failed": self.metrics.failed_requests,
            "success_rate": f"{self.metrics.success_rate:.1%}",
            "total_bytes": f"{self.metrics.total_bytes / 1024 / 1024:.2f} MB",
            "total_time": f"{self.metrics.total_time_seconds:.1f}s",
            "urls_per_second": f"{self.metrics.urls_per_second:.2f}",
            "avg_latency": f"{self.metrics.avg_latency:.2f}s",
            "p95_latency": f"{self.metrics.p95_latency:.2f}s",
            "errors": dict(self.metrics.errors_by_type),
        }
        
    def print_summary(self):
        """Print formatted summary"""
        summary = self.get_summary()
        print("\n" + "=" * 50)
        print("📊 CRAWL METRICS SUMMARY")
        print("=" * 50)
        for key, value in summary.items():
            if key != "errors":
                print(f"  {key}: {value}")
        if summary["errors"]:
            print("  errors:")
            for err_type, count in summary["errors"].items():
                print(f"    - {err_type}: {count}")
        print("=" * 50)


class RateLimiter:
    """
    Rate limiter for respectful crawling
    """
    
    def __init__(
        self,
        requests_per_second: float = 1.0,
        per_domain: bool = True,
    ):
        self.delay = 1.0 / requests_per_second
        self.per_domain = per_domain
        self._last_request: Dict[str, float] = {}
        self._global_last: float = 0.0
        
    def _get_domain(self, url: str) -> str:
        """Extract domain from URL"""
        from urllib.parse import urlparse
        try:
            return urlparse(url).netloc
        except:
            return ""
            
    async def wait(self, url: str = ""):
        """Wait if needed to respect rate limit"""
        import asyncio
        
        now = time.time()
        
        if self.per_domain and url:
            domain = self._get_domain(url)
            last = self._last_request.get(domain, 0)
        else:
            last = self._global_last
            domain = ""
            
        elapsed = now - last
        if elapsed < self.delay:
            await asyncio.sleep(self.delay - elapsed)
            
        # Update last request time
        if domain:
            self._last_request[domain] = time.time()
        self._global_last = time.time()


class HealthChecker:
    """
    Health monitoring for crawler components
    """
    
    def __init__(self):
        self._component_status: Dict[str, Dict[str, Any]] = {}
        
    def update_status(
        self,
        component: str,
        healthy: bool,
        details: Optional[str] = None,
    ):
        """Update component health status"""
        self._component_status[component] = {
            "healthy": healthy,
            "last_check": datetime.now().isoformat(),
            "details": details,
        }
        
    def is_healthy(self) -> bool:
        """Check if all components are healthy"""
        return all(
            status["healthy"]
            for status in self._component_status.values()
        )
        
    def get_status(self) -> Dict[str, Any]:
        """Get full health status"""
        return {
            "overall": "healthy" if self.is_healthy() else "unhealthy",
            "components": self._component_status,
            "checked_at": datetime.now().isoformat(),
        }


def retry_async(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """
    Async retry decorator with exponential backoff
    
    Args:
        max_retries: Maximum retry attempts
        delay: Initial delay between retries
        backoff: Backoff multiplier
        exceptions: Exceptions to catch
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            import asyncio
            
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logging.warning(
                            f"Retry {attempt + 1}/{max_retries} for {func.__name__}: {e}"
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logging.error(
                            f"All {max_retries} retries failed for {func.__name__}: {e}"
                        )
                        
            raise last_exception
            
        return wrapper
    return decorator


def log_exceptions(logger: logging.Logger = None):
    """
    Decorator to log exceptions with full traceback
    """
    if logger is None:
        logger = logging.getLogger(__name__)
        
    def decorator(func: Callable):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(
                    f"Exception in {func.__name__}: {e}\n{traceback.format_exc()}"
                )
                raise
                
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(
                    f"Exception in {func.__name__}: {e}\n{traceback.format_exc()}"
                )
                raise
                
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
        
    return decorator


class ProgressReporter:
    """
    Progress reporting for long-running operations
    """
    
    def __init__(self, total: int, description: str = "Progress"):
        self.total = total
        self.current = 0
        self.description = description
        self.start_time = time.time()
        
    def update(self, amount: int = 1):
        """Update progress"""
        self.current += amount
        self._print_progress()
        
    def _print_progress(self):
        """Print progress bar"""
        if self.total == 0:
            return
            
        percent = self.current / self.total
        elapsed = time.time() - self.start_time
        
        if self.current > 0:
            eta = (elapsed / self.current) * (self.total - self.current)
        else:
            eta = 0
            
        bar_length = 30
        filled = int(bar_length * percent)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        print(
            f"\r{self.description}: [{bar}] {percent:.1%} "
            f"({self.current}/{self.total}) "
            f"ETA: {eta:.0f}s",
            end="",
            flush=True,
        )
        
        if self.current >= self.total:
            print()  # New line when complete
            
    def complete(self):
        """Mark as complete"""
        self.current = self.total
        self._print_progress()


# Import asyncio for type checking
import asyncio
