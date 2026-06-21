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
# Logging
# ---------------------------------------------------------------------------
_LOG_FORMAT = "%(asctime)s | %(name)-22s | %(levelname)-8s | %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Tạo và cấu hình logger với stdout handler.
    Gọi lại nhiều lần cùng tên thì trả về logger đã có (không thêm handler thứ hai).
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_LOG_FORMAT, _LOG_DATE_FORMAT))
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


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
# URL helpers
# ---------------------------------------------------------------------------
def make_absolute_url(url: str, base_url: str) -> str:
    """
    Đảm bảo URL là tuyệt đối.
    Nếu url đã có scheme (http/https) → giữ nguyên.
    Nếu url bắt đầu bằng '/' → ghép với base_url.
    """
    url = url.strip()
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        return base_url.rstrip("/") + url
    return url


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