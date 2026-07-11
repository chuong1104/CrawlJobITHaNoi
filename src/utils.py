"""
Shared utility functions dùng trong toàn bộ project.
"""
import hashlib
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# ANSI Color codes
# ---------------------------------------------------------------------------
_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_RED    = "\033[31m"
_CYAN   = "\033[36m"
_BLUE   = "\033[34m"
_MAGENTA= "\033[35m"
_WHITE  = "\033[97m"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
class _ColorFormatter(logging.Formatter):
    """Formatter với màu sắc theo level + icon emoji."""

    LEVEL_STYLES = {
        logging.DEBUG:    (_DIM,    "·"),
        logging.INFO:     (_CYAN,   ""),
        logging.WARNING:  (_YELLOW, ""),
        logging.ERROR:    (_RED,    ""),
        logging.CRITICAL: (_RED + _BOLD, ""),
    }

    def format(self, record: logging.LogRecord) -> str:
        color, icon = self.LEVEL_STYLES.get(record.levelno, ("", "·"))
        ts    = self.formatTime(record, "%H:%M:%S")
        name  = record.name.replace("scraper.", "")[:16].ljust(16)
        msg   = record.getMessage()

        # Highlight phase tags như [Phase 1], [Phase 2]...
        msg = re.sub(r"(\[Phase \d\])", _BOLD + r"\1" + _RESET + color, msg)
        msg = re.sub(r"(\[Batch \d+/\d+\])", _MAGENTA + r"\1" + _RESET + color, msg)

        line = (
            f"{_DIM}{ts}{_RESET} "
            f"{color}{icon} {_BOLD}{name}{_RESET} "
            f"{color}{msg}{_RESET}"
        )
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Tạo và cấu hình logger với stdout handler và color formatting.
    Gọi lại nhiều lần cùng tên thì trả về logger đã có (không thêm handler thứ hai).
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_ColorFormatter())
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


def suppress_noisy_loggers() -> None:
    """
    Tắt các logger rác từ thư viện bên thứ ba.
    Gọi 1 lần ở đầu script hoặc DAG.
    """
    noisy = [
        "scrapling",
        "urllib3",
        "urllib3.connectionpool",
        "selenium",
        "playwright",
        "asyncio",
        "httpx",
        "httpcore",
        "boto3",
        "botocore",
        "s3transfer",
        "dbt",
        "WDM",          # webdriver-manager
        "filelock",
        "charset_normalizer",
    ]
    for lib in noisy:
        logging.getLogger(lib).setLevel(logging.ERROR)
        logging.getLogger(lib).propagate = False


# ---------------------------------------------------------------------------
# Job ID
# ---------------------------------------------------------------------------
def generate_job_id(source: str, url: str) -> str:
    """
    Tạo job_id deterministic 16-char từ source + URL.
    SHA256(source::url)[:16] — đảm bảo idempotency khi upsert.
    """
    raw = f"{source}::{url.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------
def get_date_str(dt: Optional[datetime] = None) -> str:
    """Return YYYY-MM-DD string cho ngày đã cho (mặc định: hôm nay)."""
    return (dt or datetime.now()).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
from urllib.parse import urljoin


def make_absolute_url(url: str, base_url: str) -> str:
    """
    Đảm bảo URL là tuyệt đối.
    Sử dụng urljoin để ghép relative URL với base_url một cách chính xác.
    """
    return urljoin(base_url, url.strip())


def normalize_url(url: str) -> str:
    """Xóa query string và fragment dư thừa (chỉ giữ path)."""
    return re.split(r"[?#]", url.strip())[0]


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------
def ensure_dir(path: Path) -> Path:
    """Tạo thư mục nếu chưa có, trả về path."""
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------
def safe_strip(value: Optional[str]) -> Optional[str]:
    """Strip whitespace; trả về None nếu rỗng."""
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def truncate(text: str, max_len: int = 10_000) -> str:
    """Cắt text về max_len ký tự."""
    return text[:max_len] if text and len(text) > max_len else (text or "")


# ---------------------------------------------------------------------------
# Human-readable duration
# ---------------------------------------------------------------------------
def fmt_duration(seconds: float) -> str:
    """Chuyển số giây thành chuỗi dễ đọc: 1h 23m 45s hoặc 12.3s."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"