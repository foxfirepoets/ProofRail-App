"""CHUNK_8_SCALE — multi-company read sync, the swappable-adapter QBO stub, and the
end-to-end approved + proof-signed payable pipeline (the 90-day MVP capstone).

Public surface:
    from app.scale import MultiCompanySync, QBOAdapter, run_payable_pipeline, PipelineResult
"""
from __future__ import annotations

from app.scale.pipeline import PipelineResult, run_payable_pipeline
from app.scale.qbo_adapter import QBOAdapter
from app.scale.sync import DEFAULT_COMPANY_FILES, MultiCompanySync

__all__ = [
    "DEFAULT_COMPANY_FILES",
    "MultiCompanySync",
    "PipelineResult",
    "QBOAdapter",
    "run_payable_pipeline",
]
