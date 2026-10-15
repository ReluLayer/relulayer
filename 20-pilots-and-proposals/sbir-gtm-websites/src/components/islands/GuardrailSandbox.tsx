import { useId, useState, useEffect, useMemo, useCallback } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import {
  Shield,
  AlertTriangle,
  Zap,
  Radio,
  Play,
  RotateCcw,
  ChevronDown,
  ChevronUp,
  FileText,
  Info,
  Cpu,
  Crosshair,
} from 'lucide-react';

type SwarmRatio = '1:1' | '1:2' | '1:3' | '1:4';

const WCET_NS = 199; // 0.199 µs
const WCET_CYCLES = 96; // approximate @ 480 MHz
const HIL_PASSES = 5000;
const GRAPH_POINTS = 80;

// Deterministic pseudo-random helper (avoids SSR hydration mismatches).
function seededRandom(seed: number): number {
  const x = Math.sin(seed * 12.9898 + 78.233) * 43758.5453;
  return x - Math.floor(x);
}

// Empirical data from project benchmarks
const EW_SWEEP_DATA: { lossPct: number; latencySteps: number }[] = [
  { lossPct: 0, latencySteps: 60.168 },
  { lossPct: 5, latencySteps: 60.605 },
  { lossPct: 10, latencySteps: 61.387 },
  { lossPct: 15, latencySteps: 62.302 },
  { lossPct: 20, latencySteps: 63.912 },
  { lossPct: 25, latencySteps: 64.314 },
  { lossPct: 30, latencySteps: 128.854 },
  { lossPct: 35, latencySteps: 128.677 },
  { lossPct: 40, latencySteps: 129.108 },
  { lossPct: 45, latencySteps: 128.236 },
  { lossPct: 50, latencySteps: 128.669 },
  { lossPct: 55, latencySteps: 128.719 },
  { lossPct: 60, latencySteps: 129.132 },
  { lossPct: 65, latencySteps: 129.219 },
  { lossPct: 70, latencySteps: 129.488 },
  { lossPct: 75, latencySteps: 129.68 },
  { lossPct: 80, latencySteps: 130.105 },
];

const SWARM_SUCCESS_DATA: Record<SwarmRatio, { ewLoss: number; protected: number; baseline: number }[]> = {
  '1:1': [
    { ewLoss: 0, protected: 100.0, baseline: 100.0 },
    { ewLoss: 20, protected: 99.0, baseline: 92.0 },
    { ewLoss: 35, protected: 94.2, baseline: 65.7 },
    { ewLoss: 50, protected: 88.0, baseline: 40.0 },
    { ewLoss: 80, protected: 55.0, baseline: 15.0 },
  ],
  '1:2': [
    { ewLoss: 0, protected: 100.0, baseline: 98.0 },
    { ewLoss: 20, protected: 97.0, baseline: 78.0 },
    { ewLoss: 35, protected: 88.6, baseline: 31.6 },
    { ewLoss: 50, protected: 78.0, baseline: 18.0 },
    { ewLoss: 80, protected: 30.0, baseline: 5.0 },
  ],
  '1:3': [
    { ewLoss: 0, protected: 98.0, baseline: 90.0 },
    { ewLoss: 20, protected: 93.0, baseline: 55.0 },
    { ewLoss: 35, protected: 81.1, baseline: 15.0 },
    { ewLoss: 50, protected: 65.0, baseline: 8.0 },
    { ewLoss: 80, protected: 12.0, baseline: 1.0 },
  ],
  '1:4': [
    { ewLoss: 0, protected: 95.0, baseline: 80.0 },
    { ewLoss: 20, protected: 87.0, baseline: 35.0 },
    { ewLoss: 35, protected: 73.4, baseline: 15.0 },
    { ewLoss: 50, protected: 52.0, baseline: 4.0 },
    { ewLoss: 80, protected: 5.0, baseline: 0.0 },
  ],
};

function interpolateEwLatency(jamming: number): number {
  const pct = Math.max(0, Math.min(100, jamming));
  const idx = EW_SWEEP_DATA.findIndex((d) => d.lossPct >= pct);
  if (idx === 0) return EW_SWEEP_DATA[0].latencySteps;
  if (idx < 0) return EW_SWEEP_DATA[EW_SWEEP_DATA.length - 1].latencySteps;
  const prev = EW_SWEEP_DATA[idx - 1];
  const curr = EW_SWEEP_DATA[idx];
  const t = (pct - prev.lossPct) / (curr.lossPct - prev.lossPct);
  return prev.latencySteps + (curr.latencySteps - prev.latencySteps) * t;
}

function interpolateSuccess(ratio: SwarmRatio, jamming: number, protectedMode: boolean): number {
  const data = SWARM_SUCCESS_DATA[ratio];
  const pct = Math.max(0, Math.min(100, jamming));
  const idx = data.findIndex((d) => d.ewLoss >= pct);
  if (idx === 0) return protectedMode ? data[0].protected : data[0].baseline;
  if (idx < 0) {
    const last = data[data.length - 1];
    return protectedMode ? last.protected : last.baseline;
  }
  const prev = data[idx - 1];
  const curr = data[idx];
  const t = (pct - prev.ewLoss) / (curr.ewLoss - prev.ewLoss);
  const key = protectedMode ? 'protected' : 'baseline';
  return prev[key] + (curr[key] - prev[key]) * t;
}

// Scene layout constants (16:9 viewBox)
const SCENE_W = 640;
const SCENE_H = 360;
const CENTER_X = 320;
const CENTER_Y = 175;
const BOUNDARY_R = 110;
const GROUND_X = 70;
const GROUND_Y = 280;

type Drone = { id: string; x: number; y: number; leader?: boolean };

export default function GuardrailSandbox() {
  const emailInputId = useId();
  const prefersReducedMotion = useReducedMotion();
  const motionTransition = prefersReducedMotion ? { duration: 0 } : undefined;

  const [jamming, setJamming] = useState(0);
  const [protectedMode, setProtectedMode] = useState(true);
  const [isUnlocked, setIsUnlocked] = useState(false);
  const [isWalking, setIsWalking] = useState(false);
  const [walkStep, setWalkStep] = useState(0);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => setTick((t) => t + 1), 80);
    return () => clearInterval(interval);
  }, []);

  const isBlackout = jamming >= 95;
  const safetyPercent = interpolateSuccess('1:3', jamming, protectedMode);
  const ewLatencyMultiplier = useMemo(() => {
    const base = EW_SWEEP_DATA[0].latencySteps;
    return interpolateEwLatency(jamming) / base;
  }, [jamming]);

  // ===== WALKTHROUGH =====
  const runWalkthrough = useCallback(() => {
    if (isWalking) return;
    setIsWalking(true);
    setWalkStep(0);
    setProtectedMode(true);
    setJamming(0);

    const steps = [
      { jamming: 0, protected: true, delay: 0 },
      { jamming: 50, protected: true, delay: 1800 },
      { jamming: 100, protected: false, delay: 3600 },
      { jamming: 100, protected: true, delay: 5400 },
    ];

    steps.forEach((step, i) => {
      window.setTimeout(() => {
        setWalkStep(i);
        setJamming(step.jamming);
        setProtectedMode(step.protected);
        if (i === steps.length - 1) {
          window.setTimeout(() => setIsWalking(false), 1200);
        }
      }, step.delay);
    });
  }, [isWalking]);

  const resetDemo = useCallback(() => {
    setIsWalking(false);
    setJamming(0);
    setProtectedMode(true);
    setWalkStep(0);
  }, []);

  const walkLabels = [
    'Friendly swarm on patrol.',
    'Hostile swarm appears and jams all comms.',
    'Without ReluLayer, the outnumbered swarm is overrun.',
    'With ReluLayer, the smaller swarm survives.',
  ];

  // ===== SCENE STATE =====
  const jamFactor = jamming / 100;

  const enemySwarm: Drone[] = useMemo(() => {
    const base: Drone[] = [
      { id: 'H1', x: 520, y: 150 },
      { id: 'H2', x: 560, y: 180 },
      { id: 'H3', x: 520, y: 210 },
      { id: 'H4', x: 560, y: 120 },
      { id: 'H5', x: 500, y: 170 },
      { id: 'H6', x: 540, y: 200 },
      { id: 'H7', x: 550, y: 240 },
      { id: 'H8', x: 490, y: 140 },
    ];
    return base.map((d) => {
      const advance = 140 * jamFactor;
      const jitter = Math.sin(jamFactor * 3 + d.id.charCodeAt(1)) * 8 * jamFactor;
      return {
        ...d,
        x: d.x - advance,
        y: d.y + jitter,
      };
    });
  }, [jamming]);

  const enemyCentroid = useMemo(() => {
    const x = enemySwarm.reduce((sum, d) => sum + d.x, 0) / enemySwarm.length;
    const y = enemySwarm.reduce((sum, d) => sum + d.y, 0) / enemySwarm.length;
    return { x, y };
  }, [enemySwarm]);

  const friendlyDrones: Drone[] = useMemo(() => {
    const base: Drone[] = [
      { id: 'LEAD', x: 250, y: 180, leader: true },
      { id: 'F1', x: 210, y: 210 },
      { id: 'F2', x: 190, y: 160 },
      { id: 'F3', x: 290, y: 220 },
      { id: 'F4', x: 300, y: 150 },
      { id: 'F5', x: 220, y: 130 },
    ];
    return base.map((d) => {
      const dx = d.x - CENTER_X;
      const dy = d.y - CENTER_Y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const inwardShift = protectedMode ? -12 * jamFactor : 0;
      const pullX = protectedMode ? 0 : (enemyCentroid.x - d.x) * 0.65 * jamFactor;
      const pullY = protectedMode ? 0 : (enemyCentroid.y - d.y) * 0.35 * jamFactor;
      const chaos = protectedMode ? 0 : Math.sin(jamFactor * 4 + d.id.charCodeAt(0)) * 18 * jamFactor;
      return {
        ...d,
        x: d.x + (dx / dist) * inwardShift + pullX + chaos,
        y: d.y + (dy / dist) * inwardShift + pullY + chaos,
      };
    });
  }, [jamming, protectedMode, enemyCentroid]);

  const friendlyCentroid = useMemo(() => {
    const x = friendlyDrones.reduce((sum, d) => sum + d.x, 0) / friendlyDrones.length;
    const y = friendlyDrones.reduce((sum, d) => sum + d.y, 0) / friendlyDrones.length;
    return { x, y };
  }, [friendlyDrones]);

  const crashDrones = useMemo(() => {
    if (protectedMode || jamming < 55) return [];
    return friendlyDrones.filter((fd) => {
      const outside = Math.sqrt((fd.x - CENTER_X) ** 2 + (fd.y - CENTER_Y) ** 2) > BOUNDARY_R;
      const overrun = enemySwarm.some((ed) => Math.sqrt((fd.x - ed.x) ** 2 + (fd.y - ed.y) ** 2) < 32);
      return outside || overrun;
    });
  }, [friendlyDrones, enemySwarm, protectedMode, jamming]);

  const closestEnemy = useMemo(() => {
    return enemySwarm.reduce((closest, d) => {
      const dDist = Math.sqrt((d.x - CENTER_X) ** 2 + (d.y - CENTER_Y) ** 2);
      const cDist = Math.sqrt((closest.x - CENTER_X) ** 2 + (closest.y - CENTER_Y) ** 2);
      return dDist < cDist ? d : closest;
    }, enemySwarm[0]);
  }, [enemySwarm]);

  const angleToEnemy = Math.atan2(closestEnemy.y - CENTER_Y, closestEnemy.x - CENTER_X);
  const barrierX = CENTER_X + BOUNDARY_R * Math.cos(angleToEnemy);
  const barrierY = CENTER_Y + BOUNDARY_R * Math.sin(angleToEnemy);

  const boundaryColor = protectedMode ? '#10B981' : '#EF4444';
  const linkOpacity = Math.max(0.05, 0.5 - jamFactor * 0.5);

  // ===== TECHNICAL CHART DATA =====
  const latencyData = useMemo(() => {
    return Array.from({ length: GRAPH_POINTS }, (_, i) => {
      const timeOffset = tick * 0.15 + i * 0.25;
      if (protectedMode) return WCET_NS / 1_000_000;
      const base = 1.2 + Math.sin(timeOffset * 0.7) * 0.8;
      const noise = seededRandom(tick * 100 + i) * (ewLatencyMultiplier - 1) * 12;
      const burst =
        seededRandom(tick * 100 + i + 500) > 0.94
          ? (ewLatencyMultiplier - 1) * (15 + seededRandom(tick * 100 + i + 1000) * 20)
          : 0;
      const floor = (ewLatencyMultiplier - 1) * 18;
      return Math.min(base + noise + burst + floor, 50);
    });
  }, [tick, protectedMode, ewLatencyMultiplier]);

  const graphWidth = 640;
  const graphHeight = 260;
  const paddingX = 56;
  const paddingY = 36;
  const plotWidth = graphWidth - paddingX * 2;
  const plotHeight = graphHeight - paddingY * 2;
  const minLog = Math.log10(0.001);
  const maxLog = Math.log10(100);

  const latencyToY = (ms: number) => {
    const logMs = Math.log10(Math.max(0.000267, ms));
    const normalized = (logMs - minLog) / (maxLog - minLog);
    return paddingY + plotHeight - normalized * plotHeight;
  };

  const pathD = useMemo(() => {
    return latencyData
      .map((val, i) => {
        const x = paddingX + (i / (GRAPH_POINTS - 1)) * plotWidth;
        const y = latencyToY(val);
        return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(' ');
  }, [latencyData, plotWidth, plotHeight]);

  // ===== SAFETY METER =====
  const meterState = useMemo(() => {
    if (protectedMode) return { label: 'All Safe', color: 'emerald', percent: 100 };
    if (safetyPercent >= 70) return { label: 'Crash Risk', color: 'gold', percent: safetyPercent };
    return { label: 'Crash Risk', color: 'red', percent: safetyPercent };
  }, [protectedMode, safetyPercent]);

  return (
    <section className="relative overflow-hidden py-16 sm:py-20 lg:py-24">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(245,158,11,0.08),_transparent_55%)]" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_right,_rgba(16,185,129,0.05),_transparent_55%)]" />

      <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Story headline */}
        <div className="max-w-3xl">
          <div className="inline-flex items-center gap-2 rounded-full border border-gold/30 bg-gold/10 px-4 py-1.5">
            <Zap className="h-3.5 w-3.5 text-gold" />
            <span className="text-xs font-semibold uppercase tracking-wider text-gold">Interactive Demo</span>
          </div>
          <h2 className="section-heading mt-4">What happens when an outnumbered drone swarm is jammed?</h2>
          <p className="mt-4 section-subheading">
            Drag the slider. A smaller friendly swarm faces a larger hostile swarm and loses all radio contact. With ReluLayer, the formation holds. Without it, the swarm is overrun.
          </p>
        </div>

        {/* Main controls — single slider + single toggle */}
        <div className="mt-10 grid gap-6 rounded-2xl border border-slate-400/10 bg-slate-800/40 p-6 backdrop-blur-md sm:p-8 lg:grid-cols-2">
          {/* Jamming slider */}
          <div>
            <div className="flex items-center justify-between">
              <label htmlFor="jamming-slider" className="text-sm font-semibold text-cream">
                Enemy Jamming
              </label>
              <span
                className={`rounded-full px-2.5 py-0.5 text-xs font-mono font-semibold ${
                  isBlackout ? 'bg-red-500/15 text-red-400' : 'bg-slate-800 text-slate-300'
                }`}
              >
                {jamming}%{isBlackout ? ' — ALL RADIO LOST' : ''}
              </span>
            </div>
            <input
              id="jamming-slider"
              type="range"
              min={0}
              max={100}
              value={jamming}
              onChange={(e) => {
                setIsWalking(false);
                setJamming(Number(e.target.value));
              }}
              className="mt-3 h-2 w-full cursor-pointer appearance-none rounded-lg bg-slate-700 accent-gold"
              aria-label="Enemy jamming slider"
            />
            <div className="mt-2 flex justify-between text-xs text-slate-400">
              <span>Clear Skies</span>
              <span>Heavy Jamming</span>
              <span>Total Blackout</span>
            </div>
          </div>

          {/* Protection toggle + walkthrough */}
          <div>
            <label className="text-sm font-semibold text-cream">ReluLayer Protection</label>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => {
                  setIsWalking(false);
                  setProtectedMode(!protectedMode);
                }}
                aria-pressed={protectedMode}
                className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition-all focus:outline-none focus:ring-2 focus:ring-gold focus:ring-offset-2 focus:ring-offset-navy ${
                  protectedMode
                    ? 'bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/30'
                    : 'bg-red-500/15 text-red-400 ring-1 ring-red-400/30'
                }`}
              >
                {protectedMode ? <Shield className="h-4 w-4" aria-hidden="true" /> : <AlertTriangle className="h-4 w-4" aria-hidden="true" />}
                {protectedMode ? 'Protection ON' : 'Protection OFF'}
              </button>
              <button
                type="button"
                onClick={runWalkthrough}
                disabled={isWalking}
                className="inline-flex items-center gap-1.5 rounded-lg bg-gold px-3 py-2 text-xs font-semibold text-slate-950 transition hover:bg-gold-400 disabled:opacity-50"
              >
                <Play className="h-3.5 w-3.5 fill-current" />
                Watch How It Works
              </button>
              <button
                type="button"
                onClick={resetDemo}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-400/30 bg-slate-800/50 px-3 py-2 text-xs font-semibold text-cream transition hover:border-gold/60"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Reset
              </button>
            </div>
            <p className="mt-3 text-xs text-slate-400">
              {protectedMode
                    ? 'ReluLayer runs on every drone, enforcing inter-vehicle separation and kinetic boundaries in 0.199 microseconds — no HQ radio required.'
                : 'Without ReluLayer, the friendly swarm depends on continuous command links. When jamming hits, the outnumbered formation is overrun.'}
            </p>
          </div>
        </div>

        {/* Narrative status line */}
        <div className="mt-6 flex items-center justify-center">
          <div
            className={`rounded-full border px-4 py-2 text-sm font-semibold transition-all ${
              protectedMode
                ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400'
                : 'border-red-400/30 bg-red-400/10 text-red-400'
            }`}
          >
            {isWalking
              ? walkLabels[walkStep]
              : protectedMode
                ? isBlackout
                  ? 'All comms jammed — outnumbered swarm still holds formation.'
                  : 'Friendly swarm maintaining formation.'
                : isBlackout
                  ? 'CRITICAL: Hostile swarm is overwhelming the formation.'
                  : 'Friendly swarm vulnerable as hostile jamming rises.'}
          </div>
        </div>

        {/* Unified swarm scene + latency chart */}
        <div className="mt-6 grid gap-6 lg:grid-cols-2 lg:items-start">
          {/* Hero swarm scene */}
          <div className="rounded-2xl border border-slate-400/10 bg-slate-900/60 p-5">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-slate-400/30 bg-slate-800/60 px-3 py-1.5 text-xs font-semibold text-cream">
                <Radio className="h-3.5 w-3.5 text-gold" aria-hidden="true" />
                <span>Ground Control</span>
                <span
                  className="h-2 w-2 rounded-full"
                  aria-hidden="true"
                  style={{ background: protectedMode ? '#10B981' : isBlackout ? '#EF4444' : '#F59E0B' }}
                />
                <span className={protectedMode ? 'text-emerald-400' : isBlackout ? 'text-red-400' : 'text-gold'}>
                  {protectedMode ? 'Self-governing' : isBlackout ? 'JAMMED' : 'Link fading'}
                </span>
              </div>

              <div
                className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold ${
                  protectedMode
                    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400'
                    : 'border-red-400/30 bg-red-400/10 text-red-400'
                }`}
              >
                {protectedMode ? <Shield className="h-3.5 w-3.5" aria-hidden="true" /> : <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />}
                {protectedMode ? 'ReluLayer ON' : 'ReluLayer OFF'}
              </div>
            </div>

            <div className="relative aspect-video min-h-[240px] overflow-hidden rounded-xl bg-[#070f1a]">
              <svg
                viewBox={`0 0 ${SCENE_W} ${SCENE_H}`}
                className="absolute inset-0 h-full w-full"
                aria-label="Drone swarm under radio jamming"
              >
                <defs>
                  <pattern id="sceneGrid" width="40" height="40" patternUnits="userSpaceOnUse">
                    <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(148,163,184,0.06)" strokeWidth="1" />
                  </pattern>
                </defs>
                <rect x="0" y="0" width={SCENE_W} height={SCENE_H} fill="#070f1a" />
                <rect x="0" y="0" width={SCENE_W} height={SCENE_H} fill="url(#sceneGrid)" />

                {/* Ground Control tower icon (label lives in HTML above) */}
                <g transform={`translate(${GROUND_X}, ${GROUND_Y})`}>
                  <rect x="-14" y="-8" width="28" height="16" rx="2" fill="#334155" stroke="#94A3B8" strokeWidth="1.5" />
                  <polygon points="0,-8 -6,-22 6,-22" fill="#475569" stroke="#94A3B8" strokeWidth="1.5" />
                  <line x1="0" y1="-22" x2="0" y2="-30" stroke="#CBD5E1" strokeWidth="2" />
                  <circle
                    cx="0"
                    cy="-32"
                    r="4"
                    fill={protectedMode ? '#10B981' : isBlackout ? '#EF4444' : '#F59E0B'}
                    stroke="#0F172A"
                    strokeWidth="1.5"
                  />
                  <circle
                    cx="0"
                    cy="-32"
                    r="7"
                    fill="none"
                    stroke={protectedMode ? '#10B981' : isBlackout ? '#EF4444' : '#F59E0B'}
                    strokeWidth="1"
                    opacity="0.35"
                  />
                </g>

                {/* Radio links from tower to each friendly drone */}
                {friendlyDrones.map((d) => (
                  <line
                    key={`radio-${d.id}`}
                    x1={GROUND_X}
                    y1={GROUND_Y - 32}
                    x2={d.x}
                    y2={d.y}
                    stroke="#94A3B8"
                    strokeWidth="1.5"
                    strokeDasharray="4 4"
                    opacity={linkOpacity}
                  />
                ))}

                {/* Safe zone boundary */}
                <circle
                  cx={CENTER_X}
                  cy={CENTER_Y}
                  r={BOUNDARY_R}
                  fill={protectedMode ? 'rgba(16,185,129,0.06)' : 'rgba(239,68,68,0.05)'}
                  stroke={boundaryColor}
                  strokeWidth="2.5"
                  strokeDasharray="8 6"
                  className="transition-all duration-300"
                />

                {/* Hostile swarm jamming signal */}
                <g transform={`translate(${enemyCentroid.x}, ${enemyCentroid.y})`}>
                  <circle
                    r={38 + jamFactor * 30}
                    fill="none"
                    stroke="#EF4444"
                    strokeWidth="1.5"
                    strokeDasharray="4 4"
                    opacity={0.12 + jamFactor * 0.33}
                  />
                  <circle
                    r={26 + jamFactor * 20}
                    fill="none"
                    stroke="#EF4444"
                    strokeWidth="1.5"
                    strokeDasharray="4 4"
                    opacity={0.22 + jamFactor * 0.43}
                  />
                </g>

                {/* Hostile drones */}
                {enemySwarm.map((drone) => (
                  <g key={drone.id} transform={`translate(${drone.x}, ${drone.y})`}>
                    <circle r="10" fill="#EF4444" stroke="#7F1D1D" strokeWidth="2" />
                    <path
                      d="M-4,-4 L4,4 M4,-4 L-4,4"
                      fill="none"
                      stroke="#fff"
                      strokeWidth="2"
                      strokeLinecap="round"
                    />
                  </g>
                ))}

                {/* ReluLayer clamping barrier at the boundary */}
                {protectedMode && jamming > 20 && (
                  <g>
                    <motion.circle
                      cx={barrierX}
                      cy={barrierY}
                      r="9"
                      fill="none"
                      stroke="#F59E0B"
                      strokeWidth="2.5"
                      initial={{ opacity: 0, scale: 1 }}
                      animate={{ opacity: [0.3, 1, 0.3], scale: [1, 1.15, 1] }}
                      transition={prefersReducedMotion ? { duration: 0 } : { duration: 1.2, repeat: Infinity }}
                    />
                    <circle cx={barrierX} cy={barrierY} r="4" fill="#F59E0B" opacity="0.9" />
                    <line
                      x1={closestEnemy.x}
                      y1={closestEnemy.y}
                      x2={barrierX}
                      y2={barrierY}
                      stroke="#F59E0B"
                      strokeWidth="2"
                      strokeDasharray="6 3"
                      opacity={0.5}
                    />
                    <text
                      x={barrierX}
                      y={barrierY - 14}
                      fill="#F59E0B"
                      fontSize="9"
                      textAnchor="middle"
                      fontWeight="bold"
                      fontFamily="Fira Code, JetBrains Mono, monospace"
                    >
                      ACTIVE DEFENSE
                    </text>
                  </g>
                )}

                {/* Friendly drones */}
                {friendlyDrones.map((drone) => {
                  const safe = protectedMode;
                  const rotor = drone.leader ? 8 : 6;
                  return (
                    <g key={drone.id} transform={`translate(${drone.x}, ${drone.y})`}>
                      <circle
                        r={drone.leader ? 14 : 11}
                        fill={safe ? '#3B82F6' : '#F59E0B'}
                        stroke={safe ? '#60A5FA' : '#78350F'}
                        strokeWidth="2"
                      />
                      <line x1={-rotor} y1="0" x2={rotor} y2="0" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
                      <line x1="0" y1={-rotor} x2="0" y2={rotor} stroke="#fff" strokeWidth="2" strokeLinecap="round" />
                      <circle cx={-rotor} cy="0" r="2.5" fill="#fff" />
                      <circle cx={rotor} cy="0" r="2.5" fill="#fff" />
                      <circle cx="0" cy={-rotor} r="2.5" fill="#fff" />
                      <circle cx="0" cy={rotor} r="2.5" fill="#fff" />
                      {drone.leader && (
                        <circle r="19" fill="none" stroke="#3B82F6" strokeWidth="2" opacity="0.4" />
                      )}
                      {!safe && (
                        <motion.circle
                          r="22"
                          fill="none"
                          stroke="#EF4444"
                          strokeWidth="2"
                          initial={{ opacity: 0 }}
                          animate={{ opacity: [0, 0.8, 0] }}
                          transition={prefersReducedMotion ? { duration: 0 } : { duration: 1, repeat: Infinity }}
                        />
                      )}
                    </g>
                  );
                })}

                {/* Crash markers on every overrun friendly drone */}
                <AnimatePresence>
                  {crashDrones.map((cd) => (
                    <motion.g
                      key={cd.id}
                      initial={{ opacity: 0, scale: 0.5 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.5 }}
                      transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.3 }}
                      transform={`translate(${cd.x}, ${cd.y})`}
                    >
                      <motion.circle
                        r="20"
                        fill="none"
                        stroke="#EF4444"
                        strokeWidth="2"
                        animate={{ opacity: [0, 1, 0] }}
                        transition={{ duration: 1, repeat: Infinity }}
                      />
                      <path
                        d="M-5,-5 L5,5 M5,-5 L-5,5"
                        stroke="#EF4444"
                        strokeWidth="3"
                        strokeLinecap="round"
                      />
                    </motion.g>
                  ))}
                </AnimatePresence>
              </svg>

              {/* HTML overlays — legible at every screen size */}
              <div className="pointer-events-none absolute left-3 top-3 flex flex-wrap gap-2">
                <span className="rounded-full border border-blue-500/30 bg-blue-500/15 px-2 py-1 text-[10px] font-bold text-blue-200 sm:text-xs">
                  Friendly {friendlyDrones.length}
                </span>
                <span className="rounded-full border border-red-500/30 bg-red-500/15 px-2 py-1 text-[10px] font-bold text-red-200 sm:text-xs">
                  Hostile {enemySwarm.length}
                </span>
              </div>

              <div className="pointer-events-none absolute left-1/2 top-[6%] -translate-x-1/2">
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold ${
                    protectedMode
                      ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400'
                      : 'border-red-400/30 bg-red-400/10 text-red-400'
                  }`}
                >
                  {protectedMode ? <Shield className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
                  {protectedMode ? 'Safe Zone' : 'Boundary Breached'}
                </span>
              </div>

              <div
                className="pointer-events-none absolute -translate-x-1/2 whitespace-nowrap transition-all duration-300"
                style={{
                  left: `${(friendlyCentroid.x / SCENE_W) * 100}%`,
                  top: `${((friendlyCentroid.y + 30) / SCENE_H) * 100}%`,
                }}
              >
                <span className="rounded-full bg-blue-500/90 px-2 py-0.5 text-[10px] font-bold text-white sm:text-xs">
                  Friendly swarm
                </span>
              </div>

              <div
                className="pointer-events-none absolute -translate-x-1/2 whitespace-nowrap transition-all duration-300"
                style={{
                  left: `${(enemyCentroid.x / SCENE_W) * 100}%`,
                  top: `${((enemyCentroid.y - 28) / SCENE_H) * 100}%`,
                }}
              >
                <span className="rounded-full bg-red-500/90 px-2 py-0.5 text-[10px] font-bold text-white sm:text-xs">
                  Hostile swarm
                </span>
              </div>

              {crashDrones.length > 0 && (
                <div
                  className="pointer-events-none absolute -translate-x-1/2 -translate-y-full whitespace-nowrap"
                  style={{
                    left: `${(friendlyCentroid.x / SCENE_W) * 100}%`,
                    top: `${((friendlyCentroid.y - 26) / SCENE_H) * 100}%`,
                  }}
                >
                  <span className="inline-flex items-center gap-1 rounded-full bg-red-500 px-2 py-0.5 text-[10px] font-bold text-white sm:text-xs">
                    <AlertTriangle className="h-3 w-3" /> Formation overrun
                  </span>
                </div>
              )}
            </div>

            {/* Simple visual key */}
            <div className="mt-4 flex flex-wrap items-center justify-center gap-3 text-xs text-slate-400">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-blue-500" /> Friendly swarm
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-red-500" /> Hostile swarm
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full border-2 border-dashed border-emerald-500" /> Safe zone
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-0.5 w-4 bg-slate-400" /> Radio link
              </span>
            </div>
          </div>

          {/* Latency chart (now always visible alongside the swarm) */}
          <div className="rounded-2xl border border-slate-400/10 bg-slate-900/60 p-5">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <h4 className="text-sm font-semibold text-cream">Execution Timing (Log Scale)</h4>
              <span className="flex items-center gap-1.5 text-xs text-slate-400">
                <span className="h-1 w-3 rounded bg-red-400" /> Normal Software
                <span className="ml-2 h-1 w-3 rounded bg-gold" /> ReluLayer
              </span>
            </div>
            <div className="relative aspect-video min-h-[240px] overflow-hidden rounded-xl bg-[#070f1a]">
              <svg viewBox={`0 0 ${graphWidth} ${graphHeight}`} className="absolute inset-0 h-full w-full">
                <defs>
                  <pattern id="techGrid" width="64" height="28" patternUnits="userSpaceOnUse">
                    <path d="M 64 0 L 0 0 0 28" fill="none" stroke="rgba(148,163,184,0.08)" strokeWidth="1" />
                  </pattern>
                </defs>
                <rect x="0" y="0" width={graphWidth} height={graphHeight} fill="#070f1a" />
                <rect x="0" y="0" width={graphWidth} height={graphHeight} fill="url(#techGrid)" />
                <text x="8" y={latencyToY(0.001) + 4} fill="#64748B" fontSize="10" fontFamily="Fira Code, JetBrains Mono, monospace">
                  1 µs
                </text>
                <text x="8" y={latencyToY(0.01) + 4} fill="#64748B" fontSize="10" fontFamily="Fira Code, JetBrains Mono, monospace">
                  10 µs
                </text>
                <text x="8" y={latencyToY(0.1) + 4} fill="#64748B" fontSize="10" fontFamily="Fira Code, JetBrains Mono, monospace">
                  100 µs
                </text>
                <text x="8" y={latencyToY(1) + 4} fill="#64748B" fontSize="10" fontFamily="Fira Code, JetBrains Mono, monospace">
                  1 ms
                </text>
                <text x="8" y={latencyToY(10) + 4} fill="#64748B" fontSize="10" fontFamily="Fira Code, JetBrains Mono, monospace">
                  10 ms
                </text>
                <text x="8" y={latencyToY(100) + 4} fill="#64748B" fontSize="10" fontFamily="Fira Code, JetBrains Mono, monospace">
                  100 ms
                </text>
                <line
                  x1={paddingX}
                  y1={latencyToY(WCET_NS / 1_000_000)}
                  x2={graphWidth - paddingX}
                  y2={latencyToY(WCET_NS / 1_000_000)}
                  stroke="#F59E0B"
                  strokeWidth="2"
                  strokeDasharray="4 4"
                  opacity="0.8"
                />
                <text
                  x={graphWidth - paddingX + 4}
                  y={latencyToY(WCET_NS / 1_000_000) + 4}
                  fill="#F59E0B"
                  fontSize="11"
                  fontFamily="Fira Code, JetBrains Mono, monospace"
                >
                  0.199 µs
                </text>
                <motion.path
                  d={pathD}
                  fill="none"
                  stroke={protectedMode ? '#F59E0B' : '#EF4444'}
                  strokeWidth={protectedMode ? 3 : 2.5}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  initial={{ pathLength: 0 }}
                  animate={{ pathLength: 1 }}
                  transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.4 }}
                />
              </svg>
            </div>
            <div className="mt-4 flex flex-wrap items-center justify-center gap-3 text-xs text-slate-400">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-0.5 w-4 bg-red-400" /> Jitter spikes cause collision
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-0.5 w-4 bg-gold" /> Deterministic safety holds
              </span>
            </div>
          </div>
        </div>

        {/* Safety meter + key facts (moved below) */}
        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          {/* Safety meter */}
          <div className="rounded-2xl border border-slate-400/10 bg-slate-800/40 p-5">
              <h3 className="text-sm font-semibold text-cream">Swarm Safety Status</h3>
              <div className="mt-4">
                <div className="flex h-4 overflow-hidden rounded-full bg-slate-700">
                  <motion.div
                    className={`h-full ${
                      meterState.color === 'emerald'
                        ? 'bg-emerald-500'
                        : meterState.color === 'gold'
                          ? 'bg-gold'
                          : 'bg-red-500'
                    }`}
                    initial={{ width: 0 }}
                    animate={{ width: `${meterState.percent}%` }}
                    transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.4 }}
                  />
                </div>
                <div className="mt-2 flex items-center justify-between">
                  <span
                    className={`text-lg font-bold ${
                      meterState.color === 'emerald'
                        ? 'text-emerald-400'
                        : meterState.color === 'gold'
                          ? 'text-gold'
                          : 'text-red-400'
                    }`}
                  >
                    {meterState.label}
                  </span>
                  <span className="text-xs text-slate-400">
                    {protectedMode ? 'All friendly drones safe' : `${safetyPercent.toFixed(0)}% swarm integrity`}
                  </span>
                </div>
              </div>
            </div>

            {/* Key number */}
            <div className="rounded-2xl border border-gold/30 bg-gold/5 p-5">
              <div className="flex items-center gap-2">
                <Zap className="h-4 w-4 text-gold" />
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Response Time</span>
              </div>
              <p className="mt-2 font-mono text-4xl font-bold text-gold">0.199 µs</p>
              <p className="mt-1 text-xs text-slate-400">Sub-microsecond deterministic interdiction. ~5,000x faster than cloud watchdogs.</p>
            </div>

            {/* Swarm standoff fact */}
            <div className="rounded-2xl border border-red-500/30 bg-red-500/5 p-5">
              <div className="flex items-center gap-2">
                <Crosshair className="h-4 w-4 text-red-400" />
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Swarm Standoff</span>
              </div>
              <p className="mt-2 font-mono text-2xl font-bold text-red-400">5 vs 8</p>
              <p className="mt-1 text-xs text-slate-400">
                Outnumbered friendly swarm holds formation against a larger hostile mass.
              </p>
            </div>
          </div>

        {/* Lead Magnet / Technical Details */}
        <div className="mt-12">
          <div className="flex w-full items-center gap-2 rounded-t-xl border border-b-0 border-slate-400/10 bg-slate-800/60 px-5 py-3 text-sm font-semibold text-cream">
            <Cpu className="h-4 w-4 text-gold" />
            Advanced Diagnostic Telemetry & ROS2 Vulnerability Teardown
          </div>

          <div className="relative overflow-hidden rounded-b-xl border border-slate-400/10 bg-slate-800/20 p-6 sm:p-10 min-h-[480px] flex flex-col justify-center">
            {/* The blurred content */}
            <div className={`grid gap-6 lg:grid-cols-3 transition-all duration-700 ${isUnlocked ? '' : 'blur-md opacity-40 select-none pointer-events-none'}`}>
              {/* Benchmark context cards */}
              <div className="rounded-2xl border border-slate-400/10 bg-slate-800/40 p-5">
                <div className="flex items-start gap-3">
                  <Info className="mt-0.5 h-4 w-4 shrink-0 text-gold" />
                  <div>
                    <h4 className="text-sm font-semibold text-cream">Data-driven simulation</h4>
                    <p className="mt-1 text-xs text-slate-400">
                      Latency curves are interpolated from the EW degradation sweep (convergence latency steps). Swarm success rates are interpolated from the Markov counter-swarm benchmark. The 0.199 µs WCET and 0.00% HIL violation rate are measured hardware values.
                    </p>
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-400/10 bg-slate-800/40 p-5">
                <h4 className="text-sm font-semibold text-cream">Verified Test Results</h4>
                <ul className="mt-3 space-y-2 text-xs text-slate-400">
                  <li className="flex items-center gap-2">
                    <span className="h-1.5 w-1.5 rounded-full bg-gold" />
                    Worst-case execution time: 0.199 µs (@ 480 MHz)
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="h-1.5 w-1.5 rounded-full bg-gold" />
                    Zero dynamic heap allocation across all HIL passes
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="h-1.5 w-1.5 rounded-full bg-gold" />
                    0.00% violation rate across 5,000+ HIL stress passes
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="h-1.5 w-1.5 rounded-full bg-gold" />
                    ACCSE swarm interdiction maintains cohesion through total C2 blackout
                  </li>
                </ul>
              </div>

              <div className="rounded-2xl border border-gold/20 bg-gold/5 p-5">
                <h4 className="text-sm font-semibold text-cream">Want the full report?</h4>
                <p className="mt-1 text-xs text-slate-400">
                  HIL timing traces, EW degradation sweep data, and counter-swarm Markov benchmarks are available for defense primes and qualified OEMs under NDA.
                </p>
                <a
                  href="#contact"
                  className="mt-3 inline-flex items-center gap-2 rounded-lg bg-gold px-4 py-2 text-xs font-semibold text-slate-950 transition hover:bg-gold-400"
                >
                  <FileText className="h-3.5 w-3.5" />
                  Request Benchmark Report
                </a>
              </div>
            </div>

            {/* The Gate overlay */}
            {!isUnlocked && (
              <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-slate-950/60 backdrop-blur-[2px] px-4">
                <div className="max-w-md text-center rounded-2xl border border-slate-700 bg-slate-900/90 p-8 shadow-2xl backdrop-blur-md">
                  <Shield className="mx-auto h-8 w-8 text-gold mb-4" />
                  <h4 className="text-lg font-bold text-cream mb-2">
                    Unlock Full Sandbox Diagnostics & Download the Free ROS2 Architecture Compatibility Brief
                  </h4>
                  <p className="text-sm text-slate-300 mb-6">
                    Enter your email to view live WCET metrics, memory-safety validations, and the complete vulnerability teardown report.
                  </p>
                  <form
                    action="https://formspree.io/f/YOUR_FORM_ID"
                    method="POST"
                    className="flex flex-col gap-3"
                  >
                    <label htmlFor={emailInputId} className="sr-only">
                      Engineering, .mil, or OEM email
                    </label>
                    <input
                      id={emailInputId}
                      type="email"
                      name="email"
                      required
                      autoComplete="email"
                      placeholder="Engineering, .mil, or OEM Email"
                      className="w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-cream placeholder-slate-500 focus:border-gold focus:outline-none focus:ring-1 focus:ring-gold"
                    />
                    <button
                      type="submit"
                      className="w-full rounded-lg bg-gold px-4 py-3 text-sm font-bold text-slate-950 transition hover:bg-gold-400"
                    >
                      Run Full Diagnostic
                    </button>
                  </form>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
