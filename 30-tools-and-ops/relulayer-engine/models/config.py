from __future__ import annotations

import os
from dataclasses import dataclass, field

# Model Assignments
ETL_MODEL = os.environ.get("ETL_MODEL", "qwen2.5-coder:32b")
GTM_MODEL = os.environ.get("GTM_MODEL", "gemma3:12b")

# Connection Defaults
# Host-side dev: use localhost. 
# Docker Compose: sets OLLAMA_HOST to http://host.docker.internal:11434.
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


def _resolve_base_url() -> str:
    """
    Determines the Ollama API endpoint by checking the OLLAMA_HOST 
    environment variable first, falling back to the local default.
    """
    url = os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_URL)
    return url.rstrip("/")


def image_synth_backend() -> str:
    """
    Layer 5 image synthesis: ``disabled`` | ``http`` | ``diffusers``.
    Use ``http`` for Automatic1111 / compatible API; ``diffusers`` for in-process SDXL/Flux.
    """
    return os.environ.get("RELULAYER_IMAGE_BACKEND", "disabled").strip().lower()


def image_synth_http_url() -> str:
    """Base URL for A1111-style ``POST /sdapi/v1/txt2img`` (no trailing slash)."""
    return os.environ.get("RELULAYER_IMAGE_HTTP_URL", "http://127.0.0.1:7860").rstrip("/")


def rag_embed_model() -> str:
    """Ollama embedding model for folder RAG (``ollama pull nomic-embed-text``)."""
    return os.environ.get("RELULAYER_EMBED_MODEL", "nomic-embed-text").strip()


def vision_ingest_enabled() -> bool:
    """Path L: PNG/JPG ingestion via local vision LLM (Ollama ``/api/chat``)."""
    return os.environ.get("RELULAYER_VISION_INGEST", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def vision_ingest_model() -> str:
    """Ollama vision model tag, e.g. ``llava``, ``llava:13b``, ``moondream``, ``gemma3`` variants with vision."""
    m = os.environ.get("RELULAYER_VISION_MODEL", "llava").strip()
    return m or "llava"


def vision_ingest_timeout_s() -> float:
    try:
        return max(30.0, float(os.environ.get("RELULAYER_VISION_TIMEOUT", "180")))
    except ValueError:
        return 180.0


def vision_ingest_max_image_bytes() -> int:
    try:
        mb = float(os.environ.get("RELULAYER_VISION_MAX_MB", "14"))
    except ValueError:
        mb = 14.0
    return int(max(1.0, mb) * 1024 * 1024)


def rag_max_files() -> int:
    return max(1, int(os.environ.get("RELULAYER_RAG_MAX_FILES", "200")))


def rag_chunk_chars() -> int:
    return max(200, int(os.environ.get("RELULAYER_RAG_CHUNK_CHARS", "1200")))


def rag_chunk_overlap() -> int:
    return max(0, min(rag_chunk_chars() // 2, int(os.environ.get("RELULAYER_RAG_CHUNK_OVERLAP", "200"))))


def graph_rag_enabled() -> bool:
    """Path X: LLM-built strategic knowledge graph over ``project_folder`` (JSON-LD-ish store)."""
    return os.environ.get("RELULAYER_GRAPH_RAG", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def graph_extract_model() -> str:
    """Ollama tag for entity/relation extraction (defaults to ``GTM_MODEL``)."""
    m = os.environ.get("RELULAYER_GRAPH_MODEL", GTM_MODEL).strip()
    return m or GTM_MODEL


def graph_extract_timeout_s() -> float:
    try:
        return max(60.0, float(os.environ.get("RELULAYER_GRAPH_EXTRACT_TIMEOUT", "300")))
    except ValueError:
        return 300.0


def graph_max_source_chars_per_batch() -> int:
    return max(2000, int(os.environ.get("RELULAYER_GRAPH_BATCH_CHARS", "10000")))


def graph_force_rebuild() -> bool:
    return os.environ.get("RELULAYER_GRAPH_FORCE", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def self_correction_max_slides() -> int:
    """Path Y: max slides refined in one autonomous pass after a REVISE judge verdict."""
    return max(1, int(os.environ.get("RELULAYER_SELF_CORRECT_MAX_SLIDES", "12")))


def success_benchmark_top_k() -> int:
    """Path AA: number of historical successes averaged for the confidence score."""
    return max(1, min(10, int(os.environ.get("RELULAYER_SUCCESS_BENCHMARK_TOP_K", "3"))))


def success_benchmark_embed_cap() -> int:
    """Path AA: max success-store rows embedded per draft (rest skipped after lexical pre-rank)."""
    return max(16, min(200, int(os.environ.get("RELULAYER_SUCCESS_BENCHMARK_EMBED_CAP", "64"))))


def image_synth_diffusion_model_id() -> str:
    """Hugging Face model id when ``RELULAYER_IMAGE_BACKEND=diffusers``."""
    return os.environ.get(
        "RELULAYER_DIFFUSION_MODEL_ID",
        "stabilityai/stable-diffusion-xl-base-1.0",
    )


@dataclass(frozen=True)
class EngineConfig:
    """
    Maps workflow roles to local Ollama models and the resolved API base.
    Provides a centralized 'Glass Box' configuration for the engine.
    """
    etl_model: str = ETL_MODEL
    gtm_model: str = GTM_MODEL
    base_url: str = field(default_factory=_resolve_base_url)

# Global instance for easy access across the orchestration layer
config = EngineConfig()