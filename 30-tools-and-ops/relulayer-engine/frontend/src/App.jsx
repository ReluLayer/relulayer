/**
 * File: src/App.jsx
 * Path: ~/projects/relulayer-engine/frontend/src/App.jsx
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

/**
 * Full API origin (no trailing slash), or null to use same-origin `/api` (Vite proxy → port 8000).
 * Override with VITE_API_BASE when the UI is not served by Vite dev server.
 */
const getConfiguredApiBase = () => {
  try {
    const v = import.meta.env?.VITE_API_BASE;
    if (v != null && String(v).trim() !== '') {
      return String(v).replace(/\/$/, '');
    }
  } catch (e) {
    /* ignore */
  }
  return null;
};

/** @param {string} path e.g. `/process/gtm/draft` */
const apiUrl = (path) => {
  const base = getConfiguredApiBase();
  const p = path.startsWith('/') ? path : `/${path}`;
  if (base != null) return `${base}${p}`;
  return `/api${p}`;
};

/** FastAPI serves repo `assets/` at `/static/...` (see vite proxy when dev). */
const staticAssetUrl = (href) => {
  if (!href) return '';
  if (href.startsWith('http://') || href.startsWith('https://')) return href;
  const base = getConfiguredApiBase();
  if (base != null) return `${base}${href}`;
  return href;
};

function getOrCreateWarRoomUserId() {
  try {
    let u = localStorage.getItem('relulayer_war_room_user_id');
    if (!u) {
      u =
        typeof crypto !== 'undefined' && crypto.randomUUID
          ? crypto.randomUUID()
          : `user_${Date.now()}`;
      localStorage.setItem('relulayer_war_room_user_id', u);
    }
    return u;
  } catch {
    return `user_${Date.now()}`;
  }
}

/** Path U: Vite dev uses same-origin ``/ws`` proxy; ``VITE_API_BASE`` uses that host with ws/wss. */
function buildWarRoomWsUrl(sessionId, userId, displayName) {
  const q = new URLSearchParams({
    user_id: userId,
    display_name: displayName || 'Strategist',
  });
  const base = getConfiguredApiBase();
  if (base != null) {
    const wsBase = base.replace(/^http:/i, 'ws:').replace(/^https:/i, 'wss:');
    return `${wsBase}/ws/war-room/${encodeURIComponent(sessionId)}?${q}`;
  }
  const wsProto =
    typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss' : 'ws';
  const host = typeof window !== 'undefined' ? window.location.host : 'localhost:5173';
  return `${wsProto}://${host}/ws/war-room/${encodeURIComponent(sessionId)}?${q}`;
}

/** Path DD: GTM draft telemetry stream (same JSON body as POST /process/gtm/draft). */
function buildGtmDraftWsUrl() {
  const base = getConfiguredApiBase();
  if (base != null) {
    const wsBase = base.replace(/^http:/i, 'ws:').replace(/^https:/i, 'wss:');
    return `${wsBase}/ws/process/gtm/draft`;
  }
  const wsProto =
    typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss' : 'ws';
  const host = typeof window !== 'undefined' ? window.location.host : 'localhost:5173';
  return `${wsProto}://${host}/ws/process/gtm/draft`;
}

const formatApiDetail = (detail) => {
  if (!detail) return 'An error occurred during processing.';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map(d => d.msg || JSON.stringify(d)).join(' | ');
  }
  if (typeof detail === 'object') {
    return JSON.stringify(detail);
  }
  return String(detail);
};

/** Path NN: render persisted Path LL drift events (newest first). */
function DriftTimelinePanel({ entries }) {
  const ordered = useMemo(() => {
    const arr = Array.isArray(entries) ? [...entries] : [];
    arr.sort((a, b) => {
      const ta = String(a?.at || a?.timestamp || '');
      const tb = String(b?.at || b?.timestamp || '');
      return tb.localeCompare(ta);
    });
    return arr;
  }, [entries]);

  return (
    <div className="rounded-xl border border-fuchsia-700/40 bg-fuchsia-950/20 p-4 text-left">
      <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-fuchsia-300 font-sans">
        Drift timeline (Path NN · Path LL)
      </div>
      <p className="mt-1 text-[10px] text-slate-500 font-mono leading-relaxed">
        Contradiction alerts are persisted on the strategy session. Reconnect or reload the session ID to restore
        history.
      </p>
      {ordered.length === 0 ? (
        <p className="mt-3 text-[11px] text-slate-500 font-mono">
          No drift events yet. Enable drift monitoring for this session (Path JJ); when Path LL flags a material
          contradiction, it appears here.
        </p>
      ) : (
        <ul className="mt-3 space-y-4 list-none max-h-[min(24rem,50vh)] overflow-y-auto pr-1">
          {ordered.map((ev, idx) => (
            <li
              key={ev.event_id || `${ev.at || 'ev'}-${idx}`}
              className="border-l-2 border-fuchsia-600/60 pl-3 pb-1"
            >
              <div className="text-[10px] font-mono text-fuchsia-500/90">
                {ev.at ? String(ev.at) : '(no timestamp)'}
              </div>
              <div className="text-xs text-fuchsia-100/95 font-sans mt-0.5">
                {ev.headline || 'Strategic Drift Detected: New Market Reality'}
              </div>
              {typeof ev.reasoning === 'string' && ev.reasoning.trim() !== '' && (
                <div className="mt-1 text-[11px] text-slate-300 font-mono whitespace-pre-wrap">{ev.reasoning}</div>
              )}
              {Array.isArray(ev.top_snippets) && ev.top_snippets.length > 0 && (
                <div className="mt-2 space-y-1">
                  <div className="text-[9px] uppercase tracking-wider text-slate-500 font-sans">Top web snippets</div>
                  {ev.top_snippets.slice(0, 5).map((s, i) => (
                    <div key={i} className="text-[10px] text-slate-400 font-mono border-t border-fuchsia-900/30 pt-1">
                      <span className="text-slate-300">{s.title || '(untitled)'}</span>
                      {s.url ? <span className="block break-all text-fuchsia-600/80">{s.url}</span> : null}
                      {s.snippet ? (
                        <span className="block text-slate-500 mt-0.5 line-clamp-3">{s.snippet}</span>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
              <div className="mt-1 text-[10px] text-slate-500 font-mono">
                snippets {ev.snippet_count ?? '—'}
                {ev.classifier ? ` · ${ev.classifier}` : ''}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const TELEMETRY_TABS = [
  { id: 'rationale', label: 'Strategy Rationale' },
  { id: 'prompt', label: 'Raw Prompt' },
  { id: 'output', label: 'Raw Output' },
];

// --- Path W: Interactive rehearsal (teleprompter + Web Speech API) ------------

function normalizeTeleprompterWord(w) {
  return String(w || '')
    .toLowerCase()
    .replace(/[^a-z0-9']/g, '');
}

function buildRehearsalFullScript(briefing, deckSlides) {
  const chunks = [];
  const summary = (briefing?.executive_summary || '').trim();
  if (summary) {
    chunks.push(summary);
  }
  const rows = [...(briefing?.slide_talk_tracks || [])].sort(
    (a, b) => Number(a.slide_index) - Number(b.slide_index),
  );
  for (const row of rows) {
    const t = (row.talk_track || '').trim();
    if (t) chunks.push(t);
  }
  return chunks.join('\n\n');
}

/**
 * Advance read cursor: match trailing words from Web Speech transcript to script.
 */
function alignHeardToScript(normWords, startIdx, heardText) {
  if (!normWords.length) return 0;
  const hw = heardText
    .toLowerCase()
    .replace(/[^a-z0-9\s']/g, ' ')
    .split(/\s+/)
    .map((w) => normalizeTeleprompterWord(w))
    .filter(Boolean);
  if (hw.length === 0) return startIdx;
  const tailLen = Math.min(16, hw.length);
  const tail = hw.slice(-tailLen);
  const searchStart = Math.max(0, startIdx - 8);
  let bestEnd = startIdx;
  for (let i = searchStart; i < normWords.length; i++) {
    let k = 0;
    while (
      k < tail.length &&
      i + k < normWords.length &&
      normWords[i + k] &&
      (normWords[i + k] === tail[k] ||
        normWords[i + k].startsWith(tail[k]) ||
        tail[k].startsWith(normWords[i + k]))
    ) {
      k++;
    }
    if (k >= Math.min(2, tail.length)) {
      const end = i + k;
      if (end > bestEnd) bestEnd = end;
    }
  }
  const cap = Math.max(0, normWords.length - 1);
  return Math.min(Math.max(bestEnd, startIdx), cap);
}

/**
 * Path W.1 — Teleprompter + SpeechRecognition-driven scroll; avatar placeholder for future Video-LLM.
 */
function InteractiveRehearsalPanel({ briefing, deckSlides, onReportError, onReadAloud }) {
  const fullScript = useMemo(
    () => buildRehearsalFullScript(briefing, deckSlides),
    [briefing, deckSlides],
  );
  const rawWords = useMemo(() => {
    const t = fullScript.trim();
    if (!t) return [];
    return t.split(/\s+/).filter(Boolean);
  }, [fullScript]);
  const normWords = useMemo(
    () => rawWords.map((w) => normalizeTeleprompterWord(w)),
    [rawWords],
  );

  const [listening, setListening] = useState(false);
  const [activeWordIdx, setActiveWordIdx] = useState(0);
  const accumulatedFinalRef = useRef('');
  const recognitionRef = useRef(null);
  const activeSpanRef = useRef(null);
  const teleprompterRef = useRef(null);

  const speechSupported =
    typeof window !== 'undefined' &&
    (window.SpeechRecognition || window.webkitSpeechRecognition);

  useEffect(() => {
    accumulatedFinalRef.current = '';
    setActiveWordIdx(0);
  }, [fullScript]);

  useEffect(() => {
    const el = activeSpanRef.current;
    if (!el) return;
    el.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [activeWordIdx]);

  useEffect(() => {
    return () => {
      try {
        recognitionRef.current?.stop?.();
      } catch (_) {
        /* ignore */
      }
      recognitionRef.current = null;
    };
  }, []);

  const stopListening = useCallback(() => {
    try {
      recognitionRef.current?.stop?.();
    } catch (_) {
      /* ignore */
    }
    recognitionRef.current = null;
    setListening(false);
  }, []);

  const startListening = useCallback(() => {
    if (!speechSupported || !rawWords.length) return;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    try {
      recognitionRef.current?.stop?.();
    } catch (_) {
      /* ignore */
    }
    accumulatedFinalRef.current = '';
    setActiveWordIdx(0);
    const rec = new SR();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = (typeof navigator !== 'undefined' && navigator.language) || 'en-US';
    rec.onresult = (event) => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const tr = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          accumulatedFinalRef.current = `${accumulatedFinalRef.current} ${tr}`.trim();
        } else {
          interim += tr;
        }
      }
      const combined = `${accumulatedFinalRef.current} ${interim}`.trim();
      setActiveWordIdx((prev) =>
        Math.max(prev, alignHeardToScript(normWords, prev, combined)),
      );
    };
    rec.onerror = (ev) => {
      if (ev.error === 'not-allowed') {
        onReportError?.('Microphone permission denied — allow mic for rehearsal alignment.');
      } else if (ev.error !== 'aborted' && ev.error !== 'no-speech') {
        onReportError?.(`Speech recognition: ${ev.error || 'error'}`);
      }
    };
    rec.onend = () => {
      if (recognitionRef.current === rec) {
        setListening(false);
        recognitionRef.current = null;
      }
    };
    recognitionRef.current = rec;
    try {
      rec.start();
      setListening(true);
    } catch (e) {
      onReportError?.(e?.message || 'Could not start speech recognition.');
      recognitionRef.current = null;
      setListening(false);
    }
  }, [normWords, onReportError, rawWords.length, speechSupported]);

  if (!rawWords.length) {
    return (
      <p className="text-xs text-slate-500 font-mono">
        No talk-track text to rehearse. Generate an executive briefing first.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-teal-800/40 bg-teal-950/15 px-3 py-2 text-[11px] text-teal-200/90 font-sans leading-relaxed">
        <span className="font-bold text-teal-400">Path W — Interactive rehearsal:</span> speak naturally; the
        teleprompter advances when your words match the script (Chrome / Edge recommended). Use a quiet room for
        best alignment.
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(220px,280px)_1fr] items-start">
        {/* Presenter avatar placeholder — swap for Video-LLM / frame sequence later */}
        <div className="space-y-2">
          <div className="relative aspect-[4/3] max-h-56 rounded-xl overflow-hidden border border-teal-800/50 bg-gradient-to-br from-slate-950 via-teal-950/40 to-slate-900 shadow-[0_0_40px_rgba(20,184,166,0.08)]">
            <div
              className="absolute inset-0 opacity-40"
              style={{
                background:
                  'radial-gradient(ellipse 80% 60% at 50% 40%, rgba(45,212,191,0.15), transparent 70%)',
              }}
            />
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-4">
              <div
                className={`relative h-28 w-28 rounded-full border-2 border-teal-500/35 bg-gradient-to-t from-teal-900/50 to-cyan-800/20 ${
                  listening ? 'animate-pulse' : ''
                }`}
              >
                <div className="absolute inset-3 rounded-full bg-slate-900/60 border border-teal-600/20" />
                <div className="absolute bottom-6 left-1/2 h-2 w-10 -translate-x-1/2 rounded-full bg-teal-500/25" />
              </div>
              <span className="text-[10px] font-mono text-teal-500/70 text-center px-2">
                AI presenter avatar — placeholder (local Video-LLM / animated frames TBD)
              </span>
            </div>
            {listening && (
              <div className="absolute top-2 right-2 flex items-center gap-1.5 rounded-full bg-rose-950/90 px-2 py-0.5 border border-rose-600/50">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-rose-500" />
                </span>
                <span className="text-[9px] font-bold uppercase text-rose-200 font-mono">Live</span>
              </div>
            )}
          </div>
        </div>

        <div className="flex flex-col min-h-[min(60vh,28rem)] rounded-xl border border-slate-800 bg-black/50 overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 bg-slate-900/80 px-3 py-2">
            {!speechSupported ? (
              <span className="text-[10px] text-amber-400 font-mono">
                Web Speech API unavailable — use Chromium-based browser for mic-driven scroll.
              </span>
            ) : (
              <>
                {typeof onReadAloud === 'function' && rawWords.length > 0 && (
                  <button
                    type="button"
                    onClick={() => onReadAloud(fullScript)}
                    className="rounded-lg border border-slate-600 bg-slate-900 px-3 py-1.5 text-[10px] font-bold uppercase font-mono text-slate-300 hover:bg-slate-800"
                  >
                    Read aloud (Path W)
                  </button>
                )}
                <button
                  type="button"
                  onClick={listening ? stopListening : startListening}
                  className={`rounded-lg px-3 py-1.5 text-[10px] font-bold uppercase font-mono border ${
                    listening
                      ? 'border-rose-700/60 bg-rose-950/50 text-rose-200 hover:bg-rose-900/50'
                      : 'border-teal-600/60 bg-teal-950/40 text-teal-200 hover:bg-teal-900/50'
                  }`}
                >
                  {listening ? 'Stop mic' : 'Start rehearsal mic'}
                </button>
                <span className="text-[10px] text-slate-500 font-mono">
                  {listening ? 'Listening — read aloud to advance' : 'Mic off'}
                </span>
                <span className="text-[10px] text-slate-600 font-mono ml-auto">
                  {Math.min(activeWordIdx, rawWords.length)} / {rawWords.length} words
                </span>
              </>
            )}
          </div>
          <div
            ref={teleprompterRef}
            className="flex-1 overflow-y-auto px-4 py-6 text-left leading-[1.85] scroll-smooth"
          >
            <p className="text-[10px] uppercase tracking-widest text-slate-600 font-mono mb-3">
              Talk track — teleprompter
            </p>
            <div className="text-lg sm:text-xl text-slate-200 font-sans font-light">
              {rawWords.map((w, i) => {
                const done = i < activeWordIdx;
                const current = i === activeWordIdx;
                return (
                  <span
                    key={`w-${i}`}
                    ref={current ? activeSpanRef : undefined}
                    className={`inline mr-[0.35em] rounded-sm transition-colors duration-150 ${
                      done
                        ? 'text-slate-500/80'
                        : current
                          ? 'bg-teal-500/35 text-teal-50 ring-1 ring-teal-400/40 shadow-[0_0_20px_rgba(45,212,191,0.12)]'
                          : 'text-slate-300'
                    }`}
                  >
                    {w}
                  </span>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** API values must match orchestration/main.GtmPersonaId */
const STRATEGIC_PERSONAS = [
  { id: 'consensus', label: 'Multi-Agent Consensus (VC + GovTech + Risk)' },
  { id: 'venture_capital', label: 'Venture Capital' },
  { id: 'govtech', label: 'GovTech Specialist' },
  { id: 'risk_auditor', label: 'Risk Auditor' },
];

const CONSENSUS_SUB_PERSONA_LABELS = {
  venture_capital: 'Venture Capital sub-draft',
  govtech: 'GovTech sub-draft',
  risk_auditor: 'Risk Auditor sub-draft',
};

/** Path O — Decision Matrix categories (1–10 strategist scores). */
const DECISION_MATRIX_ROWS = [
  { id: 'market_speed', label: 'Market speed' },
  { id: 'compliance', label: 'Compliance' },
  { id: 'technical_feasibility', label: 'Technical feasibility' },
];

/** Persona-weighted seed scores for the matrix (strategist can override in the overlay). */
const MATRIX_SEED_BY_PERSONA = {
  venture_capital: { market_speed: 8, compliance: 4, technical_feasibility: 7 },
  govtech: { market_speed: 5, compliance: 8, technical_feasibility: 7 },
  risk_auditor: { market_speed: 4, compliance: 9, technical_feasibility: 6 },
  consensus: { market_speed: 6, compliance: 6, technical_feasibility: 6 },
};

function matrixSeedForPersona(personaId) {
  return { ...(MATRIX_SEED_BY_PERSONA[personaId] || MATRIX_SEED_BY_PERSONA.consensus) };
}

function adjustMatrixForRedTeam(scores, telemetry) {
  if (!telemetry?.audit_report?.red_team_alert) return scores;
  return {
    ...scores,
    compliance: Math.min(10, (scores.compliance ?? 5) + 1),
    market_speed: Math.max(1, (scores.market_speed ?? 5) - 1),
  };
}

function buildDecisionMatrixScores(personaA, personaB, telemetryA, telemetryB) {
  return {
    pathA: adjustMatrixForRedTeam(matrixSeedForPersona(personaA), telemetryA),
    pathB: adjustMatrixForRedTeam(matrixSeedForPersona(personaB), telemetryB),
  };
}

function matrixPathTotal(scores, pathKey) {
  const p = scores[pathKey];
  return DECISION_MATRIX_ROWS.reduce((s, r) => s + (Number(p[r.id]) || 0), 0);
}

/**
 * @param {{
 *   user_prompt: string,
 *   file_paths: string[],
 *   project_folder: string,
 *   persona: string,
 *   self_correction?: boolean,
 *   wargame_debate?: boolean,
 * }} body
 */
async function fetchGtmDraft(body) {
  const draftRes = await fetch(apiUrl('/process/gtm/draft'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  let draftPayload = null;
  const draftJson = draftRes.headers.get('content-type')?.includes('application/json');
  if (draftJson) {
    draftPayload = await draftRes.json();
  } else {
    const textDetail = await draftRes.text();
    draftPayload = { detail: textDetail || `HTTP Error ${draftRes.status}` };
  }
  if (!draftRes.ok) {
    return {
      ok: false,
      errorMessage: formatApiDetail(draftPayload.detail),
      slides: [],
      telemetry: null,
      design_specs: null,
      template_hint: null,
      persona: body.persona,
    };
  }
  return {
    ok: true,
    errorMessage: null,
    slides: Array.isArray(draftPayload.slides) ? draftPayload.slides : [],
    telemetry: draftPayload.telemetry ?? null,
    design_specs: draftPayload.design_specs ?? null,
    template_hint: draftPayload.template_hint ?? null,
    persona: body.persona,
  };
}

export default function App() {
  const [dashboardMode, setDashboardMode] = useState('standard');
  const [sandboxPersonaA, setSandboxPersonaA] = useState('venture_capital');
  const [sandboxPersonaB, setSandboxPersonaB] = useState('risk_auditor');
  const [sandboxLabelA, setSandboxLabelA] = useState('Aggressive VC');
  const [sandboxLabelB, setSandboxLabelB] = useState('Conservative risk');
  const [sandboxDraftA, setSandboxDraftA] = useState(null);
  const [sandboxDraftB, setSandboxDraftB] = useState(null);
  const [sandboxGenerating, setSandboxGenerating] = useState(false);
  const [decisionMatrixOpen, setDecisionMatrixOpen] = useState(false);
  const [decisionMatrixScores, setDecisionMatrixScores] = useState(null);

  const [persona, setPersona] = useState('govtech');
  /** Path Y — judge-triggered autonomous slide refine before draft is returned */
  const [selfCorrection, setSelfCorrection] = useState(false);
  /** Path BB — adversarial wargame after Red Team */
  const [wargameDebate, setWargameDebate] = useState(false);
  /** Path II — compliance benchmarking pass */
  const [compliancePass, setCompliancePass] = useState(false);
  const [complianceStandard, setComplianceStandard] = useState('NIST CSF');
  /** Path DD — stream agent rationales over WebSocket while drafting */
  const [liveDraftStream, setLiveDraftStream] = useState(false);
  const [liveThinkingFeed, setLiveThinkingFeed] = useState([]);
  const draftWsRef = useRef(null);
  const [prompt, setPrompt] = useState("Create a high-level strategic brief for a municipal infrastructure project focused on 5G integration.");
  const [filePath, setFilePath] = useState("assets/uploaded_template.pptx");
  const [projectFolder, setProjectFolder] = useState("");
  const [phase, setPhase] = useState('form');
  const [deckSlides, setDeckSlides] = useState([]);
  const [deckTemplate, setDeckTemplate] = useState('');
  const [deckDesignSpecs, setDeckDesignSpecs] = useState(null);
  const [heroPreviewByIndex, setHeroPreviewByIndex] = useState({});
  const [synthBusy, setSynthBusy] = useState({});
  const [refineBusy, setRefineBusy] = useState({});
  const [refineInputs, setRefineInputs] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState(null);
  /** Path CC — financial appendix .xlsx from materialize (server absolute path) */
  const [financialAppendixPath, setFinancialAppendixPath] = useState(null);
  const [error, setError] = useState(null);
  const [telemetry, setTelemetry] = useState(null);
  const [materializeStructural, setMaterializeStructural] = useState(null);
  /** Path Z — last generated microsite ``/static/outputs/sites/…`` */
  const [micrositeHref, setMicrositeHref] = useState(null);
  const [micrositeBusy, setMicrositeBusy] = useState(false);
  /** Path V — scores must match current deck JSON to enable materialize */
  const [qualityGate, setQualityGate] = useState(null);
  const [qualityGateSig, setQualityGateSig] = useState(null);
  const [qualityGateBusy, setQualityGateBusy] = useState(false);
  const [telemetryOpen, setTelemetryOpen] = useState(false);
  const [telemetryTab, setTelemetryTab] = useState('rationale');
  /** Path P: ``slides`` | ``speaker_notes`` during slide review */
  const [reviewViewTab, setReviewViewTab] = useState('slides');
  const [executiveBriefing, setExecutiveBriefing] = useState(null);
  /** Path W: ``document`` | ``rehearsal`` within Executive briefing tab */
  const [briefingViewMode, setBriefingViewMode] = useState('document');
  const [briefingBusy, setBriefingBusy] = useState(false);
  const [briefingTtsBusy, setBriefingTtsBusy] = useState(null);
  /** Path HH — generated mp4 brief under /static/outputs/video/… */
  const [videoBriefHref, setVideoBriefHref] = useState(null);
  const [videoBriefBusy, setVideoBriefBusy] = useState(false);
  /** Path MM: from GET /process/gtm/media-capabilities */
  const [mediaCaps, setMediaCaps] = useState(null);
  /** Path PP: GET /health — production readiness & degraded paths */
  const [systemHealth, setSystemHealth] = useState(null);
  /** Path GG export: 'jsonld' | 'turtle' while downloading */
  const [kgExportBusy, setKgExportBusy] = useState(null);
  const briefingAudioRef = useRef(null);

  /** Path U — War Room (WebSocket + strategy locks) */
  const [warRoomUserId] = useState(() => getOrCreateWarRoomUserId());
  const [warRoomDisplayName, setWarRoomDisplayName] = useState('Strategist');
  const [strategySessionId, setStrategySessionId] = useState('');
  const [warRoomLive, setWarRoomLive] = useState(false);
  const [warRoomConnId, setWarRoomConnId] = useState(null);
  const [warRoomSlideLocks, setWarRoomSlideLocks] = useState({});
  const [warRoomPresence, setWarRoomPresence] = useState([]);
  /** Path JJ — drift alerts pushed over war room WS */
  /** Path NN: persisted drift timeline for current strategy session (from REST + War Room). */
  const [driftHistory, setDriftHistory] = useState([]);
  const [warRoomSessionSaving, setWarRoomSessionSaving] = useState(false);
  const warRoomWsRef = useRef(null);
  const warRoomConnIdRef = useRef(null);
  const warRoomLockPendingRef = useRef({});
  const skipNextDeckPushRef = useRef(false);

  const telemetryTabList = useMemo(() => {
    const base = [...TELEMETRY_TABS];
    if (telemetry?.live_grounding_data) {
      base.push({ id: 'grounding', label: 'Live Grounding Data' });
    }
    if (
      telemetry?.consensus_persona_turns &&
      telemetry.consensus_persona_turns.length > 0
    ) {
      base.push({ id: 'consensus', label: 'Consensus sub-drafts' });
    }
    if (telemetry?.audit_report) {
      base.push({ id: 'redteam', label: 'Red Team Audit' });
    }
    if (
      telemetry?.self_correction_applied ||
      (telemetry?.self_correction_skipped_reason != null &&
        String(telemetry.self_correction_skipped_reason).trim() !== '') ||
      telemetry?.self_correction_judge_verdict != null
    ) {
      base.push({ id: 'selfcorrection', label: 'Self-correction (Path Y)' });
    }
    if (telemetry?.wargame_audit != null) {
      base.push({ id: 'wargame', label: 'Wargame Audit' });
    }
    if (telemetry?.compliance_pass != null) {
      base.push({ id: 'compliance', label: 'Compliance Pass' });
    }
    return base;
  }, [
    telemetry?.audit_report,
    telemetry?.consensus_persona_turns,
    telemetry?.live_grounding_data,
    telemetry?.self_correction_applied,
    telemetry?.self_correction_skipped_reason,
    telemetry?.self_correction_judge_verdict,
    telemetry?.wargame_audit,
    telemetry?.compliance_pass,
  ]);

  useEffect(() => {
    if (!telemetryTabList.some((t) => t.id === telemetryTab)) {
      setTelemetryTab('rationale');
    }
  }, [telemetryTabList, telemetryTab]);

  useEffect(() => {
    let cancelled = false;
    fetch(apiUrl('/process/gtm/media-capabilities'))
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((j) => {
        if (!cancelled && j && typeof j === 'object') {
          setMediaCaps({
            sadtalker_configured: !!j.sadtalker_configured,
            piper_configured: !!j.piper_configured,
          });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setMediaCaps({ sadtalker_configured: false, piper_configured: false });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const pull = () => {
      fetch(apiUrl('/health'))
        .then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json();
        })
        .then((j) => {
          if (!cancelled && j && typeof j === 'object') {
            setSystemHealth(j);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setSystemHealth({
              status: 'critical',
              degraded_paths: [
                {
                  path_id: 'api_health',
                  label: 'API /health',
                  reason: 'Unreachable from browser (proxy or backend down).',
                  severity: 'error',
                },
              ],
            });
          }
        });
    };
    pull();
    const id = setInterval(pull, 60000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const systemHealthSummary = useMemo(() => {
    if (!systemHealth) {
      return { dot: 'bg-slate-500', label: 'System Health…', title: 'Checking production readiness…' };
    }
    const st = systemHealth.status;
    const degraded = Array.isArray(systemHealth.degraded_paths)
      ? systemHealth.degraded_paths
      : [];
    const gpuName = systemHealth.gpu?.name;
    const vram =
      systemHealth.gpu?.memory_used_mb != null &&
      systemHealth.gpu?.memory_total_mb != null
        ? `${systemHealth.gpu.memory_used_mb} / ${systemHealth.gpu.memory_total_mb} MiB`
        : null;
    const lines = degraded.map((d) => `${d.label}: ${d.reason || ''}`);
    const baseTitle = [
      `Status: ${st}`,
      gpuName ? `GPU: ${gpuName}` : null,
      vram ? `VRAM: ${vram}` : null,
      lines.length ? '—' : null,
      ...lines,
    ]
      .filter(Boolean)
      .join('\n');
    if (st === 'healthy') {
      return {
        dot: 'bg-emerald-500',
        label: 'System healthy',
        title: baseTitle || 'All checked paths nominal.',
      };
    }
    if (st === 'degraded') {
      return {
        dot: 'bg-amber-500',
        label: 'Degraded paths',
        title: baseTitle,
      };
    }
    return {
      dot: 'bg-red-500',
      label: 'System critical',
      title: baseTitle,
    };
  }, [systemHealth]);

  const draftRequestBody = () => ({
    user_prompt: prompt,
    file_paths: filePath.trim() ? [filePath.trim()] : [],
    project_folder: projectFolder.trim(),
    self_correction: selfCorrection,
    wargame_debate: wargameDebate,
    compliance_pass: compliancePass,
    compliance_standard: complianceStandard,
  });

  const applyDraftSuccessToReview = useCallback(
    (tel, slides, templateHint, designSpecs) => {
      setTelemetry(tel);
      if (tel?.audit_report?.red_team_alert) {
        setTelemetryTab('redteam');
      } else if (tel?.wargame_audit?.wargame_alert) {
        setTelemetryTab('wargame');
      } else if (
        tel?.self_correction_applied ||
        (tel?.self_correction_skipped_reason != null &&
          String(tel.self_correction_skipped_reason).trim() !== '') ||
        tel?.self_correction_judge_verdict != null
      ) {
        setTelemetryTab('selfcorrection');
      } else {
        setTelemetryTab('rationale');
      }
      setDeckSlides(slides);
      setDeckTemplate(templateHint || filePath);
      setDeckDesignSpecs(designSpecs ?? null);
      setExecutiveBriefing(null);
      setQualityGate(null);
      setQualityGateSig(null);
      setReviewViewTab('slides');
      setPhase('review');
    },
    [filePath],
  );

  const handleDraftOnly = async () => {
    setIsLoading(true);
    setError(null);
    setResult(null);
    setFinancialAppendixPath(null);
    setTelemetry(null);
    setMaterializeStructural(null);
    setMicrositeHref(null);
    setTelemetryOpen(false);
    setHeroPreviewByIndex({});
    setSynthBusy({});
    setRefineBusy({});
    setRefineInputs({});
    setLiveThinkingFeed([]);
    if (draftWsRef.current) {
      try {
        draftWsRef.current.close();
      } catch (_) {
        /* ignore */
      }
      draftWsRef.current = null;
    }

    try {
      if (liveDraftStream) {
        const body = { ...draftRequestBody(), persona };
        const payload = await new Promise((resolve, reject) => {
          let settled = false;
          const finish = (fn) => {
            if (settled) return;
            settled = true;
            fn();
          };
          const ws = new WebSocket(buildGtmDraftWsUrl());
          draftWsRef.current = ws;
          ws.onopen = () => {
            ws.send(JSON.stringify(body));
          };
          ws.onmessage = (ev) => {
            let msg;
            try {
              msg = JSON.parse(ev.data);
            } catch {
              return;
            }
            if (msg.type === 'final') {
              if (draftWsRef.current === ws) draftWsRef.current = null;
              try {
                ws.close();
              } catch (_) {
                /* ignore */
              }
              finish(() => {
                if (msg.ok) {
                  resolve(msg.payload);
                } else {
                  reject(new Error(formatApiDetail(msg.detail)));
                }
              });
              return;
            }
            setLiveThinkingFeed((prev) => [
              ...prev,
              { ...msg, _id: `${Date.now()}_${prev.length}` },
            ]);
          };
          ws.onerror = () => {
            if (draftWsRef.current === ws) draftWsRef.current = null;
            finish(() =>
              reject(
                new Error(
                  'WebSocket draft stream failed. Ensure the API is running and Vite proxies /ws (or use VITE_API_BASE with ws/wss).',
                ),
              ),
            );
          };
          ws.onclose = () => {
            if (draftWsRef.current === ws) draftWsRef.current = null;
            finish(() =>
              reject(new Error('WebSocket closed before the draft finished (no final payload).')),
            );
          };
        });
        const tel = payload.telemetry ?? null;
        applyDraftSuccessToReview(
          tel,
          Array.isArray(payload.slides) ? payload.slides : [],
          payload.template_hint,
          payload.design_specs ?? null,
        );
      } else {
        const draftPayload = await fetchGtmDraft({ ...draftRequestBody(), persona });
        if (!draftPayload.ok) {
          throw new Error(draftPayload.errorMessage || 'Draft failed');
        }
        applyDraftSuccessToReview(
          draftPayload.telemetry ?? null,
          draftPayload.slides,
          draftPayload.template_hint,
          draftPayload.design_specs ?? null,
        );
      }
    } catch (err) {
      const isNetwork =
        err instanceof TypeError &&
        (err.message === 'Failed to fetch' || err.message.includes('fetch'));
      setError(
        isNetwork
          ? 'Failed to reach the API. Start the backend (e.g. uvicorn on :8000) and keep using Vite dev server so /api proxies to it, or set VITE_API_BASE to the full API URL.'
          : err.message || String(err),
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleSandboxGenerateBoth = async () => {
    setSandboxGenerating(true);
    setSandboxDraftA(null);
    setSandboxDraftB(null);
    setDecisionMatrixScores(null);
    setDecisionMatrixOpen(false);
    setError(null);
    setResult(null);
    setFinancialAppendixPath(null);
    setMaterializeStructural(null);
    setMicrositeHref(null);
    setTelemetryOpen(false);
    const base = draftRequestBody();
    try {
      const a = await fetchGtmDraft({ ...base, persona: sandboxPersonaA });
      setSandboxDraftA(a);
      const b = await fetchGtmDraft({ ...base, persona: sandboxPersonaB });
      setSandboxDraftB(b);
      setDecisionMatrixScores(
        buildDecisionMatrixScores(sandboxPersonaA, sandboxPersonaB, a.telemetry, b.telemetry),
      );
      setPhase('sandbox_review');
    } catch (err) {
      const isNetwork =
        err instanceof TypeError &&
        (err.message === 'Failed to fetch' || err.message.includes('fetch'));
      setError(
        isNetwork
          ? 'Failed to reach the API while running the sandbox. Check backend and /api proxy.'
          : err.message || String(err),
      );
    } finally {
      setSandboxGenerating(false);
    }
  };

  const recalibrateDecisionMatrix = () => {
    if (!sandboxDraftA || !sandboxDraftB) return;
    setDecisionMatrixScores(
      buildDecisionMatrixScores(
        sandboxPersonaA,
        sandboxPersonaB,
        sandboxDraftA.telemetry,
        sandboxDraftB.telemetry,
      ),
    );
  };

  const openDecisionMatrix = () => {
    if (!sandboxDraftA || !sandboxDraftB) return;
    setDecisionMatrixScores((prev) =>
      prev
        ? prev
        : buildDecisionMatrixScores(
            sandboxPersonaA,
            sandboxPersonaB,
            sandboxDraftA.telemetry,
            sandboxDraftB.telemetry,
          ),
    );
    setDecisionMatrixOpen(true);
  };

  const adoptSandboxPath = (which) => {
    const d = which === 'a' ? sandboxDraftA : sandboxDraftB;
    if (!d?.ok) {
      setError(`Cannot adopt ${which === 'a' ? sandboxLabelA : sandboxLabelB}: draft failed. Regenerate or pick the other path.`);
      return;
    }
    setPersona(d.persona);
    setTelemetry(d.telemetry);
    if (d.telemetry?.audit_report?.red_team_alert) {
      setTelemetryTab('redteam');
    } else if (d.telemetry?.wargame_audit?.wargame_alert) {
      setTelemetryTab('wargame');
    } else {
      setTelemetryTab('rationale');
    }
    setDeckSlides(d.slides);
    setDeckTemplate(d.template_hint || filePath);
    setDeckDesignSpecs(d.design_specs ?? null);
    setQualityGate(null);
    setQualityGateSig(null);
    setHeroPreviewByIndex({});
    setSynthBusy({});
    setRefineBusy({});
    setRefineInputs({});
    setDashboardMode('standard');
    setExecutiveBriefing(null);
    setReviewViewTab('slides');
    setPhase('review');
  };

  const buildSandboxPayload = useCallback(
    () => ({
      user_prompt: prompt,
      file_paths: filePath.trim() ? [filePath.trim()] : [],
      project_folder: projectFolder.trim(),
      self_correction: selfCorrection,
      wargame_debate: wargameDebate,
      persona_a: sandboxPersonaA,
      persona_b: sandboxPersonaB,
      label_a: sandboxLabelA,
      label_b: sandboxLabelB,
      draft_a: sandboxDraftA,
      draft_b: sandboxDraftB,
      decision_matrix_scores: decisionMatrixScores,
      phase_hint: phase,
    }),
    [
      prompt,
      filePath,
      projectFolder,
      sandboxPersonaA,
      sandboxPersonaB,
      sandboxLabelA,
      sandboxLabelB,
      sandboxDraftA,
      sandboxDraftB,
      decisionMatrixScores,
      phase,
      selfCorrection,
      wargameDebate,
    ],
  );

  const applyRemoteSandbox = useCallback((sandbox) => {
    if (!sandbox || typeof sandbox !== 'object') return;
    if (typeof sandbox.user_prompt === 'string') setPrompt(sandbox.user_prompt);
    if (Array.isArray(sandbox.file_paths) && sandbox.file_paths.length > 0) {
      setFilePath(String(sandbox.file_paths[0]));
    }
    if (typeof sandbox.project_folder === 'string') setProjectFolder(sandbox.project_folder);
    if (typeof sandbox.self_correction === 'boolean') setSelfCorrection(sandbox.self_correction);
    if (typeof sandbox.wargame_debate === 'boolean') setWargameDebate(sandbox.wargame_debate);
    if (typeof sandbox.persona_a === 'string') setSandboxPersonaA(sandbox.persona_a);
    if (typeof sandbox.persona_b === 'string') setSandboxPersonaB(sandbox.persona_b);
    if (typeof sandbox.label_a === 'string') setSandboxLabelA(sandbox.label_a);
    if (typeof sandbox.label_b === 'string') setSandboxLabelB(sandbox.label_b);
    if (sandbox.draft_a !== undefined && sandbox.draft_a !== null) setSandboxDraftA(sandbox.draft_a);
    if (sandbox.draft_b !== undefined && sandbox.draft_b !== null) setSandboxDraftB(sandbox.draft_b);
    if (sandbox.decision_matrix_scores && typeof sandbox.decision_matrix_scores === 'object') {
      setDecisionMatrixScores(sandbox.decision_matrix_scores);
    }
    const ph = sandbox.phase_hint;
    if (ph === 'sandbox_review' || ph === 'form') setPhase(ph);
  }, []);

  useEffect(() => {
    const sid = strategySessionId.trim();
    if (!sid) {
      setDriftHistory([]);
      return undefined;
    }
    let cancelled = false;
    fetch(apiUrl(`/process/gtm/strategy-sessions/${encodeURIComponent(sid)}`))
      .then((r) => (r.ok ? r.json() : null))
      .then((doc) => {
        if (cancelled || !doc) return;
        if (String(doc.session_id || '') !== sid) return;
        if (Array.isArray(doc.drift_history)) setDriftHistory(doc.drift_history);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [strategySessionId]);

  useEffect(() => {
    if (!strategySessionId.trim() || !warRoomLive) {
      if (warRoomWsRef.current) {
        try {
          warRoomWsRef.current.close();
        } catch (_) {
          /* ignore */
        }
        warRoomWsRef.current = null;
      }
      warRoomConnIdRef.current = null;
      setWarRoomConnId(null);
      return undefined;
    }
    const sid = strategySessionId.trim();
    const url = buildWarRoomWsUrl(sid, warRoomUserId, warRoomDisplayName);
    const ws = new WebSocket(url);
    warRoomWsRef.current = ws;
    ws.onmessage = (ev) => {
      let msg;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (!msg || typeof msg !== 'object') return;
      if (msg.type === 'welcome') {
        warRoomConnIdRef.current = msg.conn_id ?? null;
        setWarRoomConnId(msg.conn_id ?? null);
        if (msg.slide_locks && typeof msg.slide_locks === 'object') {
          setWarRoomSlideLocks(msg.slide_locks);
        }
        if (Array.isArray(msg.presence)) setWarRoomPresence(msg.presence);
        if (Array.isArray(msg.drift_history)) setDriftHistory(msg.drift_history);
        return;
      }
      if (msg.type === 'slide_lock_ack' && msg.request_id) {
        const p = warRoomLockPendingRef.current[msg.request_id];
        if (p) {
          delete warRoomLockPendingRef.current[msg.request_id];
          if (msg.ok) p.resolve();
          else {
            const holder = msg.held_by?.display_name || msg.held_by?.user_id || 'another strategist';
            p.reject(new Error(`Slide locked by ${holder}`));
          }
        }
        return;
      }
      if (msg.type === 'slide_locks' && msg.locks && typeof msg.locks === 'object') {
        setWarRoomSlideLocks(msg.locks);
        return;
      }
      if (msg.type === 'presence' && Array.isArray(msg.users)) {
        setWarRoomPresence(msg.users);
        return;
      }
      if (msg.type === 'sandbox_sync' && msg.sandbox) {
        if (msg.origin_conn_id && msg.origin_conn_id === warRoomConnIdRef.current) return;
        applyRemoteSandbox(msg.sandbox);
        if (Array.isArray(msg.drift_history)) setDriftHistory(msg.drift_history);
        return;
      }
      if (msg.type === 'deck_state_sync' && Array.isArray(msg.slides)) {
        if (msg.origin_conn_id && msg.origin_conn_id === warRoomConnIdRef.current) return;
        skipNextDeckPushRef.current = true;
        setDeckSlides(msg.slides);
        if (typeof msg.template === 'string') setDeckTemplate(msg.template);
        if (msg.design_specs !== undefined) setDeckDesignSpecs(msg.design_specs);
        return;
      }
      if (msg.type === 'strategic_drift_alert') {
        if (Array.isArray(msg.drift_history)) {
          setDriftHistory(msg.drift_history);
        }
        return;
      }
    };
    ws.onclose = () => {
      if (warRoomWsRef.current === ws) warRoomWsRef.current = null;
      warRoomConnIdRef.current = null;
      setWarRoomConnId(null);
    };
    ws.onerror = () => {};
    return () => {
      ws.close();
      if (warRoomWsRef.current === ws) warRoomWsRef.current = null;
    };
  }, [strategySessionId, warRoomLive, warRoomUserId, warRoomDisplayName, applyRemoteSandbox]);

  useEffect(() => {
    const ws = warRoomWsRef.current;
    if (!strategySessionId.trim() || !warRoomConnId || ws?.readyState !== WebSocket.OPEN) {
      return undefined;
    }
    if (phase !== 'sandbox_review') return undefined;
    const t = setTimeout(() => {
      try {
        ws.send(
          JSON.stringify({
            type: 'sandbox_push',
            sandbox: buildSandboxPayload(),
          }),
        );
      } catch (_) {
        /* ignore */
      }
    }, 750);
    return () => clearTimeout(t);
  }, [
    buildSandboxPayload,
    phase,
    strategySessionId,
    warRoomConnId,
    sandboxDraftA,
    sandboxDraftB,
    decisionMatrixScores,
    sandboxPersonaA,
    sandboxPersonaB,
    sandboxLabelA,
    sandboxLabelB,
    prompt,
    filePath,
    projectFolder,
  ]);

  useEffect(() => {
    const ws = warRoomWsRef.current;
    if (!strategySessionId.trim() || !warRoomConnId || ws?.readyState !== WebSocket.OPEN) {
      return undefined;
    }
    if (phase !== 'review' && phase !== 'done') return undefined;
    if (skipNextDeckPushRef.current) {
      skipNextDeckPushRef.current = false;
      return undefined;
    }
    const t = setTimeout(() => {
      try {
        ws.send(
          JSON.stringify({
            type: 'deck_state_push',
            slides: deckSlides,
            template: deckTemplate,
            design_specs: deckDesignSpecs,
          }),
        );
      } catch (_) {
        /* ignore */
      }
    }, 650);
    return () => clearTimeout(t);
  }, [
    deckSlides,
    deckTemplate,
    deckDesignSpecs,
    phase,
    strategySessionId,
    warRoomConnId,
  ]);

  const handleCreateStrategySession = async () => {
    setWarRoomSessionSaving(true);
    setError(null);
    try {
      const res = await fetch(apiUrl('/process/gtm/strategy-sessions'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          branch_label: 'War room',
          sandbox: buildSandboxPayload(),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(formatApiDetail(data.detail) || `HTTP ${res.status}`);
      }
      if (!data.session_id) throw new Error('No session_id returned');
      setStrategySessionId(data.session_id);
      setWarRoomLive(true);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setWarRoomSessionSaving(false);
    }
  };

  const wideLayout = phase === 'sandbox_review';

  const currentDeckSig = useMemo(() => JSON.stringify(deckSlides), [deckSlides]);
  const qualityGatePassed =
    qualityGate != null &&
    qualityGateSig != null &&
    qualityGateSig === currentDeckSig;

  const speakBriefingInBrowser = (text) => {
    const t = String(text || '').trim();
    if (!t || typeof window === 'undefined' || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(t);
    u.rate = 0.92;
    window.speechSynthesis.speak(u);
  };

  const requestBriefingPiperTts = async (text, busyKey) => {
    const t = String(text || '').trim();
    if (!t) return;
    setBriefingTtsBusy(busyKey);
    setError(null);
    try {
      const res = await fetch(apiUrl('/process/gtm/executive-briefing/tts'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: t.slice(0, 8000) }),
      });
      let payload = null;
      const isJson = res.headers.get('content-type')?.includes('application/json');
      if (isJson) {
        payload = await res.json();
      } else {
        payload = { detail: await res.text() };
      }
      if (!res.ok) {
        throw new Error(formatApiDetail(payload.detail));
      }
      if (payload.engine === 'piper' && payload.audio_href) {
        const el = briefingAudioRef.current;
        if (el) {
          el.src = staticAssetUrl(payload.audio_href);
          el.play().catch(() => {
            setError('Audio element could not play. Check browser autoplay policy.');
          });
        }
      } else {
        setError(
          'Server Piper TTS unavailable. Set RELULAYER_PIPER_MODEL (and RELULAYER_PIPER_BIN if needed) on the API host, or use Browser speak.',
        );
      }
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBriefingTtsBusy(null);
    }
  };

  const handleGenerateExecutiveBriefing = async () => {
    if (!Array.isArray(deckSlides) || deckSlides.length === 0) {
      setError('No slides to brief.');
      return;
    }
    setBriefingBusy(true);
    setError(null);
    try {
      const res = await fetch(apiUrl('/process/gtm/executive-briefing'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          slides: deckSlides,
          user_prompt: prompt,
        }),
      });
      let payload = null;
      const isJson = res.headers.get('content-type')?.includes('application/json');
      if (isJson) {
        payload = await res.json();
      } else {
        payload = { detail: await res.text() };
      }
      if (!res.ok) {
        throw new Error(formatApiDetail(payload.detail));
      }
      setExecutiveBriefing({
        executive_summary: payload.executive_summary || '',
        slide_talk_tracks: Array.isArray(payload.slide_talk_tracks)
          ? payload.slide_talk_tracks
          : [],
        telemetry: payload.telemetry ?? null,
      });
      setVideoBriefHref(null);
      setBriefingViewMode('document');
    } catch (err) {
      const isNetwork =
        err instanceof TypeError &&
        (err.message === 'Failed to fetch' || err.message.includes('fetch'));
      setError(
        isNetwork
          ? 'Failed to reach the API for executive briefing.'
          : err.message || String(err),
      );
    } finally {
      setBriefingBusy(false);
    }
  };

  const handleGenerateVideoBrief = async () => {
    if (!executiveBriefing) {
      setError('Generate an executive briefing first (Path P talk track).');
      return;
    }
    if (!Array.isArray(deckSlides) || deckSlides.length === 0) {
      setError('No slides available for video brief.');
      return;
    }
    const script = buildRehearsalFullScript(executiveBriefing, deckSlides).trim();
    if (!script) {
      setError('No talk-track script available for video brief.');
      return;
    }
    setVideoBriefBusy(true);
    setError(null);
    try {
      const res = await fetch(apiUrl('/process/gtm/video-brief'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          slides: deckSlides,
          talk_track_text: script.slice(0, 12000),
          seconds_per_slide: 4.0,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(formatApiDetail(data.detail) || `HTTP ${res.status}`);
      }
      const href = typeof data.static_href === 'string' ? data.static_href : '';
      setVideoBriefHref(href || null);
      if (href) {
        window.open(staticAssetUrl(href), '_blank', 'noopener,noreferrer');
      }
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setVideoBriefBusy(false);
    }
  };

  const handleGenerateRehearsalAudio = async () => {
    if (!executiveBriefing) {
      setError('Generate an executive briefing first (Path P talk track).');
      return;
    }
    const script = buildRehearsalFullScript(executiveBriefing, deckSlides).trim();
    if (!script) {
      setError('No talk-track script available for rehearsal audio.');
      return;
    }
    await requestBriefingPiperTts(script.slice(0, 8000), 'rehearsal-full');
  };

  const downloadKnowledgeGraphExport = async (fmt) => {
    const folder = projectFolder.trim();
    if (!folder) {
      setError('Set a project folder (RAG path) before exporting the knowledge graph.');
      return;
    }
    setKgExportBusy(fmt);
    setError(null);
    try {
      const q = new URLSearchParams({ folder, format: fmt });
      const res = await fetch(apiUrl(`/process/gtm/knowledge-graph/export?${q}`));
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          const j = await res.json();
          detail = formatApiDetail(j.detail) || detail;
        } catch {
          detail = (await res.text()) || detail;
        }
        throw new Error(detail);
      }
      const blob = await res.blob();
      const dispo = res.headers.get('Content-Disposition');
      let fname = fmt === 'jsonld' ? 'strategic_kg.jsonld' : 'strategic_kg.ttl';
      const m = dispo && /filename="?([^";]+)"?/i.exec(dispo);
      if (m) fname = m[1];
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fname;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setKgExportBusy(null);
    }
  };

  const handleSynthesizeSlide = async (slideIndex) => {
    const slide = deckSlides[slideIndex];
    const ip = slide?.image_prompt;
    if (!ip || String(ip).trim() === '') {
      setError('This slide has no image_prompt; add one in the draft or regenerate.');
      return;
    }
    setSynthBusy((b) => ({ ...b, [slideIndex]: true }));
    setError(null);
    try {
      const res = await fetch(apiUrl('/process/gtm/synthesize-image'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          slide_index: slideIndex,
          image_prompt: String(ip).trim(),
          width: 1280,
          height: 720,
        }),
      });
      let payload = null;
      const isJson = res.headers.get('content-type')?.includes('application/json');
      if (isJson) {
        payload = await res.json();
      } else {
        const textDetail = await res.text();
        payload = { detail: textDetail || `HTTP Error ${res.status}` };
      }
      if (!res.ok) {
        throw new Error(formatApiDetail(payload.detail));
      }
      setDeckSlides((prev) =>
        prev.map((s, i) =>
          i === slideIndex ? { ...s, image_path: payload.image_path } : s,
        ),
      );
      setHeroPreviewByIndex((p) => ({ ...p, [slideIndex]: payload.static_href }));
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setSynthBusy((b) => ({ ...b, [slideIndex]: false }));
    }
  };

  const handleRefineSlide = async (slideIndex) => {
    const instruction = (refineInputs[slideIndex] ?? '').trim();
    if (!instruction) {
      setError('Enter a refinement instruction (e.g. “Make this more aggressive”).');
      return;
    }
    const slide = deckSlides[slideIndex];
    if (!slide) return;
    const useWarRoom =
      !!strategySessionId.trim() &&
      warRoomLive &&
      warRoomWsRef.current?.readyState === WebSocket.OPEN;

    const releaseLock = () => {
      if (!useWarRoom) return;
      try {
        warRoomWsRef.current?.send(
          JSON.stringify({ type: 'slide_lock_release', slide_index: slideIndex }),
        );
      } catch (_) {
        /* ignore */
      }
    };

    setRefineBusy((b) => ({ ...b, [slideIndex]: true }));
    setError(null);
    try {
      if (useWarRoom) {
        await new Promise((resolve, reject) => {
          const request_id =
            typeof crypto !== 'undefined' && crypto.randomUUID
              ? crypto.randomUUID()
              : `${Date.now()}_${slideIndex}`;
          const t = setTimeout(() => {
            delete warRoomLockPendingRef.current[request_id];
            reject(new Error('Timed out acquiring slide lock'));
          }, 20000);
          warRoomLockPendingRef.current[request_id] = {
            resolve: () => {
              clearTimeout(t);
              resolve();
            },
            reject: (e) => {
              clearTimeout(t);
              reject(e);
            },
          };
          warRoomWsRef.current.send(
            JSON.stringify({
              type: 'slide_lock_acquire',
              slide_index: slideIndex,
              request_id,
            }),
          );
        });
      }

      const res = await fetch(apiUrl('/process/gtm/refine'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          slide,
          refinement_instruction: instruction,
          ...(useWarRoom
            ? {
                war_room: {
                  session_id: strategySessionId.trim(),
                  user_id: warRoomUserId,
                  slide_index: slideIndex,
                },
              }
            : {}),
        }),
      });
      let payload = null;
      const isJson = res.headers.get('content-type')?.includes('application/json');
      if (isJson) {
        payload = await res.json();
      } else {
        const textDetail = await res.text();
        payload = { detail: textDetail || `HTTP Error ${res.status}` };
      }
      if (!res.ok) {
        throw new Error(formatApiDetail(payload.detail));
      }
      setDeckSlides((prev) =>
        prev.map((s, i) => (i === slideIndex ? { ...payload.slide } : s)),
      );
      setRefineInputs((prev) => ({ ...prev, [slideIndex]: '' }));
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      releaseLock();
      setRefineBusy((b) => ({ ...b, [slideIndex]: false }));
    }
  };

  const handleRunQualityGate = async () => {
    if (!(deckSlides || []).length) return;
    setQualityGateBusy(true);
    setError(null);
    try {
      const res = await fetch(apiUrl('/process/gtm/strategic-judge'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_prompt: prompt,
          slides: deckSlides,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(formatApiDetail(data.detail) || `HTTP ${res.status}`);
      }
      setQualityGate({
        clarity: data.scores?.clarity,
        feasibility: data.scores?.feasibility,
        strategic_impact: data.scores?.strategic_impact,
        verdict: data.committee_verdict,
        rationale: data.auditor_rationale || '',
      });
      setQualityGateSig(JSON.stringify(deckSlides));
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setQualityGateBusy(false);
    }
  };

  const handleMaterialize = async () => {
    if (!qualityGatePassed) {
      setError('Run the Final Quality Gate (Executive Committee rubric) before materializing.');
      return;
    }
    setIsLoading(true);
    setError(null);
    setMaterializeStructural(null);
    try {
      const matRes = await fetch(apiUrl('/process/gtm/materialize'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          slides: deckSlides,
          template_path: deckTemplate,
          design_specs: deckDesignSpecs ?? undefined,
        }),
      });

      let matPayload = null;
      const matIsJson = matRes.headers.get('content-type')?.includes('application/json');
      if (matIsJson) {
        matPayload = await matRes.json();
      } else {
        const textDetail = await matRes.text();
        matPayload = { detail: textDetail || `HTTP Error ${matRes.status}` };
      }

      if (!matRes.ok) {
        throw new Error(formatApiDetail(matPayload.detail));
      }

      setResult(matPayload.pptx_path);
      setFinancialAppendixPath(matPayload.financial_appendix_path ?? null);
      setMaterializeStructural(matPayload.structural_telemetry ?? null);
      setPhase('done');
    } catch (err) {
      const isNetwork =
        err instanceof TypeError &&
        (err.message === 'Failed to fetch' || err.message.includes('fetch'));
      setError(
        isNetwork
          ? 'Failed to reach the API during materialize.'
          : err.message || String(err),
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleMicrositeExport = async () => {
    if (!qualityGatePassed) {
      setError('Run the Final Quality Gate (Path V) before exporting the HTML microsite.');
      return;
    }
    if (!(deckSlides || []).length) return;
    setMicrositeBusy(true);
    setError(null);
    try {
      const res = await fetch(apiUrl('/process/gtm/materialize-microsite'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          slides: deckSlides,
          page_title: 'Executive briefing',
          subtitle: '',
          user_prompt: prompt,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(formatApiDetail(data.detail) || `HTTP ${res.status}`);
      }
      const href = typeof data.static_href === 'string' ? data.static_href : '';
      setMicrositeHref(href);
      if (href) {
        window.open(staticAssetUrl(href), '_blank', 'noopener,noreferrer');
      }
    } catch (err) {
      const isNetwork =
        err instanceof TypeError &&
        (err.message === 'Failed to fetch' || err.message.includes('fetch'));
      setError(
        isNetwork
          ? 'Failed to reach the API during microsite export.'
          : err.message || String(err),
      );
    } finally {
      setMicrositeBusy(false);
    }
  };

  const handleDownload = async () => {
    if (!result) return;
    try {
      const fileName = result.split('/').pop();
      const downloadUrl = apiUrl(`/static/outputs/${fileName}`);

      const response = await fetch(downloadUrl);
      if (!response.ok) {
        throw new Error(`The file exists at ${result}, but the web server isn't serving it at ${downloadUrl} yet.`);
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      if (Array.isArray(deckSlides) && deckSlides.length > 0) {
        fetch(apiUrl('/process/gtm/memory/record-success'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_prompt: prompt,
            persona,
            slides: deckSlides,
            design_specs: deckDesignSpecs,
          }),
        }).catch(() => {});
      }
    } catch (err) {
      console.warn('Direct download failed:', err.message);
      setError(`Download failed: ${err.message} You can still find it in your project's 'assets/outputs' folder.`);
    }
  };

  const handleDownloadFinancialAppendix = async () => {
    if (!financialAppendixPath) return;
    try {
      const fileName = financialAppendixPath.split('/').pop();
      const downloadUrl = apiUrl(`/static/outputs/${fileName}`);
      const response = await fetch(downloadUrl);
      if (!response.ok) {
        throw new Error(
          `Workbook path ${financialAppendixPath} is not served at ${downloadUrl} yet.`,
        );
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fileName || 'financial_appendix.xlsx';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.warn('Financial appendix download failed:', err.message);
      setError(
        `Financial appendix download failed: ${err.message} Check assets/outputs on the server.`,
      );
    }
  };

  const handleCopy = async () => {
    if (!result) return;
    try {
      const textArea = document.createElement("textarea");
      textArea.value = result;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
    } catch (err) {
      console.warn("Clipboard write failed:", err);
    }
  };

  const updateMatrixScore = (pathKey, rowId, raw) => {
    const n = Math.max(1, Math.min(10, Number(raw) || 1));
    setDecisionMatrixScores((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        [pathKey]: { ...prev[pathKey], [rowId]: n },
      };
    });
  };

  const totalA = decisionMatrixScores ? matrixPathTotal(decisionMatrixScores, 'pathA') : 0;
  const totalB = decisionMatrixScores ? matrixPathTotal(decisionMatrixScores, 'pathB') : 0;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-8 font-mono selection:bg-blue-500/30">
      <div className={`mx-auto space-y-8 ${wideLayout ? 'max-w-[min(96rem,calc(100vw-4rem))]' : 'max-w-4xl'}`}>
        <header className="border-b border-slate-800 pb-6 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-4xl font-extrabold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-emerald-400 font-sans text-left">
              ReluLayer Engine
            </h1>
            <p className="text-slate-400 mt-2 text-sm text-left">Layer 7: Glass-Box Orchestration</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div
              className="flex rounded-lg border border-slate-700 bg-slate-900/90 p-0.5 font-sans"
              role="group"
              aria-label="Dashboard mode"
            >
              <button
                type="button"
                disabled={phase !== 'form' && phase !== 'sandbox_review'}
                onClick={() => {
                  setDashboardMode('standard');
                  if (phase === 'sandbox_review') {
                    setPhase('form');
                    setSandboxDraftA(null);
                    setSandboxDraftB(null);
                  }
                }}
                className={`rounded-md px-3 py-1.5 text-xs font-bold uppercase tracking-wider transition-colors ${
                  dashboardMode === 'standard'
                    ? 'bg-slate-700 text-white'
                    : 'text-slate-500 hover:text-slate-300'
                } disabled:opacity-40`}
              >
                Standard
              </button>
              <button
                type="button"
                disabled={phase !== 'form' && phase !== 'sandbox_review'}
                onClick={() => setDashboardMode('sandbox')}
                className={`rounded-md px-3 py-1.5 text-xs font-bold uppercase tracking-wider transition-colors ${
                  dashboardMode === 'sandbox'
                    ? 'bg-indigo-700 text-white'
                    : 'text-slate-500 hover:text-slate-300'
                } disabled:opacity-40`}
              >
                Strategic Sandbox
              </button>
            </div>
            <div
              className="flex items-center space-x-2 bg-slate-900 px-3 py-1.5 rounded-full border border-slate-700 max-w-[14rem] sm:max-w-md cursor-default"
              title={systemHealthSummary.title}
              role="status"
              aria-live="polite"
            >
              <div
                className={`w-2.5 h-2.5 rounded-full shrink-0 ${systemHealthSummary.dot} ${
                  systemHealth?.status === 'healthy' ? 'animate-pulse' : ''
                }`}
              />
              <span className="text-xs text-slate-300 truncate font-sans">
                {systemHealthSummary.label}
              </span>
            </div>
          </div>
        </header>

        {phase === 'form' ? (
          <div className="bg-slate-900 p-8 rounded-2xl border border-slate-800 shadow-2xl space-y-6 relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-500 via-indigo-500 to-emerald-500 opacity-50"></div>
            {dashboardMode === 'sandbox' && (
              <div className="rounded-xl border border-indigo-800/50 bg-indigo-950/25 p-4 text-left">
                <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-indigo-400 font-sans">
                  Path O — Strategic Sandbox
                </div>
                <p className="mt-2 text-xs text-slate-400 font-sans leading-relaxed">
                  Run two drafts with the same RAG context and directive, compare outcomes side-by-side, then score them in the Decision Matrix overlay before you commit one path to slide review and materialization.
                </p>
              </div>
            )}
            {dashboardMode === 'standard' ? (
            <div className="text-left">
              <label
                htmlFor="strategic-persona"
                className="block text-sm font-semibold text-slate-300 mb-2 uppercase tracking-wider font-sans"
              >
                Strategic Persona
              </label>
              <select
                id="strategic-persona"
                value={persona}
                onChange={(e) => setPersona(e.target.value)}
                disabled={isLoading}
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/50 font-mono"
              >
                {STRATEGIC_PERSONAS.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
              <p className="mt-1.5 text-xs text-slate-500 font-sans">
                Selects the DSPy signature (VC pitch, GovTech, or risk audit) for the draft stage.
              </p>
              <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-xl border border-slate-800 bg-slate-950/80 px-4 py-3 font-sans">
                <input
                  type="checkbox"
                  checked={selfCorrection}
                  onChange={(e) => setSelfCorrection(e.target.checked)}
                  disabled={isLoading}
                  className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-900 text-violet-500 focus:ring-violet-500/40"
                />
                <span>
                  <span className="block text-sm font-semibold text-slate-200">
                    Path Y — Self-correction (pre-polish)
                  </span>
                  <span className="mt-1 block text-xs text-slate-500 leading-relaxed">
                    After the draft, run the Strategic Judge (Path V). If the verdict is{' '}
                    <span className="text-slate-400">revise</span> and any rubric score is below 7, the engine runs one
                    autonomous refine pass on the highest-impact slides using the judge&apos;s rationale, then returns
                    the updated deck (before Red Team audit).
                  </span>
                </span>
              </label>
              <label className="mt-3 flex cursor-pointer items-start gap-3 rounded-xl border border-slate-800 bg-slate-950/80 px-4 py-3 font-sans">
                <input
                  type="checkbox"
                  checked={wargameDebate}
                  onChange={(e) => setWargameDebate(e.target.checked)}
                  disabled={isLoading}
                  className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-900 text-orange-500 focus:ring-orange-500/40"
                />
                <span>
                  <span className="block text-sm font-semibold text-slate-200">
                    Path BB — Wargame debate (post–Red Team)
                  </span>
                  <span className="mt-1 block text-xs text-slate-500 leading-relaxed">
                    After the Red Team pass, run three Adversary vs Proponent rounds on the consensus deck, then summarize
                    residual strategic risks. Results appear under Telemetry → Wargame Audit.
                  </span>
                </span>
              </label>
              <div className="mt-3 rounded-xl border border-slate-800 bg-slate-950/80 px-4 py-3 font-sans space-y-2">
                <label className="flex cursor-pointer items-start gap-3">
                  <input
                    type="checkbox"
                    checked={compliancePass}
                    onChange={(e) => setCompliancePass(e.target.checked)}
                    disabled={isLoading}
                    className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-900 text-sky-500 focus:ring-sky-500/40"
                  />
                  <span>
                    <span className="block text-sm font-semibold text-slate-200">
                      Path II — Compliance pass (benchmarking)
                    </span>
                    <span className="mt-1 block text-xs text-slate-500 leading-relaxed">
                      Scores the deck against a chosen standard (NIST/ISO/ESG) and suggests corrective copy by slide.
                      Results appear under Telemetry → Compliance Pass.
                    </span>
                  </span>
                </label>
                <div className="flex flex-wrap items-center gap-2 pl-7">
                  <span className="text-[10px] uppercase tracking-widest text-slate-500 font-bold">Standard</span>
                  <input
                    type="text"
                    value={complianceStandard}
                    onChange={(e) => setComplianceStandard(e.target.value)}
                    disabled={isLoading || !compliancePass}
                    placeholder="e.g. NIST CSF, ISO 27001, ESG"
                    className="flex-1 min-w-[14rem] rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 outline-none focus:border-sky-600/60 font-mono disabled:opacity-50"
                  />
                </div>
              </div>
              <label className="mt-3 flex cursor-pointer items-start gap-3 rounded-xl border border-slate-800 bg-slate-950/80 px-4 py-3 font-sans">
                <input
                  type="checkbox"
                  checked={liveDraftStream}
                  onChange={(e) => setLiveDraftStream(e.target.checked)}
                  disabled={isLoading}
                  className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-900 text-fuchsia-500 focus:ring-fuchsia-500/40"
                />
                <span>
                  <span className="block text-sm font-semibold text-slate-200">
                    Path DD — Live Thinking (WebSocket stream)
                  </span>
                  <span className="mt-1 block text-xs text-slate-500 leading-relaxed">
                    Uses <span className="text-slate-400">/ws/process/gtm/draft</span> instead of HTTP: rationales and
                    agent steps appear below as VC, GovTech, Risk, synthesis, judge, and Red Team run. Best with{' '}
                    <span className="text-slate-400">Consensus</span> persona to see collaboration.
                  </span>
                </span>
              </label>
            </div>
            ) : (
            <div className="grid gap-6 md:grid-cols-2 text-left">
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 space-y-3">
                <div className="text-[10px] font-bold uppercase tracking-widest text-cyan-500/90 font-sans">
                  Path A
                </div>
                <label htmlFor="sandbox-label-a" className="block text-xs font-semibold text-slate-400 font-sans">
                  Label
                </label>
                <input
                  id="sandbox-label-a"
                  type="text"
                  value={sandboxLabelA}
                  onChange={(e) => setSandboxLabelA(e.target.value)}
                  disabled={sandboxGenerating}
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-600/60 font-mono"
                />
                <label htmlFor="sandbox-persona-a" className="block text-xs font-semibold text-slate-400 font-sans">
                  Persona
                </label>
                <select
                  id="sandbox-persona-a"
                  value={sandboxPersonaA}
                  onChange={(e) => setSandboxPersonaA(e.target.value)}
                  disabled={sandboxGenerating}
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-600/60 font-mono"
                >
                  {STRATEGIC_PERSONAS.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 space-y-3">
                <div className="text-[10px] font-bold uppercase tracking-widest text-amber-500/90 font-sans">
                  Path B
                </div>
                <label htmlFor="sandbox-label-b" className="block text-xs font-semibold text-slate-400 font-sans">
                  Label
                </label>
                <input
                  id="sandbox-label-b"
                  type="text"
                  value={sandboxLabelB}
                  onChange={(e) => setSandboxLabelB(e.target.value)}
                  disabled={sandboxGenerating}
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-amber-600/60 font-mono"
                />
                <label htmlFor="sandbox-persona-b" className="block text-xs font-semibold text-slate-400 font-sans">
                  Persona
                </label>
                <select
                  id="sandbox-persona-b"
                  value={sandboxPersonaB}
                  onChange={(e) => setSandboxPersonaB(e.target.value)}
                  disabled={sandboxGenerating}
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-amber-600/60 font-mono"
                >
                  {STRATEGIC_PERSONAS.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            )}
            <div className="text-left">
              <label className="block text-sm font-semibold text-slate-300 mb-2 uppercase tracking-wider font-sans">Strategic Directive</label>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                className="w-full h-32 bg-slate-950 border border-slate-700 rounded-xl p-4 text-slate-100 placeholder-slate-600 focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 outline-none transition-all resize-none"
                placeholder="Describe the presentation you want to generate..."
              />
            </div>
            <div className="text-left">
              <label className="block text-sm font-semibold text-slate-300 mb-2 uppercase tracking-wider font-sans">Repo-Relative Path</label>
              <div className="flex bg-slate-950 border border-slate-700 rounded-xl focus-within:ring-2 focus-within:ring-blue-500/50 focus-within:border-blue-500 transition-all overflow-hidden">
                <span className="flex items-center px-4 bg-slate-800 text-slate-400 text-sm border-r border-slate-700">/app/</span>
                <input
                  type="text"
                  value={filePath}
                  onChange={(e) => setFilePath(e.target.value)}
                  className="w-full bg-transparent p-4 text-slate-100 outline-none text-sm"
                />
              </div>
              <p className="mt-1.5 text-xs text-slate-500 font-sans">
                PPTX template, data files, or a PNG/JPG/WebP path — vision models describe images for slide structure (Ollama{' '}
                <code className="text-slate-400">RELULAYER_VISION_MODEL</code>).
              </p>
            </div>
            <div className="text-left">
              <label
                htmlFor="project-folder-rag"
                className="block text-sm font-semibold text-slate-300 mb-2 uppercase tracking-wider font-sans"
              >
                Project folder (RAG)
              </label>
              <div className="flex bg-slate-950 border border-slate-700 rounded-xl focus-within:ring-2 focus-within:ring-indigo-500/50 focus-within:border-indigo-500/60 transition-all overflow-hidden">
                <span className="flex items-center px-4 bg-slate-800 text-slate-400 text-sm border-r border-slate-700">/app/</span>
                <input
                  id="project-folder-rag"
                  type="text"
                  value={projectFolder}
                  onChange={(e) => setProjectFolder(e.target.value)}
                  disabled={isLoading}
                  placeholder="e.g. assets — leave empty to skip"
                  className="w-full bg-transparent p-4 text-slate-100 outline-none text-sm placeholder-slate-600"
                />
              </div>
              <p className="mt-1.5 text-xs text-slate-500 font-sans">
                Recursively scans supported files; ranks top 5 snippets vs your Strategic Directive (Ollama{' '}
                <code className="text-indigo-400/90">nomic-embed-text</code>
                {' '}or lexical fallback). Stays inside the repo root.
              </p>
            </div>
            {dashboardMode === 'standard' && (liveDraftStream || liveThinkingFeed.length > 0) && (
              <div className="rounded-xl border border-fuchsia-800/45 bg-fuchsia-950/15 p-4 text-left">
                <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                  <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-fuchsia-400/95 font-sans">
                    Live Thinking — Path DD
                  </div>
                  {isLoading && liveDraftStream && (
                    <span className="text-[10px] font-mono text-fuchsia-300/90 animate-pulse">Streaming telemetry…</span>
                  )}
                </div>
                <div className="max-h-72 overflow-y-auto space-y-2.5">
                  {liveThinkingFeed.length === 0 && isLoading && liveDraftStream && (
                    <p className="text-xs text-slate-500 font-mono">Connecting… waiting for first agent event.</p>
                  )}
                  {liveThinkingFeed.map((ev) => {
                    const accent =
                      ev.agent === 'venture_capital'
                        ? 'border-amber-800/50 bg-amber-950/25'
                        : ev.agent === 'govtech'
                          ? 'border-cyan-800/50 bg-cyan-950/20'
                          : ev.agent === 'risk_auditor'
                            ? 'border-rose-800/50 bg-rose-950/20'
                            : ev.agent === 'strategy_synthesis'
                              ? 'border-violet-800/50 bg-violet-950/25'
                              : ev.agent === 'strategic_judge'
                                ? 'border-emerald-800/50 bg-emerald-950/20'
                                : ev.agent === 'red_team'
                                  ? 'border-orange-800/50 bg-orange-950/20'
                                  : ev.agent === 'wargame'
                                    ? 'border-orange-900/40 bg-orange-950/15'
                                    : 'border-slate-700/80 bg-slate-950/50';
                    return (
                      <div
                        key={ev._id}
                        className={`rounded-lg border px-3 py-2 text-left ${accent}`}
                      >
                        <div className="flex flex-wrap items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-slate-400 font-sans">
                          <span className="text-fuchsia-400/90">{ev.type?.replace(/_/g, ' ')}</span>
                          {ev.label && <span className="text-slate-300">{ev.label}</span>}
                          {ev.phase && <span className="font-mono text-slate-500 normal-case">{ev.phase}</span>}
                        </div>
                        {ev.message && (
                          <p className="mt-1 text-[11px] text-slate-400 font-sans leading-snug">{ev.message}</p>
                        )}
                        {ev.context_chars != null && (
                          <p className="mt-0.5 text-[10px] font-mono text-slate-600">
                            Context chars: {ev.context_chars}
                          </p>
                        )}
                        {ev.verdict && (
                          <p className="mt-1 text-[11px] text-emerald-300/90 font-mono">
                            Verdict: {ev.verdict}
                            {ev.rubric && (
                              <span className="text-slate-500">
                                {' '}
                                · clarity {ev.rubric.clarity ?? '—'} · feasibility {ev.rubric.feasibility ?? '—'} · impact{' '}
                                {ev.rubric.strategic_impact ?? '—'}
                              </span>
                            )}
                          </p>
                        )}
                        {ev.rationale && (
                          <p className="mt-1.5 text-[11px] text-slate-300/95 whitespace-pre-wrap break-words leading-relaxed">
                            {ev.rationale}
                          </p>
                        )}
                        {ev.critique && (
                          <p className="mt-1 text-[11px] text-amber-200/85 whitespace-pre-wrap break-words">
                            <span className="text-amber-500/90 font-semibold">Critique: </span>
                            {ev.critique}
                          </p>
                        )}
                        {ev.completion_excerpt && (
                          <details className="mt-1.5 text-[10px] text-slate-500">
                            <summary className="cursor-pointer text-slate-500 hover:text-slate-400">
                              Raw completion excerpt
                            </summary>
                            <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap break-words text-slate-500">
                              {ev.completion_excerpt}
                            </pre>
                          </details>
                        )}
                        {ev.deck_json_chars != null && (
                          <p className="mt-1 text-[10px] font-mono text-slate-600">
                            Sub-draft JSON: {ev.deck_json_chars} chars
                          </p>
                        )}
                        {ev.red_team_alert != null && (
                          <p className="mt-1 text-[10px] font-mono text-orange-300/90">
                            Red team alert: {String(ev.red_team_alert)} · risks: {ev.risk_count ?? '—'}
                          </p>
                        )}
                        {ev.residual_headline && (
                          <p className="mt-1 text-[11px] text-orange-200/90">{ev.residual_headline}</p>
                        )}
                        {ev.error && (
                          <p className="mt-1 text-[11px] text-rose-400">{ev.message || 'Agent error'}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            {dashboardMode === 'standard' ? (
            <button
              onClick={handleDraftOnly}
              disabled={isLoading}
              className={`w-full py-4 rounded-xl font-bold text-lg tracking-wide transition-all duration-300 flex items-center justify-center space-x-3 font-sans
                ${isLoading 
                  ? 'bg-blue-900/50 text-blue-300 cursor-not-allowed border border-blue-700/50' 
                  : 'bg-blue-600 hover:bg-blue-500 text-white shadow-[0_0_20px_rgba(37,99,235,0.3)] hover:shadow-[0_0_25px_rgba(59,130,246,0.5)] border border-blue-500'}`}
            >
              {isLoading ? (
                <>
                  <svg className="animate-spin h-5 w-5 text-blue-300" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span>Drafting...</span>
                </>
              ) : (
                <span>Draft deck (Layer 3–4)</span>
              )}
            </button>
            ) : (
            <button
              type="button"
              onClick={handleSandboxGenerateBoth}
              disabled={sandboxGenerating}
              className={`w-full py-4 rounded-xl font-bold text-lg tracking-wide transition-all duration-300 flex items-center justify-center space-x-3 font-sans border
                ${sandboxGenerating
                  ? 'bg-indigo-950/80 text-indigo-300 cursor-not-allowed border-indigo-800/60'
                  : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-[0_0_20px_rgba(79,70,229,0.25)] border-indigo-500'}`}
            >
              {sandboxGenerating ? (
                <>
                  <svg className="animate-spin h-5 w-5 text-indigo-300" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span>Running path A → path B (sequential)…</span>
                </>
              ) : (
                <span>Generate both strategic paths</span>
              )}
            </button>
            )}
          </div>
        ) : phase === 'sandbox_review' ? (
          <div className="space-y-6 text-left">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold text-slate-100 font-sans">Strategic Sandbox — compare</h2>
                <p className="text-xs text-slate-500 font-mono mt-1">
                  Same directive and RAG inputs; two persona passes. Open the Decision Matrix to score, then adopt one path for heroes and materialization.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={openDecisionMatrix}
                  className="rounded-lg border border-indigo-600/70 bg-indigo-950/50 px-4 py-2 text-xs font-bold uppercase tracking-wider text-indigo-200 hover:bg-indigo-900/50 font-sans"
                >
                  Decision Matrix
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setPhase('form');
                    setSandboxDraftA(null);
                    setSandboxDraftB(null);
                    setDecisionMatrixScores(null);
                    setDecisionMatrixOpen(false);
                  }}
                  className="rounded-lg border border-slate-600 px-4 py-2 text-xs text-slate-300 hover:bg-slate-800 font-sans"
                >
                  Back to inputs
                </button>
              </div>
            </div>
            <div className="rounded-xl border border-sky-800/60 bg-sky-950/20 p-4 space-y-3">
              <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-sky-400 font-sans">
                Path U — War Room (WebSocket)
              </div>
              <p className="text-xs text-slate-500 font-mono">
                Create a strategy session, enable live sync, then open the same session ID in another browser. Sandbox state persists through the socket; after you adopt a path, deck edits sync in real time.
              </p>
              <div className="flex flex-wrap gap-2 items-end">
                <label className="flex flex-col gap-1 text-[10px] text-slate-500 font-mono">
                  Session UUID
                  <input
                    type="text"
                    value={strategySessionId}
                    onChange={(e) => setStrategySessionId(e.target.value.trim())}
                    placeholder="Paste existing session id…"
                    className="w-64 max-w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-200 font-mono"
                  />
                </label>
                <label className="flex flex-col gap-1 text-[10px] text-slate-500 font-mono">
                  Display name
                  <input
                    type="text"
                    value={warRoomDisplayName}
                    onChange={(e) => setWarRoomDisplayName(e.target.value)}
                    className="w-40 rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-200 font-mono"
                  />
                </label>
                <button
                  type="button"
                  onClick={handleCreateStrategySession}
                  disabled={warRoomSessionSaving}
                  className="rounded-lg border border-sky-600/70 bg-sky-900/40 px-3 py-2 text-xs font-bold text-sky-200 hover:bg-sky-900/60 font-sans disabled:opacity-50"
                >
                  {warRoomSessionSaving ? 'Saving…' : 'Create session from sandbox'}
                </button>
                <label className="flex items-center gap-2 text-xs text-slate-400 font-sans cursor-pointer">
                  <input
                    type="checkbox"
                    checked={warRoomLive}
                    onChange={(e) => setWarRoomLive(e.target.checked)}
                    disabled={!strategySessionId.trim()}
                    className="rounded border-slate-600"
                  />
                  Live socket
                </label>
              </div>
              <div className="text-[10px] text-slate-600 font-mono">
                Strategist id (this browser): <span className="text-slate-400">{warRoomUserId}</span>
                {' · '}
                {warRoomConnId ? (
                  <span className="text-emerald-500/90">connected</span>
                ) : strategySessionId.trim() && warRoomLive ? (
                  <span className="text-amber-500/90">connecting…</span>
                ) : (
                  <span className="text-slate-600">offline</span>
                )}
              </div>
              {warRoomPresence.length > 0 && (
                <div className="text-[10px] text-slate-500 font-mono">
                  In room:{' '}
                  {warRoomPresence.map((u) => u.display_name || u.user_id).join(', ')}
                </div>
              )}
              {strategySessionId.trim() && <DriftTimelinePanel entries={driftHistory} />}
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              {[
                {
                  key: 'a',
                  label: sandboxLabelA || 'Path A',
                  draft: sandboxDraftA,
                  accent: 'border-cyan-900/60 bg-cyan-950/15',
                  bar: 'from-cyan-600/80 to-cyan-500/20',
                },
                {
                  key: 'b',
                  label: sandboxLabelB || 'Path B',
                  draft: sandboxDraftB,
                  accent: 'border-amber-900/60 bg-amber-950/15',
                  bar: 'from-amber-600/80 to-amber-500/20',
                },
              ].map((col) => (
                <div
                  key={col.key}
                  className={`rounded-2xl border p-5 space-y-4 ${col.accent}`}
                >
                  <div className={`h-1 w-full rounded-full bg-gradient-to-r ${col.bar}`} />
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <h3 className="text-base font-bold text-slate-100 font-sans">{col.label}</h3>
                    {col.draft?.ok === false && (
                      <span className="rounded bg-rose-950/80 px-2 py-0.5 text-[10px] font-bold uppercase text-rose-300 font-mono">
                        Failed
                      </span>
                    )}
                    {col.draft?.ok && col.draft.telemetry?.audit_report?.red_team_alert && (
                      <span className="rounded bg-rose-900/50 px-2 py-0.5 text-[10px] font-bold uppercase text-rose-200 font-mono">
                        Red team alert
                      </span>
                    )}
                    {col.draft?.ok && col.draft.telemetry?.wargame_audit?.wargame_alert && (
                      <span className="rounded bg-orange-950/80 px-2 py-0.5 text-[10px] font-bold uppercase text-orange-200 font-mono">
                        Wargame alert
                      </span>
                    )}
                  </div>
                  {col.draft?.ok === false && (
                    <p className="text-xs text-rose-300/95 font-mono">{col.draft.errorMessage}</p>
                  )}
                  {col.draft?.ok && (
                    <>
                      <p className="text-xs text-slate-500 font-mono">
                        {STRATEGIC_PERSONAS.find((p) => p.id === col.draft.persona)?.label || col.draft.persona} ·{' '}
                        {col.draft.slides.length} slide{col.draft.slides.length === 1 ? '' : 's'}
                      </p>
                      <ul className="max-h-52 space-y-2 overflow-y-auto border border-slate-800/80 rounded-lg bg-slate-950/40 p-3 list-none">
                        {col.draft.slides.map((s, i) => (
                          <li key={i} className="text-xs text-slate-300 font-sans border-b border-slate-800/60 pb-2 last:border-0 last:pb-0">
                            <span className="font-mono text-[10px] text-slate-600">{i + 1}.</span>{' '}
                            {s?.title || '(no title)'}
                          </li>
                        ))}
                      </ul>
                      <button
                        type="button"
                        onClick={() => adoptSandboxPath(col.key)}
                        className="w-full py-2.5 rounded-lg bg-emerald-700 hover:bg-emerald-600 text-white text-sm font-bold font-sans"
                      >
                        Use this path → slide review
                      </button>
                    </>
                  )}
                </div>
              ))}
            </div>
          </div>
        ) : phase === 'review' ? (
          <div className="space-y-6 text-left">
            {telemetry?.audit_report?.red_team_alert && (
              <div
                role="alert"
                className="rounded-xl border-2 border-rose-600/80 bg-rose-950/45 p-4 shadow-[0_0_24px_rgba(225,29,72,0.12)]"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-rose-600/30 text-lg" aria-hidden>
                      ⚠
                    </span>
                    <div>
                      <h3 className="text-sm font-bold uppercase tracking-wider text-rose-300 font-sans">
                        Red Team Alert
                      </h3>
                      <p className="mt-1 text-xs text-rose-200/90 font-sans">
                        The autonomous auditor flagged material logic gaps or strategic risks before human review. Inspect slides and telemetry before materializing.
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setTelemetryTab('redteam');
                      setTelemetryOpen(true);
                    }}
                    className="shrink-0 rounded-lg border border-rose-500/60 bg-rose-900/40 px-3 py-1.5 text-xs font-bold text-rose-200 hover:bg-rose-900/70 font-mono"
                  >
                    Open Red Team Audit
                  </button>
                </div>
                {Array.isArray(telemetry.audit_report.weak_points) && telemetry.audit_report.weak_points.length > 0 && (
                  <ul className="mt-3 space-y-2 border-t border-rose-800/50 pt-3 text-xs text-rose-100/95 font-sans list-none">
                    {telemetry.audit_report.weak_points.map((w, i) => (
                      <li key={i} className="flex gap-2">
                        <span
                          className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase font-mono ${
                            w.severity === 'high'
                              ? 'bg-rose-600/50 text-white'
                              : w.severity === 'medium'
                                ? 'bg-amber-600/40 text-amber-100'
                                : 'bg-slate-600/50 text-slate-200'
                          }`}
                        >
                          {w.severity || 'medium'}
                        </span>
                        <span>{w.point}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            {telemetry?.audit_report &&
              !telemetry.audit_report.red_team_alert &&
              Array.isArray(telemetry.audit_report.weak_points) &&
              telemetry.audit_report.weak_points.length > 0 && (
                <div className="rounded-xl border border-amber-700/45 bg-amber-950/20 p-4">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-amber-400/90 font-sans">
                    Red Team — advisory
                  </h3>
                  <p className="mt-1 text-xs text-amber-200/80 font-sans">
                    Minor findings only; no critical alert threshold met.
                  </p>
                  <ul className="mt-2 space-y-1.5 text-xs text-amber-100/90 font-sans list-none">
                    {telemetry.audit_report.weak_points.map((w, i) => (
                      <li key={i} className="flex gap-2">
                        <span className="shrink-0 font-mono text-[10px] text-amber-500/90">{w.severity}</span>
                        <span>{w.point}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            {telemetry?.wargame_audit?.wargame_alert && (
              <div
                role="alert"
                className="rounded-xl border-2 border-orange-700/70 bg-orange-950/35 p-4 shadow-[0_0_20px_rgba(234,88,12,0.1)]"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-orange-600/25 text-lg" aria-hidden>
                      ⚔
                    </span>
                    <div>
                      <h3 className="text-sm font-bold uppercase tracking-wider text-orange-300 font-sans">
                        Wargame — residual risk alert
                      </h3>
                      <p className="mt-1 text-xs text-orange-100/85 font-sans">
                        The adversarial debate left material residual risks (same severity heuristic as Red Team). Review
                        mitigations and residual list before committing.
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setTelemetryTab('wargame');
                      setTelemetryOpen(true);
                    }}
                    className="shrink-0 rounded-lg border border-orange-500/50 bg-orange-900/40 px-3 py-1.5 text-xs font-bold text-orange-200 hover:bg-orange-900/65 font-mono"
                  >
                    Open Wargame Audit
                  </button>
                </div>
              </div>
            )}
            <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3 flex flex-wrap gap-3 items-center text-xs font-mono">
              <span className="text-slate-500 uppercase text-[10px] tracking-wider shrink-0">War room</span>
              <input
                type="text"
                value={strategySessionId}
                onChange={(e) => setStrategySessionId(e.target.value.trim())}
                placeholder="Strategy session UUID"
                className="flex-1 min-w-[10rem] max-w-md rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-[11px] text-slate-200"
              />
              <label className="flex items-center gap-1.5 text-slate-400 font-sans shrink-0 cursor-pointer">
                <input
                  type="checkbox"
                  checked={warRoomLive}
                  onChange={(e) => setWarRoomLive(e.target.checked)}
                  disabled={!strategySessionId.trim()}
                  className="rounded border-slate-600"
                />
                Live
              </label>
              <span className="text-[10px] text-slate-600 shrink-0">
                {warRoomConnId ? (
                  <span className="text-emerald-500/90">socket on</span>
                ) : strategySessionId.trim() && warRoomLive ? (
                  <span className="text-amber-500/90">connecting…</span>
                ) : (
                  'off'
                )}
              </span>
              {warRoomPresence.length > 0 && (
                <span className="text-[10px] text-slate-500 truncate max-w-[14rem]">
                  {warRoomPresence.map((u) => u.display_name || u.user_id).join(', ')}
                </span>
              )}
            </div>
            {strategySessionId.trim() && <DriftTimelinePanel entries={driftHistory} />}
            <div className="flex flex-wrap gap-2 rounded-xl border border-slate-800 bg-slate-900/90 p-1.5 font-sans">
              <button
                type="button"
                onClick={() => setReviewViewTab('slides')}
                className={`rounded-lg px-4 py-2 text-xs font-bold uppercase tracking-wider transition-colors ${
                  reviewViewTab === 'slides'
                    ? 'bg-slate-700 text-white'
                    : 'text-slate-500 hover:bg-slate-800 hover:text-slate-300'
                }`}
              >
                Slide build
              </button>
              <button
                type="button"
                onClick={() => setReviewViewTab('speaker_notes')}
                className={`rounded-lg px-4 py-2 text-xs font-bold uppercase tracking-wider transition-colors ${
                  reviewViewTab === 'speaker_notes'
                    ? 'bg-teal-800 text-teal-100'
                    : 'text-slate-500 hover:bg-slate-800 hover:text-slate-300'
                }`}
              >
                Speaker notes
              </button>
            </div>
            <audio ref={briefingAudioRef} className="hidden" preload="none" />

            {reviewViewTab === 'slides' && (
            <>
            <div className="bg-slate-900 p-6 rounded-2xl border border-slate-800 space-y-4">
              <h2 className="text-lg font-bold text-slate-200 font-sans">Slide review — GPU heroes</h2>
              <p className="text-xs text-slate-500 font-mono">
                Generate 1280×720 images per slide (RTX / A1111 / diffusers). Set RELULAYER_IMAGE_BACKEND on the server. Slides without a generated image get a text placeholder at materialize.
              </p>
              <div>
                <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1 font-sans">Template path</label>
                <input
                  type="text"
                  value={deckTemplate}
                  onChange={(e) => setDeckTemplate(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 font-mono"
                />
              </div>
              <div className="rounded-xl border border-violet-800/50 bg-violet-950/25 p-4 space-y-4">
                <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-violet-300 font-sans">
                  Path V — Final Quality Gate
                </div>
                <p className="text-xs text-slate-500 font-mono leading-relaxed">
                  An independent LM auditor scores this deck vs an Executive Committee rubric:{' '}
                  <span className="text-slate-400">Clarity</span>,{' '}
                  <span className="text-slate-400">Feasibility</span>, and{' '}
                  <span className="text-slate-400">Strategic Impact</span> (1–10 each). Assembly stays
                  locked until you run a fresh audit for the current slide JSON.
                </p>
                <button
                  type="button"
                  onClick={handleRunQualityGate}
                  disabled={qualityGateBusy || !deckSlides.length}
                  className={`w-full sm:w-auto px-4 py-2.5 rounded-lg text-xs font-bold font-sans border transition-colors ${
                    qualityGateBusy
                      ? 'border-violet-900/60 bg-violet-950/50 text-violet-500 cursor-wait'
                      : 'border-violet-600/70 bg-violet-900/40 text-violet-100 hover:bg-violet-900/65'
                  } disabled:opacity-50`}
                >
                  {qualityGateBusy ? 'Executive Committee auditing…' : 'Run Executive Committee audit'}
                </button>
                {qualityGate && qualityGateSig !== currentDeckSig && (
                  <p className="text-xs text-amber-400/95 font-sans">
                    Deck changed since the last audit — run the gate again to enable Assemble PPTX.
                  </p>
                )}
                {qualityGate && qualityGateSig === currentDeckSig && (
                  <div className="space-y-3 border-t border-violet-900/40 pt-3">
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      {[
                        { k: 'clarity', label: 'Clarity' },
                        { k: 'feasibility', label: 'Feasibility' },
                        { k: 'strategic_impact', label: 'Strategic impact' },
                      ].map(({ k, label }) => (
                        <div
                          key={k}
                          className="rounded-lg border border-slate-700/80 bg-slate-950/80 px-3 py-2 text-center"
                        >
                          <div className="text-[10px] uppercase tracking-wider text-slate-500 font-mono">
                            {label}
                          </div>
                          <div className="text-2xl font-bold text-violet-200 font-sans tabular-nums">
                            {qualityGate[k] ?? '—'}
                            <span className="text-sm text-slate-500 font-mono">/10</span>
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[10px] uppercase tracking-wider text-slate-500 font-mono">
                        Committee verdict
                      </span>
                      <span
                        className={`rounded-md px-2 py-0.5 text-[11px] font-bold uppercase font-sans ${
                          qualityGate.verdict === 'proceed'
                            ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-800/60'
                            : qualityGate.verdict === 'reject'
                              ? 'bg-rose-950/80 text-rose-300 border border-rose-800/60'
                              : 'bg-amber-950/80 text-amber-200 border border-amber-800/60'
                        }`}
                      >
                        {qualityGate.verdict || 'revise'}
                      </span>
                    </div>
                    {qualityGate.rationale && (
                      <p className="text-xs text-slate-400 font-sans leading-relaxed whitespace-pre-wrap">
                        {qualityGate.rationale}
                      </p>
                    )}
                  </div>
                )}
              </div>
              {telemetry?.historical_benchmark &&
                telemetry.historical_benchmark.mode !== 'disabled' && (
                  <div className="rounded-xl border border-emerald-800/50 bg-emerald-950/20 p-4 space-y-2">
                    <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-300/90 font-sans">
                      Path AA — Historical benchmark
                    </div>
                    <p className="text-lg font-bold text-emerald-200 font-sans tabular-nums">
                      {telemetry.historical_benchmark.confidence_percent ?? 0}%
                      <span className="text-xs font-normal text-emerald-500/80 ml-2 font-mono uppercase tracking-wider">
                        {telemetry.historical_benchmark.mode === 'embedding'
                          ? 'embedding'
                          : telemetry.historical_benchmark.mode === 'lexical_fallback'
                            ? 'lexical fallback'
                            : telemetry.historical_benchmark.mode}
                      </span>
                    </p>
                    <p className="text-sm text-slate-300 font-sans leading-relaxed">
                      {telemetry.historical_benchmark.display_hint ||
                        'Compared this draft (directive + slide digest) to the top successful materializations in success_store.jsonl.'}
                    </p>
                    {telemetry.historical_benchmark.mean_top_k_similarity != null && (
                      <p className="text-[10px] text-slate-500 font-mono">
                        Mean top-{telemetry.historical_benchmark.top_matches?.length || 3} similarity:{' '}
                        {Number(telemetry.historical_benchmark.mean_top_k_similarity).toFixed(3)}
                      </p>
                    )}
                    {Array.isArray(telemetry.historical_benchmark.top_matches) &&
                      telemetry.historical_benchmark.top_matches.length > 0 && (
                        <details className="text-xs text-slate-500 font-sans">
                          <summary className="cursor-pointer text-emerald-600/90 hover:text-emerald-400">
                            Top historical matches
                          </summary>
                          <ul className="mt-2 space-y-2 list-none border-t border-emerald-900/40 pt-2">
                            {telemetry.historical_benchmark.top_matches.map((m, i) => (
                              <li key={i} className="border-l-2 border-emerald-800/50 pl-2">
                                <span className="text-emerald-600/90 font-mono text-[10px]">
                                  sim {m.similarity != null ? Number(m.similarity).toFixed(3) : '—'}
                                  {m.entry_id_prefix ? ` · ${m.entry_id_prefix}` : ''}
                                </span>
                                <p className="text-slate-400 mt-0.5">{m.prompt_excerpt || '—'}</p>
                              </li>
                            ))}
                          </ul>
                        </details>
                      )}
                  </div>
                )}
              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setPhase('form');
                    setDeckSlides([]);
                    setQualityGate(null);
                    setQualityGateSig(null);
                    setRefineInputs({});
                    setRefineBusy({});
                    setSandboxDraftA(null);
                    setSandboxDraftB(null);
                    setDecisionMatrixScores(null);
                    setDecisionMatrixOpen(false);
                    setExecutiveBriefing(null);
                    setReviewViewTab('slides');
                    setMicrositeHref(null);
                  }}
                  className="px-4 py-2 rounded-lg border border-slate-600 text-slate-300 text-sm hover:bg-slate-800 font-sans"
                >
                  Back to inputs
                </button>
                <button
                  type="button"
                  onClick={handleMicrositeExport}
                  disabled={micrositeBusy || !qualityGatePassed}
                  title={
                    qualityGatePassed
                      ? 'Path Z: single-file HTML with Tailwind + interactive Plotly charts (opens in new tab)'
                      : 'Run Final Quality Gate first (Path V).'
                  }
                  className="px-5 py-2 rounded-lg bg-cyan-700 hover:bg-cyan-600 text-white text-sm font-bold font-sans disabled:opacity-50"
                >
                  {micrositeBusy ? 'Building microsite…' : 'Export HTML microsite'}
                </button>
                <button
                  type="button"
                  onClick={handleMaterialize}
                  disabled={isLoading || !qualityGatePassed}
                  title={
                    qualityGatePassed
                      ? 'Build PPTX from current slides'
                      : 'Run Final Quality Gate first (Path V).'
                  }
                  className="px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-bold font-sans disabled:opacity-50"
                >
                  {isLoading ? 'Assembling…' : 'Assemble PPTX'}
                </button>
              </div>
              {micrositeHref ? (
                <p className="text-[11px] text-slate-500 font-mono mt-2">
                  Path Z microsite:{' '}
                  <a
                    href={staticAssetUrl(micrositeHref)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-cyan-400 hover:text-cyan-300 underline break-all"
                  >
                    {staticAssetUrl(micrositeHref)}
                  </a>
                </p>
              ) : null}
            </div>
            <div className="grid gap-4">
              {deckSlides.map((slide, idx) => {
                const previewHref = heroPreviewByIndex[idx];
                const busy = !!synthBusy[idx];
                const refining = !!refineBusy[idx];
                const hasPrompt = !!(slide?.image_prompt && String(slide.image_prompt).trim());
                const slideLock = warRoomSlideLocks[String(idx)];
                const lockedByOther =
                  slideLock && slideLock.user_id && slideLock.user_id !== warRoomUserId;
                return (
                  <div
                    key={`slide-${idx}`}
                    className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <span className="text-[10px] uppercase tracking-widest text-slate-500 font-mono">Slide {idx + 1}</span>
                        <h3 className="text-base font-semibold text-slate-100 font-sans mt-1">
                          {slide?.title || '(no title)'}
                        </h3>
                      </div>
                      <button
                        type="button"
                        disabled={!hasPrompt || busy}
                        onClick={() => handleSynthesizeSlide(idx)}
                        className="shrink-0 px-3 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:bg-slate-700 disabled:text-slate-500 text-white text-xs font-bold font-sans"
                      >
                        {busy ? 'Synthesizing…' : 'Generate Image'}
                      </button>
                    </div>
                    {slide?.body && (
                      <p className="text-xs text-slate-400 line-clamp-3 font-sans">{slide.body}</p>
                    )}
                    <div>
                      <span className="text-[10px] text-slate-600 uppercase font-mono">image_prompt</span>
                      <p className="text-xs text-slate-300 font-mono mt-0.5 whitespace-pre-wrap break-words">
                        {hasPrompt ? slide.image_prompt : '—'}
                      </p>
                    </div>
                    {previewHref && (
                      <img
                        src={staticAssetUrl(previewHref)}
                        alt={`Slide ${idx + 1} hero`}
                        className="w-full max-h-48 object-cover rounded-lg border border-slate-700"
                      />
                    )}
                    <div className="border-t border-slate-800 pt-3 mt-1 space-y-2">
                      <div className="text-[10px] uppercase tracking-widest text-amber-500/90 font-mono">
                        Refine slide
                      </div>
                      {slideLock && (
                        <div
                          role="status"
                          className="rounded-lg border border-rose-800/60 bg-rose-950/30 px-2 py-1.5 text-[10px] text-rose-200/95 font-mono"
                        >
                          Currently being audited by{' '}
                          <span className="font-bold text-rose-100">
                            {slideLock.display_name || slideLock.user_id || 'Strategist'}
                          </span>
                        </div>
                      )}
                      <textarea
                        value={refineInputs[idx] ?? ''}
                        onChange={(e) =>
                          setRefineInputs((prev) => ({ ...prev, [idx]: e.target.value }))
                        }
                        disabled={refining || lockedByOther}
                        rows={2}
                        placeholder="e.g. Make this more aggressive, shorten bullets, add a compliance hook…"
                        className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 placeholder-slate-600 outline-none focus:border-amber-600/60 focus:ring-1 focus:ring-amber-600/30 font-mono resize-y min-h-[52px]"
                      />
                      <button
                        type="button"
                        disabled={refining || lockedByOther}
                        onClick={() => handleRefineSlide(idx)}
                        className="w-full py-2 rounded-lg bg-amber-950/80 hover:bg-amber-900/80 border border-amber-800/60 text-amber-200 text-xs font-bold font-sans disabled:opacity-50"
                      >
                        {refining ? 'Refining…' : 'Apply refinement'}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
            </>
            )}

            {reviewViewTab === 'speaker_notes' && (
            <div className="space-y-4">
              <div className="rounded-2xl border border-teal-900/50 bg-slate-900 p-6 space-y-4">
                <div>
                  <h2 className="text-lg font-bold text-teal-200/95 font-sans">Executive briefing & talk track</h2>
                  <p className="mt-1 text-xs text-slate-500 font-mono">
                    Path P — one-page summary plus per-slide spoken script from the Briefing Agent (DSPy). Path MM
                    tiers: SadTalker-backed video when configured; Piper rehearsal WAV when configured; Read aloud via
                    Web Speech API (Path W) always.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleGenerateExecutiveBriefing}
                  disabled={briefingBusy}
                  className={`w-full py-3 rounded-xl text-sm font-bold font-sans border transition-colors ${
                    briefingBusy
                      ? 'border-teal-900/60 bg-teal-950/40 text-teal-600 cursor-not-allowed'
                      : 'border-teal-700/60 bg-teal-900/40 text-teal-100 hover:bg-teal-900/70'
                  }`}
                >
                  {briefingBusy ? 'Generating briefing…' : 'Generate executive briefing'}
                </button>
                {executiveBriefing && (
                  <div className="rounded-xl border border-teal-800/40 bg-teal-950/15 p-4 space-y-3">
                    <div className="text-[10px] font-bold uppercase tracking-widest text-teal-500/90 font-sans">
                      Path MM — universal media adapter
                    </div>
                    {mediaCaps === null && (
                      <p className="text-[10px] text-slate-500 font-mono">Checking server media capabilities…</p>
                    )}
                    {mediaCaps?.sadtalker_configured && (
                      <button
                        type="button"
                        onClick={handleGenerateVideoBrief}
                        disabled={videoBriefBusy}
                        className={`w-full py-3 rounded-xl text-sm font-bold font-sans border transition-colors ${
                          videoBriefBusy
                            ? 'border-fuchsia-900/60 bg-fuchsia-950/30 text-fuchsia-600 cursor-not-allowed'
                            : 'border-fuchsia-700/60 bg-fuchsia-900/30 text-fuchsia-100 hover:bg-fuchsia-900/55'
                        }`}
                      >
                        {videoBriefBusy
                          ? 'Generating video brief…'
                          : 'Tier 1 — Generate video brief (Path HH · SadTalker)'}
                      </button>
                    )}
                    {mediaCaps && !mediaCaps.sadtalker_configured && (
                      <p className="text-[10px] text-slate-600 font-mono leading-relaxed">
                        Tier 1 (video) hidden: SadTalker not configured on the API host. Set{' '}
                        <code className="text-teal-700/90">RELULAYER_SADTALKER_DIR</code> to a valid repo path to enable
                        the video brief button.
                      </p>
                    )}
                    {mediaCaps?.piper_configured && (
                      <button
                        type="button"
                        onClick={handleGenerateRehearsalAudio}
                        disabled={briefingTtsBusy === 'rehearsal-full'}
                        className={`w-full py-2.5 rounded-xl text-sm font-bold font-sans border transition-colors ${
                          briefingTtsBusy === 'rehearsal-full'
                            ? 'border-violet-900/60 bg-violet-950/25 text-violet-600 cursor-not-allowed'
                            : 'border-violet-700/60 bg-violet-900/25 text-violet-100 hover:bg-violet-900/50'
                        }`}
                      >
                        {briefingTtsBusy === 'rehearsal-full'
                          ? 'Synthesizing rehearsal audio…'
                          : 'Tier 2 — Generate rehearsal audio (Piper WAV · full script)'}
                      </button>
                    )}
                    {mediaCaps && !mediaCaps.piper_configured && (
                      <p className="text-[10px] text-slate-600 font-mono leading-relaxed">
                        Tier 2 (server audio) unavailable: set{' '}
                        <code className="text-teal-700/90">RELULAYER_PIPER_MODEL</code> (and optional{' '}
                        <code className="text-teal-700/90">RELULAYER_PIPER_BIN</code>) on the API host, or use Tier 3
                        Read aloud.
                      </p>
                    )}
                    <p className="text-[10px] text-slate-500 font-mono border-t border-teal-900/35 pt-2 leading-relaxed">
                      Tier 3 — Read aloud (Path W): Web Speech API buttons below; works without Piper or SadTalker.
                    </p>
                  </div>
                )}
                {videoBriefHref && (
                  <div className="rounded-xl border border-fuchsia-800/45 bg-fuchsia-950/15 p-3 text-left">
                    <div className="text-[10px] font-bold uppercase tracking-widest text-fuchsia-400 font-sans">
                      Video brief ready
                    </div>
                    <a
                      className="mt-1 block text-xs font-mono text-fuchsia-200 hover:text-fuchsia-100 break-all"
                      href={staticAssetUrl(videoBriefHref)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {videoBriefHref}
                    </a>
                  </div>
                )}
                {executiveBriefing && (
                  <div
                    className="flex rounded-xl border border-teal-800/45 bg-teal-950/20 p-1 font-sans"
                    role="tablist"
                    aria-label="Briefing view mode"
                  >
                    <button
                      type="button"
                      role="tab"
                      aria-selected={briefingViewMode === 'document'}
                      onClick={() => setBriefingViewMode('document')}
                      className={`flex-1 rounded-lg px-3 py-2 text-xs font-bold uppercase tracking-wider transition-colors ${
                        briefingViewMode === 'document'
                          ? 'bg-slate-800 text-teal-100 shadow-sm'
                          : 'text-slate-500 hover:text-slate-300'
                      }`}
                    >
                      Briefing document
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={briefingViewMode === 'rehearsal'}
                      onClick={() => setBriefingViewMode('rehearsal')}
                      className={`flex-1 rounded-lg px-3 py-2 text-xs font-bold uppercase tracking-wider transition-colors ${
                        briefingViewMode === 'rehearsal'
                          ? 'bg-teal-900/50 text-teal-100 shadow-sm border border-teal-600/40'
                          : 'text-slate-500 hover:text-slate-300'
                      }`}
                    >
                      Interactive rehearsal
                    </button>
                  </div>
                )}
                {executiveBriefing && briefingViewMode === 'rehearsal' && (
                  <InteractiveRehearsalPanel
                    briefing={executiveBriefing}
                    deckSlides={deckSlides}
                    onReportError={(msg) => setError(msg)}
                    onReadAloud={speakBriefingInBrowser}
                  />
                )}
                {executiveBriefing && briefingViewMode === 'document' && (
                  <div className="space-y-4">
                    <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4 space-y-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h3 className="text-xs font-bold uppercase tracking-widest text-slate-400 font-sans">
                          Executive summary
                        </h3>
                        <div className="flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() => speakBriefingInBrowser(executiveBriefing.executive_summary)}
                            className="rounded-lg border border-slate-600 bg-slate-900 px-2 py-1 text-[10px] font-bold uppercase text-slate-300 hover:bg-slate-800 font-mono"
                          >
                            Read aloud (Path W)
                          </button>
                          {mediaCaps?.piper_configured && (
                            <button
                              type="button"
                              disabled={briefingTtsBusy === 'summary'}
                              onClick={() =>
                                requestBriefingPiperTts(executiveBriefing.executive_summary, 'summary')
                              }
                              className="rounded-lg border border-violet-800/60 bg-violet-950/40 px-2 py-1 text-[10px] font-bold uppercase text-violet-300 hover:bg-violet-900/50 font-mono disabled:opacity-40"
                            >
                              {briefingTtsBusy === 'summary' ? 'Piper…' : 'Piper WAV'}
                            </button>
                          )}
                        </div>
                      </div>
                      <p className="text-sm text-slate-200 whitespace-pre-wrap font-sans leading-relaxed">
                        {executiveBriefing.executive_summary}
                      </p>
                    </div>
                    {(executiveBriefing.slide_talk_tracks || []).map((row) => {
                      const idx = Number(row.slide_index);
                      const slide = deckSlides[idx];
                      const busyKey = `slide-${idx}`;
                      return (
                        <div
                          key={`tt-${idx}`}
                          className="rounded-xl border border-slate-800 bg-slate-950/40 p-4 space-y-2"
                        >
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div>
                              <span className="text-[10px] font-mono text-slate-600">Slide {idx + 1}</span>
                              <h4 className="text-sm font-semibold text-slate-100 font-sans">
                                {slide?.title || '(no title)'}
                              </h4>
                            </div>
                            <div className="flex flex-wrap gap-2 shrink-0">
                              <button
                                type="button"
                                onClick={() => speakBriefingInBrowser(row.talk_track)}
                                className="rounded-lg border border-slate-600 bg-slate-900 px-2 py-1 text-[10px] font-bold uppercase text-slate-300 hover:bg-slate-800 font-mono"
                              >
                                Read aloud (Path W)
                              </button>
                              {mediaCaps?.piper_configured && (
                                <button
                                  type="button"
                                  disabled={briefingTtsBusy === busyKey}
                                  onClick={() => requestBriefingPiperTts(row.talk_track, busyKey)}
                                  className="rounded-lg border border-violet-800/60 bg-violet-950/40 px-2 py-1 text-[10px] font-bold uppercase text-violet-300 hover:bg-violet-900/50 font-mono disabled:opacity-40"
                                >
                                  {briefingTtsBusy === busyKey ? 'Piper…' : 'Piper WAV'}
                                </button>
                              )}
                            </div>
                          </div>
                          <p className="text-sm text-slate-300 whitespace-pre-wrap font-sans leading-relaxed">
                            {row.talk_track || '—'}
                          </p>
                          {slide?.speaker_notes && String(slide.speaker_notes).trim() && (
                            <details className="text-xs text-slate-500 font-sans">
                              <summary className="cursor-pointer text-slate-400 hover:text-slate-300">
                                Draft slide speaker_notes
                              </summary>
                              <p className="mt-2 whitespace-pre-wrap text-slate-500">{slide.speaker_notes}</p>
                            </details>
                          )}
                        </div>
                      );
                    })}
                    {executiveBriefing.telemetry &&
                      (executiveBriefing.telemetry.raw_prompt ||
                        executiveBriefing.telemetry.raw_completion) && (
                        <details className="rounded-lg border border-slate-800 bg-black/30 p-3 font-mono text-[10px] text-slate-500">
                          <summary className="cursor-pointer text-slate-400 text-xs font-sans">
                            Briefing agent — glass box
                          </summary>
                          {executiveBriefing.telemetry.rationale && (
                            <p className="mt-2 text-slate-400 whitespace-pre-wrap">
                              {executiveBriefing.telemetry.rationale}
                            </p>
                          )}
                          <div className="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap break-words">
                            {executiveBriefing.telemetry.raw_completion || '(no completion capture)'}
                          </div>
                        </details>
                      )}
                  </div>
                )}
                <p className="text-[10px] text-slate-600 font-mono">
                  Switch to <span className="text-slate-400">Slide build</span> for template path, hero synthesis, and Assemble PPTX.
                  {executiveBriefing && (
                    <>
                      {' '}
                      Open <span className="text-teal-600/90">Interactive rehearsal</span> for Path W teleprompter + mic.
                    </>
                  )}
                </p>
              </div>
            </div>
            )}
          </div>
        ) : (
          <div className="bg-slate-900 p-8 rounded-2xl border border-emerald-500/30 shadow-2xl space-y-6 relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-1 bg-emerald-500 opacity-50"></div>
            <div className="flex items-center space-x-4 text-left">
              <div className="bg-emerald-500/20 p-3 rounded-full">
                <svg className="w-8 h-8 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
              </div>
              <div>
                <h3 className="text-2xl font-bold text-emerald-400 font-sans">Materialization Complete</h3>
                <p className="text-slate-400 text-sm font-sans">Your presentation is ready.</p>
              </div>
            </div>
            {telemetry && (
              <div className="text-left">
                <button
                  type="button"
                  onClick={() => {
                    setTelemetryTab('rationale');
                    setTelemetryOpen(true);
                  }}
                  className="w-full py-3 rounded-xl font-semibold text-sm tracking-wide border border-cyan-700/60 bg-cyan-950/40 text-cyan-300 hover:bg-cyan-900/50 hover:border-cyan-500/50 transition-all font-mono"
                >
                  View Telemetry (Glass-Box)
                </button>
              </div>
            )}
            <div
              className={`grid grid-cols-1 gap-4 ${financialAppendixPath ? 'md:grid-cols-3' : 'md:grid-cols-2'}`}
            >
              <button
                type="button"
                onClick={handleDownload}
                className="flex flex-col items-center justify-center p-6 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl transition-all group border border-emerald-400 shadow-[0_0_15px_rgba(16,185,129,0.2)]"
              >
                <svg className="w-8 h-8 mb-2 group-hover:scale-110 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                <span className="font-bold font-sans">Download deck (PPTX)</span>
              </button>
              {financialAppendixPath && (
                <button
                  type="button"
                  onClick={handleDownloadFinancialAppendix}
                  className="flex flex-col items-center justify-center p-6 bg-amber-700/90 hover:bg-amber-600 text-white rounded-xl transition-all group border border-amber-500/80 shadow-[0_0_15px_rgba(245,158,11,0.15)]"
                >
                  <svg className="w-8 h-8 mb-2 group-hover:scale-110 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 17v-6a2 2 0 012-2h7m-9 12h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10"></path></svg>
                  <span className="font-bold font-sans text-center">Financial appendix (XLSX)</span>
                  <span className="mt-1 text-[10px] font-mono text-amber-100/80 uppercase tracking-wider">Path CC</span>
                </button>
              )}
              <button
                type="button"
                onClick={() => {
                  setResult(null);
                  setFinancialAppendixPath(null);
                  setTelemetry(null);
                  setMaterializeStructural(null);
                  setTelemetryOpen(false);
                  setPhase('form');
                  setDeckSlides([]);
                  setQualityGate(null);
                  setQualityGateSig(null);
                  setHeroPreviewByIndex({});
                  setRefineInputs({});
                  setRefineBusy({});
                  setSandboxDraftA(null);
                  setSandboxDraftB(null);
                  setDecisionMatrixScores(null);
                  setDecisionMatrixOpen(false);
                  setExecutiveBriefing(null);
                  setReviewViewTab('slides');
                }}
                className="flex flex-col items-center justify-center p-6 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl transition-all border border-slate-700"
              >
                <svg className="w-8 h-8 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4"></path></svg>
                <span className="font-bold font-sans">New Presentation</span>
              </button>
            </div>
            <div className="space-y-2 text-left">
              <label className="text-xs font-bold text-slate-500 uppercase tracking-widest font-sans">Resource paths</label>
              <div
                onClick={handleCopy}
                className="bg-black/40 p-4 rounded-lg border border-slate-800 flex items-center justify-between group cursor-pointer hover:border-blue-500/50 transition-colors"
              >
                <code className="text-xs text-blue-400 truncate mr-4">{result}</code>
                <svg className="w-4 h-4 text-slate-600 group-hover:text-blue-400 transition-colors shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
              </div>
              {financialAppendixPath && (
                <div className="bg-black/40 p-4 rounded-lg border border-amber-900/50 flex items-center justify-between font-mono text-[11px] text-amber-200/90">
                  <code className="truncate mr-4">{financialAppendixPath}</code>
                  <span className="shrink-0 text-amber-600/80 uppercase text-[10px]">XLSX</span>
                </div>
              )}
            </div>
            {materializeStructural && (
              <div className="rounded-xl border border-violet-800/50 bg-violet-950/25 p-4 text-left space-y-3">
                <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-violet-400 font-sans">
                  Materialization structural telemetry
                </div>
                <p className="text-xs text-slate-400 font-mono">
                  Path M — placeholder overflow heuristic · Audit{' '}
                  {materializeStructural.audit_enabled ? 'on' : 'off'} · Checks:{' '}
                  {materializeStructural.checks_performed ?? 0} · Adjustments:{' '}
                  {materializeStructural.adjustments?.length ?? 0}
                </p>
                {(materializeStructural.adjustments || []).length > 0 ? (
                  <ul className="space-y-2 text-xs text-slate-300 list-none font-mono">
                    {materializeStructural.adjustments.map((a, i) => (
                      <li
                        key={i}
                        className="border-l-2 border-violet-600/60 pl-3 py-0.5"
                      >
                        <span className="text-violet-300 font-semibold">
                          Slide {Number(a.slide_index) + 1}
                        </span>
                        <span className="text-slate-500"> · {a.role}</span>
                        <span className="text-amber-400/90"> · {a.action}</span>
                        <div className="text-slate-400 mt-1 whitespace-pre-wrap break-words">
                          {a.message}
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-slate-500 font-mono">
                    No font-scale or truncate fixes (content fit within estimated placeholder bounds), or audit disabled via env.
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {telemetryOpen && telemetry && (
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/75 backdrop-blur-[2px]"
            role="dialog"
            aria-modal="true"
            aria-label="Telemetry inspector"
            onClick={() => setTelemetryOpen(false)}
            onKeyDown={(e) => e.key === 'Escape' && setTelemetryOpen(false)}
          >
            <div
              className="flex w-full max-w-4xl max-h-[88vh] flex-col overflow-hidden rounded-lg border border-slate-600 bg-black/92 font-mono text-sm text-slate-200 shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex flex-shrink-0 items-center justify-between border-b border-slate-700 bg-black/80 px-4 py-3">
                <div>
                  <div className="text-xs font-bold uppercase tracking-[0.2em] text-emerald-400">
                    Glass-Box Terminal
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">
                    LM history turns: {telemetry.history_turns ?? 0}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setTelemetryOpen(false)}
                  className="rounded border border-slate-600 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800"
                >
                  Close
                </button>
              </div>
              <div className="flex flex-shrink-0 gap-1 border-b border-slate-800 bg-black/60 px-2 py-2">
                {telemetryTabList.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setTelemetryTab(t.id)}
                    className={`rounded px-3 py-1.5 text-xs font-semibold transition-colors ${
                      telemetryTab === t.id
                        ? 'bg-slate-700 text-white'
                        : 'text-slate-500 hover:bg-slate-800/80 hover:text-slate-300'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              <div className="flex flex-shrink-0 flex-wrap items-center gap-2 border-b border-slate-800 bg-black/50 px-4 py-2">
                <span className="text-[10px] font-bold uppercase tracking-widest text-emerald-600/90 font-sans shrink-0">
                  Path GG — knowledge graph
                </span>
                <button
                  type="button"
                  disabled={!projectFolder.trim() || kgExportBusy != null}
                  onClick={() => downloadKnowledgeGraphExport('jsonld')}
                  className="rounded border border-slate-600 px-2 py-1 text-[10px] font-mono text-slate-300 hover:bg-slate-800 disabled:opacity-40"
                >
                  {kgExportBusy === 'jsonld' ? 'Downloading…' : 'Download JSON-LD'}
                </button>
                <button
                  type="button"
                  disabled={!projectFolder.trim() || kgExportBusy != null}
                  onClick={() => downloadKnowledgeGraphExport('turtle')}
                  className="rounded border border-slate-600 px-2 py-1 text-[10px] font-mono text-slate-300 hover:bg-slate-800 disabled:opacity-40"
                >
                  {kgExportBusy === 'turtle' ? 'Downloading…' : 'Download Turtle'}
                </button>
                <span className="text-[10px] text-slate-600 font-mono min-w-0 flex-1 truncate">
                  {projectFolder.trim()
                    ? `folder: ${projectFolder.trim()}`
                    : '(set project folder on the draft form for Path X / GG export)'}
                </span>
              </div>
              <div className="min-h-0 flex-1 overflow-auto p-4 whitespace-pre-wrap break-words text-slate-300">
                {telemetryTab === 'grounding' && telemetry.live_grounding_data && (
                  <div className="space-y-4">
                    <div className="text-[10px] uppercase tracking-widest text-slate-500">
                      Path K — real-time web / news context merged into draft ingestion
                    </div>
                    <p className="text-xs text-slate-400">
                      <span className="text-cyan-400 font-semibold">Active:</span>{' '}
                      {telemetry.live_grounding_data.active ? 'yes' : 'no'}
                      {' · '}
                      <span className="text-cyan-400 font-semibold">Provider:</span>{' '}
                      {telemetry.live_grounding_data.provider || '(n/a)'}
                      {' · '}
                      <span className="text-cyan-400 font-semibold">Snippets:</span>{' '}
                      {telemetry.live_grounding_data.snippet_count ?? 0}
                    </p>
                    {telemetry.live_grounding_data.search_query_used?.trim() && (
                      <div>
                        <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">
                          Search query (from strategic directive)
                        </div>
                        <span className="text-sm text-slate-200">
                          {telemetry.live_grounding_data.search_query_used}
                        </span>
                      </div>
                    )}
                    {telemetry.live_grounding_data.error?.trim() && (
                      <div className="rounded border border-amber-800/50 bg-amber-950/30 p-3 text-xs text-amber-200/90">
                        {telemetry.live_grounding_data.error}
                      </div>
                    )}
                    <div>
                      <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-2">
                        Snippets injected into model context
                      </div>
                      <ul className="list-none space-y-3 text-sm">
                        {(telemetry.live_grounding_data.snippets || []).map((s, i) => (
                          <li
                            key={i}
                            className="border-l-2 border-cyan-800/60 pl-3 text-slate-300"
                          >
                            <div className="font-semibold text-slate-100">{s.title || '(untitled)'}</div>
                            {s.url?.trim() && (
                              <div className="text-[11px] text-cyan-500/90 break-all">{s.url}</div>
                            )}
                            <div className="mt-1 text-xs text-slate-400">{s.snippet || ''}</div>
                          </li>
                        ))}
                      </ul>
                      {(!telemetry.live_grounding_data.snippets ||
                        telemetry.live_grounding_data.snippets.length === 0) &&
                        !telemetry.live_grounding_data.error?.trim() && (
                          <span className="text-slate-500 text-xs">(no snippets)</span>
                        )}
                    </div>
                  </div>
                )}
                {telemetryTab === 'rationale' && (
                  <span>{telemetry.rationale?.trim() ? telemetry.rationale : '(no rationale field on prediction)'}</span>
                )}
                {telemetryTab === 'prompt' && (
                  <span>{telemetry.raw_prompt?.trim() ? telemetry.raw_prompt : '(empty — history disabled or no LM call recorded)'}</span>
                )}
                {telemetryTab === 'output' && (
                  <span>{telemetry.raw_completion?.trim() ? telemetry.raw_completion : '(empty — history disabled or no LM call recorded)'}</span>
                )}
                {telemetryTab === 'consensus' &&
                  Array.isArray(telemetry.consensus_persona_turns) &&
                  telemetry.consensus_persona_turns.length > 0 && (
                    <div className="space-y-6">
                      <p className="text-[10px] uppercase tracking-widest text-slate-500">
                        Three persona passes (serial on GPU), then synthesis. Raw prompt/output
                        below is the <span className="text-cyan-400">synthesis</span> step; use
                        Strategy Rationale for merge notes.
                      </p>
                      {telemetry.consensus_persona_turns.map((turn, i) => (
                        <div
                          key={`${turn.persona}-${i}`}
                          className="rounded border border-slate-700/80 bg-slate-950/50 p-3"
                        >
                          <div className="text-[10px] font-bold uppercase tracking-widest text-amber-400/90 mb-2">
                            {CONSENSUS_SUB_PERSONA_LABELS[turn.persona] || turn.persona}
                          </div>
                          <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">
                            Raw completion (LM history)
                          </div>
                          <span className="text-xs text-slate-400">
                            {turn.raw_completion?.trim() || '(empty)'}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                {telemetryTab === 'selfcorrection' && (
                  <div className="space-y-4">
                    <div className="text-[10px] uppercase tracking-widest text-slate-500">
                      Path Y — autonomous judge → refine loop (draft pipeline)
                    </div>
                    <p className="text-xs text-slate-400">
                      <span className="text-violet-400 font-semibold">Applied:</span>{' '}
                      {telemetry.self_correction_applied ? 'yes' : 'no'}
                      {' · '}
                      <span className="text-violet-400 font-semibold">Slides refined:</span>{' '}
                      {telemetry.self_correction_slides_refined ?? 0}
                    </p>
                    {telemetry.self_correction_skipped_reason != null &&
                      String(telemetry.self_correction_skipped_reason).trim() !== '' && (
                        <p className="text-xs text-slate-400">
                          <span className="text-amber-400/90 font-semibold">Skipped / outcome:</span>{' '}
                          {telemetry.self_correction_skipped_reason}
                        </p>
                      )}
                    {(telemetry.self_correction_judge_verdict != null ||
                      telemetry.self_correction_rubric_clarity != null) && (
                      <p className="text-xs text-slate-400">
                        {telemetry.self_correction_judge_verdict != null && (
                          <>
                            <span className="text-cyan-400 font-semibold">Judge verdict:</span>{' '}
                            {telemetry.self_correction_judge_verdict}
                            <br />
                          </>
                        )}
                        <span className="text-slate-500">Rubric (1–10):</span> clarity{' '}
                        {telemetry.self_correction_rubric_clarity ?? '—'}, feasibility{' '}
                        {telemetry.self_correction_rubric_feasibility ?? '—'}, strategic_impact{' '}
                        {telemetry.self_correction_rubric_strategic_impact ?? '—'}
                      </p>
                    )}
                    {!telemetry.self_correction_applied &&
                      !telemetry.self_correction_judge_verdict &&
                      !(telemetry.self_correction_skipped_reason != null &&
                        String(telemetry.self_correction_skipped_reason).trim() !== '') && (
                        <p className="text-xs text-slate-500">
                          Enable Self-correction on the draft form and run a new draft to populate this trace.
                        </p>
                      )}
                  </div>
                )}
                {telemetryTab === 'redteam' && telemetry.audit_report && (
                  <div className="space-y-4">
                    {telemetry.audit_report.red_team_alert && (
                      <p className="text-rose-400 text-xs font-bold uppercase tracking-wider font-sans">
                        Significant gaps flagged — see list below
                      </p>
                    )}
                    {telemetry.audit_report.rationale?.trim() && (
                      <div>
                        <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">Auditor rationale</div>
                        <span className="text-slate-300">{telemetry.audit_report.rationale}</span>
                      </div>
                    )}
                    <div>
                      <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-2">Weak points / risks</div>
                      <ul className="list-none space-y-2 text-sm">
                        {(telemetry.audit_report.weak_points || []).map((w, i) => (
                          <li key={i} className="border-l-2 border-rose-700/60 pl-3">
                            <span className="text-xs font-mono text-rose-400/90">{w.severity}</span>
                            <span className="text-slate-200"> — {w.point}</span>
                          </li>
                        ))}
                      </ul>
                      {(!telemetry.audit_report.weak_points || telemetry.audit_report.weak_points.length === 0) && (
                        <span className="text-slate-500">(no parsed risks — check raw auditor output below)</span>
                      )}
                    </div>
                    <div>
                      <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">Auditor raw prompt</div>
                      <span className="text-xs text-slate-400">
                        {telemetry.audit_raw_prompt?.trim() || '(empty)'}
                      </span>
                    </div>
                    <div>
                      <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">Auditor raw completion</div>
                      <span className="text-xs text-slate-400">
                        {telemetry.audit_raw_completion?.trim() || '(empty)'}
                      </span>
                    </div>
                  </div>
                )}
                {telemetryTab === 'wargame' && telemetry.wargame_audit && (
                  <div className="space-y-4">
                    <div className="text-[10px] uppercase tracking-widest text-slate-500">
                      Path BB — Blue (Proponent) vs Red (Adversary) on consensus deck (after Red Team audit)
                    </div>
                    {telemetry.wargame_audit.wargame_alert && (
                      <p className="text-orange-400 text-xs font-bold uppercase tracking-wider font-sans">
                        Residual risks meet alert threshold — see list below
                      </p>
                    )}
                    {telemetry.wargame_audit.skipped_reason != null &&
                      String(telemetry.wargame_audit.skipped_reason).trim() !== '' && (
                        <p className="text-xs text-amber-200/90">
                          <span className="font-semibold text-amber-400/90">Skipped / error:</span>{' '}
                          {telemetry.wargame_audit.skipped_reason}
                        </p>
                      )}
                    {telemetry.wargame_audit.residual_headline?.trim() && (
                      <div>
                        <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">Residual headline</div>
                        <span className="text-slate-200 text-sm">{telemetry.wargame_audit.residual_headline}</span>
                      </div>
                    )}
                    <div>
                      <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-2">Debate rounds</div>
                      {(telemetry.wargame_audit.turns || []).length > 0 ? (
                        <ul className="list-none space-y-4">
                          {telemetry.wargame_audit.turns.map((tr, i) => (
                            <li
                              key={`${tr.turn}-${i}`}
                              className="rounded border border-slate-700/80 bg-slate-950/50 p-3 space-y-2"
                            >
                              <div className="text-[10px] font-bold uppercase tracking-widest text-rose-400/90">
                                Round {tr.turn} — Adversary
                              </div>
                              <p className="text-xs text-slate-300 whitespace-pre-wrap">{tr.adversary_attack || '(empty)'}</p>
                              <div className="text-[10px] font-bold uppercase tracking-widest text-cyan-400/90 pt-1 border-t border-slate-800">
                                Round {tr.turn} — Proponent
                              </div>
                              <p className="text-xs text-slate-300 whitespace-pre-wrap">{tr.proponent_mitigation || '(empty)'}</p>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <span className="text-slate-500 text-xs">
                          {(telemetry.wargame_audit.skipped_reason || '').trim()
                            ? '(no rounds — see skip reason above)'
                            : '(no rounds in telemetry)'}
                        </span>
                      )}
                    </div>
                    <div>
                      <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-2">Residual risks</div>
                      <ul className="list-none space-y-2 text-sm">
                        {(telemetry.wargame_audit.residual_risks || []).map((w, i) => (
                          <li key={i} className="border-l-2 border-orange-700/60 pl-3">
                            <span className="text-xs font-mono text-orange-400/90">{w.severity}</span>
                            <span className="text-slate-200"> — {w.point}</span>
                          </li>
                        ))}
                      </ul>
                      {(!telemetry.wargame_audit.residual_risks ||
                        telemetry.wargame_audit.residual_risks.length === 0) && (
                        <span className="text-slate-500 text-xs">(no parsed residual risks)</span>
                      )}
                    </div>
                  </div>
                )}
                {telemetryTab === 'compliance' && telemetry.compliance_pass && (
                  <div className="space-y-4">
                    <div className="text-[10px] uppercase tracking-widest text-slate-500">
                      Path II — compliance benchmarking pass
                    </div>
                    <p className="text-xs text-slate-400">
                      <span className="text-sky-400 font-semibold">Standard:</span>{' '}
                      {telemetry.compliance_pass.standard || '(unspecified)'}
                      {telemetry.compliance_pass.skipped_reason?.trim() && (
                        <>
                          {' '}
                          · <span className="text-amber-400/90 font-semibold">Skipped:</span>{' '}
                          {telemetry.compliance_pass.skipped_reason}
                        </>
                      )}
                    </p>
                    {telemetry.compliance_pass.summary?.trim() && (
                      <div>
                        <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">Summary</div>
                        <p className="text-sm text-slate-200 whitespace-pre-wrap font-sans leading-relaxed">
                          {telemetry.compliance_pass.summary}
                        </p>
                      </div>
                    )}
                    <div>
                      <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-2">Findings</div>
                      {(telemetry.compliance_pass.findings || []).length > 0 ? (
                        <ul className="list-none space-y-3 text-sm">
                          {telemetry.compliance_pass.findings.map((f, i) => (
                            <li key={i} className="rounded border border-slate-800 bg-slate-950/40 p-3 space-y-2">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="text-[10px] font-mono text-slate-500">Slide {Number(f.slide_index) + 1}</span>
                                <span
                                  className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase font-mono ${
                                    f.severity === 'high'
                                      ? 'bg-rose-600/50 text-white'
                                      : f.severity === 'medium'
                                        ? 'bg-amber-600/40 text-amber-100'
                                        : 'bg-slate-600/50 text-slate-200'
                                  }`}
                                >
                                  {f.severity || 'medium'}
                                </span>
                                {f.standard_clause?.trim() && (
                                  <span className="text-[10px] font-mono text-sky-300/90">
                                    {f.standard_clause}
                                  </span>
                                )}
                              </div>
                              {f.issue?.trim() && (
                                <p className="text-xs text-slate-200 whitespace-pre-wrap">{f.issue}</p>
                              )}
                              {(f.suggested_copy?.title?.trim() ||
                                f.suggested_copy?.body?.trim() ||
                                f.suggested_copy?.speaker_notes?.trim()) && (
                                <details className="text-xs text-slate-400">
                                  <summary className="cursor-pointer text-slate-500 hover:text-slate-300">
                                    Suggested corrective copy
                                  </summary>
                                  <div className="mt-2 space-y-2">
                                    {f.suggested_copy?.title?.trim() && (
                                      <div>
                                        <div className="text-[10px] uppercase tracking-widest text-slate-600 mb-0.5">Title</div>
                                        <div className="text-slate-300 whitespace-pre-wrap">{f.suggested_copy.title}</div>
                                      </div>
                                    )}
                                    {f.suggested_copy?.body?.trim() && (
                                      <div>
                                        <div className="text-[10px] uppercase tracking-widest text-slate-600 mb-0.5">Body</div>
                                        <div className="text-slate-300 whitespace-pre-wrap">{f.suggested_copy.body}</div>
                                      </div>
                                    )}
                                    {f.suggested_copy?.speaker_notes?.trim() && (
                                      <div>
                                        <div className="text-[10px] uppercase tracking-widest text-slate-600 mb-0.5">Speaker notes</div>
                                        <div className="text-slate-300 whitespace-pre-wrap">{f.suggested_copy.speaker_notes}</div>
                                      </div>
                                    )}
                                  </div>
                                </details>
                              )}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <span className="text-slate-500 text-xs">(no findings)</span>
                      )}
                    </div>
                  </div>
                )}
              </div>
              {telemetryTab === 'prompt' && telemetry.raw_prompt && (
                <div className="flex-shrink-0 border-t border-slate-800 bg-black/80 px-4 py-3">
                  <button
                    type="button"
                    onClick={() => {
                      const text = telemetry.raw_prompt || '';
                      void navigator.clipboard?.writeText(text).catch(() => {
                        const ta = document.createElement('textarea');
                        ta.value = text;
                        document.body.appendChild(ta);
                        ta.select();
                        document.execCommand('copy');
                        document.body.removeChild(ta);
                      });
                    }}
                    className="rounded border border-cyan-700/50 bg-cyan-950/50 px-4 py-2 text-xs font-bold uppercase tracking-wider text-cyan-300 hover:bg-cyan-900/60"
                  >
                    Copy Prompt
                  </button>
                  <span className="ml-3 text-[10px] text-slate-500">Paste into Ollama / your client to reproduce the exact request.</span>
                </div>
              )}
            </div>
          </div>
        )}

        {decisionMatrixOpen && decisionMatrixScores && (
          <div
            className="fixed inset-0 z-[110] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm"
            role="dialog"
            aria-modal="true"
            aria-label="Decision matrix"
            onClick={() => setDecisionMatrixOpen(false)}
            onKeyDown={(e) => e.key === 'Escape' && setDecisionMatrixOpen(false)}
          >
            <div
              className="w-full max-w-3xl overflow-hidden rounded-xl border border-indigo-800/60 bg-slate-950 shadow-2xl font-mono text-sm"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-800 px-5 py-4 bg-indigo-950/40">
                <div>
                  <div className="text-xs font-bold uppercase tracking-[0.2em] text-indigo-400 font-sans">
                    Decision Matrix
                  </div>
                  <p className="mt-1 text-[11px] text-slate-500 font-sans max-w-xl leading-relaxed">
                    1–10 rubric seeded from persona stances and Red Team alerts; drag sliders to match your weighting before you adopt a path for materialization.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setDecisionMatrixOpen(false)}
                  className="rounded border border-slate-600 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800 shrink-0"
                >
                  Close
                </button>
              </div>
              <div className="p-5 space-y-4">
                <div className="overflow-x-auto rounded-lg border border-slate-800">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-800 bg-slate-900/80">
                        <th className="p-3 font-sans font-bold text-slate-400 uppercase tracking-wider w-[38%]">
                          Criterion
                        </th>
                        <th className="p-3 font-sans font-bold text-cyan-400/90">
                          {sandboxLabelA || 'Path A'}
                        </th>
                        <th className="p-3 font-sans font-bold text-amber-400/90">
                          {sandboxLabelB || 'Path B'}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {DECISION_MATRIX_ROWS.map((row) => (
                        <tr key={row.id} className="border-b border-slate-800/80">
                          <td className="p-3 text-slate-300 font-sans align-top">{row.label}</td>
                          <td className="p-3 align-top">
                            <input
                              type="range"
                              min={1}
                              max={10}
                              value={decisionMatrixScores.pathA[row.id] ?? 5}
                              onChange={(e) => updateMatrixScore('pathA', row.id, e.target.value)}
                              className="w-full accent-cyan-600"
                            />
                            <div className="text-center font-mono text-cyan-200/90 mt-1">
                              {decisionMatrixScores.pathA[row.id] ?? 5}
                            </div>
                          </td>
                          <td className="p-3 align-top">
                            <input
                              type="range"
                              min={1}
                              max={10}
                              value={decisionMatrixScores.pathB[row.id] ?? 5}
                              onChange={(e) => updateMatrixScore('pathB', row.id, e.target.value)}
                              className="w-full accent-amber-600"
                            />
                            <div className="text-center font-mono text-amber-200/90 mt-1">
                              {decisionMatrixScores.pathB[row.id] ?? 5}
                            </div>
                          </td>
                        </tr>
                      ))}
                      <tr className="bg-slate-900/60">
                        <td className="p-3 font-bold text-slate-200 font-sans">Total (max 30)</td>
                        <td className="p-3 font-mono text-cyan-300">{totalA}</td>
                        <td className="p-3 font-mono text-amber-300">{totalB}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                {sandboxDraftA?.ok && sandboxDraftB?.ok && (
                  <p className="text-xs text-slate-400 font-sans">
                    <span className="text-indigo-400 font-semibold">Signal:</span>{' '}
                    {totalA === totalB
                      ? 'Composite tie — use slide headlines and Red Team notes to break the tie.'
                      : totalA > totalB
                        ? `${sandboxLabelA || 'Path A'} leads on summed rubric.`
                        : `${sandboxLabelB || 'Path B'} leads on summed rubric.`}
                  </p>
                )}
                <button
                  type="button"
                  onClick={recalibrateDecisionMatrix}
                  className="rounded-lg border border-slate-600 bg-slate-900 px-4 py-2 text-xs font-bold text-slate-300 hover:bg-slate-800 font-sans"
                >
                  Recalibrate from personas
                </button>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="bg-red-950/50 border border-red-500/50 text-red-200 p-5 rounded-xl text-left space-y-3">
            <div className="flex items-center space-x-2 mb-1">
              <svg className="w-5 h-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
              <span className="font-bold text-red-400 uppercase tracking-wider text-sm font-sans">System Error</span>
            </div>
            <p className="text-sm ml-7">{error}</p>
            {telemetry && (
              <button
                type="button"
                onClick={() => {
                  setTelemetryTab('rationale');
                  setTelemetryOpen(true);
                }}
                className="ml-7 rounded border border-cyan-800/60 bg-cyan-950/30 px-3 py-1.5 text-xs font-mono text-cyan-300 hover:bg-cyan-950/50"
              >
                View Telemetry (draft may have succeeded)
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}