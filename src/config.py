"""
Project-wide configuration — đọc từ .env / biến môi trường.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Xóa các biến proxy trống khỏi environment để tránh lỗi 'relative URL without a base' trong deltalake (Rust HTTP client)
for key in ["PROXY_URL", "PROXY_USERNAME", "PROXY_PASSWORD"]:
    if not os.environ.get(key):
        os.environ.pop(key, None)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent
DATA_BRONZE_DIR = BASE_DIR / "data" / "bronze"
DATA_SILVER_DIR = BASE_DIR / "data" / "silver"

# Gold — Delta Lake (primary storage, supports time-travel & ACID)
# Structure: data/gold/mart_bi/<table>/_delta_log/
DATA_GOLD_DIR   = BASE_DIR / "data" / "gold"

# Gold — Parquet fallback (flat files cho Power BI Desktop / quick access)
# Structure: data/mart_bi/<table>.parquet
#            data/mart_ml/<table>.parquet
# NOTE: Được tạo song song với Delta bởi gold_exporter.py.
#       Nếu chỉ dùng DuckDB/Power BI Service thì có thể bỏ fallback này.
DATA_MART_BI_DIR  = BASE_DIR / "data" / "mart_bi"
DATA_MART_ML_DIR  = BASE_DIR / "data" / "mart_ml"


# ---------------------------------------------------------------------------
# Scraper defaults
# ---------------------------------------------------------------------------
class ScraperConfig:
    MAX_RETRIES: int = int(os.getenv("SCRAPER_MAX_RETRIES", "3"))
    DELAY_MIN: float = float(os.getenv("SCRAPER_DELAY_MIN", "1.0"))
    DELAY_MAX: float = float(os.getenv("SCRAPER_DELAY_MAX", "3.0"))
    BATCH_SIZE: int = int(os.getenv("SCRAPER_BATCH_SIZE", "10"))
    PROXY_URL: str = os.getenv("PROXY_URL", "")

    @classmethod
    def delay_range(cls) -> tuple[float, float]:
        return (cls.DELAY_MIN, cls.DELAY_MAX)


# ---------------------------------------------------------------------------
# Proxy Config
# ---------------------------------------------------------------------------
class ProxyConfig:
    URL: str = os.getenv("PROXY_URL", "")
    USERNAME: str = os.getenv("PROXY_USERNAME", "")
    PASSWORD: str = os.getenv("PROXY_PASSWORD", "")


# ---------------------------------------------------------------------------
# AWS / Floci Config
# ---------------------------------------------------------------------------
class AWSConfig:
    ENDPOINT_URL: str = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
    ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "test")
    SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "test")
    DEFAULT_REGION: str = os.getenv("AWS_DEFAULT_REGION", "us-east-1")


# ---------------------------------------------------------------------------
# LinkedIn Credentials
# ---------------------------------------------------------------------------
class LinkedInConfig:
    USERNAME: str = os.getenv("LINKEDIN_USERNAME") or os.getenv("LINKEDIN_EMAIL", "")
    PASSWORD: str = os.getenv("LINKEDIN_PASSWORD") or os.getenv("LINKEDIN_PASS", "")


# ---------------------------------------------------------------------------
# ITViec Credentials
# ---------------------------------------------------------------------------
class ITViecConfig:
    EMAIL: str = os.getenv("ITVIEC_EMAIL", "")
    PASSWORD: str = os.getenv("ITVIEC_PASSWORD", "")


# ---------------------------------------------------------------------------
# Google Cloud Platform (BigQuery) Config
# ---------------------------------------------------------------------------
class GCPConfig:
    CREDENTIALS: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    PROJECT_ID: str = os.getenv("BIGQUERY_PROJECT_ID", "")
    DATASET: str = os.getenv("BIGQUERY_DATASET", "job_scraper")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
class DBConfig:
    HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    DB: str = os.getenv("POSTGRES_DB", "job_scraper_db")
    USER: str = os.getenv("POSTGRES_USER", "airflow")
    PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "airflow")

    @classmethod
    def url(cls) -> str:
        return (
            f"postgresql+psycopg2://{cls.USER}:{cls.PASSWORD}"
            f"@{cls.HOST}:{cls.PORT}/{cls.DB}"
        )

    @classmethod
    def dsn(cls) -> str:
        """Raw psycopg2 DSN string."""
        return (
            f"host={cls.HOST} port={cls.PORT} dbname={cls.DB} "
            f"user={cls.USER} password={cls.PASSWORD}"
        )


# ---------------------------------------------------------------------------
# Airflow-related
# ---------------------------------------------------------------------------
class AirflowConfig:
    SCRAPE_PAGES: int = int(os.getenv("SCRAPE_PAGES", "5"))
    DB_BATCH_SIZE: int = int(os.getenv("DB_BATCH_SIZE", "500"))