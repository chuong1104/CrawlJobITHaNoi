"""
Project-wide configuration — đọc từ .env / biến môi trường.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent
DATA_RAW_DIR = BASE_DIR / "data" / "raw"
DATA_PROCESSED_DIR = BASE_DIR / "data" / "processed"


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