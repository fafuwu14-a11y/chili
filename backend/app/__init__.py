"""Backend package for the 赤鲤 · 高考志愿辅助平台 demo."""

from .mock_data import DATA_SOURCE, TARGET_YEAR, YEARS, build_dataset  # noqa: F401
from .predictor import Dataset, TIER_BAO, TIER_CHONG, TIER_WEN  # noqa: F401

__all__ = [
    "Dataset",
    "build_dataset",
    "DATA_SOURCE",
    "TARGET_YEAR",
    "YEARS",
    "TIER_CHONG",
    "TIER_WEN",
    "TIER_BAO",
]
