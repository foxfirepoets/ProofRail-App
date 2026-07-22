"""Summa Terra catalog ingest: parse the QB Import_Files CSVs and load them into the
canonical store (SPEC_SUMMA_TERRA_BINDING.md §13.4). The CSVs are the QB-upload-ready
source of truth; this package mirrors them 1:1, never reshapes them.
"""
