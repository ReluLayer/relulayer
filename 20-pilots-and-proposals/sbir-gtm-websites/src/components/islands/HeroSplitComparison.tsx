import { useState } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { Shield, AlertTriangle, Zap, CheckCircle2, RotateCcw } from 'lucide-react';

export default function HeroSplitComparison() {
  const prefersReducedMotion = useReducedMotion();
  const [run, setRun] = useState(0);

  const replay = () => setRun((n) => n + 1);

  return (
    <div className="relative rounded-2xl border border-slate-400/10 bg-slate-800/30 p-5 sm:p-7 overflow-hidden backdrop-blur-sm">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(245,158,11,0.06),transparent_60%)]" />

      <div className="relative grid gap-5 lg:grid-cols-2">
        {/* Standard AI Panel */}
        <div className="rounded-xl border border-red-400/20 bg-navy-300/50 p-5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-400/15 text-red-400">
              <AlertTriangle className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <p className="font-semibold text-cream">Standard AI</p>
              <p className="text-xs text-slate-400">Unfiltered guidance path</p>
            </div>
          </div>

          <div className="mt-6">
            <svg
              viewBox="0 0 320 160"
              className="h-auto w-full"
              aria-label="Standard AI allows an unsafe trajectory"
            >
              <defs>
                <linearGradient id="dangerPath" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#0B192C" />
                  <stop offset="100%" stopColor="#EF4444" stopOpacity="0.5" />
                </linearGradient>
              </defs>

              <line x1="20" y1="130" x2="300" y2="130" stroke="#334155" strokeWidth="2" strokeDasharray="5 4" />

              <motion.path
                key={`danger-${run}`}
                d="M 30 100 C 90 100, 120 30, 180 30 S 260 80, 300 80"
                fill="none"
                stroke="url(#dangerPath)"
                strokeWidth="4"
                strokeLinecap="round"
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={prefersReducedMotion ? { duration: 0 } : { duration: 1.8, ease: 'easeInOut' }}
              />

              <g transform="translate(180, 30)">
                <circle r="22" fill="#EF4444" fillOpacity="0.12" />
                <circle r="10" fill="#EF4444" fillOpacity="0.35" />
                <circle r="3" fill="#EF4444" />
              </g>

              <text x="160" y="150" textAnchor="middle" fill="#94A3B8" fontSize="11" fontFamily="Fira Code, monospace">
                SAFE ENVELOPE VIOLATED
              </text>
            </svg>

            <AnimatePresence mode="wait">
              <motion.div
                key={`danger-text-${run}`}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={prefersReducedMotion ? { duration: 0 } : { delay: 1.4 }}
                className="mt-4 flex items-center justify-center gap-2 rounded-lg border border-red-400/20 bg-red-400/10 px-4 py-3"
              >
                <AlertTriangle className="h-4 w-4 text-red-400" aria-hidden="true" />
                <p className="text-sm font-semibold text-red-400">Unsafe command reaches actuator</p>
              </motion.div>
            </AnimatePresence>
          </div>
        </div>

        {/* ReluLayer Interdicted Panel */}
        <div className="rounded-xl border border-gold/30 bg-gold/5 p-5 shadow-gold-glow">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gold/15 text-gold">
              <Shield className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <p className="font-semibold text-cream">ReluLayer Interdicted</p>
              <p className="text-xs text-slate-400">Deterministic safety governor</p>
            </div>
          </div>

          <div className="mt-6">
            <svg
              viewBox="0 0 320 160"
              className="h-auto w-full"
              aria-label="ReluLayer blocks the unsafe trajectory in 0.199 microseconds"
            >
              <defs>
                <linearGradient id="safePath" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#0B192C" />
                  <stop offset="100%" stopColor="#F59E0B" stopOpacity="0.4" />
                </linearGradient>
              </defs>

              <line x1="20" y1="130" x2="300" y2="130" stroke="#334155" strokeWidth="2" strokeDasharray="5 4" />

              <motion.path
                key={`safe-${run}`}
                d="M 30 100 C 80 100, 110 40, 150 40"
                fill="none"
                stroke="url(#safePath)"
                strokeWidth="4"
                strokeLinecap="round"
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={prefersReducedMotion ? { duration: 0 } : { duration: 1.2, ease: 'easeInOut' }}
              />

              <motion.path
                key={`hold-${run}`}
                d="M 150 40 L 290 40"
                fill="none"
                stroke="#F59E0B"
                strokeWidth="4"
                strokeDasharray="6 4"
                strokeLinecap="round"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={prefersReducedMotion ? { duration: 0 } : { delay: 1.2, duration: 0.4 }}
              />

              <g transform="translate(150, 40)">
                <rect x="-24" y="-24" width="48" height="80" fill="#F59E0B" fillOpacity="0.08" stroke="#F59E0B" strokeWidth="1.5" strokeDasharray="4 4" rx="4" />
                <circle r="4" fill="#F59E0B" />
              </g>

              <text x="150" y="150" textAnchor="middle" fill="#F59E0B" fontSize="11" fontFamily="Fira Code, monospace">
                INTERDICTION ZONE
              </text>
            </svg>

            <AnimatePresence mode="wait">
              <motion.div
                key={`safe-text-${run}`}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={prefersReducedMotion ? { duration: 0 } : { delay: 1.2 }}
                className="mt-4 flex items-center justify-center gap-2 rounded-lg border border-gold/30 bg-gold/10 px-4 py-3"
              >
                <Zap className="h-4 w-4 text-gold" aria-hidden="true" />
                <p className="text-sm font-mono font-semibold text-gold">0.199 µs interdiction</p>
                <CheckCircle2 className="h-4 w-4 text-gold" aria-hidden="true" />
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </div>

      <div className="relative mt-6 flex justify-center">
        <button
          type="button"
          onClick={replay}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-400/30 bg-slate-800/60 px-4 py-2 text-sm font-medium text-cream hover:border-gold/60 hover:text-gold transition-colors focus:outline-none focus:ring-2 focus:ring-gold focus:ring-offset-2 focus:ring-offset-navy"
        >
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
          Replay Runaway Scenario
        </button>
      </div>
    </div>
  );
}
