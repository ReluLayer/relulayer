from __future__ import annotations

import dspy

# Path N: optional per-slide data chart (materialized to PNG for PPTX content area).
_CHART_REQUEST_HINT = (
    "Optional chart_request: {chart_type: bar|line|scatter|pie, title?, x:[], y:[]} "
    "or pie with labels:[], values:[]; optional series:[{name,x:[],y:[]}] for multi-series. "
    "Use when RAG or bullets contain numeric series worth plotting."
)


class ExtractDeterministicSchema(dspy.Signature):
    """Structured extraction into JSON matching a supplied schema."""

    context = dspy.InputField(
        desc="Raw unstructured municipal or enterprise data.",
    )
    schema_template = dspy.InputField(
        desc="The target JSON structure or Pydantic schema.",
    )
    extracted_json = dspy.OutputField(
        desc="A valid, strictly formatted JSON string adhering to the template.",
    )


class GenerateStrategicVisualBrief(dspy.Signature):
    """Plan slide content and abstract image prompts for multimodal deck generation."""

    context = dspy.InputField(
        desc="Background data and reference files.",
    )
    user_instructions = dspy.InputField(
        desc="Specific goals for the presentation.",
    )
    presentation_json = dspy.OutputField(
        desc=(
            "JSON array of slides. Each slide must include: title, body, speaker_notes, "
            "and an image_prompt (abstract, no text, no charts). "
            "Optionally add icon_request (short theme string) on key slides for a corner icon. "
            + _CHART_REQUEST_HINT
        ),
    )


class VCPitchSignature(dspy.Signature):
    """Venture capital pitch lens: emphasize growth, TAM/SAM/SOM, category momentum, and calibrated investor FOMO; ground claims in the supplied context."""

    context = dspy.InputField(
        desc="Market, product, traction, and financial reference material.",
    )
    user_instructions = dspy.InputField(
        desc="Round, stage, sector focus, and narrative goals for investors.",
    )
    presentation_json = dspy.OutputField(
        desc=(
            "JSON array of slides. Each slide must include: title, body, speaker_notes, "
            "and an image_prompt (abstract, no text, no charts). "
            "Optionally add icon_request (short theme string) on key slides for a corner icon. "
            + _CHART_REQUEST_HINT
        ),
    )


class GovTechSignature(dspy.Signature):
    """GovTech lens: emphasize regulatory compliance, secure 5G and network integration, municipal scale, procurement realism, and public-sector outcomes tied to the context."""

    context = dspy.InputField(
        desc="Policies, infrastructure data, municipal programs, and technical constraints.",
    )
    user_instructions = dspy.InputField(
        desc="Agency goals, timelines, stakeholders, and compliance targets.",
    )
    presentation_json = dspy.OutputField(
        desc=(
            "JSON array of slides. Each slide must include: title, body, speaker_notes, "
            "and an image_prompt (abstract, no text, no charts). "
            "Optionally add icon_request (short theme string) on key slides for a corner icon. "
            + _CHART_REQUEST_HINT
        ),
    )


class StrategicCritiqueSignature(dspy.Signature):
    """Red-team audit: adversarial review of the drafted deck against the stated strategic intent."""

    user_prompt = dspy.InputField(
        desc="The strategist's original directive, goals, and constraints.",
    )
    slide_deck_json = dspy.InputField(
        desc="Full generated deck as JSON (object with slides array or raw slides array).",
    )
    strategic_risks_json = dspy.OutputField(
        desc=(
            'Strict JSON array only. Each element: {"risk": string, "severity": "low"|"medium"|"high"}. '
            "List concrete logic gaps, missing proof, audience mismatches, compliance holes, or overclaims. "
            "No markdown fences or prose outside the array."
        ),
    )


class RefineSlideSignature(dspy.Signature):
    """Layer 6: apply a strategist's delta to one slide while preserving deck role (hero vs detail)."""

    slide_json = dspy.InputField(
        desc="Single slide as JSON (title, body, speaker_notes, image_prompt, subtitle, type, original_id, etc.). "
        "If original_id is present, do not change strategic identity of the slide beyond title/body wording.",
    )
    refinement_instruction = dspy.InputField(
        desc="What to change: tone, urgency, length, audience, or factual emphasis.",
    )
    refined_title = dspy.OutputField(
        desc="Updated slide title only; short, title-case or sentence as appropriate; no quotes or markdown.",
    )
    refined_body = dspy.OutputField(
        desc="Updated slide body (bullets or prose); keep slide-appropriate density; no markdown fences.",
    )


class RiskAuditSignature(dspy.Signature):
    """Risk and audit lens: emphasize vulnerabilities, threat surfaces, mitigation plans, residual risk, and technical debt with traceability to the supplied context."""

    context = dspy.InputField(
        desc="Systems inventory, controls evidence, incident history, and architecture notes.",
    )
    user_instructions = dspy.InputField(
        desc="Audit scope, frameworks (e.g. NIST), and reporting objectives.",
    )
    presentation_json = dspy.OutputField(
        desc=(
            "JSON array of slides. Each slide must include: title, body, speaker_notes, "
            "and an image_prompt (abstract, no text, no charts). "
            "Optionally add icon_request (short theme string) on key slides for a corner icon. "
            + _CHART_REQUEST_HINT
        ),
    )


class StrategySynthesisSignature(dspy.Signature):
    """Layer 3 consensus: fuse Venture Capital, GovTech, and Risk-Auditor drafts into one auditable master deck."""

    user_instructions = dspy.InputField(
        desc="Original strategic directive; use as the tie-breaker when persona views conflict.",
    )
    vc_deck_json = dspy.InputField(
        desc='Venture Capital persona output: JSON array of slides or {"slides":[...]}; each slide has title, body, speaker_notes, image_prompt.',
    )
    govtech_deck_json = dspy.InputField(
        desc="GovTech persona output: same JSON shape as vc_deck_json.",
    )
    risk_deck_json = dspy.InputField(
        desc="Risk / audit persona output: same JSON shape as vc_deck_json.",
    )
    presentation_json = dspy.OutputField(
        desc=(
            "Single merged JSON array of slides (not wrapped in an object). "
            "Each slide: title, body, speaker_notes, image_prompt; optional type, subtitle, icon_request. "
            + _CHART_REQUEST_HINT + " "
            "Resolve contradictions explicitly in content; prefer claims grounded in the combined evidence; "
            "one coherent narrative arc with ~similar or fewer slides than the longest sub-draft unless the directive demands more."
        ),
    )
    consensus_rationale = dspy.OutputField(
        desc=(
            "Concise prose (no JSON, no markdown code fences): which lenses dominated where, "
            "major tradeoffs and conflicts resolved, and the single robust strategic thread the master deck follows."
        ),
    )


class ChairmanSignature(dspy.Signature):
    """
    Path FF: executive “Chairman” pass that applies risk mitigations to the deck.

    Inputs include the consensus deck plus the Path BB wargame transcript; output is a revised deck JSON
    with minimal, surgical edits that incorporate mitigations.
    """

    strategic_directive = dspy.InputField(
        desc="Original strategist directive; do not violate goals or constraints.",
    )
    consensus_deck_json = dspy.InputField(
        desc="Consensus draft deck JSON (object with slides array or raw slides array).",
    )
    wargame_transcript = dspy.InputField(
        desc="Full 3-turn wargame transcript (Adversary attacks + Proponent mitigations).",
    )
    residual_risks_json = dspy.InputField(
        desc=(
            "Residual risks JSON array from Path BB summary "
            '(each element: {"risk": string, "severity": "low"|"medium"|"high"}).'
        ),
    )
    revised_deck_json = dspy.OutputField(
        desc=(
            "STRICT JSON only (no markdown fences). "
            "Return either a JSON array of slides, or an object {\"slides\": [...], \"design_specs\"?: {...}}. "
            "Make minimal edits to incorporate mitigations: tighten claims, add missing caveats, adjust numbers, "
            "insert 1 mitigation bullet where needed, and align speaker_notes with mitigation posture. "
            "Each slide object MUST preserve its input \"original_id\" string exactly (same count, order optional but IDs must match 1:1)."
        ),
    )
    chairman_rationale = dspy.OutputField(
        desc=(
            "Concise prose (no JSON): what was changed and why; call out which wargame mitigations were incorporated "
            "and which residual risks remain intentionally unresolved."
        ),
    )


class ComplianceAuditSignature(dspy.Signature):
    """
    Path II: compliance benchmarking pass against an industry standard (ESG, NIST, ISO, etc.).

    Produces a strict JSON list of slide-level findings with suggested corrective copy.
    """

    standard = dspy.InputField(
        desc=(
            "Compliance standard/framework identifier, e.g. NIST CSF, ISO 27001, SOC 2, ESG, HIPAA, PCI DSS. "
            "Keep it short and specific."
        ),
    )
    strategic_directive = dspy.InputField(
        desc="Original strategist directive and constraints (audience, scope, tone).",
    )
    slide_deck_json = dspy.InputField(
        desc="Full deck JSON (object with slides array or raw slides array).",
    )
    findings_json = dspy.OutputField(
        desc=(
            "STRICT JSON array only. Each element:\n"
            '{\"slide_index\": <0-based int>, \"issue\": <string>, \"standard_clause\": <string>, '
            '\"severity\": \"low\"|\"medium\"|\"high\", '
            '\"suggested_copy\": {\"title\": <string|\"\">, \"body\": <string|\"\">, \"speaker_notes\": <string|\"\">}}\n'
            "Rules: only flag concrete violations/gaps relative to the named standard; reference a clause/control id "
            "when possible; suggested_copy must be concise and slide-ready; no markdown fences; no prose outside JSON."
        ),
    )
    audit_summary = dspy.OutputField(
        desc="One-paragraph plain text summary of overall compliance posture and top remediation themes.",
    )


class ContradictionSignature(dspy.Signature):
    """
    Path LL: decide whether fresh web evidence materially contradicts a saved strategic posture.

    Used by Path JJ drift monitoring to reduce false positives from naive keyword overlap.
    """

    original_strategic_context = dspy.InputField(
        desc=(
            "Strategic rationale and risk posture from when the session was saved "
            "(draft chain-of-thought, red-team weak points, and/or the strategist directive)."
        ),
    )
    new_web_snippets = dspy.InputField(
        desc="Fresh web/news grounding: titles, URLs, and snippet text for the same strategic question.",
    )
    contradiction_json = dspy.OutputField(
        desc=(
            'STRICT JSON only (no markdown fences): {"is_contradictory": <boolean>, "reasoning": "<short paragraph>"}. '
            "Set is_contradictory to true only when snippets materially undermine assumptions, timelines, regulatory "
            "posture, market thesis, or key risks reflected in the saved context—not for unrelated sector noise, "
            "generic macro news, or mentions that do not conflict with the strategy. "
            "reasoning must state what assumption is challenged and how the new evidence conflicts."
        ),
    )


class ExecutiveBriefingSignature(dspy.Signature):
    """Path P: post-draft executive summary and spoken talk track for rehearsal."""

    deck_json = dspy.InputField(
        desc=(
            "JSON object with a 'slides' array. Each slide may include title, body, speaker_notes, "
            "subtitle, type; preserve order. This is the materialization-ready or reviewed deck."
        ),
    )
    strategic_context = dspy.InputField(
        desc=(
            "Strategist's original directive, target audience (e.g. board, investors, agency CIO), "
            "and tone constraints; may be empty if only deck content should drive the briefing."
        ),
    )
    executive_summary = dspy.OutputField(
        desc=(
            "One page or less of tight executive prose (no JSON, no markdown fences): "
            "thesis, stakes, recommendation, and what success looks like. Suitable for a cover email or 1-pager."
        ),
    )
    talk_track_json = dspy.OutputField(
        desc=(
            "Strict JSON array only, same length and order as slides in deck_json. "
            "Each element is a string: full spoken script for that slide (transitions, emphasis, timing cues allowed). "
            "No markdown code fences; escape quotes inside strings properly."
        ),
    )


class StrategicJudgeSignature(dspy.Signature):
    """Path V: external Executive Committee auditor — score finalized consensus deck vs industry rubric."""

    strategic_directive = dspy.InputField(
        desc=(
            "Strategist's original directive: goals, audience (e.g. board, investors, agency), "
            "constraints, and what 'good' looks like for this engagement."
        ),
    )
    finalized_deck_json = dspy.InputField(
        desc=(
            'The deck under review as JSON: object with "slides" array or a raw array of slide objects. '
            "Each slide typically includes title, body, speaker_notes, image_prompt; preserve order."
        ),
    )
    rubric_scores_json = dspy.OutputField(
        desc=(
            'Strict JSON object only — no markdown code fences, no trailing commentary: '
            '{"clarity": <integer 1-10>, "feasibility": <integer 1-10>, "strategic_impact": <integer 1-10>}. '
            "Clarity: crisp narrative, slide hygiene, audience-appropriate language. "
            "Feasibility: realism of claims, resourcing, timelines, and evidence vs ambition. "
            "Strategic_impact: differentiation, stakes, coherent arc, decision-forcing value for executives."
        ),
    )
    committee_verdict = dspy.OutputField(
        desc=(
            'Exactly one token from this set (lowercase): "proceed" | "revise" | "reject" — '
            "as an independent Executive Committee would minute for materialization gate."
        ),
    )
    auditor_rationale = dspy.OutputField(
        desc=(
            "Concise prose only (no JSON, no code fences): 3–6 sentences citing rubric dimensions, "
            "key strengths, material gaps vs industry-standard strategy decks, and why that verdict; "
            "if any score is below 7, name the weakest dimension first."
        ),
    )


class DataAuditorSignature(dspy.Signature):
    """Path R: write executable Python to compute metrics from whitelisted tabular files."""

    user_instructions = dspy.InputField(
        desc=(
            "Strategic directive requiring quantitative analysis (ROI, aggregates, trends, "
            "correlations, forecasts, etc.). Honor this intent exactly."
        ),
    )
    data_file_manifest = dspy.InputField(
        desc=(
            "JSON array of objects with string keys path (absolute file path on server) and name (filename). "
            "Only these CSV/Excel files may be read. Do not assume other paths exist."
        ),
    )
    tabular_context_excerpt = dspy.InputField(
        desc=(
            "Truncated markdown excerpt from ingestion (column previews / sample rows). "
            "Use to infer dtypes and column names; trust file reads for exact numbers."
        ),
    )
    audit_plan = dspy.OutputField(
        desc=(
            "Short prose (no code fences): what you will compute, which columns/metrics, "
            "and how results support slide-ready claims."
        ),
    )
    python_script = dspy.OutputField(
        desc=(
            "Complete Python script body only (no markdown fences). "
            "A preamble is injected by the runtime defining DATA_MANIFEST = list of {path, name} from the environment. "
            "Use pandas: pd.read_csv(path) or pd.read_excel(path) for each DATA_MANIFEST entry. "
            "Allowed: pandas, numpy, json, math, statistics, datetime. "
            "Print a clear text summary of numeric results to stdout (labels + values, suitable for slide bullets). "
            "Handle missing columns gracefully; if impossible, print AUDIT_FAILED: reason."
        ),
    )


class StrategicSimulationSignature(dspy.Signature):
    """Path S: Monte Carlo stress-test; executable script uses Data Auditor sandbox (Path R)."""

    user_instructions = dspy.InputField(
        desc=(
            "Strategic goals and risk framing (e.g. NPV/ROI thresholds, go/no-go criteria, "
            "time horizon). Used to define 'success' for Monte Carlo draws."
        ),
    )
    strategy_deck_json = dspy.InputField(
        desc=(
            "JSON string: deck with slides array (title, body, speaker_notes) or compact summary object. "
            "Ground scenario assumptions (revenue, capex, adoption) implied by the draft."
        ),
    )
    data_file_manifest = dspy.InputField(
        desc=(
            "JSON array of {path: absolute server path, name: filename} for CSV/Excel only. "
            "These are the only files the script may read."
        ),
    )
    contextual_variables_excerpt = dspy.InputField(
        desc=(
            "RAG + ingestion text describing market drivers, ranges, correlations, or risks "
            "(use to set uncertainty distributions—not invented constants)."
        ),
    )
    simulation_design = dspy.OutputField(
        desc=(
            "Prose (no code fences): which uncertain inputs are varied, their distributions tied to context/data, "
            "success metric (e.g. NPV>0 or ROI>X%), and interpretation intent for executives."
        ),
    )
    python_script = dspy.OutputField(
        desc=(
            "Complete Python body only (no markdown fences). Runtime injects imports + DATA_MANIFEST + numpy as np. "
            "Read int(os.environ.get('RELULAYER_SIM_MC_RUNS','1000')) for scenario count (cap at 5000 if higher). "
            "Run Monte Carlo with np.random.default_rng(seed=42); vectorize where possible. "
            "Derive base-case inputs from loaded dataframes; perturb key drivers per contextual_variables_excerpt. "
            "Compute NPV or ROI proxy per scenario if data supports it; else a clear numeric success proxy. "
            "After diagnostics, print exactly one line: RELULAYER_SIM_JSON= followed by compact JSON with keys: "
            "probability_of_success (0-100 float, percent chance success criterion met), "
            "sensitivity_analysis_markdown (slide-ready markdown: ranked drivers / tornado-style bullets), "
            "headline (one sentence). No other text on that final line."
        ),
    )


class WargameAdversaryTurnSignature(dspy.Signature):
    """Path BB — Adversary (Red Team): attack the consensus deck; surface one strategic vulnerability per round."""

    strategic_directive = dspy.InputField(
        desc="Strategist's original goals, audience, constraints, and success criteria.",
    )
    consensus_deck_json = dspy.InputField(
        desc='Full deck JSON: object with "slides" array (title, body, speaker_notes, etc.).',
    )
    prior_transcript = dspy.InputField(
        desc="Completed debate so far (plain text). Empty string on round 1.",
    )
    turn_number = dspy.InputField(desc="Round index as digit string: 1, 2, or 3.")
    adversary_attack = dspy.OutputField(
        desc=(
            "3–8 sentences: one sharp flaw — logic gap, hidden assumption, competitive weakness, "
            "execution risk, or stakeholder blind spot. Be specific to this deck. "
            "If prior_transcript is non-empty, do not repeat the same attack; escalate or change angle."
        ),
    )


class WargameProponentTurnSignature(dspy.Signature):
    """Path BB — Proponent (Blue Team): defend the deck against the adversary's latest attack."""

    strategic_directive = dspy.InputField(
        desc="Strategist's original goals, audience, constraints.",
    )
    consensus_deck_json = dspy.InputField(
        desc='Full deck JSON under debate.',
    )
    adversary_attack = dspy.InputField(
        desc="The adversary's attack text for this round only.",
    )
    prior_transcript = dspy.InputField(
        desc="All completed prior rounds (adversary + proponent pairs), plain text.",
    )
    turn_number = dspy.InputField(desc="Round index: 1, 2, or 3.")
    proponent_mitigation = dspy.OutputField(
        desc=(
            "3–10 sentences: counter-argument, evidence implied by the deck, honest scope boundary, "
            "or acknowledged residual risk with a concrete mitigation path. Stay credible — no hand-waving."
        ),
    )


class WargameResidualSummarySignature(dspy.Signature):
    """Path BB — After three debate rounds, extract remaining strategic risks."""

    strategic_directive = dspy.InputField(desc="Original strategist directive.")
    consensus_deck_json = dspy.InputField(desc="Full deck JSON.")
    full_debate_transcript = dspy.InputField(
        desc="Full transcript: for each round, ADVERSARY then PROPONENT blocks in order.",
    )
    residual_risks_json = dspy.OutputField(
        desc=(
            'Strict JSON array only — no markdown fences: '
            '[{"risk": string, "severity": "low"|"medium"|"high"}, ...] '
            "Risks that remain credible AFTER proponent mitigations: unanswered gaps, fragile assumptions, "
            "or issues the proponent could not fully neutralize."
        ),
    )
    residual_headline = dspy.OutputField(
        desc="2–5 sentences: executive summary of residual fragility for the strategist.",
    )
