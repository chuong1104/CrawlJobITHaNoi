"""
utils — Tiện ích nội bộ cho tầng src/extract.

  regex_extractor.py — FallbackRegexExtractor: parse salary, skills, location
                        từ plain text khi scraper chính không lấy được structured data.
"""
from src.extract.utils.regex_extractor import FallbackRegexExtractor

__all__ = ["FallbackRegexExtractor"]
