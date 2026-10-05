from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib.util
import io
import json
import logging
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
from collections.abc import Callable
from typing import Any, Literal

import importlib
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image, ImageDraw, ImageFont

from infrastructure.vram_manager import VRAMManager
from knowledge.ingestion import IngestionEngine, IngestionFile, SuccessStore
from models.config import (
    config as engine_runtime_config,
    graph_rag_enabled,
    image_synth_backend,
    image_synth_http_url,
    rag_embed_model,
    self_correction_max_slides,
)
from orchestration.dspy_modules.modules import (
    ChairmanResolutionOrchestrator,
    ComplianceAuditorOrchestrator,
    ContradictionClassifierOrchestrator,
    DataAuditorOrchestrator,
    ETLOrchestrator,
    ExecutiveBriefingOrchestrator,
    GTM_CONSENSUS_PERSONA_ORDER,
    GTMOrchestrator,
    RedTeamAuditorOrchestrator,
    SlideRefinementOrchestrator,
    StrategicJudgeOrchestrator,
    StrategicSimulator,
    StrategicWargameOrchestrator,
    execute_data_audit_script,
)
from tools.narrative_tts import piper_synthesize_wav
from tools.pptx_builder import assemble_deck
from tools.site_builder import build_executive_microsite
from tools.web_search import fetch_live_grounding
from tools.visual_generator import (
    build_financial_appendix_for_materialize,
    build_video_brief,
    generate_flux_image,
    generate_slide_theme_icon_assets,
    process_raster_image,
    render_slide_chart_from_spec,
    slide_asset_path,
    synth_hero_asset_path,
)

logger = logging.getLogger("relulayer.switchboard")

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Path Q — collaborative strategy rooms: JSON “DB” (one file per session).
_STRATEGY_SESSIONS_DIR = _REPO_ROOT / "memory" / "strategy_sessions"
_STRATEGY_SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_ingestion = IngestionEngine(project_root=_REPO_ROOT)
_success_store = SuccessStore(project_root=_REPO_ROOT)
_gtm = GTMOrchestrator()
_gtm_refine = SlideRefinementOrchestrator()
_strategic_judge = StrategicJudgeOrchestrator()
_red_team = RedTeamAuditorOrchestrator()
_wargame = StrategicWargameOrchestrator()
_chairman = ChairmanResolutionOrchestrator()
_compliance = ComplianceAuditorOrchestrator()
_contradiction_classifier = ContradictionClassifierOrchestrator()
_executive_briefing = ExecutiveBriefingOrchestrator()
_data_auditor = DataAuditorOrchestrator()
_strategic_sim = StrategicSimulator()
_etl = ETLOrchestrator()

app = FastAPI(
    title="ReluLayer Engine",
    description="Ingestion → DSPy → deterministic tools (GTM split: draft / materialize).",
    version="0.2.0",
)

# Repo `assets/` (outputs/, generated/, etc.) at /static for React downloads, e.g.
# GET /static/outputs/<file>.pptx — path must be absolute; plain "assets" is cwd-relative.
_ASSETS_STATIC_DIR = _REPO_ROOT / "assets"
_ASSETS_STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/static",
    StaticFiles(directory=str(_ASSETS_STATIC_DIR)),
    name="static",
)

# Browsers reject allow_origins=["*"] together with allow_credentials=True.
# Default: permissive dev CORS without credentials. Set CORS_ORIGINS + CORS_ALLOW_CREDENTIALS=true for cookies.
_cors_origins = [
    o.strip()
    for o in os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://[::1]:5173",
    ).split(",")
    if o.strip()
]
_cors_credentials = os.environ.get("CORS_ALLOW_CREDENTIALS", "").lower() in (
    "1",
    "true",
    "yes",
)
if _cors_origins and _cors_credentials:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
elif _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# --- Production health (Path PP) -----------------------------------------------


class HealthComponent(BaseModel):
    ok: bool
    detail: str = ""


class GpuHealth(BaseModel):
    ok: bool
    detail: str = ""
    name: str | None = None
    memory_used_mb: int | None = None
    memory_total_mb: int | None = None


class DegradedPathItem(BaseModel):
    path_id: str
    label: str
    reason: str
    severity: Literal["warn", "error"] = "warn"


class ProductionHealthResponse(BaseModel):
    version: str = "path_pp_1"
    status: Literal["healthy", "degraded", "critical"]
    ollama: HealthComponent
    ollama_base_url: str
    gtm_model: str
    gtm_model_listed: bool | None = None
    gpu: GpuHealth
    ffmpeg: HealthComponent
    piper: HealthComponent
    sadtalker: HealthComponent
    image_synthesis: HealthComponent
    matplotlib: HealthComponent
    degraded_paths: list[DegradedPathItem]


def _health_check_ollama(base_url: str, gtm_model: str) -> tuple[bool, str, bool | None]:
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            raw = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code} from Ollama tags", None
    except urllib.error.URLError as e:
        return False, f"unreachable: {e.reason!s}", None
    except Exception as e:
        return False, str(e)[:300], None
    models = raw.get("models") or []
    names: list[str] = []
    for m in models:
        if isinstance(m, dict) and m.get("name"):
            names.append(str(m["name"]))
    if not gtm_model:
        return True, "reachable", None
    listed = any(gtm_model == n or gtm_model in n or n in gtm_model for n in names)
    if not listed:
        return (
            True,
            f"reachable; GTM model {gtm_model!r} not found in tags ({len(names)} models)",
            False,
        )
    return True, "reachable", True


def _health_check_nvidia_gpu() -> GpuHealth:
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )
    except FileNotFoundError:
        return GpuHealth(ok=False, detail="nvidia-smi not found (no NVIDIA driver in PATH)")
    except subprocess.TimeoutExpired:
        return GpuHealth(ok=False, detail="nvidia-smi timed out")
    except Exception as e:
        return GpuHealth(ok=False, detail=str(e)[:300])
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:300]
        return GpuHealth(ok=False, detail=err or f"exit {proc.returncode}")
    line = (proc.stdout or "").strip().split("\n")[0].strip()
    if not line:
        return GpuHealth(ok=False, detail="empty nvidia-smi output")
    parts = [p.strip() for p in line.split(",")]
    try:
        name = parts[0] if parts else ""
        used = int(float(parts[1])) if len(parts) > 1 else None
        total = int(float(parts[2])) if len(parts) > 2 else None
    except (ValueError, IndexError):
        return GpuHealth(ok=True, detail=line, name=line)
    return GpuHealth(
        ok=True,
        detail=line,
        name=name or None,
        memory_used_mb=used,
        memory_total_mb=total,
    )


def _health_check_ffmpeg() -> HealthComponent:
    path = shutil.which("ffmpeg")
    if not path:
        return HealthComponent(ok=False, detail="ffmpeg not on PATH")
    return HealthComponent(ok=True, detail=path)


def _health_check_piper() -> HealthComponent:
    raw = os.environ.get("RELULAYER_PIPER_MODEL", "").strip()
    if not raw:
        return HealthComponent(ok=False, detail="RELULAYER_PIPER_MODEL unset")
    p = Path(raw).expanduser()
    if not p.is_file():
        return HealthComponent(ok=False, detail=f"model file missing: {raw}")
    bin_hint = os.environ.get("RELULAYER_PIPER_BIN", "piper").strip() or "piper"
    if Path(bin_hint).is_file():
        return HealthComponent(ok=True, detail=f"model={raw}; bin={bin_hint}")
    if shutil.which(bin_hint) or shutil.which(Path(bin_hint).name):
        return HealthComponent(ok=True, detail=f"model={raw}; bin={bin_hint}")
    return HealthComponent(
        ok=False,
        detail=f"model file ok but piper binary not found ({bin_hint})",
    )


def _health_check_sadtalker() -> HealthComponent:
    raw = os.environ.get("RELULAYER_SADTALKER_DIR", "").strip()
    if not raw:
        return HealthComponent(ok=False, detail="RELULAYER_SADTALKER_DIR unset")
    p = Path(raw).expanduser()
    if not p.is_dir():
        return HealthComponent(ok=False, detail=f"not a directory: {raw}")
    return HealthComponent(ok=True, detail=str(p.resolve()))


def _health_check_image_synthesis() -> HealthComponent:
    backend = image_synth_backend()
    if backend == "disabled":
        return HealthComponent(ok=False, detail="RELULAYER_IMAGE_BACKEND=disabled")
    if backend == "http":
        base = image_synth_http_url()
        try:
            req = urllib.request.Request(
                f"{base}/sdapi/v1/sd-models",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status != 200:
                    return HealthComponent(
                        ok=False,
                        detail=f"A1111 HTTP {resp.status} at {base}",
                    )
        except Exception as e:
            return HealthComponent(
                ok=False,
                detail=f"http backend unreachable ({base}): {e}"[:400],
            )
        return HealthComponent(ok=True, detail=f"http backend ok ({base})")
    if backend == "diffusers":
        gh = _health_check_nvidia_gpu()
        if not gh.ok:
            return HealthComponent(
                ok=False,
                detail="diffusers requires CUDA; GPU check failed",
            )
        return HealthComponent(
            ok=True,
            detail=f"diffusers; GPU {gh.name or 'ok'}",
        )
    return HealthComponent(ok=False, detail=f"unknown backend {backend!r}")


def _health_check_matplotlib() -> HealthComponent:
    if importlib.util.find_spec("matplotlib") is None:
        return HealthComponent(ok=False, detail="matplotlib not installed")
    return HealthComponent(ok=True, detail="importable")


@app.get("/health", response_model=ProductionHealthResponse)
def production_health() -> ProductionHealthResponse:
    """
    Path PP: production readiness — Ollama, GPU VRAM, FFmpeg, Piper model file,
    SadTalker repo dir, image stack, and chart rendering deps; plus degraded UX paths.
    """
    base = engine_runtime_config.base_url
    gtm_model = engine_runtime_config.gtm_model
    o_ok, o_detail, listed = _health_check_ollama(base, gtm_model)
    ollama = HealthComponent(ok=o_ok, detail=o_detail)

    gpu = _health_check_nvidia_gpu()
    ffmpeg = _health_check_ffmpeg()
    piper = _health_check_piper()
    sadtalker = _health_check_sadtalker()
    image_syn = _health_check_image_synthesis()
    mpl = _health_check_matplotlib()

    degraded: list[DegradedPathItem] = []
    if not ollama.ok:
        degraded.append(
            DegradedPathItem(
                path_id="draft_gtm",
                label="GTM draft & judges (DSPy)",
                reason=ollama.detail or "Ollama unreachable",
                severity="error",
            )
        )
    elif listed is False:
        degraded.append(
            DegradedPathItem(
                path_id="draft_gtm_model",
                label="GTM draft model",
                reason=ollama.detail,
                severity="warn",
            )
        )
    if not gpu.ok:
        degraded.append(
            DegradedPathItem(
                path_id="compute_gpu",
                label="GPU / VRAM (5090-class)",
                reason=gpu.detail,
                severity="warn",
            )
        )
    elif gpu.name and "5090" not in gpu.name:
        degraded.append(
            DegradedPathItem(
                path_id="compute_gpu_class",
                label="GPU class (expected RTX 5090)",
                reason=f"Detected {gpu.name!r}; production profile targets RTX 5090.",
                severity="warn",
            )
        )
    if not ffmpeg.ok:
        degraded.append(
            DegradedPathItem(
                path_id="video_encode",
                label="Video brief (slideshow / mux)",
                reason=ffmpeg.detail,
                severity="warn",
            )
        )
    if not piper.ok:
        degraded.append(
            DegradedPathItem(
                path_id="rehearsal_tts",
                label="Executive rehearsal (server Piper WAV)",
                reason=piper.detail,
                severity="warn",
            )
        )
    if not sadtalker.ok:
        degraded.append(
            DegradedPathItem(
                path_id="video_sadtalker",
                label="Video brief (SadTalker tier)",
                reason=sadtalker.detail,
                severity="warn",
            )
        )
    if not image_syn.ok:
        degraded.append(
            DegradedPathItem(
                path_id="slide_heroes",
                label="Slide hero / image synthesis",
                reason=image_syn.detail,
                severity="warn",
            )
        )
    if not mpl.ok:
        degraded.append(
            DegradedPathItem(
                path_id="data_charts",
                label="Data charts (matplotlib fallback)",
                reason=mpl.detail,
                severity="warn",
            )
        )

    if not ollama.ok:
        status: Literal["healthy", "degraded", "critical"] = "critical"
    elif degraded:
        # Only model-mismatch or GPU-class hints: still "degraded"
        status = "degraded"
    else:
        status = "healthy"

    return ProductionHealthResponse(
        status=status,
        ollama=ollama,
        ollama_base_url=base,
        gtm_model=gtm_model,
        gtm_model_listed=listed,
        gpu=gpu,
        ffmpeg=ffmpeg,
        piper=piper,
        sadtalker=sadtalker,
        image_synthesis=image_syn,
        matplotlib=mpl,
        degraded_paths=degraded,
    )


# --- Request / response models -------------------------------------------------


GtmPersonaId = Literal["venture_capital", "govtech", "risk_auditor", "consensus"]
AuditSeverity = Literal["low", "medium", "high"]


class AuditRiskItem(BaseModel):
    point: str = Field(description="Weak point or strategic risk.")
    severity: AuditSeverity = Field(
        default="medium",
        description="Impact: low (nit), medium (material), high (logic / credibility gap).",
    )


class RedTeamAuditReport(BaseModel):
    weak_points: list[AuditRiskItem] = Field(default_factory=list)
    red_team_alert: bool = Field(
        default=False,
        description="True when material gaps: any high severity, or two+ medium/high issues.",
    )
    rationale: str | None = Field(
        default=None,
        description="Auditor chain-of-thought when exposed by the module.",
    )


class GTMRequest(BaseModel):
    user_prompt: str = Field(..., min_length=1)
    file_paths: list[str] = Field(
        default_factory=list,
        description=(
            "Repo-relative files for ingestion: tabular, PDF, JSON, PPTX template, "
            "and raster images (PNG/JPG/WebP) described by a local Ollama vision model (Path L)."
        ),
    )
    project_folder: str = Field(
        default="",
        description=(
            "Optional repo-relative folder for recursive multi-document RAG; "
            "top-5 snippets ranked vs user_prompt (Ollama embeddings, lexical fallback). "
            "Path X: same folder also drives an LLM-extracted strategic knowledge graph "
            "(entities/relations) merged into context when RELULAYER_GRAPH_RAG is enabled."
        ),
    )
    persona: GtmPersonaId = Field(
        default="govtech",
        description=(
            "Strategic persona, or ``consensus`` to run VC + GovTech + Risk sequentially "
            "then StrategySynthesisSignature for one master deck."
        ),
    )
    web_grounding: bool = Field(
        default=True,
        description=(
            "When True, run live web/news search (Tavily or Serper) from the strategic directive "
            "and inject snippets into context. Requires API key env vars."
        ),
    )
    self_correction: bool = Field(
        default=False,
        description=(
            "Path Y: after the initial draft, run the Strategic Judge; on verdict ``revise`` with any "
            "rubric dimension below 7, run one autonomous SlideRefinement pass on selected slides "
            "using the judge's auditor_rationale before returning the draft."
        ),
    )
    wargame_debate: bool = Field(
        default=False,
        description=(
            "Path BB: after Red Team audit, run a 3-round Adversary vs Proponent wargame on the deck "
            "and attach residual risks to telemetry."
        ),
    )
    compliance_pass: bool = Field(
        default=False,
        description="Path II: run a compliance benchmarking pass against the selected standard and attach findings to telemetry.",
    )
    compliance_standard: str = Field(
        default="NIST CSF",
        description="Path II: compliance standard/framework label (e.g. NIST CSF, ISO 27001, ESG).",
    )


class ConsensusPersonaTurn(BaseModel):
    """One sub-draft LM pass inside ``persona=consensus`` mode."""

    persona: str
    raw_prompt: str = ""
    raw_completion: str = ""
    history_turns: int = 0


class LiveGroundingSnippet(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""


class DataAuditTelemetry(BaseModel):
    """Path R — empirical Python audit over attached CSV/Excel before GTM draft."""

    triggered: bool = Field(
        False,
        description="True when tabular files were present and heuristics/env selected an audit run.",
    )
    ran: bool = Field(
        False,
        description="True after the subprocess attempted to run the generated script.",
    )
    skip_reason: str | None = Field(
        default=None,
        description="Why no audit chunk was injected (no files, heuristic, LM error, etc.).",
    )
    audit_plan_excerpt: str = ""
    script_excerpt: str = ""
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    return_code: int | None = None
    lm_raw_prompt_excerpt: str = ""
    lm_raw_completion_excerpt: str = ""


class HistoricalBenchmarkMatch(BaseModel):
    """Path AA: one row from success_store.jsonl in the top-k similarity set."""

    prompt_excerpt: str = ""
    similarity: float = Field(
        0.0,
        description="Cosine similarity in [-1,1] (embedding mode) or lexical Dice in [0,1] (fallback).",
    )
    entry_id_prefix: str = ""
    persona: str = ""


class HistoricalBenchmarkTelemetry(BaseModel):
    """Path AA: Historical Confidence Score vs recorded successful materializations."""

    confidence_percent: int = Field(0, ge=0, le=100)
    mode: str = Field(
        "",
        description="embedding | lexical_fallback | unavailable | insufficient_history",
    )
    reference_label: str = Field(
        "",
        description="Short label for the strongest-matching historical directive.",
    )
    mean_top_k_similarity: float | None = Field(
        default=None,
        description="Mean similarity across the top-k historical decks (raw score, mode-dependent).",
    )
    top_matches: list[HistoricalBenchmarkMatch] = Field(default_factory=list)
    display_hint: str = Field(
        "",
        description="One-line copy for the strategist UI.",
    )


class WargameDebateTurnTelemetry(BaseModel):
    """Path BB: one round — adversary attack and proponent mitigation."""

    turn: int = Field(..., ge=1, le=3)
    adversary_attack: str = ""
    proponent_mitigation: str = ""


class WargameAuditTelemetry(BaseModel):
    """Path BB: adversarial wargame transcript and residual strategic risks."""

    skipped_reason: str = Field(
        "",
        description="Empty when the wargame ran; otherwise no_slides, orchestrator_error, etc.",
    )
    turns: list[WargameDebateTurnTelemetry] = Field(default_factory=list)
    residual_risks: list[AuditRiskItem] = Field(default_factory=list)
    residual_headline: str = ""
    wargame_alert: bool = Field(
        False,
        description="True when residual risks are material (same heuristic as Red Team alert).",
    )


class ComplianceFindingSuggestedCopy(BaseModel):
    title: str = ""
    body: str = ""
    speaker_notes: str = ""


class ComplianceFinding(BaseModel):
    slide_index: int = Field(ge=0)
    issue: str = ""
    standard_clause: str = ""
    severity: AuditSeverity = Field(
        default="medium",
        description="Impact: low (nit), medium (material), high (compliance blocker).",
    )
    suggested_copy: ComplianceFindingSuggestedCopy = Field(
        default_factory=ComplianceFindingSuggestedCopy,
    )


class CompliancePassTelemetry(BaseModel):
    """Path II: Compliance benchmarking findings over the draft deck."""

    standard: str = ""
    summary: str = ""
    findings: list[ComplianceFinding] = Field(default_factory=list)
    skipped_reason: str = Field(default="", description="Empty when the pass ran; otherwise disabled/no_slides/error.")


class StructuralSentinelAlertTelemetry(BaseModel):
    """Path KK / Path OO: slide count and/or original_id integrity after Chairman or Self-Correction."""

    type: Literal["structural_drift_alert", "structural_identity_drift"] = "structural_drift_alert"
    stage: str = Field(
        ...,
        description="path_ff_chairman | path_y_self_correction | path_e_refine",
    )
    original_slide_count: int = Field(ge=0)
    revised_slide_count: int = Field(ge=0)
    detail: str = Field(default="", description="Why the revision was rejected.")
    identity_missing_ids: list[str] = Field(
        default_factory=list,
        description="Path OO: consensus original_id values absent after revision (or slot markers).",
    )
    identity_duplicate_ids: list[str] = Field(
        default_factory=list,
        description="Path OO: original_id values that appeared more than once.",
    )


class LiveGroundingData(BaseModel):
    """Telemetry: Live Grounding Data (Path K — real-time web/news snippets)."""

    active: bool = Field(
        False,
        description="True when snippets were retrieved and injected into draft context.",
    )
    provider: str = Field(
        "",
        description="tavily | serper | none | disabled | error",
    )
    search_query_used: str = ""
    snippet_count: int = 0
    snippets: list[LiveGroundingSnippet] = Field(default_factory=list)
    error: str | None = Field(
        default=None,
        description="Set when grounding was attempted but failed or was skipped with reason.",
    )


class GTMTelemetry(BaseModel):
    """Glass-box trace for the last DSPy → Ollama turn(s)."""

    rationale: str | None = Field(
        default=None,
        description="Chain-of-thought rationale field from the GTM module, if present.",
    )
    raw_prompt: str = Field(
        default="",
        description="Serialized chat messages (or text prompt) sent to the LM.",
    )
    raw_completion: str = Field(
        default="",
        description="Raw LM outputs / response payload from history.",
    )
    history_turns: int = Field(
        default=0,
        description="Number of global LM history entries merged into raw_* fields.",
    )
    audit_report: RedTeamAuditReport | None = Field(
        default=None,
        description="Red-team audit of draft vs Strategic Directive (second LM pass on /draft).",
    )
    audit_raw_prompt: str = Field(
        default="",
        description="Auditor LM request payload (glass-box).",
    )
    audit_raw_completion: str = Field(
        default="",
        description="Auditor LM completion (glass-box).",
    )
    consensus_persona_turns: list[ConsensusPersonaTurn] = Field(
        default_factory=list,
        description="Populated when persona=consensus: one trace per VC/GovTech/Risk sub-draft.",
    )
    live_grounding_data: LiveGroundingData | None = Field(
        default=None,
        description="Live web/news grounding merged into draft context (Path K).",
    )
    data_audit: DataAuditTelemetry | None = Field(
        default=None,
        description="Optional code-interpreter audit over tabular attachments (Path R).",
    )
    graph_mode: str | None = Field(
        default=None,
        description="Path X: strategic KG mode (disabled | cache_hit | rebuilt | etc.).",
    )
    graph_cache_hit: bool | None = Field(
        default=None,
        description="True when the folder graph was loaded from disk cache.",
    )
    graph_entities_total: int | None = Field(
        default=None,
        description="Total entities in the stored graph for project_folder.",
    )
    graph_subgraph_entities: int | None = Field(
        default=None,
        description="Entities included in the query-aligned subgraph injected into context.",
    )
    graph_subgraph_relations: int | None = Field(
        default=None,
        description="Relations included in the query-aligned subgraph.",
    )
    self_correction_applied: bool = Field(
        default=False,
        description="Path Y: true when at least one slide was refined after a REVISE + low rubric judge pass.",
    )
    self_correction_skipped_reason: str = Field(
        default="",
        description="Path Y: why auto-refine did not run (e.g. disabled, proceed, scores_ok, judge_error).",
    )
    self_correction_judge_verdict: str | None = Field(
        default=None,
        description="Path Y: judge verdict when self_correction was requested.",
    )
    self_correction_rubric_clarity: int | None = None
    self_correction_rubric_feasibility: int | None = None
    self_correction_rubric_strategic_impact: int | None = None
    self_correction_slides_refined: int = Field(
        default=0,
        ge=0,
        description="Path Y: number of slides passed through SlideRefinementOrchestrator.",
    )
    historical_benchmark: HistoricalBenchmarkTelemetry | None = Field(
        default=None,
        description="Path AA: similarity of this draft to top-k entries in success_store.jsonl.",
    )
    wargame_audit: WargameAuditTelemetry | None = Field(
        default=None,
        description="Path BB: Blue vs Red debate + residual risks after Red Team.",
    )
    compliance_pass: CompliancePassTelemetry | None = Field(
        default=None,
        description="Path II: compliance benchmarking pass against a selected standard.",
    )
    structural_sentinel_alerts: list[StructuralSentinelAlertTelemetry] = Field(
        default_factory=list,
        description="Path KK/OO: alerts when slide count or original_id identity breaks after Path FF, Path Y, or Path E.",
    )


class GTMDraftResponse(BaseModel):
    """Raw slide definitions from DSPy (Layer 3); Layer 5 runs in /materialize."""

    slides: list[dict[str, Any]]
    design_specs: dict[str, Any] | None = None
    template_hint: str | None = Field(
        default=None,
        description="Path to ingested .pptx template when ingestion saved one.",
    )
    telemetry: GTMTelemetry


class GTMRefineWarRoomContext(BaseModel):
    """Path U: require an active slide lock for this strategist in the war room."""

    session_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    slide_index: int = Field(..., ge=0)


class GTMRefineRequest(BaseModel):
    """Layer 6: iterative dialogue on one slide."""

    slide: dict[str, Any] = Field(
        ...,
        description="Current slide object (title, body, image_prompt, etc.).",
    )
    refinement_instruction: str = Field(
        ...,
        min_length=1,
        description="Strategist instruction, e.g. tone or emphasis change.",
    )
    war_room: GTMRefineWarRoomContext | None = Field(
        default=None,
        description="When set, /refine returns 409 unless this user holds the slide lock in the room.",
    )


class GTMRefineResponse(BaseModel):
    slide: dict[str, Any]
    telemetry: GTMTelemetry


class StrategicJudgeRubricScores(BaseModel):
    """Path V: Executive Committee rubric (1–10 each)."""

    clarity: int = Field(..., ge=1, le=10)
    feasibility: int = Field(..., ge=1, le=10)
    strategic_impact: int = Field(..., ge=1, le=10)


class GTMStrategicJudgeRequest(BaseModel):
    """Path V: score current deck before materialization gate."""

    user_prompt: str = Field(
        default="",
        description="Original strategic directive (same intent as GTM draft).",
    )
    slides: list[dict[str, Any]] = Field(
        ...,
        description="Current slide objects under review (consensus or single-persona draft).",
    )


class GTMStrategicJudgeResponse(BaseModel):
    scores: StrategicJudgeRubricScores
    committee_verdict: str = Field(
        description='Normalized: "proceed" | "revise" | "reject".',
    )
    auditor_rationale: str = ""
    telemetry: GTMTelemetry


class GTMMaterializeRequest(BaseModel):
    slides: list[dict[str, Any]]
    template_path: str = Field(..., min_length=1)
    design_specs: dict[str, Any] | None = None


class MaterializeStructuralAdjustment(BaseModel):
    """Path M: one layout overflow fix from ``pptx_builder`` structural auditor."""

    slide_index: int = Field(ge=0)
    role: str = Field(description="title | body | subtitle | notes")
    action: str = Field(description="font_scale_down | smart_truncate")
    message: str = Field(description="Human-readable explanation for glass-box UI.")


class MaterializationStructuralTelemetry(BaseModel):
    """Path M — materialization structural audit (placeholder overflow heuristics)."""

    audit_enabled: bool = Field(
        default=True,
        description="False when RELULAYER_STRUCTURAL_AUDIT is off.",
    )
    checks_performed: int = Field(
        default=0,
        ge=0,
        description="Placeholder/notes shapes evaluated for overflow.",
    )
    adjustments: list[MaterializeStructuralAdjustment] = Field(default_factory=list)


class GTMMaterializeResponse(BaseModel):
    pptx_path: str
    structural_telemetry: MaterializationStructuralTelemetry = Field(
        default_factory=MaterializationStructuralTelemetry,
        description="Layout overflow auditor: font scaling / smart truncate (Path M).",
    )
    financial_appendix_path: str | None = Field(
        default=None,
        description="Path CC: absolute path to companion Excel workbook under assets/outputs/, if built.",
    )


class GTMMicrositeRequest(BaseModel):
    """Path Z: deck JSON → single-file HTML under ``/static/outputs/sites/``."""

    slides: list[dict[str, Any]]
    page_title: str = Field(
        default="Executive briefing",
        max_length=240,
        description="HTML document title and H1 heading.",
    )
    subtitle: str = Field(
        default="",
        max_length=4000,
        description="Optional strapline under the title.",
    )
    user_prompt: str = Field(
        default="",
        description="When ``subtitle`` is empty, first ~400 chars used as subtitle.",
    )


class GTMMicrositeResponse(BaseModel):
    html_path: str = Field(description="Absolute path to the written .html file on the server.")
    static_href: str = Field(
        description="Browser path under the API host, e.g. ``/static/outputs/sites/microsite_….html``.",
    )


class GTMMemoryRecordRequest(BaseModel):
    user_prompt: str = Field(..., min_length=1)
    persona: str = Field(default="govtech")
    slides: list[dict[str, Any]]
    design_specs: dict[str, Any] | None = None


class GTMMemoryRecordResponse(BaseModel):
    stored: bool


class ExecutiveBriefingSlideTrack(BaseModel):
    """Path P: spoken script for one slide index."""

    slide_index: int = Field(ge=0)
    talk_track: str = Field(default="")


class GTMExecutiveBriefingRequest(BaseModel):
    slides: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        description="Deck slides (title, body, speaker_notes, etc.) in presentation order.",
    )
    user_prompt: str = Field(
        default="",
        description="Strategic directive, audience, and tone hints for the briefing agent.",
    )


class GTMExecutiveBriefingResponse(BaseModel):
    executive_summary: str
    slide_talk_tracks: list[ExecutiveBriefingSlideTrack]
    telemetry: GTMTelemetry


class GTMExecutiveBriefingTtsRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000)


class GTMExecutiveBriefingTtsResponse(BaseModel):
    audio_href: str | None = Field(
        default=None,
        description="Browser URL under /static when Piper synthesis succeeded.",
    )
    engine: str = Field(default="none", description="piper | none")


class GTMStrategicSimRequest(BaseModel):
    """Path S — Monte Carlo stress-test against tabular attachments + draft + optional RAG."""

    user_prompt: str = Field(..., min_length=1)
    slides: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Current deck JSON for scenario assumptions.",
    )
    file_paths: list[str] = Field(
        default_factory=list,
        description="Repo-relative paths; must include at least one .csv/.xlsx/.xlsm/.xls.",
    )
    project_folder: str = Field(
        default="",
        description="Optional folder RAG for market-variable context (same rules as /draft).",
    )


class StrategicSimLMTrace(BaseModel):
    raw_prompt: str = ""
    raw_completion: str = ""
    history_turns: int = 0


class GTMStrategicSimResponse(BaseModel):
    probability_of_success: float | None = Field(
        default=None,
        description="Percent in [0,100] when JSON parse succeeded.",
    )
    sensitivity_analysis_markdown: str = ""
    headline: str = ""
    simulation_design: str = ""
    return_code: int = 0
    parsed_ok: bool = False
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    lm_telemetry: StrategicSimLMTrace = Field(default_factory=StrategicSimLMTrace)


class SynthesizeSlideImageRequest(BaseModel):
    """GPU hero synthesis (SDXL / Flux / A1111); uses ``image_prompt`` from the draft slide."""

    slide_index: int = Field(..., ge=0, description="Deck index for filenames and UI correlation.")
    image_prompt: str = Field(..., min_length=1)
    negative_prompt: str = Field(default="")
    width: int = Field(default=1280, ge=512, le=2048)
    height: int = Field(default=720, ge=384, le=2048)


class SynthesizeSlideImageResponse(BaseModel):
    image_path: str = Field(description="Absolute path on the server; pass back in materialize slides JSON.")
    static_href: str = Field(
        description="Browser URL path under FastAPI /static (repo assets/).",
    )


# --- Path Q: Strategy session store (JSON per session) -------------------------


class StrategySandboxStatePayload(BaseModel):
    """Strategic Sandbox snapshot from the UI (paths A/B, drafts, matrix)."""

    user_prompt: str = ""
    file_paths: list[str] = Field(default_factory=list)
    project_folder: str = ""
    persona_a: str = Field(default="venture_capital")
    persona_b: str = Field(default="risk_auditor")
    label_a: str = ""
    label_b: str = ""
    draft_a: dict[str, Any] | None = None
    draft_b: dict[str, Any] | None = None
    decision_matrix_scores: dict[str, Any] | None = None
    phase_hint: str = Field(
        default="sandbox_review",
        description="Client phase hint, e.g. sandbox_review | form.",
    )


class StrategySessionCreateRequest(BaseModel):
    sandbox: StrategySandboxStatePayload
    branch_label: str = Field(
        default="",
        max_length=256,
        description="Human-readable name for this saved session.",
    )


class StrategySessionUpdateRequest(BaseModel):
    sandbox: StrategySandboxStatePayload
    branch_label: str | None = Field(
        default=None,
        max_length=256,
        description="If set, updates the display label for this session.",
    )


class StrategySessionBranchRequest(BaseModel):
    branch_label: str = Field(
        default="",
        max_length=256,
        description="Label for the new branch; default derived from parent id.",
    )


class StrategySessionIdResponse(BaseModel):
    session_id: str
    parent_session_id: str | None = None


class StrategySessionDocument(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    session_id: str
    parent_session_id: str | None = None
    branch_label: str | None = None
    created_at: str
    updated_at: str
    sandbox: dict[str, Any]
    drift_history: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Path NN: persisted Path LL drift alerts (contradiction timeline) for this session.",
    )


class DriftMonitorConfig(BaseModel):
    """Path JJ: drift monitor configuration stored in the session JSON."""

    enabled: bool = Field(default=False)
    interval_s: float = Field(default=3600.0, ge=30.0, le=7 * 24 * 3600.0)


class StrategySessionListEntry(BaseModel):
    session_id: str
    parent_session_id: str | None = None
    branch_label: str | None = None
    created_at: str
    updated_at: str


class ETLRequest(BaseModel):
    user_prompt: str = ""
    file_paths: list[str] = Field(default_factory=list)
    schema_template: str = Field(..., min_length=1)


class ETLResponse(BaseModel):
    data: Any
    raw: str
    csv: str | None = None


# --- Path & ingestion helpers -------------------------------------------------


def _resolve_project_path(path_str: str) -> Path:
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = (_REPO_ROOT / p).resolve()
    else:
        p = p.resolve()
    return p


def _file_not_found_detail(missing: Path) -> str:
    msg = f"File not found: {missing}"
    assets = _REPO_ROOT / "assets"
    if not assets.is_dir():
        return msg
    pptx = sorted(assets.glob("*.pptx"), key=lambda x: x.name.lower())
    if not pptx:
        return (
            f"{msg} | No .pptx files in assets/; add a template or ingest one."
        )
    rel = [str(p.relative_to(_REPO_ROOT)) for p in pptx[:12]]
    return (
        f"{msg} | Example: {rel[0]!r} — available: {', '.join(rel)}"
    )


def _strategy_session_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strategy_session_validate_id(session_id: str) -> str:
    s = (session_id or "").strip()
    if not s or not _STRATEGY_SESSION_ID_RE.match(s):
        raise HTTPException(
            status_code=400,
            detail="Invalid session_id (expected UUID).",
        )
    return s


def _strategy_session_path(session_id: str) -> Path:
    sid = _strategy_session_validate_id(session_id)
    return _STRATEGY_SESSIONS_DIR / f"{sid}.json"


def _strategy_session_ensure_dir() -> None:
    _STRATEGY_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _strategy_session_atomic_write(path: Path, doc: dict[str, Any]) -> None:
    _strategy_session_ensure_dir()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(doc, indent=2, ensure_ascii=False, default=str)
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def _strategy_session_load_doc(session_id: str) -> dict[str, Any]:
    path = _strategy_session_path(session_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Strategy session not found: {session_id}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logger.exception("event=strategy_session.corrupt path=%s", path)
        raise HTTPException(
            status_code=500,
            detail=f"Session file is not valid JSON: {e}",
        ) from e


def _strategy_session_sandbox_to_dict(p: StrategySandboxStatePayload) -> dict[str, Any]:
    return p.model_dump(mode="json", exclude_none=False)


def _strategy_session_list_entries() -> list[StrategySessionListEntry]:
    _strategy_session_ensure_dir()
    out: list[StrategySessionListEntry] = []
    for path in sorted(_STRATEGY_SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.name.endswith(".tmp"):
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        sid = doc.get("session_id")
        if not isinstance(sid, str) or not _STRATEGY_SESSION_ID_RE.match(sid):
            continue
        out.append(
            StrategySessionListEntry(
                session_id=sid,
                parent_session_id=doc.get("parent_session_id")
                if isinstance(doc.get("parent_session_id"), str)
                else None,
                branch_label=doc.get("branch_label") if isinstance(doc.get("branch_label"), str) else None,
                created_at=str(doc.get("created_at") or ""),
                updated_at=str(doc.get("updated_at") or ""),
            ),
        )
    return out


# --- Path U: War Room WebSocket hub (Layer 7) ----------------------------------


@dataclass
class _WarRoomConn:
    conn_id: str
    websocket: WebSocket
    session_id: str
    user_id: str
    display_name: str


@dataclass
class _WarRoomSlideLock:
    holder_conn_id: str
    user_id: str
    display_name: str


class WarRoomHub:
    """
    In-memory collaboration: strategy session rooms, sandbox persistence + broadcast,
    ephemeral slide locks for refine, and deck state relay (not written to JSON).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_conn: dict[str, _WarRoomConn] = {}
        self._room_conns: dict[str, set[str]] = {}
        self._slide_locks: dict[tuple[str, int], _WarRoomSlideLock] = {}

    def register(
        self,
        websocket: WebSocket,
        session_id: str,
        user_id: str,
        display_name: str,
    ) -> str:
        cid = str(uuid.uuid4())
        conn = _WarRoomConn(
            conn_id=cid,
            websocket=websocket,
            session_id=session_id,
            user_id=(user_id or "anonymous").strip() or "anonymous",
            display_name=(display_name or "Strategist").strip() or "Strategist",
        )
        with self._lock:
            self._by_conn[cid] = conn
            self._room_conns.setdefault(session_id, set()).add(cid)
        return cid

    def unregister(self, conn_id: str) -> str | None:
        with self._lock:
            conn = self._by_conn.pop(conn_id, None)
            if conn is None:
                return None
            sid = conn.session_id
            members = self._room_conns.get(sid)
            if members is not None:
                members.discard(conn_id)
                if not members:
                    self._room_conns.pop(sid, None)
            dead_keys = [
                k
                for k, lock in self._slide_locks.items()
                if k[0] == sid and lock.holder_conn_id == conn_id
            ]
            for k in dead_keys:
                self._slide_locks.pop(k, None)
            return sid

    def try_acquire_slide_lock(
        self,
        session_id: str,
        slide_index: int,
        conn_id: str,
    ) -> tuple[bool, dict[str, str] | None]:
        with self._lock:
            conn = self._by_conn.get(conn_id)
            if conn is None or conn.session_id != session_id:
                return False, None
            key = (session_id, int(slide_index))
            existing = self._slide_locks.get(key)
            if existing is None:
                self._slide_locks[key] = _WarRoomSlideLock(
                    holder_conn_id=conn_id,
                    user_id=conn.user_id,
                    display_name=conn.display_name,
                )
                return True, None
            if existing.holder_conn_id == conn_id:
                return True, None
            return False, {
                "user_id": existing.user_id,
                "display_name": existing.display_name,
            }

    def release_slide_lock(self, session_id: str, slide_index: int, conn_id: str) -> None:
        with self._lock:
            key = (session_id, int(slide_index))
            lock = self._slide_locks.get(key)
            if lock is None or lock.holder_conn_id != conn_id:
                return
            self._slide_locks.pop(key, None)

    def slide_lock_held_by_user(self, session_id: str, slide_index: int, user_id: str) -> bool:
        with self._lock:
            lock = self._slide_locks.get((session_id, int(slide_index)))
            if lock is None:
                return False
            return lock.user_id == (user_id or "").strip()

    def locks_snapshot(self, session_id: str) -> dict[str, dict[str, str]]:
        with self._lock:
            out: dict[str, dict[str, str]] = {}
            for (sid, idx), lock in self._slide_locks.items():
                if sid != session_id:
                    continue
                out[str(idx)] = {
                    "user_id": lock.user_id,
                    "display_name": lock.display_name,
                }
            return out

    def presence_snapshot(self, session_id: str) -> list[dict[str, str]]:
        with self._lock:
            cids = list(self._room_conns.get(session_id, set()))
            users: list[dict[str, str]] = []
            seen: set[str] = set()
            for cid in cids:
                c = self._by_conn.get(cid)
                if c is None:
                    continue
                if c.user_id in seen:
                    continue
                seen.add(c.user_id)
                users.append(
                    {
                        "user_id": c.user_id,
                        "display_name": c.display_name,
                        "conn_id": c.conn_id,
                    },
                )
            return users

    async def broadcast_json(
        self,
        session_id: str,
        payload: dict[str, Any],
        *,
        exclude_conn_id: str | None = None,
    ) -> None:
        with self._lock:
            cids = list(self._room_conns.get(session_id, set()))
            targets = [
                self._by_conn[c].websocket
                for c in cids
                if c in self._by_conn and (exclude_conn_id is None or c != exclude_conn_id)
            ]
        for ws in targets:
            try:
                await ws.send_text(json.dumps(payload, default=str))
            except Exception:
                logger.debug("event=war_room.send_failed", exc_info=True)

    async def broadcast_slide_locks(self, session_id: str) -> None:
        locks = self.locks_snapshot(session_id)
        await self.broadcast_json(session_id, {"type": "slide_locks", "locks": locks})

    async def broadcast_presence(self, session_id: str) -> None:
        users = self.presence_snapshot(session_id)
        await self.broadcast_json(session_id, {"type": "presence", "users": users})


_war_room_hub = WarRoomHub()
_WAR_ROOM_ASYNC_LOOP: asyncio.AbstractEventLoop | None = None


def _war_room_schedule_broadcast(coro: Any) -> None:
    loop = _WAR_ROOM_ASYNC_LOOP
    if loop is None or not loop.is_running():
        return

    def _done(fut: asyncio.Future[Any]) -> None:
        try:
            fut.result()
        except Exception:
            logger.exception("event=war_room.broadcast_task_failed")

    try:
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        fut.add_done_callback(_done)
    except Exception:
        logger.exception("event=war_room.schedule_broadcast_failed")


def _war_room_broadcast_session_doc(session_id: str, doc: dict[str, Any]) -> None:
    """Notify WebSocket clients after REST (or WS) persisted a strategy session."""

    async def _push() -> None:
        dh = doc.get("drift_history")
        drift_hist = dh if isinstance(dh, list) else []
        await _war_room_hub.broadcast_json(
            session_id,
            {
                "type": "sandbox_sync",
                "sandbox": doc.get("sandbox"),
                "updated_at": doc.get("updated_at"),
                "branch_label": doc.get("branch_label"),
                "drift_history": drift_hist,
            },
        )

    _war_room_schedule_broadcast(_push())


def _strategy_session_drift_history_append(
    doc: dict[str, Any],
    *,
    reasoning: str,
    top_snippets: list[dict[str, Any]],
    snippet_count: int,
) -> list[dict[str, Any]]:
    """Path NN: append one Path LL drift event to session JSON (mutates doc)."""
    raw = doc.get("drift_history")
    history: list[Any] = list(raw) if isinstance(raw, list) else []
    try:
        cap = max(8, min(500, int(os.environ.get("RELULAYER_DRIFT_HISTORY_MAX", "200") or 200)))
    except ValueError:
        cap = 200
    entry: dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "at": _strategy_session_now_iso(),
        "headline": "Strategic Drift Detected: New Market Reality",
        "reasoning": reasoning,
        "top_snippets": top_snippets,
        "snippet_count": int(snippet_count),
        "classifier": "Path LL contradiction classifier",
    }
    history.append(entry)
    if len(history) > cap:
        history = history[-cap:]
    doc["drift_history"] = history
    return history


def _war_room_broadcast_alert(session_id: str, payload: dict[str, Any]) -> None:
    """Path JJ: broadcast a non-persistent alert message to a war-room session."""

    async def _push() -> None:
        await _war_room_hub.broadcast_json(session_id, payload)

    _war_room_schedule_broadcast(_push())


def _drift_digest_from_grounding(snips: list[dict[str, Any]]) -> str:
    blob = "\n".join(
        f"{s.get('title','')}|{s.get('url','')}|{s.get('snippet','')}"
        for s in snips
        if isinstance(s, dict)
    )
    return hashlib.sha256(blob.encode("utf-8", errors="ignore")).hexdigest()


def _best_effort_session_rationale(doc: dict[str, Any]) -> str:
    sandbox = doc.get("sandbox") if isinstance(doc.get("sandbox"), dict) else {}
    # Prefer whichever draft payload exists (sandbox stores draft_a/draft_b).
    for k in ("draft_a", "draft_b"):
        d = sandbox.get(k)
        if not isinstance(d, dict):
            continue
        tel = d.get("telemetry") if isinstance(d.get("telemetry"), dict) else {}
        r = tel.get("rationale")
        if isinstance(r, str) and r.strip():
            return r.strip()
    return ""


def _best_effort_session_risk_audit(doc: dict[str, Any]) -> str:
    sandbox = doc.get("sandbox") if isinstance(doc.get("sandbox"), dict) else {}
    for k in ("draft_a", "draft_b"):
        d = sandbox.get(k)
        if not isinstance(d, dict):
            continue
        tel = d.get("telemetry") if isinstance(d.get("telemetry"), dict) else {}
        ar = tel.get("audit_report") if isinstance(tel.get("audit_report"), dict) else {}
        pts = ar.get("weak_points")
        if isinstance(pts, list) and pts:
            joined = " | ".join(str(p.get("point") or "") for p in pts if isinstance(p, dict))
            if joined.strip():
                return joined.strip()
    return ""


def _parse_contradiction_assessment(raw: str) -> tuple[bool, str]:
    """Path LL: parse ``contradiction_json`` from the contradiction classifier."""
    cleaned = _strip_json_fence((raw or "").strip())
    if not cleaned:
        return False, ""
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning(
            "event=drift_monitor.contradiction_json_parse_failed preview=%r",
            cleaned[:400],
        )
        return False, ""
    if not isinstance(obj, dict):
        return False, ""
    flag = obj.get("is_contradictory")
    if isinstance(flag, str):
        contradictory = flag.strip().lower() in ("true", "yes", "1")
    else:
        contradictory = bool(flag)
    reasoning = str(obj.get("reasoning") or "").strip()
    return contradictory, reasoning


def _drift_build_original_context(doc: dict[str, Any], fallback_prompt: str) -> str:
    """Assemble saved rationale + risk snapshot (or session prompt) for Path LL."""
    rationale = _best_effort_session_rationale(doc)
    risk_audit = _best_effort_session_risk_audit(doc)
    parts: list[str] = []
    if rationale:
        parts.append(f"Strategic rationale (saved draft telemetry):\n{rationale}")
    if risk_audit:
        parts.append(f"Red-team weak points / risk snapshot:\n{risk_audit}")
    fp = (fallback_prompt or "").strip()
    if not parts and fp:
        parts.append(
            "Strategic directive (session only; no draft rationale cached):\n" + fp[:6000],
        )
    return "\n\n".join(parts).strip()


def _drift_format_snippets_for_llm(snips: list[dict[str, Any]]) -> str:
    try:
        mx = max(2048, int(os.environ.get("RELULAYER_DRIFT_SNIPPET_CONTEXT_CHARS", "14000")))
    except ValueError:
        mx = 14000
    lines: list[str] = []
    for i, s in enumerate(snips[:20]):
        if not isinstance(s, dict):
            continue
        title = str(s.get("title") or "").strip()
        url = str(s.get("url") or "").strip()
        sn = str(s.get("snippet") or "").strip()
        lines.append(f"--- Item {i + 1} ---\nTitle: {title}\nURL: {url}\nSnippet:\n{sn}")
    blob = "\n\n".join(lines)
    if len(blob) > mx:
        return blob[:mx] + "\n\n[...truncated for context limit...]"
    return blob


def _drift_run_contradiction_llm(
    original_context: str,
    snippets_blob: str,
) -> tuple[bool, str]:
    """Synchronous Path LL call; run from the async drift loop via ``asyncio.to_thread``."""
    if not snippets_blob.strip():
        return False, ""
    try:
        pred = _contradiction_classifier.forward(
            original_strategic_context=original_context,
            new_web_snippets=snippets_blob,
        )
        raw = str(getattr(pred, "contradiction_json", None) or "")
        return _parse_contradiction_assessment(raw)
    except Exception:
        logger.exception("event=drift_monitor.contradiction_llm_failed")
        return False, ""


async def _drift_monitor_loop() -> None:
    """
    Path JJ: background drift monitor.

    Periodically re-runs Path K (live grounding) for opted-in strategy sessions. When grounding
    content changes, Path LL (ContradictionSignature) decides if new snippets materially contradict
    the saved strategy; only then a war-room alert is broadcast.
    """
    poll_s = max(10.0, float(os.environ.get("RELULAYER_DRIFT_POLL_S", "30")))
    alert_cooldown_s = max(60.0, float(os.environ.get("RELULAYER_DRIFT_ALERT_COOLDOWN_S", "900")))
    logger.info(
        "event=drift_monitor.start poll_s=%s classifier=path_ll cooldown_s=%s",
        poll_s,
        alert_cooldown_s,
    )
    while True:
        await asyncio.sleep(poll_s)
        try:
            entries = _strategy_session_list_entries()
        except Exception:
            logger.exception("event=drift_monitor.list_failed")
            continue
        now = time.time()
        for e in entries:
            sid = e.session_id
            try:
                doc = _strategy_session_load_doc(sid)
            except HTTPException:
                continue
            drift = doc.get("drift_monitor") if isinstance(doc.get("drift_monitor"), dict) else {}
            if not drift or not drift.get("enabled"):
                continue
            interval_s = float(drift.get("interval_s") or 3600.0)
            last_checked = float(drift.get("last_checked_at") or 0.0)
            if now - last_checked < max(30.0, interval_s):
                continue
            sandbox = doc.get("sandbox") if isinstance(doc.get("sandbox"), dict) else {}
            prompt = str(sandbox.get("user_prompt") or "").strip()
            if not prompt:
                continue
            try:
                og = fetch_live_grounding(prompt)
            except Exception:
                logger.exception("event=drift_monitor.grounding_failed sid=%s", sid)
                drift["last_checked_at"] = now
                doc["drift_monitor"] = drift
                doc["updated_at"] = _strategy_session_now_iso()
                _strategy_session_atomic_write(_strategy_session_path(sid), doc)
                continue
            snips = og.snippets if isinstance(og.snippets, list) else []
            digest = _drift_digest_from_grounding(snips)
            prev = str(drift.get("last_grounding_digest") or "")
            drift["last_checked_at"] = now
            drift["last_grounding_digest"] = digest
            doc["drift_monitor"] = drift
            doc["updated_at"] = _strategy_session_now_iso()
            _strategy_session_atomic_write(_strategy_session_path(sid), doc)
            if not snips or digest == prev:
                continue
            original_ctx = _drift_build_original_context(doc, prompt)
            snippets_blob = _drift_format_snippets_for_llm(snips)
            is_contradictory, contra_reasoning = await asyncio.to_thread(
                _drift_run_contradiction_llm,
                original_ctx,
                snippets_blob,
            )
            last_alert = float(drift.get("last_alert_at") or 0.0)
            if is_contradictory and now - last_alert >= alert_cooldown_s:
                reasoning_out = (
                    contra_reasoning.strip()
                    or "Path LL flagged a material contradiction between new web evidence and the saved strategy."
                )
                drift["last_alert_at"] = now
                doc["drift_monitor"] = drift
                top_for_store = [
                    {
                        "title": str(s.get("title") or "")[:500],
                        "url": str(s.get("url") or "")[:2000],
                        "snippet": str(s.get("snippet") or "")[:4000],
                    }
                    for s in snips[:5]
                    if isinstance(s, dict)
                ]
                updated_history = _strategy_session_drift_history_append(
                    doc,
                    reasoning=reasoning_out,
                    top_snippets=top_for_store,
                    snippet_count=len(snips),
                )
                doc["updated_at"] = _strategy_session_now_iso()
                _strategy_session_atomic_write(_strategy_session_path(sid), doc)
                _war_room_broadcast_alert(
                    sid,
                    {
                        "type": "strategic_drift_alert",
                        "headline": "Strategic Drift Detected: New Market Reality",
                        "standard": "Path LL contradiction classifier",
                        "is_contradictory": True,
                        "reasoning": reasoning_out,
                        "score": 1,
                        "snippet_count": len(snips),
                        "top_snippets": snips[:5],
                        "drift_history": updated_history,
                    },
                )
                logger.info(
                    "event=drift_monitor.alert sid=%s path_nn=appended history_len=%s preview=%r",
                    sid,
                    len(updated_history),
                    reasoning_out[:200],
                )


@app.on_event("startup")
async def _drift_monitor_startup() -> None:
    if os.environ.get("RELULAYER_DRIFT_MONITOR", "1").strip().lower() in ("0", "false", "no"):
        logger.info("event=drift_monitor.disabled")
        return
    asyncio.create_task(_drift_monitor_loop())


@app.on_event("startup")
async def _war_room_bind_loop() -> None:
    global _WAR_ROOM_ASYNC_LOOP
    _WAR_ROOM_ASYNC_LOOP = asyncio.get_running_loop()


_DATA_AUDIT_TABULAR_SUFFIXES = (".csv", ".xlsx", ".xlsm", ".xls")

_DATA_AUDIT_KEYWORDS = frozenset(
    {
        "aggregate",
        "calculate",
        "cagr",
        "correlation",
        "dataset",
        "empirical",
        "excel",
        "forecast",
        "irr",
        "mean",
        "median",
        "metric",
        "monte carlo",
        "npv",
        "p-value",
        "payback",
        "percentile",
        "regression",
        "roi",
        "sensitivity",
        "statistic",
        "statistical",
        "sum",
        "variance",
    },
)


def _collect_tabular_paths_for_audit(file_paths: list[str]) -> list[Path]:
    out: list[Path] = []
    root = _REPO_ROOT.resolve()
    for fp in file_paths or []:
        low = (fp or "").strip().lower()
        if not low.endswith(_DATA_AUDIT_TABULAR_SUFFIXES):
            continue
        try:
            p = _resolve_project_path(fp.strip()).resolve()
        except Exception:
            continue
        if not p.is_file():
            continue
        try:
            p.relative_to(root)
        except ValueError:
            logger.warning("event=gtm.data_audit.skip_path_outside_repo path=%s", p)
            continue
        out.append(p)
    return out


def _should_run_data_auditor(user_prompt: str, tabular_paths: list[Path]) -> bool:
    if not tabular_paths:
        return False
    mode = os.environ.get("RELULAYER_DATA_AUDIT", "auto").strip().lower()
    if mode in ("0", "false", "no", "off", "disabled"):
        return False
    if mode in ("1", "true", "yes", "always", "on", "force"):
        return True
    pl = (user_prompt or "").lower()
    return any(k in pl for k in _DATA_AUDIT_KEYWORDS)


def _extract_tabular_excerpt_for_audit(context_string: str, *, max_chars: int) -> str:
    ctx = context_string or ""
    if "### Tabular" not in ctx:
        return ctx[:max_chars]
    blocks: list[str] = []
    for block in ctx.split("\n\n---\n\n"):
        if "### Tabular" in block:
            blocks.append(block)
    joined = "\n\n---\n\n".join(blocks) if blocks else ctx
    return joined[:max_chars]


def _run_data_audit_for_gtm(
    user_prompt: str,
    file_paths: list[str],
    ingested_context_string: str,
) -> tuple[str | None, DataAuditTelemetry]:
    tel = DataAuditTelemetry()
    paths = _collect_tabular_paths_for_audit(file_paths)
    if not paths:
        tel.skip_reason = "no_tabular_attachments"
        return None, tel
    if not _should_run_data_auditor(user_prompt, paths):
        tel.skip_reason = "skipped_by_heuristic_or_RELULAYER_DATA_AUDIT"
        return None, tel

    tel.triggered = True
    manifest = [{"path": str(p), "name": p.name} for p in paths]
    excerpt = _extract_tabular_excerpt_for_audit(
        ingested_context_string,
        max_chars=8000,
    )
    try:
        pred = _data_auditor.forward(
            user_instructions=user_prompt.strip(),
            data_file_manifest=json.dumps(manifest, ensure_ascii=False),
            tabular_context_excerpt=excerpt,
        )
    except Exception as e:
        logger.exception("event=gtm.data_audit.lm_failed")
        tel.skip_reason = f"lm_error:{type(e).__name__}:{e}"
        return None, tel

    dap, dac, _ = _extract_gtm_telemetry_from_dspy_history(last_n_calls=1)
    tel.lm_raw_prompt_excerpt = (dap or "")[:8000]
    tel.lm_raw_completion_excerpt = (dac or "")[:8000]

    plan = str(getattr(pred, "audit_plan", None) or "").strip()
    script = str(getattr(pred, "python_script", None) or "")
    tel.audit_plan_excerpt = plan[:4000]
    tel.script_excerpt = script[:12000]

    stdout, stderr, rc = execute_data_audit_script(
        script,
        manifest=manifest,
        project_root=_REPO_ROOT,
    )
    tel.ran = True
    tel.return_code = rc
    tel.stdout_excerpt = stdout[:12000]
    tel.stderr_excerpt = stderr[:6000]

    parts = ["### Empirical data audit (Path R — executed Python)\n\n"]
    if plan:
        parts.append(f"**Auditor plan:** {plan}\n\n")
    parts.append(f"**Process exit code:** {rc}\n\n")
    if stdout.strip():
        parts.append("**Stdout (use these numbers on slides; do not invent metrics):**\n```text\n")
        parts.append(stdout[:14000])
        if len(stdout) > 14000:
            parts.append("\n... [stdout truncated for GTM context]\n")
        parts.append("\n```\n\n")
    if stderr.strip():
        parts.append("**Stderr / diagnostics:**\n```text\n")
        parts.append(stderr[:6000])
        if len(stderr) > 6000:
            parts.append("\n... [truncated]\n")
        parts.append("\n```\n\n")
    if not stdout.strip() and not stderr.strip():
        parts.append("(No script output captured.)\n\n")

    chunk = "".join(parts)
    logger.info(
        "event=gtm.data_audit.done rc=%s stdout_chars=%s triggered=%s",
        rc,
        len(stdout),
        tel.triggered,
    )
    return chunk, tel


def _load_ingestion_files(file_paths: list[str]) -> list[IngestionFile]:
    files: list[IngestionFile] = []
    for fp in file_paths:
        p = _resolve_project_path(fp)
        if not p.is_file():
            raise HTTPException(status_code=400, detail=_file_not_found_detail(p))
        files.append(IngestionFile(name=p.name, data=p.read_bytes()))
        logger.info(
            "event=ingestion.file_resolved path=%s bytes=%s",
            p,
            len(files[-1].data),
        )
    return files


def _strip_json_fence(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def _parse_strategic_judge_rubric_json(raw: str) -> dict[str, int]:
    """Path V: parse ``rubric_scores_json`` from the judge LM (1–10 per dimension)."""
    cleaned = _strip_json_fence((raw or "").strip())
    if not cleaned:
        return {}
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning(
            "event=gtm.judge.rubric_parse_failed preview=%r",
            cleaned[:400],
        )
        return {}
    if not isinstance(obj, dict):
        return {}
    out: dict[str, int] = {}
    for key in ("clarity", "feasibility", "strategic_impact"):
        v = obj.get(key)
        try:
            n = int(float(v))
        except (TypeError, ValueError):
            continue
        out[key] = max(1, min(10, n))
    return out


def _normalize_committee_verdict(raw: str) -> str:
    t = re.sub(r"[^a-z\s]", " ", (raw or "").lower())
    words = set(t.split())
    if "reject" in words:
        return "reject"
    if "proceed" in words:
        return "proceed"
    return "revise"


def _any_rubric_below_7(scores: dict[str, int]) -> bool:
    return any(v < 7 for v in scores.values())


def _pick_slide_indices_for_self_correction(
    slides: list[dict[str, Any]],
    scores: dict[str, int],
    max_slides: int,
) -> list[int]:
    """Prioritize slides likely to benefit from judge feedback (Path Y)."""
    n = len(slides)
    if n == 0:
        return []
    weak = {k for k, v in scores.items() if v < 7}
    if not weak:
        weak = {"clarity", "feasibility", "strategic_impact"}
    ranked: list[tuple[float, int]] = []
    for i, s in enumerate(slides):
        title = str(s.get("title") or "")
        body = str(s.get("body") or "")
        w = 0.0
        if "clarity" in weak:
            w += min(800.0, float(len(title) + len(body)))
        if "feasibility" in weak:
            w += min(600.0, float(len(body)))
        if "strategic_impact" in weak:
            w += 400.0 if i in (0, n - 1) else min(300.0, float(len(body)) * 0.5)
        ranked.append((w, i))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    picked = [idx for _, idx in ranked[:max_slides]]
    return sorted(picked)


def _self_correction_refinement_instruction(
    *,
    user_prompt: str,
    verdict: str,
    scores: dict[str, int],
    auditor_rationale: str,
    slide_index: int,
    slide_count: int,
) -> str:
    c = scores.get("clarity", "n/a")
    f = scores.get("feasibility", "n/a")
    si = scores.get("strategic_impact", "n/a")
    return (
        "[Path Y — autonomous quality-gate revision]\n"
        "The Executive Committee judge (Path V) reviewed the full deck.\n"
        f"Committee verdict: {verdict}\n"
        f"Rubric scores (1–10): clarity={c}, feasibility={f}, strategic_impact={si}.\n\n"
        "Auditor rationale (address these issues on this slide where applicable):\n"
        f"{(auditor_rationale or '').strip()}\n\n"
        "Strategic directive (do not contradict):\n"
        f"{user_prompt.strip()[:2000]}\n\n"
        f"Refine slide {slide_index + 1} of {slide_count}: improve title and body to lift weak rubric "
        "dimensions while preserving this slide's role and keeping claims proportionate to evidence."
    )


def _apply_refine_prediction_to_slide(slide: dict[str, Any], pred: Any) -> None:
    oid = slide.get("original_id")
    oid_s = str(oid).strip() if oid is not None and str(oid).strip() else ""
    new_title = getattr(pred, "refined_title", None)
    new_body = getattr(pred, "refined_body", None)
    if new_title is not None and str(new_title).strip():
        slide["title"] = str(new_title).strip()
    if new_body is not None and str(new_body).strip():
        slide["body"] = str(new_body).strip()
    if oid_s:
        slide["original_id"] = oid_s


def _assign_consensus_slide_original_ids(slides: list[dict[str, Any]]) -> frozenset[str]:
    """
    Path OO: ensure every slide has a stable unique ``original_id`` (UUID) after the consensus draft parse.
    Existing unique string ids from the LM are kept; missing or duplicate values are replaced.
    """
    used: set[str] = set()
    for s in slides:
        if not isinstance(s, dict):
            continue
        oid = str(s.get("original_id") or "").strip()
        if not oid or oid in used:
            oid = str(uuid.uuid4())
        s["original_id"] = oid
        used.add(oid)
    return frozenset(used)


def _verify_slides_original_id_integrity(
    slides: list[dict[str, Any]],
    expected: frozenset[str],
) -> tuple[bool, str, list[str], list[str]]:
    """
    Path OO: each slide must carry an ``original_id``; the multiset must match ``expected`` exactly once each.
    Returns (ok, detail, missing_or_extra_ids_for_mismatch, duplicate_ids).
    """
    ids: list[str] = []
    missing_slots: list[str] = []
    for i, s in enumerate(slides):
        if not isinstance(s, dict):
            continue
        oid = str(s.get("original_id") or "").strip()
        if not oid:
            missing_slots.append(f"index_{i}")
            ids.append("")
        else:
            ids.append(oid)
    if missing_slots:
        return (
            False,
            "one or more slides missing original_id after revision",
            missing_slots,
            [],
        )
    if len(ids) != len(expected):
        return (
            False,
            f"slide count {len(ids)} does not match identity contract {len(expected)}",
            sorted(expected - frozenset(ids)) + sorted(frozenset(ids) - expected),
            [],
        )
    bag: Counter[str] = Counter(ids)
    dups = sorted([k for k, v in bag.items() if v > 1])
    if dups:
        return False, "duplicate original_id values in revised deck", [], dups
    if frozenset(ids) != expected:
        miss = sorted(expected - frozenset(ids))
        extra = sorted(frozenset(ids) - expected)
        return (
            False,
            f"original_id set mismatch vs consensus (missing={miss!r}, extra={extra!r})",
            miss,
            [],
        )
    return True, "", [], []


def _parse_talk_track_json(raw: str, n_slides: int) -> list[str]:
    """Parse LLM ``talk_track_json`` into ``n_slides`` strings (Path P)."""
    n = max(0, int(n_slides))
    if n == 0:
        return []
    cleaned = _strip_json_fence(raw or "")
    if not cleaned:
        return [""] * n
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning(
            "event=gtm.briefing.talk_track_json_parse_failed preview=%r",
            cleaned[:400],
        )
        return [""] * n
    out: list[str] = []
    if isinstance(data, list):
        for el in data:
            if isinstance(el, str):
                out.append(el.strip())
            elif isinstance(el, dict):
                t = el.get("talk_track") or el.get("script") or el.get("narration")
                out.append(str(t or "").strip())
            else:
                out.append("")
    while len(out) < n:
        out.append("")
    return out[:n]


def _parse_strategic_risks_json(raw: str) -> list[AuditRiskItem]:
    s = (raw or "").strip()
    if not s:
        return []
    cleaned = _strip_json_fence(s)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning(
            "event=gtm.red_team.json_parse_failed preview=%r",
            cleaned[:400],
        )
        return []
    if not isinstance(data, list):
        return []

    items: list[AuditRiskItem] = []
    for el in data:
        if isinstance(el, str):
            txt = el.strip()
            if txt:
                items.append(AuditRiskItem(point=txt, severity="medium"))
            continue
        if not isinstance(el, dict):
            continue
        txt = (
            el.get("risk")
            or el.get("point")
            or el.get("weak_point")
            or el.get("issue")
        )
        if not txt:
            continue
        sev_raw = str(el.get("severity", "medium")).strip().lower()
        sev: AuditSeverity
        if sev_raw in ("low", "medium", "high"):
            sev = sev_raw
        else:
            sev = "medium"
        items.append(AuditRiskItem(point=str(txt).strip(), severity=sev))
    return items


def _red_team_significant(items: list[AuditRiskItem]) -> bool:
    if any(i.severity == "high" for i in items):
        return True
    return sum(1 for i in items if i.severity in ("medium", "high")) >= 2


def _parse_gtm_deck(raw_presentation: str) -> dict[str, Any]:
    cleaned = _strip_json_fence(raw_presentation)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.exception("event=gtm.json_parse_failed")
        raise HTTPException(
            status_code=502,
            detail=f"Model output was not valid JSON: {e}",
        ) from e

    if isinstance(data, dict) and "slides" in data:
        return data
    if isinstance(data, list):
        return {"slides": data}
    raise HTTPException(
        status_code=502,
        detail="Model output must be a JSON array of slides or an object with a 'slides' key.",
    )


def _normalize_slide(slide: dict[str, Any]) -> dict[str, Any]:
    cr = slide.get("chart_request")
    if not isinstance(cr, dict) or not cr:
        cd = slide.get("chart_data")
        if isinstance(cd, dict) and cd:
            cr = cd
    return {
        "type": slide.get("type") or "Title and Content",
        "title": slide.get("title"),
        "body": slide.get("body"),
        "body_left": slide.get("body_left"),
        "body_right": slide.get("body_right"),
        "body_columns": slide.get("body_columns"),
        "speaker_notes": slide.get("speaker_notes") or slide.get("notes"),
        "subtitle": slide.get("subtitle"),
        "image_path": slide.get("image_path"),
        "image_prompt": slide.get("image_prompt"),
        "chart_request": cr if isinstance(cr, dict) else None,
        "chart_path": slide.get("chart_path"),
        "icon_request": slide.get("icon_request"),
        "icon_path": slide.get("icon_path"),
        "icon_svg_path": slide.get("icon_svg_path"),
        "design_specs": slide.get("design_specs"),
    }


def _placeholder_png_bytes(caption: str, width: int = 1280, height: int = 720) -> bytes:
    img = Image.new("RGB", (width, height), (24, 27, 35))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    text = (caption or "").strip()[:800]
    draw.multiline_text(
        (36, 36),
        text or "(no image prompt)",
        fill=(210, 215, 225),
        font=font,
        spacing=4,
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _serialize_lm_response(response: Any) -> str:
    if response is None:
        return ""
    if hasattr(response, "model_dump"):
        try:
            return json.dumps(response.model_dump(), indent=2, ensure_ascii=False, default=str)
        except Exception:
            pass
    return str(response)


def _extract_gtm_telemetry_from_dspy_history(*, last_n_calls: int = 1) -> tuple[str, str, int]:
    """
    Read DSPy's global LM ring buffer (same data as dspy.inspect_history pretty-prints).
    Returns (raw_prompt, raw_completion, turns_used).
    """
    try:
        base_lm = importlib.import_module("dspy.clients.base_lm")
    except ImportError:
        return "", "", 0

    hist: list[Any] = getattr(base_lm, "GLOBAL_HISTORY", None) or []
    if not hist:
        return "", "", 0

    n = max(1, last_n_calls)
    slice_ = hist[-n:]
    prompt_parts: list[str] = []
    completion_parts: list[str] = []

    for item in slice_:
        messages = item.get("messages")
        prompt = item.get("prompt")
        if messages is not None:
            prompt_parts.append(
                json.dumps(messages, indent=2, ensure_ascii=False, default=str),
            )
        elif prompt is not None:
            prompt_parts.append(str(prompt))

        outputs = item.get("outputs")
        response = item.get("response")
        if outputs is not None:
            completion_parts.append(
                json.dumps(outputs, indent=2, ensure_ascii=False, default=str),
            )
        elif response is not None:
            completion_parts.append(_serialize_lm_response(response))

    return (
        "\n\n--- turn ---\n\n".join(prompt_parts),
        "\n\n--- turn ---\n\n".join(completion_parts),
        len(slice_),
    )


def _materialize_slide_icons(
    slides: list[dict[str, Any]],
    project_root: Path,
) -> None:
    """When a slide includes ``icon_request``, write SVG + PNG under ``assets/outputs/icons/``."""
    for idx, slide in enumerate(slides):
        req = slide.get("icon_request")
        if req is None or req == "":
            continue
        existing = slide.get("icon_path")
        if existing and Path(str(existing)).is_file():
            logger.info("event=gtm.icon_skip_existing path=%s", existing)
            continue
        try:
            paths = generate_slide_theme_icon_assets(
                icon_request=req,
                slide_index=idx,
                slide_title=slide.get("title"),
                project_root=project_root,
            )
        except Exception:
            logger.exception("event=gtm.icon_generation_failed slide=%s", idx)
            continue
        slide["icon_path"] = paths["png"]
        slide["icon_svg_path"] = paths["svg"]
        logger.info(
            "event=gtm.icon_materialized slide=%s png=%s",
            idx,
            paths["png"],
        )


def _materialize_slide_charts(
    slides: list[dict[str, Any]],
    project_root: Path,
) -> None:
    """Path N: when ``chart_request`` is set, render PNG under ``assets/outputs/charts/``."""
    for idx, slide in enumerate(slides):
        existing = slide.get("chart_path")
        if existing and Path(str(existing)).is_file():
            logger.info("event=gtm.chart_skip_existing slide=%s path=%s", idx, existing)
            continue
        cr = slide.get("chart_request")
        if not isinstance(cr, dict) or not cr:
            continue
        try:
            path = render_slide_chart_from_spec(cr, idx, project_root=project_root)
            slide["chart_path"] = path
            logger.info("event=gtm.chart_materialized slide=%s path=%s", idx, path)
        except Exception:
            logger.exception("event=gtm.chart_failed slide=%s", idx)


def _materialize_slide_images(
    slides: list[dict[str, Any]],
    project_root: Path,
) -> None:
    for idx, slide in enumerate(slides):
        existing = slide.get("image_path")
        if existing and Path(str(existing)).is_file():
            logger.info("event=gtm.image_skip_existing path=%s", existing)
            continue
        prompt = slide.get("image_prompt")
        if not prompt:
            continue
        out = slide_asset_path(idx, "png", project_root=project_root)
        logger.info(
            "event=gtm.image_placeholder slide=%s chars=%s path=%s",
            idx,
            len(str(prompt)),
            out,
        )
        process_raster_image(_placeholder_png_bytes(str(prompt)), "png", out)
        slide["image_path"] = out


# --- GTM: Draft (Layer 4 + 3) --------------------------------------------------


def _persona_agent_label(persona_id: str) -> str:
    return {
        "venture_capital": "Venture Capital",
        "govtech": "GovTech",
        "risk_auditor": "Risk & Audit",
        "consensus": "Consensus synthesis",
    }.get(persona_id, persona_id)


def _prediction_monologue_excerpt(pred: Any) -> dict[str, str]:
    rationale = ""
    for attr in ("consensus_rationale", "rationale", "reasoning"):
        v = getattr(pred, attr, None)
        if v is not None and str(v).strip():
            rationale = str(v).strip()
            break
    critique = ""
    for attr in ("critique", "strategic_critique", "self_critique"):
        v = getattr(pred, attr, None)
        if v is not None and str(v).strip():
            critique = str(v).strip()
            break
    return {"rationale": rationale, "critique": critique}


def _clip_stream_text(s: str, max_len: int = 2400) -> str:
    t = (s or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _run_gtm_draft_with_stream(
    body: GTMRequest,
    stream: Callable[[dict[str, Any]], None] | None = None,
) -> GTMDraftResponse:
    """
    Ingest files, run GTMOrchestrator, return slide JSON only.
    When ``persona=consensus``, runs VC → GovTech → Risk sub-drafts (serial on one Ollama GPU),
    then ``StrategySynthesisSignature`` for the master deck.
    When ``web_grounding`` is true and ``TAVILY_API_KEY`` or ``SERPER_API_KEY`` is set, merges
    live news/web snippets into context (see telemetry ``live_grounding_data``).
    Path R: when tabular files are attached and ``RELULAYER_DATA_AUDIT`` / keyword heuristics match,
    runs ``DataAuditorOrchestrator`` + sandboxed Python; stdout is injected before GTM (see ``data_audit`` telemetry).

    Path DD: optional ``stream`` receives JSON-serializable event dicts for live telemetry (WebSocket).
    The caller is responsible for ``VRAMManager.clear()`` after this returns (HTTP route or WS handler).
    """
    def _emit(ev: dict[str, Any]) -> None:
        if stream is None:
            return
        try:
            stream(ev)
        except Exception:
            logger.exception("event=gtm.draft.stream_emit_failed")

    logger.info(
        "event=gtm.draft.start prompt_chars=%s file_count=%s folder_rag=%r persona=%s",
        len(body.user_prompt),
        len(body.file_paths),
        (body.project_folder or "").strip() or None,
        body.persona,
    )
    files = _load_ingestion_files(body.file_paths) if body.file_paths else []
    ingested = _ingestion.process_files(files)
    ctx_parts: list[str] = []
    if ingested["context_string"].strip():
        ctx_parts.append(ingested["context_string"])
    meta: dict[str, Any] = {
        "template_metadata": ingested["metadata"].get("template_metadata"),
        "paths": list(ingested["metadata"].get("paths") or []),
    }
    graph_telemetry: dict[str, Any] = {
        "graph_mode": None,
        "graph_cache_hit": None,
        "graph_entities_total": None,
        "graph_subgraph_entities": None,
        "graph_subgraph_relations": None,
    }

    pf = (body.project_folder or "").strip()
    if pf:
        try:
            rag = _ingestion.process_folder_rag(
                pf,
                body.user_prompt,
                top_k=5,
                ollama_base_url=_gtm._config.base_url,  # noqa: SLF001
                embed_model=rag_embed_model(),
            )
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=str(e),
            ) from e
        if rag["context_string"].strip():
            ctx_parts.append(rag["context_string"])
        rm = rag["metadata"]
        for p in rm.get("paths") or []:
            if p not in meta["paths"]:
                meta["paths"].append(p)
        if rm.get("rag_sources") is not None:
            meta["rag_sources"] = rm["rag_sources"]
        if rm.get("rag_mode") is not None:
            meta["rag_mode"] = rm["rag_mode"]
        if rm.get("rag_files_scanned") is not None:
            meta["rag_files_scanned"] = rm["rag_files_scanned"]
        if rm.get("rag_chunks_considered") is not None:
            meta["rag_chunks_considered"] = rm["rag_chunks_considered"]

        if graph_rag_enabled():
            try:
                gctx = _ingestion.process_folder_graph_context(
                    pf,
                    body.user_prompt,
                    ollama_base_url=_gtm._config.base_url,  # noqa: SLF001
                )
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=str(e),
                ) from e
            gm = gctx["metadata"]
            if gm.get("graph_mode") is not None:
                graph_telemetry["graph_mode"] = gm.get("graph_mode")
            if gm.get("graph_cache_hit") is not None:
                graph_telemetry["graph_cache_hit"] = gm.get("graph_cache_hit")
            if gm.get("graph_entities_total") is not None:
                graph_telemetry["graph_entities_total"] = gm.get("graph_entities_total")
            if gm.get("graph_subgraph_entities") is not None:
                graph_telemetry["graph_subgraph_entities"] = gm.get(
                    "graph_subgraph_entities",
                )
            if gm.get("graph_subgraph_relations") is not None:
                graph_telemetry["graph_subgraph_relations"] = gm.get(
                    "graph_subgraph_relations",
                )
            if gctx["context_string"].strip():
                ctx_parts.append(gctx["context_string"].strip())
                for p in gm.get("paths") or []:
                    if p not in meta["paths"]:
                        meta["paths"].append(p)

    live_grounding_data: LiveGroundingData | None = None
    if body.web_grounding:
        try:
            og = fetch_live_grounding(body.user_prompt)
            live_grounding_data = LiveGroundingData(
                active=og.active,
                provider=og.provider,
                search_query_used=og.search_query_used,
                snippet_count=og.snippet_count,
                snippets=[
                    LiveGroundingSnippet(
                        title=s.get("title") or "",
                        url=s.get("url") or "",
                        snippet=s.get("snippet") or "",
                    )
                    for s in og.snippets
                ],
                error=og.error,
            )
            if og.context_block.strip():
                ctx_parts.append(og.context_block)
                logger.info(
                    "event=gtm.live_grounding.injected provider=%s snippets=%s query=%r",
                    og.provider,
                    len(og.snippets),
                    og.search_query_used[:80] if og.search_query_used else "",
                )
            elif og.error and og.provider not in ("disabled", "none"):
                logger.info(
                    "event=gtm.live_grounding.empty provider=%s err=%s",
                    og.provider,
                    og.error[:120] if og.error else "",
                )
        except Exception:
            logger.exception("event=gtm.live_grounding_failed")
            live_grounding_data = LiveGroundingData(
                active=False,
                provider="error",
                error="Unexpected grounding failure; see server logs.",
            )
    else:
        live_grounding_data = LiveGroundingData(
            active=False,
            provider="disabled",
            error="Disabled for this request (web_grounding=false).",
        )

    data_audit_chunk, data_audit_tel = _run_data_audit_for_gtm(
        body.user_prompt,
        body.file_paths or [],
        ingested.get("context_string") or "",
    )
    if data_audit_chunk and data_audit_chunk.strip():
        ctx_parts.append(data_audit_chunk.strip())

    ctx = "\n\n---\n\n".join(ctx_parts) if ctx_parts else ""
    logger.info(
        "event=gtm.draft.ingestion_done context_chars=%s template_hint=%s rag_mode=%s",
        len(ctx),
        meta.get("template_metadata"),
        meta.get("rag_mode"),
    )

    mem_block = ""
    try:
        mem_block = _success_store.format_few_shot_block(
            body.user_prompt,
            body.persona,
            ollama_base_url=_gtm._config.base_url,  # noqa: SLF001
        )
    except Exception:
        logger.exception("event=gtm.strategic_memory_failed")
    if mem_block.strip():
        logger.info(
            "event=gtm.strategic_memory_injected chars=%s",
            len(mem_block),
        )

    ctx_for_gtm = ctx
    sm = mem_block.strip() or None
    if sm:
        ctx_for_gtm = (
            f"{sm}\n\n---\n\n## Current ingestion & RAG context\n\n{ctx}"
        )

    _emit(
        {
            "type": "phase",
            "phase": "model_context_ready",
            "message": "Ingestion, RAG, grounding, and strategic memory merged into model context.",
            "context_chars": len(ctx_for_gtm or ""),
        },
    )

    consensus_turns: list[ConsensusPersonaTurn] = []
    try:
        if body.persona == "consensus":
            logger.info(
                "event=gtm.draft.consensus.start order=%s",
                list(GTM_CONSENSUS_PERSONA_ORDER),
            )
            _emit(
                {
                    "type": "phase",
                    "phase": "consensus_sub_drafts",
                    "message": "Sub-agents drafting serially (VC → GovTech → Risk), then strategy synthesis.",
                },
            )
            drafts_json: dict[str, str] = {}
            for pid in GTM_CONSENSUS_PERSONA_ORDER:
                _emit(
                    {
                        "type": "agent_start",
                        "agent": pid,
                        "role": "sub_draft",
                        "label": _persona_agent_label(pid),
                    },
                )
                try:
                    sub = _gtm.forward_persona_draft(
                        ctx_for_gtm,
                        body.user_prompt,
                        persona_id=pid,
                    )
                except Exception as e:
                    logger.exception("event=gtm.draft.consensus.persona_failed persona=%s", pid)
                    cfg = _gtm._config  # noqa: SLF001
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            f"Consensus sub-draft failed for persona {pid!r} "
                            f"({type(e).__name__}: {e}). "
                            f"Check Ollama at {cfg.base_url!r} (model {cfg.gtm_model!r})."
                        ),
                    ) from e
                ap_sub, ac_sub, ht_sub = _extract_gtm_telemetry_from_dspy_history(
                    last_n_calls=1,
                )
                consensus_turns.append(
                    ConsensusPersonaTurn(
                        persona=pid,
                        raw_prompt=ap_sub,
                        raw_completion=ac_sub,
                        history_turns=ht_sub,
                    ),
                )
                pj = getattr(sub, "presentation_json", None)
                drafts_json[pid] = str(pj if pj is not None else sub)
                logger.info(
                    "event=gtm.draft.consensus.persona_done persona=%s chars=%s",
                    pid,
                    len(drafts_json[pid]),
                )
                mono_sub = _prediction_monologue_excerpt(sub)
                _emit(
                    {
                        "type": "agent_thought",
                        "agent": pid,
                        "role": "sub_draft",
                        "label": _persona_agent_label(pid),
                        "rationale": _clip_stream_text(mono_sub["rationale"], 4000),
                        "critique": _clip_stream_text(mono_sub["critique"], 2000),
                        "completion_excerpt": _clip_stream_text(ac_sub, 4000),
                        "deck_json_chars": len(drafts_json[pid]),
                    },
                )
            _emit(
                {
                    "type": "agent_start",
                    "agent": "strategy_synthesis",
                    "role": "synthesis",
                    "label": "Strategy synthesis (merge)",
                },
            )
            try:
                pred = _gtm.forward_strategy_synthesis(
                    body.user_prompt,
                    drafts_json[GTM_CONSENSUS_PERSONA_ORDER[0]],
                    drafts_json[GTM_CONSENSUS_PERSONA_ORDER[1]],
                    drafts_json[GTM_CONSENSUS_PERSONA_ORDER[2]],
                )
            except Exception as e:
                logger.exception("event=gtm.draft.consensus.synthesis_failed")
                cfg = _gtm._config  # noqa: SLF001
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"Strategy synthesis failed ({type(e).__name__}: {e}). "
                        f"Check Ollama at {cfg.base_url!r} (model {cfg.gtm_model!r})."
                    ),
                ) from e
            _ap_syn, ac_syn, _ht_syn = _extract_gtm_telemetry_from_dspy_history(
                last_n_calls=1,
            )
            mono_syn = _prediction_monologue_excerpt(pred)
            _emit(
                {
                    "type": "agent_thought",
                    "agent": "strategy_synthesis",
                    "role": "synthesis",
                    "label": "Strategy synthesis (merge)",
                    "rationale": _clip_stream_text(mono_syn["rationale"], 5000),
                    "critique": _clip_stream_text(mono_syn["critique"], 2000),
                    "completion_excerpt": _clip_stream_text(ac_syn, 4000),
                },
            )
        else:
            _emit(
                {
                    "type": "agent_start",
                    "agent": body.persona,
                    "role": "single_persona",
                    "label": _persona_agent_label(str(body.persona)),
                },
            )
            pred = _gtm.forward(
                context=ctx,
                user_instructions=body.user_prompt,
                persona=body.persona,
                strategic_memory=sm,
            )
            ap_sp, ac_sp, _ht_sp = _extract_gtm_telemetry_from_dspy_history(
                last_n_calls=1,
            )
            mono_sp = _prediction_monologue_excerpt(pred)
            _emit(
                {
                    "type": "agent_thought",
                    "agent": body.persona,
                    "role": "single_persona",
                    "label": _persona_agent_label(str(body.persona)),
                    "rationale": _clip_stream_text(mono_sp["rationale"], 5000),
                    "critique": _clip_stream_text(mono_sp["critique"], 2000),
                    "completion_excerpt": _clip_stream_text(ac_sp, 4000),
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("event=gtm.draft.dspy_failed")
        cfg = _gtm._config  # noqa: SLF001
        raise HTTPException(
            status_code=503,
            detail=(
                f"DSPy/Ollama call failed ({type(e).__name__}: {e}). "
                f"Ensure Ollama is running and reachable at {cfg.base_url!r} "
                f"(model {cfg.gtm_model!r}). On the host, the default base is "
                f"http://127.0.0.1:11434; in Docker set OLLAMA_HOST if needed."
            ),
        ) from e

    raw_json = getattr(pred, "presentation_json", None)
    if raw_json is None:
        raw_json = str(pred)
    logger.info("event=gtm.draft.dspy_done output_chars=%s", len(str(raw_json)))

    rationale_val = getattr(pred, "consensus_rationale", None)
    if rationale_val is None or str(rationale_val).strip() == "":
        rationale_val = getattr(pred, "rationale", None)
    if rationale_val is None:
        rationale_val = getattr(pred, "reasoning", None)
    rationale_str: str | None = (
        str(rationale_val) if rationale_val is not None else None
    )

    raw_prompt, raw_completion, hist_turns = _extract_gtm_telemetry_from_dspy_history(
        last_n_calls=1,
    )
    if not raw_prompt and not raw_completion:
        logger.warning(
            "event=gtm.draft.telemetry_empty (is DSPy history disabled? inspect_history would be empty)",
        )

    deck = _parse_gtm_deck(str(raw_json))
    slides_raw = deck.get("slides") or []
    if not isinstance(slides_raw, list):
        raise HTTPException(status_code=502, detail="slides must be a list.")
    slides_out = [s for s in slides_raw if isinstance(s, dict)]
    _assign_consensus_slide_original_ids(slides_out)

    ds = deck.get("design_specs")
    design_specs = ds if isinstance(ds, dict) else None
    template_hint = meta.get("template_metadata")

    slide_deck_payload: dict[str, Any] = {"slides": slides_out}
    if design_specs is not None:
        slide_deck_payload["design_specs"] = design_specs
    deck_str = json.dumps(slide_deck_payload, ensure_ascii=False, default=str)

    sc_applied = False
    sc_skip = ""
    sc_verdict: str | None = None
    sc_c: int | None = None
    sc_f: int | None = None
    sc_si: int | None = None
    sc_refined = 0
    structural_alerts: list[StructuralSentinelAlertTelemetry] = []

    if body.self_correction:
        if not slides_out:
            sc_skip = "no_slides"
        else:
            logger.info(
                "event=gtm.self_correction.start slides=%s",
                len(slides_out),
            )
            _emit(
                {
                    "type": "phase",
                    "phase": "self_correction",
                    "message": "Path Y — Strategic Judge evaluating draft rubric.",
                },
            )
            _emit(
                {
                    "type": "agent_start",
                    "agent": "strategic_judge",
                    "role": "judge",
                    "label": "Strategic Judge (Path Y)",
                },
            )
            try:
                jpred = _strategic_judge.forward(
                    strategic_directive=body.user_prompt.strip(),
                    finalized_deck_json=deck_str,
                )
            except Exception:
                logger.exception("event=gtm.self_correction.judge_failed")
                sc_skip = "judge_error"
            else:
                scores_raw = getattr(jpred, "rubric_scores_json", None)
                parsed_scores = _parse_strategic_judge_rubric_json(
                    str(scores_raw or ""),
                )
                verdict_raw = getattr(jpred, "committee_verdict", None)
                verdict_norm = _normalize_committee_verdict(
                    str(verdict_raw or "revise"),
                )
                rationale_body = getattr(jpred, "auditor_rationale", None)
                if rationale_body is None:
                    rationale_body = getattr(jpred, "rationale", None) or getattr(
                        jpred,
                        "reasoning",
                        None,
                    )
                auditor_rationale = str(rationale_body or "").strip()
                if not auditor_rationale:
                    auditor_rationale = (
                        "Judge returned no rationale text; improve clarity, feasibility, "
                        "and strategic impact consistent with the rubric scores."
                    )

                _emit(
                    {
                        "type": "agent_thought",
                        "agent": "strategic_judge",
                        "role": "judge",
                        "label": "Strategic Judge (Path Y)",
                        "verdict": verdict_norm,
                        "rubric": {
                            "clarity": parsed_scores.get("clarity"),
                            "feasibility": parsed_scores.get("feasibility"),
                            "strategic_impact": parsed_scores.get("strategic_impact"),
                        },
                        "rationale": _clip_stream_text(auditor_rationale, 4000),
                    },
                )

                sc_verdict = verdict_norm
                sc_c = parsed_scores.get("clarity")
                sc_f = parsed_scores.get("feasibility")
                sc_si = parsed_scores.get("strategic_impact")

                if verdict_norm != "revise":
                    sc_skip = "verdict_not_revise"
                elif not _any_rubric_below_7(parsed_scores):
                    sc_skip = "scores_all_ge_7"
                else:
                    cap = self_correction_max_slides()
                    indices = _pick_slide_indices_for_self_correction(
                        slides_out,
                        parsed_scores,
                        cap,
                    )
                    sc_original_count = len(slides_out)
                    sc_expected_original_ids = frozenset(
                        str(s.get("original_id") or "").strip() for s in slides_out
                    )
                    sc_stable_slides = copy.deepcopy(slides_out)
                    for idx in indices:
                        slide = slides_out[idx]
                        instr = _self_correction_refinement_instruction(
                            user_prompt=body.user_prompt,
                            verdict=verdict_norm,
                            scores=parsed_scores,
                            auditor_rationale=auditor_rationale,
                            slide_index=idx,
                            slide_count=len(slides_out),
                        )
                        try:
                            rp = _gtm_refine.forward(
                                slide_json=json.dumps(
                                    slide,
                                    ensure_ascii=False,
                                    default=str,
                                ),
                                refinement_instruction=instr,
                            )
                        except Exception:
                            logger.exception(
                                "event=gtm.self_correction.refine_failed slide_index=%s",
                                idx,
                            )
                            continue
                        _apply_refine_prediction_to_slide(slide, rp)
                        sc_refined += 1
                    bad_slide_count = len(slides_out)
                    id_ok, id_detail, id_miss, id_dups = _verify_slides_original_id_integrity(
                        slides_out,
                        sc_expected_original_ids,
                    )
                    if len(slides_out) != sc_original_count:
                        slides_out = copy.deepcopy(sc_stable_slides)
                        slide_deck_payload = {"slides": slides_out}
                        if design_specs is not None:
                            slide_deck_payload["design_specs"] = design_specs
                        deck_str = json.dumps(
                            slide_deck_payload,
                            ensure_ascii=False,
                            default=str,
                        )
                        structural_alerts.append(
                            StructuralSentinelAlertTelemetry(
                                stage="path_y_self_correction",
                                original_slide_count=sc_original_count,
                                revised_slide_count=bad_slide_count,
                                detail="Self-Correction pass altered slide count; reverted to pre-refine deck.",
                            ),
                        )
                        logger.warning(
                            "event=gtm.structural_drift_alert type=structural_drift_alert "
                            "stage=path_y_self_correction original=%s revised=%s",
                            sc_original_count,
                            bad_slide_count,
                        )
                        _emit(
                            {
                                "type": "structural_drift_alert",
                                "stage": "path_y_self_correction",
                                "original_slide_count": sc_original_count,
                                "revised_slide_count": bad_slide_count,
                                "message": "Structural Sentinel (Path KK): slide count mismatch; "
                                "Self-Correction revision rejected.",
                            },
                        )
                        sc_applied = False
                        sc_refined = 0
                        sc_skip = "structural_drift_alert"
                    elif not id_ok:
                        slides_out = copy.deepcopy(sc_stable_slides)
                        slide_deck_payload = {"slides": slides_out}
                        if design_specs is not None:
                            slide_deck_payload["design_specs"] = design_specs
                        deck_str = json.dumps(
                            slide_deck_payload,
                            ensure_ascii=False,
                            default=str,
                        )
                        structural_alerts.append(
                            StructuralSentinelAlertTelemetry(
                                type="structural_identity_drift",
                                stage="path_y_self_correction",
                                original_slide_count=sc_original_count,
                                revised_slide_count=bad_slide_count,
                                detail=id_detail,
                                identity_missing_ids=id_miss,
                                identity_duplicate_ids=id_dups,
                            ),
                        )
                        logger.warning(
                            "event=gtm.structural_identity_drift stage=path_y_self_correction detail=%s",
                            id_detail,
                        )
                        _emit(
                            {
                                "type": "structural_identity_drift",
                                "stage": "path_y_self_correction",
                                "original_slide_count": sc_original_count,
                                "revised_slide_count": bad_slide_count,
                                "detail": id_detail,
                                "identity_missing_ids": id_miss,
                                "identity_duplicate_ids": id_dups,
                                "message": "Structural Sentinel (Path OO): slide identity mismatch; "
                                "Self-Correction revision rejected.",
                            },
                        )
                        sc_applied = False
                        sc_refined = 0
                        sc_skip = "structural_identity_drift"
                    elif sc_refined > 0:
                        sc_applied = True
                        slide_deck_payload = {"slides": slides_out}
                        if design_specs is not None:
                            slide_deck_payload["design_specs"] = design_specs
                        deck_str = json.dumps(
                            slide_deck_payload,
                            ensure_ascii=False,
                            default=str,
                        )
                        sc_skip = ""
                    else:
                        sc_skip = "refine_all_failed"

    historical_benchmark_tel: HistoricalBenchmarkTelemetry | None = None
    try:
        raw_hb = _success_store.compute_historical_benchmark(
            user_prompt=body.user_prompt,
            draft_slides=slides_out,
            persona=str(body.persona),
            ollama_base_url=_gtm._config.base_url,  # noqa: SLF001
        )
        if raw_hb.get("mode") != "disabled":
            historical_benchmark_tel = HistoricalBenchmarkTelemetry(
                confidence_percent=int(raw_hb.get("confidence_percent") or 0),
                mode=str(raw_hb.get("mode") or ""),
                reference_label=str(raw_hb.get("reference_label") or ""),
                mean_top_k_similarity=raw_hb.get("mean_top_k_similarity"),
                top_matches=[
                    HistoricalBenchmarkMatch(**m)
                    for m in (raw_hb.get("top_matches") or [])
                    if isinstance(m, dict)
                ],
                display_hint=str(raw_hb.get("display_hint") or ""),
            )
    except Exception:
        logger.exception("event=gtm.historical_benchmark_failed")

    audit_report_obj: RedTeamAuditReport | None = None
    audit_raw_prompt = ""
    audit_raw_completion = ""
    logger.info(
        "event=gtm.red_team.start deck_json_chars=%s (second LM pass; GPU serializes after GTM)",
        len(deck_str),
    )
    _emit(
        {
            "type": "agent_start",
            "agent": "red_team",
            "role": "audit",
            "label": "Red Team auditor",
        },
    )
    try:
        audit_pred = _red_team.forward(
            user_prompt=body.user_prompt.strip(),
            slide_deck_json=deck_str,
        )
        risks_raw = getattr(audit_pred, "strategic_risks_json", None)
        items = _parse_strategic_risks_json(str(risks_raw or ""))
        r_aud = getattr(audit_pred, "rationale", None)
        if r_aud is None:
            r_aud = getattr(audit_pred, "reasoning", None)
        rationale_audit = str(r_aud) if r_aud is not None else None
        audit_report_obj = RedTeamAuditReport(
            weak_points=items,
            red_team_alert=_red_team_significant(items),
            rationale=rationale_audit,
        )
        ap_aud, ac_aud, _ = _extract_gtm_telemetry_from_dspy_history(last_n_calls=1)
        audit_raw_prompt, audit_raw_completion = ap_aud, ac_aud
        logger.info(
            "event=gtm.red_team.complete alert=%s items=%s",
            audit_report_obj.red_team_alert,
            len(items),
        )
        _emit(
            {
                "type": "agent_thought",
                "agent": "red_team",
                "role": "audit",
                "label": "Red Team auditor",
                "red_team_alert": audit_report_obj.red_team_alert,
                "risk_count": len(items),
                "rationale": _clip_stream_text(rationale_audit or "", 4000),
            },
        )
    except Exception:
        logger.exception("event=gtm.red_team.failed")
        audit_report_obj = None
        _emit(
            {
                "type": "agent_thought",
                "agent": "red_team",
                "role": "audit",
                "label": "Red Team auditor",
                "error": True,
                "message": "Red Team pass failed; see server logs.",
            },
        )

    wargame_tel: WargameAuditTelemetry | None = None
    wargame_transcript = ""
    wargame_residual_json = "[]"
    if body.wargame_debate:
        if not slides_out:
            wargame_tel = WargameAuditTelemetry(skipped_reason="no_slides")
        else:
            _emit(
                {
                    "type": "phase",
                    "phase": "wargame",
                    "message": "Path BB — Adversary vs Proponent debate (3 rounds).",
                },
            )
            try:
                wg = _wargame.forward(
                    strategic_directive=body.user_prompt.strip(),
                    consensus_deck_json=deck_str,
                )
                wargame_transcript = wg.full_transcript or ""
                wargame_residual_json = wg.residual_risks_json or "[]"
                resid = _parse_strategic_risks_json(wg.residual_risks_json)
                wargame_tel = WargameAuditTelemetry(
                    turns=[
                        WargameDebateTurnTelemetry(
                            turn=int(r.get("turn", 0)),
                            adversary_attack=str(r.get("adversary_attack") or ""),
                            proponent_mitigation=str(r.get("proponent_mitigation") or ""),
                        )
                        for r in wg.debate_turns
                        if isinstance(r, dict)
                    ],
                    residual_risks=resid,
                    residual_headline=wg.residual_headline,
                    wargame_alert=_red_team_significant(resid),
                )
                logger.info(
                    "event=gtm.wargame.complete turns=%s residual=%s alert=%s",
                    len(wargame_tel.turns),
                    len(resid),
                    wargame_tel.wargame_alert,
                )
                _emit(
                    {
                        "type": "agent_thought",
                        "agent": "wargame",
                        "role": "debate",
                        "label": "Strategic wargame (Path BB)",
                        "wargame_alert": wargame_tel.wargame_alert,
                        "residual_headline": wargame_tel.residual_headline,
                        "turns_completed": len(wargame_tel.turns),
                    },
                )
            except Exception:
                logger.exception("event=gtm.wargame.failed")
                wargame_tel = WargameAuditTelemetry(skipped_reason="orchestrator_error")
                _emit(
                    {
                        "type": "agent_thought",
                        "agent": "wargame",
                        "role": "debate",
                        "label": "Strategic wargame (Path BB)",
                        "error": True,
                        "message": "Wargame orchestrator failed.",
                    },
                )

    # Path FF: Chairman resolution — apply mitigations to deck before returning to human.
    if body.wargame_debate and wargame_tel and not wargame_tel.skipped_reason and slides_out:
        chairman_original_count = len(slides_out)
        chairman_stable_slides = copy.deepcopy(slides_out)
        chairman_expected_original_ids = frozenset(
            str(s.get("original_id") or "").strip() for s in chairman_stable_slides
        )
        chairman_stable_design = (
            copy.deepcopy(design_specs) if design_specs is not None else None
        )
        _emit(
            {
                "type": "agent_start",
                "agent": "chairman",
                "role": "resolution",
                "label": "Chairman (Path FF)",
            },
        )
        try:
            chr_ = _chairman.forward(
                strategic_directive=body.user_prompt.strip(),
                consensus_deck_json=deck_str,
                wargame_transcript=wargame_transcript,
                residual_risks_json=wargame_residual_json,
            )
            revised = _parse_gtm_deck(chr_.revised_deck_json)
            revised_slides_raw = revised.get("slides") or []
            if isinstance(revised_slides_raw, list) and revised_slides_raw:
                revised_slides = [s for s in revised_slides_raw if isinstance(s, dict)]
                revised_count = len(revised_slides)
                if revised_count != chairman_original_count:
                    slides_out = copy.deepcopy(chairman_stable_slides)
                    design_specs = (
                        copy.deepcopy(chairman_stable_design)
                        if chairman_stable_design is not None
                        else design_specs
                    )
                    slide_deck_payload = {"slides": slides_out}
                    if design_specs is not None:
                        slide_deck_payload["design_specs"] = design_specs
                    deck_str = json.dumps(
                        slide_deck_payload,
                        ensure_ascii=False,
                        default=str,
                    )
                    structural_alerts.append(
                        StructuralSentinelAlertTelemetry(
                            stage="path_ff_chairman",
                            original_slide_count=chairman_original_count,
                            revised_slide_count=revised_count,
                            detail="Chairman revised_deck_json slide count mismatch; "
                            "reverted to pre-Chairman deck.",
                        ),
                    )
                    logger.warning(
                        "event=gtm.structural_drift_alert type=structural_drift_alert "
                        "stage=path_ff_chairman original=%s revised=%s",
                        chairman_original_count,
                        revised_count,
                    )
                    _emit(
                        {
                            "type": "structural_drift_alert",
                            "stage": "path_ff_chairman",
                            "original_slide_count": chairman_original_count,
                            "revised_slide_count": revised_count,
                            "message": "Structural Sentinel (Path KK): slide count mismatch; "
                            "Chairman revision rejected.",
                        },
                    )
                    _emit(
                        {
                            "type": "agent_thought",
                            "agent": "chairman",
                            "role": "resolution",
                            "label": "Chairman (Path FF)",
                            "error": True,
                            "rationale": _clip_stream_text(chr_.chairman_rationale, 4500),
                            "message": "Chairman output rejected by Structural Sentinel (slide count).",
                        },
                    )
                else:
                    id_ok, id_detail, id_miss, id_dups = _verify_slides_original_id_integrity(
                        revised_slides,
                        chairman_expected_original_ids,
                    )
                    if not id_ok:
                        slides_out = copy.deepcopy(chairman_stable_slides)
                        design_specs = (
                            copy.deepcopy(chairman_stable_design)
                            if chairman_stable_design is not None
                            else design_specs
                        )
                        slide_deck_payload = {"slides": slides_out}
                        if design_specs is not None:
                            slide_deck_payload["design_specs"] = design_specs
                        deck_str = json.dumps(
                            slide_deck_payload,
                            ensure_ascii=False,
                            default=str,
                        )
                        structural_alerts.append(
                            StructuralSentinelAlertTelemetry(
                                type="structural_identity_drift",
                                stage="path_ff_chairman",
                                original_slide_count=chairman_original_count,
                                revised_slide_count=len(revised_slides),
                                detail=id_detail,
                                identity_missing_ids=id_miss,
                                identity_duplicate_ids=id_dups,
                            ),
                        )
                        logger.warning(
                            "event=gtm.structural_identity_drift stage=path_ff_chairman detail=%s",
                            id_detail,
                        )
                        _emit(
                            {
                                "type": "structural_identity_drift",
                                "stage": "path_ff_chairman",
                                "original_slide_count": chairman_original_count,
                                "revised_slide_count": len(revised_slides),
                                "detail": id_detail,
                                "identity_missing_ids": id_miss,
                                "identity_duplicate_ids": id_dups,
                                "message": "Structural Sentinel (Path OO): slide identity mismatch; "
                                "Chairman revision rejected.",
                            },
                        )
                        _emit(
                            {
                                "type": "agent_thought",
                                "agent": "chairman",
                                "role": "resolution",
                                "label": "Chairman (Path FF)",
                                "error": True,
                                "rationale": _clip_stream_text(chr_.chairman_rationale, 4500),
                                "message": "Chairman output rejected by Structural Sentinel (original_id integrity).",
                            },
                        )
                    else:
                        slides_out = revised_slides
                        ds2 = revised.get("design_specs")
                        if isinstance(ds2, dict):
                            design_specs = ds2
                        slide_deck_payload = {"slides": slides_out}
                        if design_specs is not None:
                            slide_deck_payload["design_specs"] = design_specs
                        deck_str = json.dumps(
                            slide_deck_payload,
                            ensure_ascii=False,
                            default=str,
                        )
                        _emit(
                            {
                                "type": "agent_thought",
                                "agent": "chairman",
                                "role": "resolution",
                                "label": "Chairman (Path FF)",
                                "rationale": _clip_stream_text(chr_.chairman_rationale, 4500),
                                "slides": len(slides_out),
                            },
                        )
                        logger.info(
                            "event=gtm.chairman.applied slides=%s",
                            len(slides_out),
                        )
            else:
                logger.warning("event=gtm.chairman.empty_deck")
        except Exception:
            logger.exception("event=gtm.chairman.failed")
            _emit(
                {
                    "type": "agent_thought",
                    "agent": "chairman",
                    "role": "resolution",
                    "label": "Chairman (Path FF)",
                    "error": True,
                    "message": "Chairman resolution failed; returning pre-chairman deck.",
                },
            )

    # Path II: Compliance pass (post-draft, after Chairman if present).
    compliance_tel: CompliancePassTelemetry | None = None
    if body.compliance_pass:
        if not slides_out:
            compliance_tel = CompliancePassTelemetry(
                standard=str(body.compliance_standard or "").strip() or "NIST CSF",
                skipped_reason="no_slides",
            )
        else:
            std = str(body.compliance_standard or "").strip() or "NIST CSF"
            compliance_tel = CompliancePassTelemetry(standard=std)
            _emit(
                {
                    "type": "agent_start",
                    "agent": "compliance",
                    "role": "audit",
                    "label": f"Compliance pass (Path II — {std})",
                },
            )
            try:
                pred = _compliance.forward(
                    standard=std,
                    strategic_directive=body.user_prompt.strip(),
                    slide_deck_json=deck_str,
                )
                findings_raw = str(getattr(pred, "findings_json", None) or "")
                summary = str(getattr(pred, "audit_summary", None) or "").strip()
                # Reuse the risk parser for severity normalization, then map into ComplianceFinding.
                findings: list[ComplianceFinding] = []
                try:
                    blob = json.loads((findings_raw or "").strip() or "[]")
                except Exception:
                    blob = []
                if isinstance(blob, list):
                    for it in blob:
                        if not isinstance(it, dict):
                            continue
                        si = it.get("slide_index")
                        try:
                            slide_index = int(si)
                        except (TypeError, ValueError):
                            continue
                        sev = str(it.get("severity") or "medium").strip().lower()
                        if sev not in ("low", "medium", "high"):
                            sev = "medium"
                        sc = it.get("suggested_copy") if isinstance(it.get("suggested_copy"), dict) else {}
                        findings.append(
                            ComplianceFinding(
                                slide_index=max(0, slide_index),
                                issue=str(it.get("issue") or "").strip(),
                                standard_clause=str(it.get("standard_clause") or "").strip(),
                                severity=sev,  # type: ignore[arg-type]
                                suggested_copy=ComplianceFindingSuggestedCopy(
                                    title=str(sc.get("title") or ""),
                                    body=str(sc.get("body") or ""),
                                    speaker_notes=str(sc.get("speaker_notes") or ""),
                                ),
                            ),
                        )
                compliance_tel = CompliancePassTelemetry(
                    standard=std,
                    summary=summary,
                    findings=findings,
                    skipped_reason="",
                )
                _emit(
                    {
                        "type": "agent_thought",
                        "agent": "compliance",
                        "role": "audit",
                        "label": f"Compliance pass (Path II — {std})",
                        "rationale": _clip_stream_text(summary, 3500),
                        "finding_count": len(findings),
                    },
                )
                logger.info("event=gtm.compliance.complete standard=%s findings=%s", std, len(findings))
            except Exception:
                logger.exception("event=gtm.compliance.failed")
                compliance_tel = CompliancePassTelemetry(
                    standard=std,
                    skipped_reason="orchestrator_error",
                )

    logger.info(
        "event=gtm.draft.complete slide_count=%s rag_mode=%s red_team=%s",
        len(slides_out),
        meta.get("rag_mode"),
        audit_report_obj.red_team_alert if audit_report_obj else None,
    )
    return GTMDraftResponse(
        slides=slides_out,
        design_specs=design_specs,
        template_hint=template_hint,
        telemetry=GTMTelemetry(
            rationale=rationale_str,
            raw_prompt=raw_prompt,
            raw_completion=raw_completion,
            history_turns=hist_turns,
            audit_report=audit_report_obj,
            audit_raw_prompt=audit_raw_prompt,
            audit_raw_completion=audit_raw_completion,
            consensus_persona_turns=consensus_turns,
            live_grounding_data=live_grounding_data,
            data_audit=data_audit_tel,
            graph_mode=graph_telemetry.get("graph_mode"),
            graph_cache_hit=graph_telemetry.get("graph_cache_hit"),
            graph_entities_total=graph_telemetry.get("graph_entities_total"),
            graph_subgraph_entities=graph_telemetry.get("graph_subgraph_entities"),
            graph_subgraph_relations=graph_telemetry.get("graph_subgraph_relations"),
            self_correction_applied=sc_applied,
            self_correction_skipped_reason=sc_skip,
            self_correction_judge_verdict=sc_verdict,
            self_correction_rubric_clarity=sc_c,
            self_correction_rubric_feasibility=sc_f,
            self_correction_rubric_strategic_impact=sc_si,
            self_correction_slides_refined=sc_refined,
            historical_benchmark=historical_benchmark_tel,
            wargame_audit=wargame_tel,
            compliance_pass=compliance_tel,
            structural_sentinel_alerts=structural_alerts,
        ),
    )


@app.post("/process/gtm/draft", response_model=GTMDraftResponse)
def process_gtm_draft(body: GTMRequest) -> GTMDraftResponse:
    try:
        return _run_gtm_draft_with_stream(body, None)
    finally:
        VRAMManager.clear()
        logger.info("event=gtm.draft.vram_cleared")


@app.websocket("/ws/process/gtm/draft")
async def gtm_draft_telemetry_websocket(websocket: WebSocket) -> None:
    """
    Path DD: same payload as ``POST /process/gtm/draft`` (``GTMRequest`` JSON), streamed events then ``final``.

    Client → server: one text frame, JSON body matching ``GTMRequest``.

    Server → client: JSON objects ``{"type": "status"|"agent_start"|"agent_thought"|"phase", ...}``,
    then ``{"type": "final", "ok": true, "payload": <GTMDraftResponse>}`` or ``ok: false`` with ``detail``.
    """
    await websocket.accept()
    try:
        raw = await websocket.receive_text()
    except WebSocketDisconnect:
        return
    try:
        body = GTMRequest.model_validate_json(raw)
    except Exception as e:
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "ok": False,
                    "detail": f"Invalid GTMRequest JSON: {e}",
                },
            )
        except Exception:
            pass
        await websocket.close(code=1003)
        return

    out_q: queue.Queue[Any] = queue.Queue()

    def stream_put(ev: dict[str, Any]) -> None:
        out_q.put(ev)

    result_holder: list[GTMDraftResponse] = []
    error_holder: list[BaseException] = []

    def worker() -> None:
        try:
            result_holder.append(_run_gtm_draft_with_stream(body, stream_put))
        except Exception as e:
            error_holder.append(e)
        finally:
            out_q.put(None)

    threading.Thread(target=worker, daemon=True).start()
    loop = asyncio.get_running_loop()

    while True:
        item = await loop.run_in_executor(None, out_q.get)
        if item is None:
            break
        try:
            await websocket.send_json(item)
        except Exception:
            logger.exception("event=gtm.draft.ws.send_failed")
            break

    try:
        if error_holder:
            err = error_holder[0]
            if isinstance(err, HTTPException):
                await websocket.send_json(
                    {
                        "type": "final",
                        "ok": False,
                        "detail": err.detail,
                        "status_code": err.status_code,
                    },
                )
            else:
                logger.exception("event=gtm.draft.ws.pipeline_failed")
                await websocket.send_json(
                    {
                        "type": "final",
                        "ok": False,
                        "detail": str(err),
                        "status_code": 500,
                    },
                )
        elif result_holder:
            await websocket.send_json(
                {
                    "type": "final",
                    "ok": True,
                    "payload": result_holder[0].model_dump(mode="json"),
                },
            )
    except Exception:
        logger.exception("event=gtm.draft.ws.final_send_failed")
    finally:
        VRAMManager.clear()
        logger.info("event=gtm.draft.vram_cleared")
        try:
            await websocket.close()
        except Exception:
            pass


# --- GTM: Refine slide (Layer 6) -----------------------------------------------


@app.post("/process/gtm/refine", response_model=GTMRefineResponse)
def process_gtm_refine(body: GTMRefineRequest) -> GTMRefineResponse:
    """
    Chat-style refinement: updates only ``title`` and ``body`` on the provided slide dict.
    """
    if not isinstance(body.slide, dict):
        raise HTTPException(status_code=400, detail="slide must be an object.")
    if body.war_room is not None:
        wr = body.war_room
        sid = _strategy_session_validate_id(wr.session_id)
        _strategy_session_load_doc(sid)
        if not _war_room_hub.slide_lock_held_by_user(sid, wr.slide_index, wr.user_id):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Slide is not locked for your strategist id in this war room, "
                    "or another user is auditing this slide."
                ),
            )
    logger.info(
        "event=gtm.refine.start instruction_chars=%s",
        len(body.refinement_instruction),
    )
    slide_out: dict[str, Any] = dict(body.slide)
    try:
        try:
            pred = _gtm_refine.forward(
                slide_json=json.dumps(slide_out, ensure_ascii=False, default=str),
                refinement_instruction=body.refinement_instruction.strip(),
            )
        except Exception as e:
            logger.exception("event=gtm.refine.dspy_failed")
            cfg = _gtm_refine._config  # noqa: SLF001
            raise HTTPException(
                status_code=503,
                detail=(
                    f"DSPy/Ollama refine failed ({type(e).__name__}: {e}). "
                    f"Check Ollama at {cfg.base_url!r} (model {cfg.gtm_model!r})."
                ),
            ) from e

        _apply_refine_prediction_to_slide(slide_out, pred)

        rationale_val = getattr(pred, "rationale", None)
        if rationale_val is None:
            rationale_val = getattr(pred, "reasoning", None)
        rationale_str: str | None = (
            str(rationale_val) if rationale_val is not None else None
        )

        raw_prompt, raw_completion, hist_turns = _extract_gtm_telemetry_from_dspy_history(
            last_n_calls=1,
        )

        oid_in = str(body.slide.get("original_id") or "").strip()
        oid_out = str(slide_out.get("original_id") or "").strip()
        if oid_in and oid_out != oid_in:
            logger.warning("event=gtm.structural_identity_drift stage=path_e_refine")
            return GTMRefineResponse(
                slide=dict(body.slide),
                telemetry=GTMTelemetry(
                    rationale=rationale_str,
                    raw_prompt=raw_prompt,
                    raw_completion=raw_completion,
                    history_turns=hist_turns,
                    structural_sentinel_alerts=[
                        StructuralSentinelAlertTelemetry(
                            type="structural_identity_drift",
                            stage="path_e_refine",
                            original_slide_count=1,
                            revised_slide_count=1,
                            detail="Refine pass lost or altered original_id; slide reverted.",
                            identity_missing_ids=[oid_in],
                            identity_duplicate_ids=[],
                        ),
                    ],
                ),
            )

        logger.info("event=gtm.refine.complete")
        return GTMRefineResponse(
            slide=slide_out,
            telemetry=GTMTelemetry(
                rationale=rationale_str,
                raw_prompt=raw_prompt,
                raw_completion=raw_completion,
                history_turns=hist_turns,
            ),
        )
    finally:
        VRAMManager.clear()
        logger.info("event=gtm.refine.vram_cleared")


# --- GTM: Strategic judge — Final Quality Gate (Path V) ----------------------


@app.post("/process/gtm/strategic-judge", response_model=GTMStrategicJudgeResponse)
def process_gtm_strategic_judge(body: GTMStrategicJudgeRequest) -> GTMStrategicJudgeResponse:
    """
    Path V: independent Executive Committee rubric over the current deck (consensus or single persona).
    UI should show scores before materialization.
    """
    slides_in = [s for s in body.slides if isinstance(s, dict)]
    if not slides_in:
        raise HTTPException(status_code=400, detail="slides must contain at least one object.")
    deck_str = json.dumps({"slides": slides_in}, ensure_ascii=False, default=str)
    directive = (body.user_prompt or "").strip()
    if not directive:
        directive = (
            "(No separate directive supplied; infer intended audience and success criteria from slide content.)"
        )
    logger.info(
        "event=gtm.judge.start slides=%s directive_chars=%s",
        len(slides_in),
        len(directive),
    )
    try:
        try:
            pred = _strategic_judge.forward(
                strategic_directive=directive,
                finalized_deck_json=deck_str,
            )
        except Exception as e:
            logger.exception("event=gtm.judge.dspy_failed")
            cfg = _strategic_judge._config  # noqa: SLF001
            raise HTTPException(
                status_code=503,
                detail=(
                    f"DSPy/Ollama judge failed ({type(e).__name__}: {e}). "
                    f"Check Ollama at {cfg.base_url!r} (model {cfg.gtm_model!r})."
                ),
            ) from e

        scores_raw = getattr(pred, "rubric_scores_json", None)
        parsed = _parse_strategic_judge_rubric_json(str(scores_raw or ""))
        clarity = parsed.get("clarity", 5)
        feasibility = parsed.get("feasibility", 5)
        strategic_impact = parsed.get("strategic_impact", 5)
        if len(parsed) < 3:
            logger.warning(
                "event=gtm.judge.rubric_partial parsed=%s raw_preview=%r",
                parsed,
                (str(scores_raw)[:200] if scores_raw else ""),
            )

        verdict_raw = getattr(pred, "committee_verdict", None)
        verdict = _normalize_committee_verdict(str(verdict_raw or "revise"))

        rationale_body = getattr(pred, "auditor_rationale", None)
        if rationale_body is None:
            rationale_body = getattr(pred, "rationale", None) or getattr(pred, "reasoning", None)
        auditor_rationale = str(rationale_body or "").strip()

        raw_prompt, raw_completion, hist_turns = _extract_gtm_telemetry_from_dspy_history(
            last_n_calls=1,
        )

        logger.info(
            "event=gtm.judge.complete clarity=%s feasibility=%s impact=%s verdict=%s",
            clarity,
            feasibility,
            strategic_impact,
            verdict,
        )
        return GTMStrategicJudgeResponse(
            scores=StrategicJudgeRubricScores(
                clarity=clarity,
                feasibility=feasibility,
                strategic_impact=strategic_impact,
            ),
            committee_verdict=verdict,
            auditor_rationale=auditor_rationale,
            telemetry=GTMTelemetry(
                rationale=auditor_rationale or None,
                raw_prompt=raw_prompt,
                raw_completion=raw_completion,
                history_turns=hist_turns,
            ),
        )
    finally:
        VRAMManager.clear()
        logger.info("event=gtm.judge.vram_cleared")


# --- GTM: Executive briefing (Path P) -----------------------------------------


@app.get("/process/gtm/media-capabilities")
def gtm_media_capabilities() -> dict[str, bool]:
    """
    Path MM: advertise server-side optional media stack so the UI can tier Video / Piper / browser.
    """
    st_dir = os.environ.get("RELULAYER_SADTALKER_DIR", "").strip()
    sadtalker = bool(st_dir and Path(st_dir).is_dir())
    piper = bool(os.environ.get("RELULAYER_PIPER_MODEL", "").strip())
    return {
        "sadtalker_configured": sadtalker,
        "piper_configured": piper,
    }


@app.get("/process/gtm/knowledge-graph/export")
def gtm_export_knowledge_graph(
    folder: str,
    kg_format: Literal["jsonld", "turtle"] = Query(
        "jsonld",
        alias="format",
        description="jsonld | turtle",
    ),
) -> Response:
    """Path GG: download Path X strategic knowledge graph for a project folder (BI portability)."""
    try:
        fname, data, mime = _ingestion.export_folder_knowledge_graph(
            folder,
            export_format=kg_format,
            ollama_base_url=_gtm._config.base_url,  # noqa: SLF001
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("event=knowledge_graph.export.failed")
        raise HTTPException(
            status_code=502,
            detail=f"Knowledge graph export failed: {e}",
        ) from e
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", fname) or "strategic_kg_export"
    return Response(
        content=data,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{safe}"'},
    )


@app.post("/process/gtm/executive-briefing", response_model=GTMExecutiveBriefingResponse)
def process_gtm_executive_briefing(body: GTMExecutiveBriefingRequest) -> GTMExecutiveBriefingResponse:
    """
    DSPy ``ExecutiveBriefingSignature``: one-page executive summary + per-slide talk track
    from the current deck JSON (for rehearsal and stakeholder pre-read).
    """
    slides_in = [s for s in body.slides if isinstance(s, dict)]
    if not slides_in:
        raise HTTPException(status_code=400, detail="slides must contain at least one object.")
    n = len(slides_in)
    deck_str = json.dumps({"slides": slides_in}, ensure_ascii=False, default=str)
    ctx = (body.user_prompt or "").strip()
    if not ctx:
        ctx = (
            "(No separate strategic directive supplied; infer audience and tone from slide content only.)"
        )
    logger.info("event=gtm.briefing.start slides=%s context_chars=%s", n, len(ctx))
    try:
        try:
            pred = _executive_briefing.forward(
                deck_json=deck_str,
                strategic_context=ctx,
            )
        except Exception as e:
            logger.exception("event=gtm.briefing.dspy_failed")
            cfg = _executive_briefing._config  # noqa: SLF001
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Executive briefing LM failed ({type(e).__name__}: {e}). "
                    f"Check Ollama at {cfg.base_url!r} (model {cfg.gtm_model!r})."
                ),
            ) from e

        summary = str(getattr(pred, "executive_summary", None) or "").strip()
        tt_raw = getattr(pred, "talk_track_json", None)
        track_strings = _parse_talk_track_json(str(tt_raw or ""), n)

        rationale_val = getattr(pred, "rationale", None)
        if rationale_val is None:
            rationale_val = getattr(pred, "reasoning", None)
        rationale_str: str | None = (
            str(rationale_val) if rationale_val is not None else None
        )

        raw_prompt, raw_completion, hist_turns = _extract_gtm_telemetry_from_dspy_history(
            last_n_calls=1,
        )

        logger.info("event=gtm.briefing.complete summary_chars=%s", len(summary))
        return GTMExecutiveBriefingResponse(
            executive_summary=summary or "(no executive summary produced)",
            slide_talk_tracks=[
                ExecutiveBriefingSlideTrack(slide_index=i, talk_track=track_strings[i])
                for i in range(n)
            ],
            telemetry=GTMTelemetry(
                rationale=rationale_str,
                raw_prompt=raw_prompt,
                raw_completion=raw_completion,
                history_turns=hist_turns,
            ),
        )
    finally:
        VRAMManager.clear()
        logger.info("event=gtm.briefing.vram_cleared")


@app.post(
    "/process/gtm/executive-briefing/tts",
    response_model=GTMExecutiveBriefingTtsResponse,
)
def process_gtm_executive_briefing_tts(
    body: GTMExecutiveBriefingTtsRequest,
) -> GTMExecutiveBriefingTtsResponse:
    """
    Optional Piper WAV synthesis when ``RELULAYER_PIPER_MODEL`` is set (see ``tools/narrative_tts``).
    """
    href = piper_synthesize_wav(body.text, project_root=_REPO_ROOT)
    if href:
        logger.info("event=gtm.briefing.tts.piper_ok href=%s", href)
        return GTMExecutiveBriefingTtsResponse(audio_href=href, engine="piper")
    return GTMExecutiveBriefingTtsResponse(audio_href=None, engine="none")


class GTMVideoBriefRequest(BaseModel):
    """Path HH: synthesize a short narrated video brief from talk track + slide hero images."""

    slides: list[dict[str, Any]] = Field(..., min_length=1)
    talk_track_text: str = Field(..., min_length=1, description="Narration script (Path P talk track).")
    avatar_image_path: str | None = Field(
        default=None,
        description="Optional repo-relative or absolute path to an avatar face image for SadTalker/Wav2Lip.",
    )
    seconds_per_slide: float = Field(
        default=4.0,
        ge=1.0,
        le=20.0,
        description="Slideshow fallback: duration per slide when avatar video is not configured.",
    )


class GTMVideoBriefResponse(BaseModel):
    video_path: str = Field(description="Absolute path to the written .mp4 file on the server.")
    static_href: str = Field(description="Browser URL path under /static (repo assets/).")
    mode: str = Field(description="sadtalker | slideshow")
    audio_href: str | None = Field(default=None, description="Narration WAV under /static when Piper is enabled.")


@app.post("/process/gtm/video-brief", response_model=GTMVideoBriefResponse)
def process_gtm_video_brief(body: GTMVideoBriefRequest) -> GTMVideoBriefResponse:
    """
    Path HH: Generate a short MP4 of an AI presenter.

    - If SadTalker is configured (env) and avatar_image_path is provided, attempts talking-head generation.
    - Otherwise falls back to a narrated slideshow from slide hero images (requires ffmpeg).
    """
    slides = [s for s in body.slides if isinstance(s, dict)]
    if not slides:
        raise HTTPException(status_code=400, detail="slides must contain at least one object.")
    script = (body.talk_track_text or "").strip()
    if not script:
        raise HTTPException(status_code=400, detail="talk_track_text must be non-empty.")

    href = piper_synthesize_wav(script, project_root=_REPO_ROOT)
    if not href:
        raise HTTPException(
            status_code=503,
            detail="Piper TTS unavailable. Set RELULAYER_PIPER_MODEL on the API host to enable narration WAV.",
        )
    # href is /static/outputs/audio/xxx.wav (repo assets/ mounted at /static)
    audio_abs = (_REPO_ROOT / "assets" / href.removeprefix("/static/")).resolve()

    image_paths: list[str] = []
    for s in slides:
        p = s.get("image_path")
        if isinstance(p, str) and p.strip():
            image_paths.append(p.strip())

    avatar_abs: str | None = None
    if body.avatar_image_path and str(body.avatar_image_path).strip():
        ap = str(body.avatar_image_path).strip()
        try:
            avatar_abs = str(_resolve_project_path(ap))
        except Exception:
            avatar_abs = ap

    try:
        mp4_abs = build_video_brief(
            slide_image_paths=image_paths,
            talk_track_wav_path=str(audio_abs),
            avatar_image_path=avatar_abs,
            project_root=_REPO_ROOT,
            seconds_per_slide=float(body.seconds_per_slide or 4.0),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Video brief failed ({type(e).__name__}: {e})") from e
    finally:
        VRAMManager.clear()

    mp4_path = Path(mp4_abs).resolve()
    rel = mp4_path.relative_to((_REPO_ROOT / "assets").resolve())
    static_href = f"/static/{rel.as_posix()}"
    mode = "sadtalker" if body.avatar_image_path and os.environ.get("RELULAYER_SADTALKER_DIR", "").strip() else "slideshow"
    logger.info("event=gtm.video_brief.complete mode=%s href=%s", mode, static_href)
    return GTMVideoBriefResponse(
        video_path=str(mp4_path),
        static_href=static_href,
        mode=mode,
        audio_href=href,
    )


@app.post("/process/gtm/strategic-simulate", response_model=GTMStrategicSimResponse)
def process_gtm_strategic_simulate(body: GTMStrategicSimRequest) -> GTMStrategicSimResponse:
    """
    Path S: ``StrategicSimulator`` — LM writes a Monte Carlo script; execution uses the Path R
    sandbox (``execute_data_audit_script``). Default ``RELULAYER_SIM_MC_RUNS=1000`` (capped at 5000).
    """
    logger.info(
        "event=gtm.strategic_sim.start slides=%s file_paths=%s",
        len(body.slides),
        len(body.file_paths or []),
    )
    tab_paths = _collect_tabular_paths_for_audit(body.file_paths or [])
    if not tab_paths:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one repo-relative .csv, .xlsx, .xlsm, or .xls in file_paths.",
        )
    manifest = [{"path": str(p), "name": p.name} for p in tab_paths]

    ctx_parts: list[str] = []
    try:
        files = _load_ingestion_files(body.file_paths) if body.file_paths else []
        ingested = _ingestion.process_files(files)
        if ingested["context_string"].strip():
            ctx_parts.append(ingested["context_string"])
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("event=gtm.strategic_sim.ingest_failed")
        raise HTTPException(
            status_code=400,
            detail=f"Ingestion failed ({type(e).__name__}: {e})",
        ) from e

    pf = (body.project_folder or "").strip()
    if pf:
        try:
            rag = _ingestion.process_folder_rag(
                pf,
                body.user_prompt,
                top_k=5,
                ollama_base_url=_strategic_sim._config.base_url,  # noqa: SLF001
                embed_model=rag_embed_model(),
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if rag["context_string"].strip():
            ctx_parts.append(rag["context_string"])

        if graph_rag_enabled():
            try:
                gctx = _ingestion.process_folder_graph_context(
                    pf,
                    body.user_prompt,
                    ollama_base_url=_strategic_sim._config.base_url,  # noqa: SLF001
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            if gctx["context_string"].strip():
                ctx_parts.append(gctx["context_string"].strip())

    full_ctx = "\n\n---\n\n".join(ctx_parts) if ctx_parts else ""
    var_excerpt = full_ctx[:20000]
    deck_json = json.dumps({"slides": body.slides}, ensure_ascii=False, default=str)

    try:
        try:
            res = _strategic_sim.run_monte_carlo_pipeline(
                user_instructions=body.user_prompt.strip(),
                strategy_deck_json=deck_json,
                manifest=manifest,
                contextual_variables_excerpt=var_excerpt,
                project_root=_REPO_ROOT,
            )
        except Exception as e:
            logger.exception("event=gtm.strategic_sim.pipeline_failed")
            cfg = _strategic_sim._config  # noqa: SLF001
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Strategic simulation failed ({type(e).__name__}: {e}). "
                    f"Check Ollama at {cfg.base_url!r} (model {cfg.gtm_model!r})."
                ),
            ) from e

        ap, ac, ht = _extract_gtm_telemetry_from_dspy_history(last_n_calls=1)
        logger.info(
            "event=gtm.strategic_sim.complete parsed_ok=%s prob=%s rc=%s",
            res.parsed_ok,
            res.probability_of_success,
            res.return_code,
        )
        return GTMStrategicSimResponse(
            probability_of_success=res.probability_of_success,
            sensitivity_analysis_markdown=res.sensitivity_analysis_markdown,
            headline=res.headline,
            simulation_design=res.simulation_design,
            return_code=res.return_code,
            parsed_ok=res.parsed_ok,
            stdout_excerpt=res.raw_stdout[:12000],
            stderr_excerpt=res.raw_stderr[:6000],
            lm_telemetry=StrategicSimLMTrace(
                raw_prompt=ap[:12000],
                raw_completion=ac[:12000],
                history_turns=ht,
            ),
        )
    finally:
        VRAMManager.clear()
        logger.info("event=gtm.strategic_sim.vram_cleared")


@app.post("/process/gtm/synthesize-image", response_model=SynthesizeSlideImageResponse)
def process_gtm_synthesize_image(
    body: SynthesizeSlideImageRequest,
) -> SynthesizeSlideImageResponse:
    """
    Generate a 16:9 photorealistic hero frame from ``image_prompt``.

    Run when Ollama work is idle: loads SD/Flux VRAM only for this request, then clears cache.
    Configure ``RELULAYER_IMAGE_BACKEND`` (``http`` | ``diffusers``) and URLs / model id in env.
    """
    logger.info(
        "event=gtm.synth.start slide_index=%s prompt_chars=%s",
        body.slide_index,
        len(body.image_prompt),
    )
    out_path = synth_hero_asset_path(body.slide_index, _REPO_ROOT)
    abs_path: str | None = None
    try:
        abs_path = generate_flux_image(
            body.image_prompt,
            out_path,
            width=body.width,
            height=body.height,
            negative_prompt=body.negative_prompt,
        )
    except RuntimeError as e:
        logger.warning("event=gtm.synth.disabled_or_misconfigured detail=%s", e)
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        logger.exception("event=gtm.synth.failed")
        raise HTTPException(
            status_code=500,
            detail=f"Image synthesis failed ({type(e).__name__}: {e})",
        ) from e
    finally:
        VRAMManager.clear()

    if not abs_path:
        raise HTTPException(status_code=500, detail="Synthesis produced no output path.")
    rel = Path(abs_path).resolve().relative_to((_REPO_ROOT / "assets").resolve())
    static_href = f"/static/{rel.as_posix()}"
    logger.info("event=gtm.synth.complete path=%s", abs_path)
    return SynthesizeSlideImageResponse(image_path=abs_path, static_href=static_href)


# --- GTM: Materialize (Layer 5) ------------------------------------------------


@app.post("/process/gtm/materialize", response_model=GTMMaterializeResponse)
def process_gtm_materialize(body: GTMMaterializeRequest) -> GTMMaterializeResponse:
    """
    Deterministic pipeline: theme icons from ``icon_request``, data charts from
    ``chart_request`` / ``chart_data``, placeholder hero images from ``image_prompt``,
    then python-pptx assembly (charts go in the largest body placeholder when present).
    """
    logger.info(
        "event=gtm.materialize.start slides=%s template=%r",
        len(body.slides),
        body.template_path,
    )
    try:
        tpl = _resolve_project_path(body.template_path)
        if not tpl.is_file():
            raise HTTPException(status_code=400, detail=_file_not_found_detail(tpl))

        deck: dict[str, Any] = {
            "slides": [_normalize_slide(s) for s in body.slides if isinstance(s, dict)],
        }
        if body.design_specs:
            deck["design_specs"] = body.design_specs

        def _severe_overflow_targets(
            struct_report: Any,
        ) -> list[tuple[int, str, int | None]]:
            """
            Path EE: treat ``smart_truncate`` as a severe overflow signal.
            Returns (slide_index, role, max_chars_hint?) for refine candidates.
            """
            out: list[tuple[int, str, int | None]] = []
            try:
                recs = struct_report.to_json_records()
            except Exception:
                return out
            for rec in recs:
                if not isinstance(rec, dict):
                    continue
                if rec.get("action") != "smart_truncate":
                    continue
                try:
                    slide_index = int(rec.get("slide_index", -1))
                except (TypeError, ValueError):
                    continue
                if slide_index < 0:
                    continue
                role = str(rec.get("role") or "body")
                msg = str(rec.get("message") or "")
                max_chars: int | None = None
                m = re.search(r"truncated to\s*~\s*(\d+)\s*chars", msg, flags=re.IGNORECASE)
                if m:
                    try:
                        max_chars = int(m.group(1))
                    except ValueError:
                        max_chars = None
                out.append((slide_index, role, max_chars))
            return out

        def _apply_fit_to_slide_refine(
            slide: dict[str, Any],
            *,
            slide_index: int,
            role: str,
            max_chars: int | None,
        ) -> bool:
            """
            Path EE: call ``RefineSlideSignature`` to compress overflowing text.
            Returns True if the slide dict was updated.
            """
            # RefineSlideSignature can only edit title/body in this codebase.
            if role not in ("title", "body"):
                return False
            cap = max(80, int(max_chars or 0)) if max_chars else None
            if role == "title":
                raw = str(slide.get("title") or "").strip()
            else:
                raw = str(slide.get("body") or "").strip()
            if not raw:
                return False
            hint = f"Target <= ~{cap} characters." if cap else "Target significantly shorter than current."
            instr = (
                "Path EE — Fit-to-slide agent.\n\n"
                f"This slide's {role} text overflowed the template placeholder during materialization.\n"
                f"Rewrite the {role} to fit the available space. {hint}\n\n"
                "Constraints:\n"
                "- Preserve core strategic meaning and key numbers.\n"
                "- Prefer fewer bullets with tighter phrasing; remove redundancy.\n"
                "- Keep tone consistent with the deck.\n"
                "- Output must be plain text (no markdown fences).\n\n"
                f"Overflowing {role} text:\n{raw}\n"
            )
            try:
                rp = _gtm_refine.forward(
                    slide_json=json.dumps(slide, ensure_ascii=False, default=str),
                    refinement_instruction=instr,
                )
            except Exception:
                logger.exception(
                    "event=gtm.materialize.fit_to_slide.refine_failed slide=%s role=%s",
                    slide_index,
                    role,
                )
                return False
            # Apply only the requested role (but signature always returns both fields).
            if role == "title":
                new_title = str(getattr(rp, "refined_title", None) or "").strip()
                if new_title:
                    slide["title"] = new_title
                    return True
                return False
            new_body = str(getattr(rp, "refined_body", None) or "").strip()
            if new_body:
                slide["body"] = new_body
                return True
            return False

        appendix_path: str | None = None
        try:
            _materialize_slide_icons(deck["slides"], _REPO_ROOT)
            _materialize_slide_charts(deck["slides"], _REPO_ROOT)
            _materialize_slide_images(deck["slides"], _REPO_ROOT)
            out_name = f"gtm_{time.time_ns()}.pptx"
            pptx_path, struct_report = assemble_deck(
                deck,
                str(tpl),
                out_name,
                project_root=_REPO_ROOT,
            )
            # Path EE: If structural audit had to smart-truncate, attempt an autonomous rewrite and rebuild once.
            severe = _severe_overflow_targets(struct_report)
            if severe:
                updated = 0
                seen: set[tuple[int, str]] = set()
                for slide_index, role, max_chars in severe:
                    key = (slide_index, role)
                    if key in seen:
                        continue
                    seen.add(key)
                    if slide_index >= len(deck["slides"]):
                        continue
                    ok = _apply_fit_to_slide_refine(
                        deck["slides"][slide_index],
                        slide_index=slide_index,
                        role=role,
                        max_chars=max_chars,
                    )
                    if ok:
                        updated += 1
                if updated > 0:
                    try:
                        fit_name = f"{Path(out_name).stem}_fit.pptx"
                        pptx_path, struct_report = assemble_deck(
                            deck,
                            str(tpl),
                            fit_name,
                            project_root=_REPO_ROOT,
                        )
                        logger.info(
                            "event=gtm.materialize.fit_to_slide.rebuilt slides_refined=%s severe_hits=%s pptx_path=%s",
                            updated,
                            len(severe),
                            pptx_path,
                        )
                    except Exception:
                        logger.exception("event=gtm.materialize.fit_to_slide.rebuild_failed")
            try:
                pptx_abs = Path(pptx_path)
                stem = Path(pptx_path).stem
                xlsx_name = f"{stem}_financial_appendix.xlsx"
                appendix_abs = pptx_abs.parent / xlsx_name
                appendix_path = build_financial_appendix_for_materialize(
                    deck["slides"],
                    appendix_abs,
                    project_root=_REPO_ROOT,
                )
                logger.info(
                    "event=gtm.materialize.financial_appendix path=%s",
                    appendix_path,
                )
            except Exception:
                logger.exception("event=gtm.materialize.financial_appendix_failed")
                appendix_path = None
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("event=gtm.materialize.tools_failed")
            raise HTTPException(
                status_code=500,
                detail=f"PPTX or image assembly failed ({type(e).__name__}: {e})",
            ) from e
        struct_tel = MaterializationStructuralTelemetry(
            audit_enabled=struct_report.audit_enabled,
            checks_performed=struct_report.checks_performed,
            adjustments=[
                MaterializeStructuralAdjustment(**rec)
                for rec in struct_report.to_json_records()
            ],
        )
        logger.info(
            "event=gtm.materialize.complete pptx_path=%s structural_checks=%s adjustments=%s",
            pptx_path,
            struct_tel.checks_performed,
            len(struct_tel.adjustments),
        )
        return GTMMaterializeResponse(
            pptx_path=pptx_path,
            structural_telemetry=struct_tel,
            financial_appendix_path=appendix_path,
        )
    finally:
        VRAMManager.clear()
        logger.info("event=gtm.materialize.vram_cleared")


@app.post("/process/gtm/materialize-microsite", response_model=GTMMicrositeResponse)
def process_gtm_materialize_microsite(body: GTMMicrositeRequest) -> GTMMicrositeResponse:
    """
    Path Z — Web Materializer: charts (Path N) as interactive Plotly.js, hero images embedded,
    Tailwind-styled single HTML file in ``assets/outputs/sites/`` (served at ``/static/outputs/sites/``).
    """
    logger.info(
        "event=gtm.microsite.start slides=%s",
        len(body.slides),
    )
    try:
        deck_slides = [_normalize_slide(s) for s in body.slides if isinstance(s, dict)]
        if not deck_slides:
            raise HTTPException(status_code=400, detail="slides must contain at least one object.")

        try:
            _materialize_slide_charts(deck_slides, _REPO_ROOT)
            _materialize_slide_images(deck_slides, _REPO_ROOT)
        except Exception as e:
            logger.exception("event=gtm.microsite.assets_failed")
            raise HTTPException(
                status_code=500,
                detail=f"Chart or image preparation failed ({type(e).__name__}: {e})",
            ) from e

        sub = (body.subtitle or "").strip()
        if not sub and (body.user_prompt or "").strip():
            sub = (body.user_prompt or "").strip()[:400]

        abs_path, href = build_executive_microsite(
            slides=deck_slides,
            page_title=(body.page_title or "Executive briefing").strip() or "Executive briefing",
            subtitle=sub,
            project_root=_REPO_ROOT,
        )
        logger.info("event=gtm.microsite.complete path=%s href=%s", abs_path, href)
        return GTMMicrositeResponse(html_path=abs_path, static_href=href)
    finally:
        VRAMManager.clear()
        logger.info("event=gtm.microsite.vram_cleared")


# --- Path Q: Strategy sessions (JSONDB, branching) -----------------------------


@app.post("/process/gtm/strategy-sessions", response_model=StrategySessionIdResponse)
def strategy_session_create(body: StrategySessionCreateRequest) -> StrategySessionIdResponse:
    """
    Save a new Strategic Sandbox snapshot under ``memory/strategy_sessions/<uuid>.json``.
    Use :func:`strategy_session_branch` to fork without mutating the parent file.
    """
    new_id = str(uuid.uuid4())
    now = _strategy_session_now_iso()
    label = (body.branch_label or "").strip() or "Strategy session"
    doc: dict[str, Any] = {
        "schema_version": 1,
        "session_id": new_id,
        "parent_session_id": None,
        "branch_label": label,
        "created_at": now,
        "updated_at": now,
        "sandbox": _strategy_session_sandbox_to_dict(body.sandbox),
        "drift_history": [],
    }
    _strategy_session_atomic_write(_strategy_session_path(new_id), doc)
    logger.info("event=strategy_session.created id=%s", new_id)
    _war_room_broadcast_session_doc(new_id, doc)
    return StrategySessionIdResponse(session_id=new_id, parent_session_id=None)


@app.put(
    "/process/gtm/strategy-sessions/{session_id}",
    response_model=StrategySessionIdResponse,
)
def strategy_session_update(
    session_id: str,
    body: StrategySessionUpdateRequest,
) -> StrategySessionIdResponse:
    """Overwrite sandbox payload for an existing session (e.g. after regenerating paths)."""
    sid = _strategy_session_validate_id(session_id)
    doc = _strategy_session_load_doc(sid)
    doc["sandbox"] = _strategy_session_sandbox_to_dict(body.sandbox)
    doc["updated_at"] = _strategy_session_now_iso()
    if body.branch_label is not None:
        bl = (body.branch_label or "").strip()
        if bl:
            doc["branch_label"] = bl
    _strategy_session_atomic_write(_strategy_session_path(sid), doc)
    logger.info("event=strategy_session.updated id=%s", sid)
    _war_room_broadcast_session_doc(sid, doc)
    parent = doc.get("parent_session_id")
    return StrategySessionIdResponse(
        session_id=sid,
        parent_session_id=parent if isinstance(parent, str) else None,
    )


@app.get(
    "/process/gtm/strategy-sessions/{session_id}",
    response_model=StrategySessionDocument,
)
def strategy_session_get(session_id: str) -> StrategySessionDocument:
    """Load one session document (for restore / audit / multi-user handoff)."""
    doc = _strategy_session_load_doc(session_id)
    try:
        dh = doc.get("drift_history")
        drift_hist: list[dict[str, Any]] = []
        if isinstance(dh, list):
            drift_hist = [x for x in dh if isinstance(x, dict)]
        return StrategySessionDocument(
            schema_version=int(doc.get("schema_version") or 1),
            session_id=str(doc["session_id"]),
            parent_session_id=doc.get("parent_session_id")
            if isinstance(doc.get("parent_session_id"), str)
            else None,
            branch_label=doc.get("branch_label") if isinstance(doc.get("branch_label"), str) else None,
            created_at=str(doc.get("created_at") or ""),
            updated_at=str(doc.get("updated_at") or ""),
            sandbox=dict(doc["sandbox"]) if isinstance(doc.get("sandbox"), dict) else {},
            drift_history=drift_hist,
        )
    except KeyError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Session document is missing required field: {e}",
        ) from e


@app.get(
    "/process/gtm/strategy-sessions",
    response_model=list[StrategySessionListEntry],
)
def strategy_session_list() -> list[StrategySessionListEntry]:
    """List saved sessions (most recently updated first)."""
    return _strategy_session_list_entries()


@app.post("/process/gtm/strategy-sessions/{session_id}/drift-monitor")
def strategy_session_set_drift_monitor(session_id: str, body: DriftMonitorConfig) -> dict[str, Any]:
    """Path JJ: enable/disable background drift monitoring for a session."""
    sid = _strategy_session_validate_id(session_id)
    doc = _strategy_session_load_doc(sid)
    drift = {
        "enabled": bool(body.enabled),
        "interval_s": float(body.interval_s),
    }
    # preserve last_checked / digest / last_alert fields if present
    prev = doc.get("drift_monitor") if isinstance(doc.get("drift_monitor"), dict) else {}
    for k in ("last_checked_at", "last_grounding_digest", "last_alert_at"):
        if k in prev:
            drift[k] = prev.get(k)
    doc["drift_monitor"] = drift
    doc["updated_at"] = _strategy_session_now_iso()
    _strategy_session_atomic_write(_strategy_session_path(sid), doc)
    logger.info("event=strategy_session.drift_monitor_set id=%s enabled=%s interval_s=%s", sid, body.enabled, body.interval_s)
    _war_room_broadcast_session_doc(sid, doc)
    return {"ok": True, "session_id": sid, "drift_monitor": drift}


@app.post(
    "/process/gtm/strategy-sessions/{session_id}/branch",
    response_model=StrategySessionIdResponse,
)
def strategy_session_branch(
    session_id: str,
    body: StrategySessionBranchRequest,
) -> StrategySessionIdResponse:
    """
    Save As / strategy branch: deep-copy the parent session to a new UUID.
    The parent file is unchanged; edit the branch via PUT or regenerate in the UI.
    """
    parent = _strategy_session_validate_id(session_id)
    parent_doc = _strategy_session_load_doc(parent)
    new_id = str(uuid.uuid4())
    now = _strategy_session_now_iso()
    new_doc = copy.deepcopy(parent_doc)
    new_doc["session_id"] = new_id
    new_doc["parent_session_id"] = parent
    new_doc["created_at"] = now
    new_doc["updated_at"] = now
    lbl = (body.branch_label or "").strip()
    new_doc["branch_label"] = lbl or f"Branch of {parent[:8]}"
    _strategy_session_atomic_write(_strategy_session_path(new_id), new_doc)
    logger.info("event=strategy_session.branched parent=%s child=%s", parent, new_id)
    _war_room_broadcast_session_doc(new_id, new_doc)
    return StrategySessionIdResponse(session_id=new_id, parent_session_id=parent)


@app.websocket("/ws/war-room/{session_id}")
async def war_room_websocket(websocket: WebSocket, session_id: str) -> None:
    """
    Path U: real-time war room for a strategy session (UUID).

    Query params: ``user_id``, ``display_name`` (shown to collaborators).

    Client → server JSON:
    ``ping`` | ``sandbox_push`` {sandbox} | ``deck_state_push`` {slides, template, design_specs}
    | ``slide_lock_acquire`` {slide_index, request_id?} | ``slide_lock_release`` {slide_index} .

    Server → client: ``welcome``, ``presence``, ``slide_locks``, ``sandbox_sync``,
    ``deck_state_sync``, ``slide_lock_ack``, ``pong``, ``error``.
    """
    try:
        sid = _strategy_session_validate_id(session_id)
    except HTTPException:
        await websocket.close(code=1008, reason="Invalid session id")
        return
    if not _strategy_session_path(sid).is_file():
        await websocket.close(code=1008, reason="Strategy session not found")
        return

    qp = websocket.query_params
    user_id = (qp.get("user_id") or "anonymous").strip() or "anonymous"
    display_name = (qp.get("display_name") or "Strategist").strip() or "Strategist"

    conn_id: str | None = None
    await websocket.accept()
    conn_id = _war_room_hub.register(websocket, sid, user_id, display_name)
    try:
        doc = _strategy_session_load_doc(sid)
        dh0 = doc.get("drift_history")
        drift_welcome = dh0 if isinstance(dh0, list) else []
        await websocket.send_text(
            json.dumps(
                {
                    "type": "welcome",
                    "conn_id": conn_id,
                    "session_id": sid,
                    "sandbox": doc.get("sandbox"),
                    "updated_at": doc.get("updated_at"),
                    "branch_label": doc.get("branch_label"),
                    "drift_history": drift_welcome,
                    "slide_locks": _war_room_hub.locks_snapshot(sid),
                    "presence": _war_room_hub.presence_snapshot(sid),
                },
                default=str,
            ),
        )
        await _war_room_hub.broadcast_presence(sid)

        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps(
                        {"type": "error", "detail": "Invalid JSON"},
                        default=str,
                    ),
                )
                continue
            if not isinstance(msg, dict):
                continue
            mtype = msg.get("type")
            if mtype == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}, default=str))
                continue
            if mtype == "slide_lock_acquire":
                req_id = msg.get("request_id")
                try:
                    slide_index = int(msg.get("slide_index", -1))
                except (TypeError, ValueError):
                    slide_index = -1
                if slide_index < 0:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "slide_lock_ack",
                                "request_id": req_id,
                                "ok": False,
                                "detail": "Invalid slide_index",
                            },
                            default=str,
                        ),
                    )
                    continue
                ok, held_by = _war_room_hub.try_acquire_slide_lock(sid, slide_index, conn_id)
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "slide_lock_ack",
                            "request_id": req_id,
                            "ok": ok,
                            "held_by": held_by,
                            "slide_index": slide_index,
                        },
                        default=str,
                    ),
                )
                if ok:
                    await _war_room_hub.broadcast_slide_locks(sid)
                continue
            if mtype == "slide_lock_release":
                try:
                    slide_index = int(msg.get("slide_index", -1))
                except (TypeError, ValueError):
                    slide_index = -1
                if slide_index >= 0:
                    _war_room_hub.release_slide_lock(sid, slide_index, conn_id)
                    await _war_room_hub.broadcast_slide_locks(sid)
                continue
            if mtype == "sandbox_push":
                sandbox_raw = msg.get("sandbox")
                if not isinstance(sandbox_raw, dict):
                    await websocket.send_text(
                        json.dumps(
                            {"type": "error", "detail": "sandbox must be an object"},
                            default=str,
                        ),
                    )
                    continue
                try:
                    validated = StrategySandboxStatePayload.model_validate(sandbox_raw)
                except Exception as e:
                    await websocket.send_text(
                        json.dumps(
                            {"type": "error", "detail": f"Invalid sandbox: {e}"},
                            default=str,
                        ),
                    )
                    continue
                doc2 = _strategy_session_load_doc(sid)
                doc2["sandbox"] = _strategy_session_sandbox_to_dict(validated)
                doc2["updated_at"] = _strategy_session_now_iso()
                _strategy_session_atomic_write(_strategy_session_path(sid), doc2)
                await _war_room_hub.broadcast_json(
                    sid,
                    {
                        "type": "sandbox_sync",
                        "sandbox": doc2["sandbox"],
                        "updated_at": doc2["updated_at"],
                        "origin_conn_id": conn_id,
                    },
                )
                continue
            if mtype == "deck_state_push":
                slides = msg.get("slides")
                if not isinstance(slides, list):
                    await websocket.send_text(
                        json.dumps(
                            {"type": "error", "detail": "slides must be an array"},
                            default=str,
                        ),
                    )
                    continue
                await _war_room_hub.broadcast_json(
                    sid,
                    {
                        "type": "deck_state_sync",
                        "slides": slides,
                        "template": msg.get("template") if isinstance(msg.get("template"), str) else "",
                        "design_specs": msg.get("design_specs"),
                        "origin_conn_id": conn_id,
                    },
                    exclude_conn_id=conn_id,
                )
                continue
            await websocket.send_text(
                json.dumps(
                    {"type": "error", "detail": f"Unknown message type: {mtype!r}"},
                    default=str,
                ),
            )
    finally:
        if conn_id is not None:
            left_sid = _war_room_hub.unregister(conn_id)
            if left_sid:
                await _war_room_hub.broadcast_presence(left_sid)
                await _war_room_hub.broadcast_slide_locks(left_sid)


@app.post("/process/gtm/memory/record-success", response_model=GTMMemoryRecordResponse)
def record_gtm_success_memory(body: GTMMemoryRecordRequest) -> GTMMemoryRecordResponse:
    """Persist a successful materialization for few-shot strategic memory on future drafts."""
    ok = _success_store.record_materialization(
        user_prompt=body.user_prompt,
        persona=body.persona,
        slides=body.slides,
        design_specs=body.design_specs,
        ollama_base_url=_gtm._config.base_url,  # noqa: SLF001
    )
    return GTMMemoryRecordResponse(stored=ok)


# --- ETL -----------------------------------------------------------------------


@app.post("/process/etl", response_model=ETLResponse)
def process_etl(body: ETLRequest) -> ETLResponse:
    logger.info(
        "event=etl.start prompt_chars=%s file_count=%s",
        len(body.user_prompt),
        len(body.file_paths),
    )
    try:
        files = _load_ingestion_files(body.file_paths)
        ingested = _ingestion.process_files(files)
        ctx = ingested["context_string"]
        if body.user_prompt.strip():
            ctx = f"## User objective\n{body.user_prompt}\n\n## Ingested context\n{ctx}"
        logger.info("event=etl.ingestion_done context_chars=%s", len(ctx))

        try:
            pred = _etl.forward(context=ctx, schema_template=body.schema_template)
        except Exception as e:
            logger.exception("event=etl.dspy_failed")
            cfg = _etl._config  # noqa: SLF001
            raise HTTPException(
                status_code=503,
                detail=(
                    f"DSPy/Ollama call failed ({type(e).__name__}: {e}). "
                    f"Check Ollama at {cfg.base_url!r} (model {cfg.etl_model!r})."
                ),
            ) from e
        raw = getattr(pred, "extracted_json", None)
        if raw is None:
            raw = str(pred)
        cleaned = _strip_json_fence(str(raw))
        logger.info("event=etl.dspy_done output_chars=%s", len(cleaned))

        try:
            parsed: Any = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.exception("event=etl.json_parse_failed")
            raise HTTPException(
                status_code=502,
                detail=f"Extraction output was not valid JSON: {e}",
            ) from e

        csv_out: str | None = None
        if isinstance(parsed, list) and parsed and all(isinstance(x, dict) for x in parsed):
            csv_out = pd.DataFrame(parsed).to_csv(index=False)
            logger.info("event=etl.csv_derived rows=%s", len(parsed))
        elif isinstance(parsed, dict):
            try:
                csv_out = pd.json_normalize(parsed).to_csv(index=False)
            except Exception:
                csv_out = None

        return ETLResponse(data=parsed, raw=cleaned, csv=csv_out)
    finally:
        VRAMManager.clear()
        logger.info("event=etl.vram_cleared")
