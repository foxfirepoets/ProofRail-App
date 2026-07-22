"""Integration layer — System A outbox writers and System B intent endpoints.

Reference implementations for the STV Integration Layer (spec-stv-integration-layer-2026-06-29.md).
System A modules (outbox_writer, outbox_delivery_job, approval_signal, callback_router)
are reference implementations that System A's team integrates into their Railway service.
System B modules (intents_router, invoice_proof_gate, callback_sender) are built directly
into this codebase.

DB ownership:
  System A  -> ejxrbxoncsgglrqvjulg  (never touched by System B modules)
  System B  -> fdnwlcomuddzmluvbylg  (this codebase -- CLAUDE.md canonical store)
"""
