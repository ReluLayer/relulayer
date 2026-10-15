from __future__ import annotations

import ast
import json
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import dspy

from infrastructure.vram_manager import VRAMManager
from models.config import EngineConfig
from orchestration.dspy_modules.signatures import (
    ComplianceAuditSignature,
    ContradictionSignature,
    DataAuditorSignature,
    ExecutiveBriefingSignature,
    ExtractDeterministicSchema,
    ChairmanSignature,
    GovTechSignature,
    RefineSlideSignature,
    RiskAuditSignature,
    StrategicCritiqueSignature,
    StrategicJudgeSignature,
    StrategicSimulationSignature,
    StrategySynthesisSignature,
    VCPitchSignature,
    WargameAdversaryTurnSignature,
    WargameProponentTurnSignature,
    WargameResidualSummarySignature,
)

logger = logging.getLogger(__name__)

GTM_PERSONA_VENTURE_CAPITAL = "venture_capital"
GTM_PERSONA_GOVTECH = "govtech"
GTM_PERSONA_RISK_AUDITOR = "risk_auditor"

GTM_PERSONA_SIGNATURES: dict[str, type[dspy.Signature]] = {
    GTM_PERSONA_VENTURE_CAPITAL: VCPitchSignature,
    GTM_PERSONA_GOVTECH: GovTechSignature,
    GTM_PERSONA_RISK_AUDITOR: RiskAuditSignature,
}

GTM_DEFAULT_PERSONA = GTM_PERSONA_GOVTECH

GTM_CONSENSUS_PERSONA_ORDER: tuple[str, ...] = (
    GTM_PERSONA_VENTURE_CAPITAL,
    GTM_PERSONA_GOVTECH,
    GTM_PERSONA_RISK_AUDITOR,
)


def _ollama_lm(model: str, base_url: str) -> dspy.LM:
    return dspy.LM(
        f"ollama/{model}",
        api_base=base_url.rstrip("/"),
        api_key="",
    )


def _strip_python_fence(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:python|py)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def _data_audit_timeout_sec() -> float:
    try:
        return max(5.0, float(os.environ.get("RELULAYER_DATA_AUDIT_TIMEOUT", "60")))
    except ValueError:
        return 60.0


def _data_audit_max_output_bytes() -> int:
    try:
        return max(2048, int(os.environ.get("RELULAYER_DATA_AUDIT_MAX_OUTPUT", "98304")))
    except ValueError:
        return 98304


def _simulation_timeout_sec() -> float:
    try:
        return max(30.0, float(os.environ.get("RELULAYER_SIM_TIMEOUT", "180")))
    except ValueError:
        return 180.0


def _simulation_max_output_bytes() -> int:
    try:
        return max(4096, int(os.environ.get("RELULAYER_SIM_MAX_OUTPUT", "131072")))
    except ValueError:
        return 131072


# ---------------------------------------------------------------------------
# Static analysis gate for LLM-generated audit/simulation scripts
# ---------------------------------------------------------------------------

_BLOCKED_IMPORTS: frozenset[str] = frozenset({
    "subprocess", "socket", "requests", "urllib", "urllib3",
    "httpx", "aiohttp", "ftplib", "smtplib", "paramiko",
    "ctypes", "importlib", "shutil", "pty",
    "multiprocessing", "threading", "concurrent",
    "asyncio", "ssl",
})

# os.* attribute calls that must not be reachable from LLM-generated code.
# os.environ and os.path are allowed (read-only access to manifest paths).
_BLOCKED_OS_ATTRS: frozenset[str] = frozenset({
    "system", "popen",
    "execv", "execve", "execvp", "execvpe",
    "execl", "execle", "execlp", "execlpe",
    "fork", "forkpty",
    "spawnl", "spawnle", "spawnlp", "spawnlpe",
    "spawnv", "spawnve", "spawnvp", "spawnvpe",
    "remove", "unlink", "rmdir", "removedirs",
    "rename", "renames", "replace",
    "mkdir", "makedirs", "symlink", "link",
    "chmod", "chown", "kill", "killpg", "abort",
    "setuid", "setgid", "seteuid", "setegid",
    "putenv", "unsetenv",
})

_BLOCKED_BUILTINS: frozenset[str] = frozenset({
    "eval", "exec", "compile", "__import__", "breakpoint",
})

_WRITE_OPEN_MODES: frozenset[str] = frozenset({
    "w", "wb", "wt", "a", "ab", "at", "x", "xb", "xt",
    "w+", "wb+", "r+b", "a+", "ab+",
})


def _static_check_script(source: str) -> list[str]:
    """AST-based static analysis gate for LLM-generated scripts.

    Walks the AST of *source* (the body only, not the trusted header) and
    returns a list of violation strings.  An empty list means the script
    passed all checks and is safe to execute.
    """
    violations: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"syntax_error:{exc}"]

    for node in ast.walk(tree):
        # --- import / from-import checks ---
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _BLOCKED_IMPORTS:
                    violations.append(f"blocked_import:{alias.name}")

        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            if mod in _BLOCKED_IMPORTS:
                violations.append(f"blocked_from_import:{node.module}")
            # Selectively block dangerous names from os
            if mod == "os":
                for alias in node.names:
                    if alias.name == "*" or alias.name in _BLOCKED_OS_ATTRS:
                        violations.append(f"blocked_os_from_import:{alias.name}")

        # --- call-site checks ---
        elif isinstance(node, ast.Call):
            func = node.func

            # eval(), exec(), compile(), __import__(), breakpoint()
            if isinstance(func, ast.Name) and func.id in _BLOCKED_BUILTINS:
                violations.append(f"blocked_builtin:{func.id}")

            # os.system(), os.popen(), os.fork(), os.remove(), etc.
            elif (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "os"
                and func.attr in _BLOCKED_OS_ATTRS
            ):
                violations.append(f"blocked_os_call:os.{func.attr}")

            # open(..., 'w') / open(..., mode='a') write/append modes
            elif isinstance(func, ast.Name) and func.id == "open":
                if len(node.args) >= 2:
                    arg = node.args[1]
                    if (
                        isinstance(arg, ast.Constant)
                        and str(arg.value) in _WRITE_OPEN_MODES
                    ):
                        violations.append(f"blocked_open_write_mode:{arg.value!r}")
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        if str(kw.value.value) in _WRITE_OPEN_MODES:
                            violations.append(
                                f"blocked_open_write_mode:{kw.value.value!r}"
                            )

    return violations


def _validate_audit_manifest(
    manifest: list[dict[str, str]],
    project_root: Path,
) -> list[dict[str, str]]:
    root = project_root.resolve()
    clean: list[dict[str, str]] = []
    for item in manifest:
        path_s = (item.get("path") or "").strip()
        name = (item.get("name") or Path(path_s).name).strip() or Path(path_s).name
        if not path_s:
            continue
        try:
            p = Path(path_s).resolve()
        except OSError:
            continue
        if not p.is_file():
            logger.warning("data_audit.manifest_missing_file path=%s", p)
            continue
        try:
            p.relative_to(root)
        except ValueError:
            logger.warning("data_audit.manifest_outside_repo path=%s", p)
            continue
        clean.append({"path": str(p), "name": name})
    return clean


def execute_data_audit_script(
    script_body: str,
    *,
    manifest: list[dict[str, str]],
    project_root: Path,
    extra_env: dict[str, str] | None = None,
    output_subdir: str = "data_audit",
    script_prefix: str = "audit",
    timeout_sec: float | None = None,
    max_output_bytes: int | None = None,
) -> tuple[str, str, int]:
    """
    Run LLM-produced analysis in a subprocess with ``DATA_MANIFEST`` in the environment.

    Path S passes ``extra_env`` (e.g. ``RELULAYER_SIM_MC_RUNS``), longer ``timeout_sec``,
    and ``output_subdir='strategic_simulation'``.

    Returns ``(stdout, stderr, returncode)`` (outputs may be truncated for logging callers).
    """
    body = _strip_python_fence(script_body)
    if not body.strip():
        return "", "empty_script", 2

    violations = _static_check_script(body)
    if violations:
        logger.warning(
            "data_audit.script_blocked violations=%s subdir=%s",
            violations[:10],
            output_subdir,
        )
        return "", f"script_blocked:{';'.join(violations[:5])}", 3

    allowed = _validate_audit_manifest(manifest, project_root)
    if not allowed:
        return "", "no_valid_paths_in_manifest", 2

    header = (
        "import json, os, math, statistics\n"
        "from datetime import datetime\n"
        "import pandas as pd\n"
        "import numpy as np\n"
        "\n"
        "DATA_MANIFEST = json.loads(os.environ.get('RELULAYER_AUDIT_MANIFEST', '[]'))\n"
        "\n"
    )
    full_source = header + body

    sub = (output_subdir or "data_audit").strip().replace("..", "").strip("/\\") or "data_audit"
    pre = (script_prefix or "audit").strip().replace("..", "") or "audit"
    out_dir = project_root / "assets" / "outputs" / sub
    out_dir.mkdir(parents=True, exist_ok=True)
    script_path = out_dir / f"{pre}_{os.getpid()}_{time.time_ns()}.py"
    tout = timeout_sec if timeout_sec is not None else _data_audit_timeout_sec()
    max_b = max_output_bytes if max_output_bytes is not None else _data_audit_max_output_bytes()
    try:
        script_path.write_text(full_source, encoding="utf-8")
        env = {**os.environ, "RELULAYER_AUDIT_MANIFEST": json.dumps(allowed)}
        if extra_env:
            env.update({k: str(v) for k, v in extra_env.items()})
        proc = subprocess.run(
            [sys.executable, "-u", str(script_path)],
            cwd=str(project_root.resolve()),
            env=env,
            capture_output=True,
            timeout=tout,
        )
        out_b = proc.stdout or b""
        err_b = proc.stderr or b""
        if len(out_b) > max_b:
            out_b = out_b[:max_b] + b"\n...[truncated simulation output]...\n"
        if len(err_b) > max_b:
            err_b = err_b[:max_b] + b"\n...[truncated]...\n"
        return (
            out_b.decode("utf-8", errors="replace"),
            err_b.decode("utf-8", errors="replace"),
            int(proc.returncode),
        )
    except subprocess.TimeoutExpired:
        logger.warning("data_audit.subprocess_timeout subdir=%s", sub)
        return "", "subprocess_timeout", 124
    except Exception as e:
        logger.exception("data_audit.execute_failed")
        return "", f"execute_error:{type(e).__name__}:{e}", 1
    finally:
        try:
            script_path.unlink(missing_ok=True)
        except OSError:
            pass


def _parse_strategic_sim_json_line(stdout: str) -> dict[str, Any]:
    """Extract ``RELULAYER_SIM_JSON=...`` from the last matching line."""
    for line in reversed((stdout or "").strip().splitlines()):
        s = line.strip()
        if not s.startswith("RELULAYER_SIM_JSON="):
            continue
        raw = s[len("RELULAYER_SIM_JSON=") :].strip()
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return {}


@dataclass(frozen=True)
class StrategicSimulationResult:
    """Structured outcome after LM codegen + sandbox run (Path S)."""

    probability_of_success: float | None
    sensitivity_analysis_markdown: str
    headline: str
    simulation_design: str
    raw_stdout: str
    raw_stderr: str
    return_code: int
    parsed_ok: bool
    script_excerpt: str


class DataAuditorOrchestrator(dspy.Module):
    """
    Path R: generate a pandas/numpy analysis script from the strategist directive,
    for execution via :func:`execute_data_audit_script` and injection into GTM context.
    """

    def __init__(
        self,
        config: EngineConfig | None = None,
        lm: dspy.LM | None = None,
    ) -> None:
        super().__init__()
        self._config = config or EngineConfig()
        self._lm = lm or _ollama_lm(self._config.gtm_model, self._config.base_url)
        self._cot = dspy.ChainOfThought(DataAuditorSignature)

    def forward(
        self,
        user_instructions: str,
        data_file_manifest: str,
        tabular_context_excerpt: str,
    ):
        try:
            with dspy.context(lm=self._lm):
                return self._cot(
                    user_instructions=user_instructions,
                    data_file_manifest=data_file_manifest,
                    tabular_context_excerpt=tabular_context_excerpt,
                )
        finally:
            VRAMManager.clear()


class StrategicSimulator(dspy.Module):
    """
    Path S: Monte Carlo stress-test. Uses the same sandboxed executor as the Data Auditor (Path R);
    the LM writes a script that runs ``RELULAYER_SIM_MC_RUNS`` scenarios (default 1000) and prints
    ``RELULAYER_SIM_JSON=...`` with probability of success and sensitivity slide markdown.
    """

    def __init__(
        self,
        config: EngineConfig | None = None,
        lm: dspy.LM | None = None,
    ) -> None:
        super().__init__()
        self._config = config or EngineConfig()
        self._lm = lm or _ollama_lm(self._config.gtm_model, self._config.base_url)
        self._cot = dspy.ChainOfThought(StrategicSimulationSignature)

    def forward(
        self,
        user_instructions: str,
        strategy_deck_json: str,
        data_file_manifest: str,
        contextual_variables_excerpt: str,
    ):
        try:
            with dspy.context(lm=self._lm):
                return self._cot(
                    user_instructions=user_instructions,
                    strategy_deck_json=strategy_deck_json,
                    data_file_manifest=data_file_manifest,
                    contextual_variables_excerpt=contextual_variables_excerpt,
                )
        finally:
            VRAMManager.clear()

    def run_monte_carlo_pipeline(
        self,
        *,
        user_instructions: str,
        strategy_deck_json: str,
        manifest: list[dict[str, str]],
        contextual_variables_excerpt: str,
        project_root: Path,
    ) -> StrategicSimulationResult:
        """
        Generate script via DSPy, execute in subprocess (Path R sandbox), parse JSON result line.
        """
        pred = self.forward(
            user_instructions=user_instructions.strip(),
            strategy_deck_json=strategy_deck_json,
            data_file_manifest=json.dumps(manifest, ensure_ascii=False),
            contextual_variables_excerpt=(contextual_variables_excerpt or "")[:24000],
        )
        design = str(getattr(pred, "simulation_design", None) or "").strip()
        script = str(getattr(pred, "python_script", None) or "")
        excerpt = script[:16000]

        try:
            mc_raw = int(os.environ.get("RELULAYER_SIM_MC_RUNS", "1000").strip())
        except ValueError:
            mc_raw = 1000
        mc_runs = max(1, min(mc_raw, 5000))

        stdout, stderr, rc = execute_data_audit_script(
            script,
            manifest=manifest,
            project_root=project_root,
            extra_env={"RELULAYER_SIM_MC_RUNS": str(mc_runs)},
            output_subdir="strategic_simulation",
            script_prefix="sim",
            timeout_sec=_simulation_timeout_sec(),
            max_output_bytes=_simulation_max_output_bytes(),
        )

        parsed = _parse_strategic_sim_json_line(stdout)
        p_raw = parsed.get("probability_of_success")
        prob: float | None = None
        if p_raw is not None:
            try:
                x = float(p_raw)
                if 0.0 <= x <= 1.0:
                    prob = x * 100.0
                elif 1.0 < x <= 100.0:
                    prob = x
                else:
                    prob = max(0.0, min(100.0, x))
            except (TypeError, ValueError):
                prob = None
        sens = str(parsed.get("sensitivity_analysis_markdown") or "").strip()
        headline = str(parsed.get("headline") or "").strip()
        parsed_ok = prob is not None and bool(sens or headline)

        return StrategicSimulationResult(
            probability_of_success=prob,
            sensitivity_analysis_markdown=sens,
            headline=headline,
            simulation_design=design,
            raw_stdout=stdout,
            raw_stderr=stderr,
            return_code=rc,
            parsed_ok=parsed_ok,
            script_excerpt=excerpt,
        )


class ETLOrchestrator(dspy.Module):
    def __init__(
        self,
        config: EngineConfig | None = None,
        lm: dspy.LM | None = None,
    ) -> None:
        super().__init__()
        self._config = config or EngineConfig()
        self._lm = lm or _ollama_lm(self._config.etl_model, self._config.base_url)
        self._cot = dspy.ChainOfThought(ExtractDeterministicSchema)

    def forward(self, context: str, schema_template: str):
        try:
            with dspy.context(lm=self._lm):
                return self._cot(context=context, schema_template=schema_template)
        finally:
            VRAMManager.clear()


class GTMOrchestrator(dspy.Module):
    """
    Multimodal GTM draft: one ChainOfThought per strategic persona, selected via ``persona`` id.
    """

    def __init__(
        self,
        config: EngineConfig | None = None,
        lm: dspy.LM | None = None,
    ) -> None:
        super().__init__()
        self._config = config or EngineConfig()
        self._lm = lm or _ollama_lm(self._config.gtm_model, self._config.base_url)
        self._cots: dict[str, dspy.ChainOfThought] = {
            persona_id: dspy.ChainOfThought(sig_cls)
            for persona_id, sig_cls in GTM_PERSONA_SIGNATURES.items()
        }
        self._synthesis_cot = dspy.ChainOfThought(StrategySynthesisSignature)

    def _resolve_persona(self, persona: str | None) -> str:
        if persona and persona in self._cots:
            return persona
        return GTM_DEFAULT_PERSONA

    def forward(
        self,
        context: str,
        user_instructions: str,
        persona: str | None = None,
        strategic_memory: str | None = None,
    ):
        pid = self._resolve_persona(persona)
        cot = self._cots[pid]
        ctx = context
        mem = (strategic_memory or "").strip()
        if mem:
            ctx = (
                f"{mem}\n\n---\n\n## Current ingestion & RAG context\n\n{context}"
            )
        try:
            with dspy.context(lm=self._lm):
                return cot(
                    context=ctx,
                    user_instructions=user_instructions,
                )
        finally:
            VRAMManager.clear()

    def forward_persona_draft(
        self,
        context: str,
        user_instructions: str,
        *,
        persona_id: str,
    ):
        """
        Run exactly one strategic persona CoT (for multi-agent consensus sub-drafts).
        ``persona_id`` must be a key in ``GTM_PERSONA_SIGNATURES``.
        """
        if persona_id not in self._cots:
            persona_id = GTM_DEFAULT_PERSONA
        cot = self._cots[persona_id]
        try:
            with dspy.context(lm=self._lm):
                return cot(
                    context=context,
                    user_instructions=user_instructions,
                )
        finally:
            VRAMManager.clear()

    def forward_strategy_synthesis(
        self,
        user_instructions: str,
        vc_deck_json: str,
        govtech_deck_json: str,
        risk_deck_json: str,
    ):
        """Merge three persona JSON drafts into one master ``presentation_json`` + ``consensus_rationale``."""
        try:
            with dspy.context(lm=self._lm):
                return self._synthesis_cot(
                    user_instructions=user_instructions,
                    vc_deck_json=vc_deck_json,
                    govtech_deck_json=govtech_deck_json,
                    risk_deck_json=risk_deck_json,
                )
        finally:
            VRAMManager.clear()


class RedTeamAuditorOrchestrator(dspy.Module):
    """Autonomous pre-inspection: ChainOfThought over ``StrategicCritiqueSignature``."""

    def __init__(
        self,
        config: EngineConfig | None = None,
        lm: dspy.LM | None = None,
    ) -> None:
        super().__init__()
        self._config = config or EngineConfig()
        self._lm = lm or _ollama_lm(self._config.gtm_model, self._config.base_url)
        self._cot = dspy.ChainOfThought(StrategicCritiqueSignature)

    def forward(self, user_prompt: str, slide_deck_json: str):
        try:
            with dspy.context(lm=self._lm):
                return self._cot(
                    user_prompt=user_prompt,
                    slide_deck_json=slide_deck_json,
                )
        finally:
            VRAMManager.clear()


class ComplianceAuditorOrchestrator(dspy.Module):
    """Path II: compliance benchmarking pass over a finished draft deck."""

    def __init__(
        self,
        config: EngineConfig | None = None,
        lm: dspy.LM | None = None,
    ) -> None:
        super().__init__()
        self._config = config or EngineConfig()
        self._lm = lm or _ollama_lm(self._config.gtm_model, self._config.base_url)
        self._cot = dspy.ChainOfThought(ComplianceAuditSignature)

    def forward(self, *, standard: str, strategic_directive: str, slide_deck_json: str):
        try:
            with dspy.context(lm=self._lm):
                return self._cot(
                    standard=standard,
                    strategic_directive=strategic_directive,
                    slide_deck_json=slide_deck_json,
                )
        finally:
            VRAMManager.clear()


class ContradictionClassifierOrchestrator(dspy.Module):
    """Path LL: lightweight LLM pass to detect material contradiction vs fresh web snippets (Path JJ)."""

    def __init__(
        self,
        config: EngineConfig | None = None,
        lm: dspy.LM | None = None,
    ) -> None:
        super().__init__()
        self._config = config or EngineConfig()
        self._lm = lm or _ollama_lm(self._config.gtm_model, self._config.base_url)
        self._cot = dspy.ChainOfThought(ContradictionSignature)

    def forward(self, *, original_strategic_context: str, new_web_snippets: str):
        try:
            with dspy.context(lm=self._lm):
                return self._cot(
                    original_strategic_context=original_strategic_context or "",
                    new_web_snippets=new_web_snippets or "",
                )
        finally:
            VRAMManager.clear()


@dataclass
class WargameOrchestratorResult:
    """Path BB: structured output from ``StrategicWargameOrchestrator``."""

    debate_turns: list[dict[str, Any]]
    residual_risks_json: str
    residual_headline: str
    full_transcript: str


class StrategicWargameOrchestrator(dspy.Module):
    """
    Path BB: three rounds of Adversary vs Proponent debate on the consensus deck,
    then a residual-risk JSON summary.
    """

    NUM_TURNS = 3

    def __init__(
        self,
        config: EngineConfig | None = None,
        lm: dspy.LM | None = None,
    ) -> None:
        super().__init__()
        self._config = config or EngineConfig()
        self._lm = lm or _ollama_lm(self._config.gtm_model, self._config.base_url)
        self._adv = dspy.ChainOfThought(WargameAdversaryTurnSignature)
        self._prop = dspy.ChainOfThought(WargameProponentTurnSignature)
        self._residual = dspy.ChainOfThought(WargameResidualSummarySignature)

    def forward(
        self,
        strategic_directive: str,
        consensus_deck_json: str,
    ) -> WargameOrchestratorResult:
        sd = (strategic_directive or "").strip()
        deck = consensus_deck_json or ""
        transcript_parts: list[str] = []
        turn_rows: list[dict[str, Any]] = []
        prior = ""
        full = ""
        risks_raw = ""
        headline = ""
        try:
            with dspy.context(lm=self._lm):
                for t in range(1, self.NUM_TURNS + 1):
                    ap = self._adv(
                        strategic_directive=sd,
                        consensus_deck_json=deck,
                        prior_transcript=prior,
                        turn_number=str(t),
                    )
                    attack = str(getattr(ap, "adversary_attack", None) or "").strip()
                    transcript_parts.append(f"Round {t} — ADVERSARY:\n{attack}\n")
                    pp = self._prop(
                        strategic_directive=sd,
                        consensus_deck_json=deck,
                        adversary_attack=attack,
                        prior_transcript=prior,
                        turn_number=str(t),
                    )
                    mit = str(getattr(pp, "proponent_mitigation", None) or "").strip()
                    transcript_parts.append(f"Round {t} — PROPONENT:\n{mit}\n")
                    turn_rows.append(
                        {
                            "turn": t,
                            "adversary_attack": attack,
                            "proponent_mitigation": mit,
                        },
                    )
                    prior = prior + "\n\n" + transcript_parts[-2] + transcript_parts[-1]

                full = "\n".join(transcript_parts)
                rs = self._residual(
                    strategic_directive=sd,
                    consensus_deck_json=deck,
                    full_debate_transcript=full,
                )
                risks_raw = str(getattr(rs, "residual_risks_json", None) or "")
                headline = str(getattr(rs, "residual_headline", None) or "").strip()
        finally:
            VRAMManager.clear()

        return WargameOrchestratorResult(
            debate_turns=turn_rows,
            residual_risks_json=risks_raw,
            residual_headline=headline,
            full_transcript=full,
        )


@dataclass
class ChairmanResolutionResult:
    """Path FF: structured output from the Chairman resolution pass."""

    revised_deck_json: str
    chairman_rationale: str


class ChairmanResolutionOrchestrator(dspy.Module):
    """
    Path FF: executive “Chairman” agent that edits the consensus deck to incorporate Path BB mitigations.
    """

    def __init__(
        self,
        config: EngineConfig | None = None,
        lm: dspy.LM | None = None,
    ) -> None:
        super().__init__()
        self._config = config or EngineConfig()
        self._lm = lm or _ollama_lm(self._config.gtm_model, self._config.base_url)
        self._cot = dspy.ChainOfThought(ChairmanSignature)

    def forward(
        self,
        strategic_directive: str,
        consensus_deck_json: str,
        wargame_transcript: str,
        residual_risks_json: str,
    ) -> ChairmanResolutionResult:
        sd = (strategic_directive or "").strip()
        deck = consensus_deck_json or ""
        tr = wargame_transcript or ""
        rr = residual_risks_json or "[]"
        try:
            with dspy.context(lm=self._lm):
                pred = self._cot(
                    strategic_directive=sd,
                    consensus_deck_json=deck,
                    wargame_transcript=tr,
                    residual_risks_json=rr,
                )
        finally:
            VRAMManager.clear()
        revised = str(getattr(pred, "revised_deck_json", None) or "")
        rationale = str(getattr(pred, "chairman_rationale", None) or "").strip()
        return ChairmanResolutionResult(
            revised_deck_json=revised,
            chairman_rationale=rationale,
        )


class SlideRefinementOrchestrator(dspy.Module):
    """Strategic chat on one slide: DSPy ChainOfThought over ``RefineSlideSignature``."""

    def __init__(
        self,
        config: EngineConfig | None = None,
        lm: dspy.LM | None = None,
    ) -> None:
        super().__init__()
        self._config = config or EngineConfig()
        self._lm = lm or _ollama_lm(self._config.gtm_model, self._config.base_url)
        self._cot = dspy.ChainOfThought(RefineSlideSignature)

    def forward(self, slide_json: str, refinement_instruction: str):
        try:
            with dspy.context(lm=self._lm):
                return self._cot(
                    slide_json=slide_json,
                    refinement_instruction=refinement_instruction,
                )
        finally:
            VRAMManager.clear()


class ExecutiveBriefingOrchestrator(dspy.Module):
    """Path P: ChainOfThought over ``ExecutiveBriefingSignature`` (summary + per-slide talk track)."""

    def __init__(
        self,
        config: EngineConfig | None = None,
        lm: dspy.LM | None = None,
    ) -> None:
        super().__init__()
        self._config = config or EngineConfig()
        self._lm = lm or _ollama_lm(self._config.gtm_model, self._config.base_url)
        self._cot = dspy.ChainOfThought(ExecutiveBriefingSignature)

    def forward(self, deck_json: str, strategic_context: str):
        try:
            with dspy.context(lm=self._lm):
                return self._cot(
                    deck_json=deck_json,
                    strategic_context=strategic_context,
                )
        finally:
            VRAMManager.clear()


class StrategicJudgeOrchestrator(dspy.Module):
    """Path V: ChainOfThought over ``StrategicJudgeSignature`` (Executive Committee rubric)."""

    def __init__(
        self,
        config: EngineConfig | None = None,
        lm: dspy.LM | None = None,
    ) -> None:
        super().__init__()
        self._config = config or EngineConfig()
        self._lm = lm or _ollama_lm(self._config.gtm_model, self._config.base_url)
        self._cot = dspy.ChainOfThought(StrategicJudgeSignature)

    def forward(self, strategic_directive: str, finalized_deck_json: str):
        try:
            with dspy.context(lm=self._lm):
                return self._cot(
                    strategic_directive=strategic_directive,
                    finalized_deck_json=finalized_deck_json,
                )
        finally:
            VRAMManager.clear()
