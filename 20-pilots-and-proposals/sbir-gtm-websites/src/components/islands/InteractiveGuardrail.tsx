import { useState } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import {
  Shield,
  AlertTriangle,
  Zap,
  CheckCircle2,
  Lightbulb,
  Activity,
  Cpu,
  Gauge,
  Crosshair,
  XCircle,
} from 'lucide-react';

const hilSpecs = [
  { label: 'MCU', value: 'ARM Cortex-M7 / STM32H7' },
  { label: 'FC', value: 'Pixhawk 6X FMUv6X' },
  { label: 'WCET', value: '0.199 µs' },
  { label: 'Variance', value: '0.00% across 5,000 HIL passes' },
];

export default function InteractiveGuardrail() {
  const prefersReducedMotion = useReducedMotion();
  const reducedTransition = prefersReducedMotion ? { duration: 0 } : undefined;

  const [activeTab, setActiveTab] = useState<'executive' | 'telemetry'>('executive');
  const [showInterdicted, setShowInterdicted] = useState(true);
  const [perspective, setPerspective] = useState<'single' | 'swarm'>('single');

  return (
    <div className="rounded-2xl border border-slate-400/10 bg-navy-300 p-5 sm:p-6 lg:p-8">
      <div className="relative flex flex-col items-center gap-6 sm:flex-row sm:justify-between">
        <div>
          <h3 className="text-xl font-bold text-cream">Interactive Guardrail Demo</h3>
          <p className="mt-1 text-sm text-slate-400">
            Toggle between the executive flight view and the benchtop hardware trace.
          </p>
        </div>

        <div className="inline-flex rounded-full border border-slate-400/20 bg-slate-800/50 p-1">
          <button
            type="button"
            onClick={() => setActiveTab('executive')}
            className={`rounded-full px-4 py-2 text-sm font-semibold transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-gold focus:ring-offset-2 focus:ring-offset-navy ${
              activeTab === 'executive'
                ? 'bg-gold text-slate-950 shadow'
                : 'text-slate-400 hover:text-cream'
            }`}
            aria-pressed={activeTab === 'executive'}
          >
            Executive Flight View
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('telemetry')}
            className={`rounded-full px-4 py-2 text-sm font-semibold transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-gold focus:ring-offset-2 focus:ring-offset-navy ${
              activeTab === 'telemetry'
                ? 'bg-gold text-slate-950 shadow'
                : 'text-slate-400 hover:text-cream'
            }`}
            aria-pressed={activeTab === 'telemetry'}
          >
            Benchtop Scope Telemetry
          </button>
        </div>
      </div>

      <div className="relative mt-8 min-h-[420px]">
        <AnimatePresence mode="wait">
          {activeTab === 'executive' ? (
            <motion.div
              key="executive"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.4, ease: 'easeOut' }}
              className="space-y-6"
            >
              <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
                <div className="flex items-center gap-3">
                  <span className="text-sm text-slate-400">Compare scenarios:</span>
                  <button
                    type="button"
                    onClick={() => setShowInterdicted(!showInterdicted)}
                    aria-pressed={showInterdicted}
                    className="inline-flex items-center gap-2 rounded-full border border-slate-400/20 bg-slate-800/50 px-3 py-1.5 text-sm font-semibold text-cream transition hover:border-gold/60 focus:outline-none focus:ring-2 focus:ring-gold focus:ring-offset-2 focus:ring-offset-navy"
                  >
                    {showInterdicted ? <Shield className="h-4 w-4 text-gold" aria-hidden="true" /> : <AlertTriangle className="h-4 w-4 text-red-400" aria-hidden="true" />}
                    {showInterdicted ? 'Showing ReluLayer™ Protected' : 'Showing Unprotected AI Flight'}
                  </button>
                </div>
                
                <div className="inline-flex rounded-full border border-slate-400/20 bg-slate-800/50 p-1">
                  <button
                    type="button"
                    onClick={() => setPerspective('single')}
                    aria-pressed={perspective === 'single'}
                    className={`rounded-full px-4 py-1.5 text-xs font-semibold transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-gold focus:ring-offset-2 focus:ring-offset-navy ${
                      perspective === 'single'
                        ? 'bg-slate-700 text-cream shadow'
                        : 'text-slate-400 hover:text-cream'
                    }`}
                  >
                    Single-Node Flight
                  </button>
                  <button
                    type="button"
                    onClick={() => setPerspective('swarm')}
                    aria-pressed={perspective === 'swarm'}
                    className={`rounded-full px-4 py-1.5 text-xs font-semibold transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-gold focus:ring-offset-2 focus:ring-offset-navy ${
                      perspective === 'swarm'
                        ? 'bg-slate-700 text-cream shadow'
                        : 'text-slate-400 hover:text-cream'
                    }`}
                  >
                    Swarm Formation Defense
                  </button>
                </div>
              </div>

              <div className="grid gap-6 md:grid-cols-2">
                <div className={`rounded-2xl border p-5 transition-all duration-500 ${showInterdicted ? 'opacity-60 border-slate-400/10 bg-slate-800/30' : 'border-red-400/30 bg-red-400/10'}`}>
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-400/15 text-red-400">
                      <AlertTriangle className="h-5 w-5" aria-hidden="true" />
                    </div>
                    <div>
                      <p className="font-semibold text-cream">Unprotected AI Flight</p>
                      <p className="text-xs text-slate-400">No deterministic safety governor</p>
                    </div>
                  </div>

                  <div className="mt-5">
                    {perspective === 'single' ? (
                      <svg viewBox="0 0 360 200" className="h-auto w-full" aria-label="Unprotected aircraft trajectory crosses the physical safety wall">
                        <defs>
                          <linearGradient id="dangerStroke" x1="0" y1="0" x2="1" y2="0">
                            <stop offset="0%" stopColor="#EF4444" stopOpacity="0.4" />
                            <stop offset="100%" stopColor="#EF4444" />
                          </linearGradient>
                        </defs>

                        <line x1="0" y1="170" x2="360" y2="170" stroke="#334155" strokeWidth="2" strokeDasharray="6 4" />
                        <line x1="230" y1="20" x2="230" y2="190" stroke="#EF4444" strokeWidth="2" strokeDasharray="4 4" opacity="0.6" />
                        <text x="232" y="16" fill="#EF4444" fontSize="11" fontFamily="Fira Code, JetBrains Mono, monospace">PHYSICAL SAFETY WALL</text>

                        <path
                          d="M 40 150 C 120 150, 160 40, 230 30 L 300 10"
                          fill="none"
                          stroke="url(#dangerStroke)"
                          strokeWidth="4"
                          strokeLinecap="round"
                          className="transition-all duration-700"
                        />

                        <g transform="translate(300, 10) rotate(15)">
                          <path d="M0 0 L18 5 L0 10 L3 5 Z" fill="#EF4444" />
                        </g>

                        <g transform="translate(310, 80)">
                          <XCircle className="text-red-400" style={{ width: 24, height: 24 }} aria-hidden="true" />
                        </g>
                      </svg>
                    ) : (
                      <svg viewBox="0 0 360 200" className="h-auto w-full" aria-label="Unprotected 1:N swarm trajectory crosses the physical boundary">
                        <defs>
                          <linearGradient id="swarmDangerStroke" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#EF4444" />
                            <stop offset="100%" stopColor="#EF4444" stopOpacity="0.4" />
                          </linearGradient>
                        </defs>

                        {/* Network lines */}
                        <path d="M 180 40 L 100 100 L 180 160 L 260 100 Z" fill="none" stroke="#334155" strokeWidth="1" strokeDasharray="4 4" opacity="0.4" />
                        <path d="M 180 100 L 180 40 M 180 100 L 100 100 M 180 100 L 260 100" fill="none" stroke="#334155" strokeWidth="1" strokeDasharray="4 4" opacity="0.4" />

                        {/* Safety Envelope Polygon (Collapsing) */}
                        <polygon points="180,70 210,100 180,130 150,100" fill="none" stroke="#EF4444" strokeWidth="1.5" strokeDasharray="4 4" opacity="0.6" />
                        <polygon points="180,80 200,100 180,120 160,100" fill="#EF4444" opacity="0.1" />

                        <text x="180" y="25" fill="#EF4444" fontSize="10" textAnchor="middle" fontFamily="Fira Code, JetBrains Mono, monospace">COLLISION ENVELOPE BREACHED</text>

                        {/* Lead Drone */}
                        <circle cx="180" cy="100" r="10" fill="#3b82f6" />
                        <text x="180" y="103" fill="#fff" fontSize="8" textAnchor="middle" fontWeight="bold">LD</text>

                        {/* Followers */}
                        <circle cx="180" cy="40" r="10" fill="#334155" />
                        <text x="180" y="43" fill="#94A3B8" fontSize="8" textAnchor="middle" fontWeight="bold">F1</text>
                        <circle cx="100" cy="100" r="10" fill="#334155" />
                        <text x="100" y="103" fill="#94A3B8" fontSize="8" textAnchor="middle" fontWeight="bold">F2</text>
                        <circle cx="260" cy="100" r="10" fill="#334155" />
                        <text x="260" y="103" fill="#94A3B8" fontSize="8" textAnchor="middle" fontWeight="bold">F3</text>

                        {/* Spoofed Follower F4 */}
                        <path
                          d="M 180 170 C 170 150, 165 125, 175 90"
                          fill="none"
                          stroke="url(#swarmDangerStroke)"
                          strokeWidth="3"
                          strokeLinecap="round"
                          className="transition-all duration-700"
                        />
                        <circle cx="180" cy="170" r="10" fill="#EF4444" opacity="0.2" />
                        <circle cx="180" cy="170" r="5" fill="#EF4444" />
                        <text x="180" y="185" fill="#EF4444" fontSize="8" textAnchor="middle" fontWeight="bold">F4 (SPOOFED)</text>

                        <g transform="translate(175, 90) rotate(-75)">
                          <path d="M0 0 L14 4 L0 8 L2 4 Z" fill="#EF4444" />
                        </g>
                        <g transform="translate(168, 80)">
                          <XCircle className="text-red-400" style={{ width: 14, height: 14 }} aria-hidden="true" />
                        </g>

                        {/* Telemetry Metrics */}
                        <text x="345" y="40" fill="#94A3B8" fontSize="7" textAnchor="end" fontFamily="monospace">LD-F1: 2.4m</text>
                        <text x="345" y="55" fill="#94A3B8" fontSize="7" textAnchor="end" fontFamily="monospace">LD-F2: 2.4m</text>
                        <text x="345" y="70" fill="#94A3B8" fontSize="7" textAnchor="end" fontFamily="monospace">LD-F3: 2.4m</text>
                        <text x="345" y="85" fill="#EF4444" fontSize="7" textAnchor="end" fontFamily="monospace" fontWeight="bold">LD-F4: 0.4m (CRITICAL)</text>
                      </svg>
                    )}
                  </div>

                  <div className="mt-4 rounded-xl border border-red-400/30 bg-red-400/10 px-4 py-3">
                    <p className="text-sm text-slate-200">
                      <span className="font-semibold text-red-400">
                        {perspective === 'single' ? 'Unsafe command exceeds the boundary.' : 'Compromised node breaches formation.'}
                      </span>{' '}
                      {perspective === 'single' 
                        ? 'The aircraft pitches into an aerodynamic stall or drives a control surface beyond its structural limit.'
                        : 'Adversarial spoofing forces Drone 3 to cross the 2.0m collision radius, threatening a mid-air kinetic strike with Drone 1.'}
                    </p>
                  </div>
                </div>

                <div className={`rounded-2xl border p-5 transition-all duration-500 ${showInterdicted ? 'border-gold/30 bg-gold/10' : 'opacity-60 border-slate-400/10 bg-slate-800/30'}`}>
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gold/15 text-gold">
                      <Shield className="h-5 w-5" aria-hidden="true" />
                    </div>
                    <div>
                      <p className="font-semibold text-cream">ReluLayer™ Interdicted</p>
                      <p className="text-xs text-slate-400">0.199 µs deterministic governor</p>
                    </div>
                  </div>

                  <div className="mt-5">
                    {perspective === 'single' ? (
                      <svg viewBox="0 0 360 200" className="h-auto w-full" aria-label="ReluLayer-protected aircraft trajectory rides along the safe physical envelope">
                        <defs>
                          <linearGradient id="safeStroke" x1="0" y1="0" x2="1" y2="0">
                            <stop offset="0%" stopColor="#F59E0B" stopOpacity="0.5" />
                            <stop offset="100%" stopColor="#F59E0B" />
                          </linearGradient>
                        </defs>

                        <line x1="0" y1="170" x2="360" y2="170" stroke="#334155" strokeWidth="2" strokeDasharray="6 4" />
                        <line x1="230" y1="20" x2="230" y2="190" stroke="#F59E0B" strokeWidth="2" strokeDasharray="4 4" opacity="0.6" />
                        <text x="232" y="16" fill="#F59E0B" fontSize="11" fontFamily="Fira Code, JetBrains Mono, monospace">PHYSICAL SAFETY WALL</text>

                        <path
                          d="M 40 150 C 120 150, 160 40, 230 30 C 230 30, 230 70, 230 110 C 230 140, 260 150, 320 150"
                          fill="none"
                          stroke="url(#safeStroke)"
                          strokeWidth="4"
                          strokeLinecap="round"
                          className="transition-all duration-700"
                        />

                        <g transform="translate(320, 150) rotate(-45)">
                          <path d="M0 0 L18 5 L0 10 L3 5 Z" fill="#F59E0B" />
                        </g>

                        <rect x="236" y="32" width="48" height="138" fill="#F59E0B" fillOpacity="0.08" stroke="#F59E0B" strokeWidth="1" strokeDasharray="4 4" rx="4" />
                        <text x="260" y="180" textAnchor="middle" fill="#F59E0B" fontSize="10" fontFamily="Fira Code, JetBrains Mono, monospace">SAFE ENVELOPE</text>
                      </svg>
                    ) : (
                      <svg viewBox="0 0 360 200" className="h-auto w-full" aria-label="Protected 1:N swarm trajectory projected on the polyhedral boundary">
                        <defs>
                          <linearGradient id="swarmSafeStroke" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#F59E0B" />
                            <stop offset="100%" stopColor="#F59E0B" stopOpacity="0.4" />
                          </linearGradient>
                        </defs>

                        {/* Network lines */}
                        <path d="M 180 40 L 100 100 L 180 160 L 260 100 Z" fill="none" stroke="#334155" strokeWidth="1" strokeDasharray="4 4" opacity="0.4" />
                        <path d="M 180 100 L 180 40 M 180 100 L 100 100 M 180 100 L 260 100" fill="none" stroke="#334155" strokeWidth="1" strokeDasharray="4 4" opacity="0.4" />

                        {/* Safety Envelope Polygon (Active) */}
                        <polygon points="180,60 220,100 180,140 140,100" fill="#F59E0B" opacity="0.1" stroke="#F59E0B" strokeWidth="2" />
                        {/* Pulsing ring effect */}
                        <polygon points="180,55 225,100 180,145 135,100" fill="none" stroke="#F59E0B" strokeWidth="1" opacity="0.3" className="animate-pulse" />

                        <text x="180" y="25" fill="#F59E0B" fontSize="10" textAnchor="middle" fontFamily="Fira Code, JetBrains Mono, monospace">ACTIVE-SET POLYHEDRAL BOUNDARY</text>

                        {/* Lead Drone */}
                        <circle cx="180" cy="100" r="10" fill="#3b82f6" />
                        <text x="180" y="103" fill="#fff" fontSize="8" textAnchor="middle" fontWeight="bold">LD</text>

                        {/* Followers */}
                        <circle cx="180" cy="40" r="10" fill="#334155" />
                        <text x="180" y="43" fill="#94A3B8" fontSize="8" textAnchor="middle" fontWeight="bold">F1</text>
                        <circle cx="100" cy="100" r="10" fill="#334155" />
                        <text x="100" y="103" fill="#94A3B8" fontSize="8" textAnchor="middle" fontWeight="bold">F2</text>
                        <circle cx="260" cy="100" r="10" fill="#334155" />
                        <text x="260" y="103" fill="#94A3B8" fontSize="8" textAnchor="middle" fontWeight="bold">F3</text>

                        {/* Spoofed Follower F4 Clamped */}
                        <path
                          d="M 180 180 C 170 160, 165 140, 160 120"
                          fill="none"
                          stroke="url(#swarmSafeStroke)"
                          strokeWidth="3"
                          strokeLinecap="round"
                          className="transition-all duration-700"
                        />
                        {/* Projected path along the boundary */}
                        <path
                          d="M 160 120 L 145 105"
                          fill="none"
                          stroke="#F59E0B"
                          strokeWidth="3"
                          strokeLinecap="round"
                        />

                        <circle cx="180" cy="180" r="10" fill="#F59E0B" opacity="0.2" />
                        <circle cx="180" cy="180" r="5" fill="#F59E0B" />
                        <text x="180" y="195" fill="#F59E0B" fontSize="8" textAnchor="middle" fontWeight="bold">F4 (SPOOFED)</text>

                        <g transform="translate(145, 105) rotate(-45)">
                          <path d="M0 0 L14 4 L0 8 L2 4 Z" fill="#F59E0B" />
                        </g>

                        <text x="110" y="130" fill="#F59E0B" fontSize="9" fontFamily="Fira Code, JetBrains Mono, monospace">CLAMPED &</text>
                        <text x="110" y="140" fill="#F59E0B" fontSize="9" fontFamily="Fira Code, JetBrains Mono, monospace">PROJECTED</text>

                        {/* Telemetry Metrics */}
                        <text x="345" y="40" fill="#94A3B8" fontSize="7" textAnchor="end" fontFamily="monospace">LD-F1: 2.4m</text>
                        <text x="345" y="55" fill="#94A3B8" fontSize="7" textAnchor="end" fontFamily="monospace">LD-F2: 2.4m</text>
                        <text x="345" y="70" fill="#94A3B8" fontSize="7" textAnchor="end" fontFamily="monospace">LD-F3: 2.4m</text>
                        <text x="345" y="85" fill="#F59E0B" fontSize="7" textAnchor="end" fontFamily="monospace" fontWeight="bold">LD-F4: 1.6m (CLAMPED)</text>
                      </svg>
                    )}
                  </div>

                  <div className="mt-4 rounded-xl border border-gold/30 bg-gold/10 px-4 py-3">
                    <p className="text-sm text-slate-200">
                      <span className="font-semibold text-gold">
                        {perspective === 'single' ? 'Command hits the boundary and is clamped.' : 'Spoofed command is vector-projected.'}
                      </span>{' '}
                      {perspective === 'single'
                        ? 'ReluLayer™ projects the command onto the safe envelope, keeping the aircraft inside its structural and aerodynamic limits.'
                        : <>ReluLayer™ enforces the inter-vehicle spacing (<span className="font-mono text-amber-400 font-semibold">S<sub>v</sub><sup>swarm</sup></span>) locally in 0.199 µs, projecting the trajectory along the safe perimeter without relying on jammed RF mesh communications.</>}
                    </p>
                  </div>
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-3">
                <div className="rounded-xl border border-slate-400/10 bg-slate-800/30 p-5">
                  <div className="flex items-center gap-2 text-gold">
                    <Lightbulb className="h-4 w-4" aria-hidden="true" />
                    <h4 className="font-semibold text-cream">Dual-Control Flight Instructor Metaphor</h4>
                  </div>
                  <p className="mt-2 text-sm text-slate-300">
                    ReluLayer™ acts as the certified flight instructor with override authority. When client AI guidance outputs a dangerous trajectory, ReluLayer™ instantly catches the command and clamps it to safe physical boundaries without shutting down the engine.
                  </p>
                </div>
                <div className="rounded-xl border border-slate-400/10 bg-slate-800/30 p-5">
                  <div className="flex items-center gap-2 text-gold">
                    <Crosshair className="h-4 w-4" aria-hidden="true" />
                    <h4 className="font-semibold text-cream">Deterministic Boundaries</h4>
                  </div>
                  <p className="mt-2 text-sm text-slate-300">
                    No dynamic allocation, no heuristics, no ML inside the loop. A mathematical governor that blocks runaway outputs in 0.199 µs.
                  </p>
                </div>
                <div className="rounded-xl border border-slate-400/10 bg-slate-800/30 p-5">
                  <div className="flex items-center gap-2 text-gold">
                    <Gauge className="h-4 w-4" aria-hidden="true" />
                    <h4 className="font-semibold text-cream">Measurable Latency</h4>
                  </div>
                  <p className="mt-2 text-sm text-slate-300">
                    Worst-case interdiction latency of 0.199 µs on ARM Cortex-M7 class silicon.
                  </p>
                </div>
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="telemetry"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.4, ease: 'easeOut' }}
              className="space-y-6"
            >
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gold/15 text-gold">
                    <Activity className="h-5 w-5" aria-hidden="true" />
                  </div>
                  <div>
                    <p className="font-semibold text-cream">Hardware-in-the-Loop Benchtop Trace</p>
                    <p className="text-sm text-slate-400">STM32H7 / Pixhawk 6X — 480 MHz, 0.199 µs WCET</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 rounded-lg border border-gold/30 bg-gold/10 px-3 py-2">
                  <Zap className="h-4 w-4 text-gold" aria-hidden="true" />
                  <span className="text-xs font-mono font-semibold text-gold">0.199 µs INTERDICTION</span>
                  <CheckCircle2 className="h-4 w-4 text-gold" aria-hidden="true" />
                </div>
              </div>

              <div className="rounded-xl border border-slate-400/10 bg-navy-300/80 p-4">
                <svg viewBox="0 0 640 260" className="h-auto w-full" aria-label="Oscilloscope step response showing AI command input in red and ReluLayer clamped output in gold">
                  <defs>
                    <pattern id="grid" width="80" height="40" patternUnits="userSpaceOnUse">
                      <path d="M 80 0 L 0 0 0 40" fill="none" stroke="rgba(148,163,184,0.10)" strokeWidth="1" />
                    </pattern>
                  </defs>
                  <rect x="0" y="0" width="640" height="260" fill="#070f1a" />
                  <rect x="0" y="0" width="640" height="260" fill="url(#grid)" />

                  <line x1="0" y1="200" x2="640" y2="200" stroke="rgba(245,158,11,0.25)" strokeWidth="1.5" />
                  <line x1="0" y1="80" x2="640" y2="80" stroke="#F59E0B" strokeWidth="1" strokeDasharray="4 4" opacity="0.6" />
                  <text x="8" y="72" fill="#F59E0B" fontSize="11" fontFamily="Fira Code, JetBrains Mono, monospace">SAFE CLAMP LEVEL</text>

                  <text x="40" y="245" fill="#94A3B8" fontSize="12" fontFamily="Fira Code, JetBrains Mono, monospace">AI COMMAND INPUT</text>
                  <text x="520" y="245" fill="#94A3B8" fontSize="12" fontFamily="Fira Code, JetBrains Mono, monospace">CLAMPED OUTPUT</text>

                  <path
                    d="M 40 200 L 120 200 L 120 40 L 400 40 L 400 200 L 600 200"
                    fill="none"
                    stroke="#EF4444"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />

                  <path
                    d="M 40 200 L 120 200 L 120 80 L 200 80 L 200 200"
                    fill="none"
                    stroke="#F59E0B"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeDasharray="6 3"
                  />

                  <line x1="200" y1="20" x2="200" y2="240" stroke="#F59E0B" strokeWidth="2" strokeDasharray="4 4" opacity="0.8" />

                  <rect x="210" y="24" width="150" height="56" fill="rgba(11,25,44,0.85)" stroke="rgba(245,158,11,0.4)" strokeWidth="1" rx="4" />
              <text x="220" y="50" fill="#F59E0B" fontSize="13" fontWeight="bold" fontFamily="Fira Code, JetBrains Mono, monospace">0.199 µs</text>
              <text x="220" y="70" fill="#F8FAFC" fontSize="12" fontFamily="Fira Code, JetBrains Mono, monospace">WCET @ 480 MHz</text>

                  <g transform="translate(420, 50)">
                    <rect x="0" y="0" width="14" height="4" fill="#EF4444" rx="1" />
                    <text x="20" y="8" fill="#EF4444" fontSize="11" fontFamily="Fira Code, JetBrains Mono, monospace">Unfiltered AI command</text>
                    <rect x="0" y="20" width="14" height="4" fill="#F59E0B" rx="1" />
                    <text x="20" y="28" fill="#F59E0B" fontSize="11" fontFamily="Fira Code, JetBrains Mono, monospace">ReluLayer™ clamped output</text>
                  </g>
                </svg>
              </div>

              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                {hilSpecs.map((spec) => (
                  <div key={spec.label} className="rounded-lg border border-slate-400/10 bg-navy-300/50 px-3 py-3">
                    <p className="text-[10px] font-mono uppercase tracking-wider text-slate-400">{spec.label}</p>
                    <p className="mt-0.5 text-sm font-semibold text-cream">{spec.value}</p>
                  </div>
                ))}
              </div>

              <div className="rounded-lg border border-gold/20 bg-gold/10 px-4 py-3">
                <p className="text-xs text-slate-300">
                  <span className="font-semibold text-gold">Zero-variance guarantee:</span> every unsafe command was blocked within the same 0.199 µs worst-case window across all HIL stress iterations on bare-metal <code className="rounded bg-slate-800/80 px-1 py-0.5 font-mono text-gold">#![no_std]</code> Rust.
                </p>
              </div>

              <div className="rounded-xl border border-gold/20 bg-gold/5 p-5">
                <div className="flex items-center gap-2">
                  <Cpu className="h-4 w-4 text-gold" aria-hidden="true" />
                  <h4 className="font-semibold text-cream">EU AI Act & U.S. DoD Compliance Enforcer</h4>
                </div>
                <ul className="mt-3 space-y-2 text-sm text-slate-300">
                  <li>
                    <strong className="text-cream">Mandatory Safety Component:</strong> Fulfills EU AI Act Annex I & Annex III requirements for mandatory human/deterministic override controls in high-risk autonomous robotics, aviation, and machinery.
                  </li>
                  <li>
                    <strong className="text-cream">Article 2(3) Dual-Use Delineation:</strong> Fully supports military defense contracts under Article 2(3) exemptions while providing commercial OEMs a turnkey path to EU CE-marking compliance.
                  </li>
                  <li>
                    <strong className="text-cream">DoD Directive 3000.09 Alignment:</strong> Serves as the mathematical active-set governor ensuring physical flight surfaces cannot exceed pre-approved kinematic envelopes under electronic warfare or sensor spoofing.
                  </li>
                </ul>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
