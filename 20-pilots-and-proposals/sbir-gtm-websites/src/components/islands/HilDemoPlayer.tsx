import { useEffect, useRef, useState, useCallback } from 'react';
import { Play, Pause, RotateCcw, Shield, AlertTriangle, Zap } from 'lucide-react';

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

const CYCLES_TOTAL = 1024;
const INTERDICTION_CYCLE = 128;
const WCET_NS = 267;
const SAMPLING_HZ = 480_000_000; // 480 MHz

interface HilDemoPlayerProps {
  autoplay?: boolean;
  className?: string;
}

export default function HilDemoPlayer({ autoplay = false, className = '' }: HilDemoPlayerProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const animationRef = useRef<number | null>(null);
  const startTimeRef = useRef<number | null>(null);
  const pausedAtRef = useRef<number>(0);
  const dprRef = useRef<number>(1);
  const isPlayingRef = useRef<boolean>(autoplay);
  const cycleRef = useRef<number>(0);
  const [isPlaying, setIsPlaying] = useState(autoplay && !prefersReducedMotion());
  const [cycle, setCycle] = useState(0);
  const [status, setStatus] = useState<'safe' | 'threat' | 'interdicted'>('safe');
  const [showOverlay, setShowOverlay] = useState(!autoplay || prefersReducedMotion());

  const reset = useCallback(() => {
    if (animationRef.current) {
      cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }
    startTimeRef.current = null;
    pausedAtRef.current = 0;
    cycleRef.current = 0;
    setCycle(0);
    setStatus('safe');
    setIsPlaying(false);
    setShowOverlay(true);
    drawFrame(0);
  }, []);

  const togglePlay = useCallback(() => {
    if (isPlaying) {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
        animationRef.current = null;
      }
      if (startTimeRef.current !== null) {
        pausedAtRef.current += performance.now() - startTimeRef.current;
      }
      setIsPlaying(false);
    } else {
      setShowOverlay(false);
      startTimeRef.current = performance.now();
      setIsPlaying(true);
    }
  }, [isPlaying]);

  const resizeCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    dprRef.current = Math.min(window.devicePixelRatio || 1, 2);
    const rect = container.getBoundingClientRect();
    const width = Math.max(rect.width, 320);
    const height = Math.round(width * 0.5625); // 16:9 aspect ratio

    canvas.width = Math.round(width * dprRef.current);
    canvas.height = Math.round(height * dprRef.current);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dprRef.current, 0, 0, dprRef.current, 0, 0);

    drawFrame(cycleRef.current);
  }, []);

  const drawFrame = useCallback((currentCycle: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width / dprRef.current;
    const height = canvas.height / dprRef.current;

    // Clear
    ctx.clearRect(0, 0, width, height);

    // Background
    ctx.fillStyle = '#070f1a';
    ctx.fillRect(0, 0, width, height);

    // Grid
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.12)';
    ctx.lineWidth = 1;
    const gridX = width / 12;
    const gridY = height / 8;
    for (let i = 0; i <= 12; i++) {
      ctx.beginPath();
      ctx.moveTo(i * gridX, 0);
      ctx.lineTo(i * gridX, height);
      ctx.stroke();
    }
    for (let i = 0; i <= 8; i++) {
      ctx.beginPath();
      ctx.moveTo(0, i * gridY);
      ctx.lineTo(width, i * gridY);
      ctx.stroke();
    }

    // Baseline
    const baselineY = height * 0.62;
    ctx.strokeStyle = 'rgba(245, 158, 11, 0.25)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(0, baselineY);
    ctx.lineTo(width, baselineY);
    ctx.stroke();

    // Phase logic
    const cycleInLoop = currentCycle % CYCLES_TOTAL;
    const threatStart = 80;
    const threatPeak = 200;
    const interdictionPoint = INTERDICTION_CYCLE;
    const resetWindow = 420;

    let newStatus: 'safe' | 'threat' | 'interdicted' = 'safe';
    if (cycleInLoop >= threatStart && cycleInLoop < interdictionPoint) {
      newStatus = 'threat';
    } else if (cycleInLoop >= interdictionPoint && cycleInLoop < resetWindow) {
      newStatus = 'interdicted';
    } else {
      newStatus = 'safe';
    }
    setStatus(newStatus);

    // Plot AI command signal (threat in red)
    ctx.beginPath();
    ctx.strokeStyle = newStatus === 'threat' ? '#EF4444' : '#94A3B8';
    ctx.lineWidth = 2.5;
    for (let x = 0; x <= width; x++) {
      const cycleAtX = (x / width) * CYCLES_TOTAL;
      const loopX = cycleAtX % CYCLES_TOTAL;
      let y = baselineY;
      if (loopX >= threatStart && loopX < threatPeak) {
        const progress = (loopX - threatStart) / (threatPeak - threatStart);
        const spike = Math.sin(progress * Math.PI) * height * 0.42;
        y = baselineY - spike;
      } else if (loopX >= threatPeak && loopX < interdictionPoint) {
        y = baselineY - height * 0.42;
      } else if (loopX >= interdictionPoint && loopX < resetWindow) {
        const decay = (loopX - interdictionPoint) / (resetWindow - interdictionPoint);
        y = baselineY - height * 0.42 * (1 - decay * decay);
      }
      if (x === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Plot guardrail interdiction pulse (gold)
    ctx.beginPath();
    ctx.strokeStyle = '#F59E0B';
    ctx.lineWidth = 2.5;
    for (let x = 0; x <= width; x++) {
      const cycleAtX = (x / width) * CYCLES_TOTAL;
      const loopX = cycleAtX % CYCLES_TOTAL;
      let y = baselineY;
      if (loopX >= interdictionPoint - 8 && loopX < interdictionPoint + 24) {
        const pulseProgress = (loopX - (interdictionPoint - 8)) / 32;
        const pulse = Math.sin(pulseProgress * Math.PI) * height * 0.55;
        y = baselineY - pulse;
      }
      if (x === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Interdiction marker
    const interdictionX = (INTERDICTION_CYCLE / CYCLES_TOTAL) * width;
    ctx.strokeStyle = '#F59E0B';
    ctx.setLineDash([4, 4]);
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(interdictionX, height * 0.12);
    ctx.lineTo(interdictionX, height * 0.88);
    ctx.stroke();
    ctx.setLineDash([]);

    // Annotation box
    ctx.fillStyle = 'rgba(11, 25, 44, 0.85)';
    ctx.strokeStyle = 'rgba(245, 158, 11, 0.4)';
    ctx.lineWidth = 1;
    const boxX = Math.min(interdictionX + 10, width - 160);
    const boxY = height * 0.15;
    const boxW = 150;
    const boxH = 56;
    ctx.fillRect(boxX, boxY, boxW, boxH);
    ctx.strokeRect(boxX, boxY, boxW, boxH);

    ctx.font = 'bold 12px Fira Code, JetBrains Mono, monospace';
    ctx.fillStyle = '#F59E0B';
    ctx.fillText(`${INTERDICTION_CYCLE} CYCLES`, boxX + 10, boxY + 22);
    ctx.fillStyle = '#F8FAFC';
    ctx.fillText(`${WCET_NS} ns @ 480 MHz`, boxX + 10, boxY + 42);

    // Timebase legend
    ctx.font = '11px Fira Code, JetBrains Mono, monospace';
    ctx.fillStyle = '#64748B';
    ctx.fillText(`TIMEBASE: 1 div = ${Math.round((CYCLES_TOTAL / SAMPLING_HZ) * 1e9 * 1000) / 1000} µs`, width - 160, height - 12);
  }, []);

  useEffect(() => {
    if (autoplay && !prefersReducedMotion()) {
      setIsPlaying(true);
      setShowOverlay(false);
      startTimeRef.current = performance.now();
    }
  }, [autoplay]);

  useEffect(() => {
    isPlayingRef.current = isPlaying;
  }, [isPlaying]);

  useEffect(() => {
    const handlePlayEvent = () => {
      if (!isPlayingRef.current) {
        setShowOverlay(false);
        setIsPlaying(true);
        startTimeRef.current = performance.now();
      }
    };
    window.addEventListener('hil-demo:play', handlePlayEvent);
    return () => window.removeEventListener('hil-demo:play', handlePlayEvent);
  }, []);

  useEffect(() => {
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);
    return () => window.removeEventListener('resize', resizeCanvas);
  }, [resizeCanvas]);

  useEffect(() => {
    if (!isPlaying) {
      drawFrame(cycleRef.current);
      return;
    }

    const animate = (now: number) => {
      if (startTimeRef.current === null) startTimeRef.current = now;
      const elapsed = now - startTimeRef.current + pausedAtRef.current;
      const simulatedCycles = (elapsed / 1000) * (SAMPLING_HZ / 100); // 4.8 MHz display scale for visibility
      const displayCycle = Math.floor(simulatedCycles) % CYCLES_TOTAL;
      cycleRef.current = displayCycle;
      setCycle(displayCycle);
      drawFrame(displayCycle);
      animationRef.current = requestAnimationFrame(animate);
    };

    animationRef.current = requestAnimationFrame(animate);
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [isPlaying, drawFrame]);

  const statusConfig = {
    safe: { icon: Shield, text: 'SYSTEM SAFE', color: 'text-emerald-400', bg: 'bg-emerald-400/10', border: 'border-emerald-400/30' },
    threat: { icon: AlertTriangle, text: 'UNSAFE COMMAND DETECTED', color: 'text-red-400', bg: 'bg-red-400/10', border: 'border-red-400/30' },
    interdicted: { icon: Zap, text: 'INTERDICTION ACTIVE', color: 'text-gold', bg: 'bg-gold/10', border: 'border-gold/30' },
  };
  const StatusIcon = statusConfig[status].icon;

  return (
    <div className={`relative ${className}`} ref={containerRef}>
      <div className="relative overflow-hidden rounded-xl border border-slate-400/10 bg-navy-300/80">
        <canvas
          ref={canvasRef}
          aria-label="STM32H7 hardware-in-the-loop oscilloscope trace showing 128-cycle interdiction"
          className="block w-full"
        />
        {showOverlay && (
          <button
            type="button"
            onClick={togglePlay}
            className="absolute inset-0 flex items-center justify-center bg-navy-300/60 transition hover:bg-navy-300/50 focus:outline-none"
            aria-label="Play HIL benchtop demo"
          >
            <div className="flex flex-col items-center gap-2">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-gold/15 text-gold shadow-lg shadow-gold/10">
                <Play className="h-8 w-8 fill-current" aria-hidden="true" />
              </div>
              <span className="text-sm font-semibold text-cream">Watch HIL Benchtop Demo</span>
              <span className="text-xs text-slate-400">STM32H7 / Pixhawk 6X trace</span>
            </div>
          </button>
        )}
      </div>

      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={togglePlay}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-400/30 bg-slate-800/50 px-4 py-2 text-sm font-semibold text-cream transition hover:border-gold/60 hover:text-gold focus:outline-none focus:ring-2 focus:ring-gold focus:ring-offset-2 focus:ring-offset-navy"
            aria-label={isPlaying ? 'Pause demo' : 'Play demo'}
          >
            {isPlaying ? <Pause className="h-4 w-4" aria-hidden="true" /> : <Play className="h-4 w-4 fill-current" aria-hidden="true" />}
            {isPlaying ? 'Pause' : 'Play'}
          </button>
          <button
            type="button"
            onClick={reset}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-400/30 bg-slate-800/50 px-4 py-2 text-sm font-semibold text-cream transition hover:border-gold/60 hover:text-gold focus:outline-none focus:ring-2 focus:ring-gold focus:ring-offset-2 focus:ring-offset-navy"
            aria-label="Reset demo"
          >
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            Reset
          </button>
        </div>

        <div className={`flex items-center gap-2 rounded-lg border px-3 py-2 ${statusConfig[status].bg} ${statusConfig[status].border}`}>
          <StatusIcon className={`h-4 w-4 ${statusConfig[status].color}`} aria-hidden="true" />
          <span className={`text-xs font-mono font-semibold ${statusConfig[status].color}`}>{statusConfig[status].text}</span>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-3 text-center">
        <div className="rounded-lg border border-slate-400/10 bg-navy-300/50 px-2 py-2">
          <p className="text-[10px] font-mono uppercase tracking-wider text-slate-400">Cycle</p>
          <p className="mt-0.5 text-sm font-semibold text-cream font-mono">{cycle.toString().padStart(4, '0')}</p>
        </div>
        <div className="rounded-lg border border-slate-400/10 bg-navy-300/50 px-2 py-2">
          <p className="text-[10px] font-mono uppercase tracking-wider text-slate-400">Elapsed</p>
          <p className="mt-0.5 text-sm font-semibold text-cream font-mono">{((cycle / SAMPLING_HZ) * 1e9).toFixed(1)} ns</p>
        </div>
        <div className="rounded-lg border border-slate-400/10 bg-navy-300/50 px-2 py-2">
          <p className="text-[10px] font-mono uppercase tracking-wider text-slate-400">WCET</p>
          <p className="mt-0.5 text-sm font-semibold text-gold font-mono">{WCET_NS} ns</p>
        </div>
      </div>
    </div>
  );
}
