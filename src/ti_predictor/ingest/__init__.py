"""Deterministic external-data ingestion."""

from ti_predictor.ingest.opendota import OpenDotaClient, SyncResult, sync_opendota

__all__ = ["OpenDotaClient", "SyncResult", "sync_opendota"]
