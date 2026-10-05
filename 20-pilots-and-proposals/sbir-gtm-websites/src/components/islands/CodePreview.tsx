import { useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { FileCode2, Braces, Copy, Check } from 'lucide-react';

const codeExamples = {
  rust: `// relulayer/src/guardrail.rs
#![no_std]
#![no_main]

use core::ptr::read_volatile;
use core::ptr::write_volatile;

/// 326-byte safety governor
/// Worst-case: 0.199 µs @ 480 MHz
#[repr(C)]
pub struct ReluLayer {
    mmio_status: *const u32,
    mmio_command: *const u32,
    mmio_override: *mut u32,
    bounds: FlightEnvelope,
}

impl ReluLayer {
    #[inline(always)]
    pub unsafe fn interdict(&self) -> CommandDecision {
        let raw = read_volatile(self.mmio_command);
        let cmd = GuidanceCommand::from_mmio(raw);

        if self.bounds.contains(&cmd) {
            return CommandDecision::Allow;
        }

        write_volatile(self.mmio_override, SAFE_HOLD_VECTOR);
        CommandDecision::Interdict
    }
}

#[no_mangle]
pub extern "C" fn relu_layer_tick(ctx: *const ReluLayer) -> u32 {
    unsafe { (*ctx).interdict() as u32 }
}`,

  c: `// relulayer/include/relulayer.h
#ifndef RELULAYER_H
#define RELULAYER_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    RELU_DECISION_ALLOW = 0,
    RELU_DECISION_INTERDICT = 1,
} relu_decision_t;

typedef struct {
    volatile const uint32_t *status_reg;
    volatile const uint32_t *command_reg;
    volatile uint32_t *override_reg;
    relu_envelope_t envelope;
} relu_layer_t;

/** Initialize memory-mapped guardrail context.
 *  Must be called once before flight-critical loops.
 */
relu_layer_t *relu_layer_init(
    uint32_t status_addr,
    uint32_t command_addr,
    uint32_t override_addr,
    const relu_envelope_t *envelope
);

/** Run one interdiction tick.
 *  Returns RELU_DECISION_INTERDICT if unsafe command was overridden.
 */
uint32_t relu_layer_tick(const relu_layer_t *ctx);

#ifdef __cplusplus
}
#endif

#endif /* RELULAYER_H */`,
};

const languageInfo = {
  rust: { label: 'Rust Kernel', icon: Braces },
  c: { label: 'C ABI Header', icon: FileCode2 },
};

export default function CodePreview() {
  const prefersReducedMotion = useReducedMotion();
  const [activeTab, setActiveTab] = useState<'rust' | 'c'>('rust');
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(codeExamples[activeTab]);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  const activeInfo = languageInfo[activeTab];
  const Icon = activeInfo.icon;

  return (
    <section className="py-16 sm:py-20">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="max-w-3xl">
          <h2 className="section-heading">Bare-Metal Integration</h2>
          <p className="mt-4 section-subheading">
            Drop the ReluLayer safety governor into your existing flight stack through a zero-allocation C ABI and memory-mapped register interface.
          </p>
        </div>

        <div className="mt-12 overflow-hidden rounded-2xl border border-slate-400/10 bg-navy-300">
          <div className="flex items-center justify-between border-b border-slate-400/10 bg-slate-800/60 px-4 py-3 sm:px-6">
            <div className="flex gap-2">
              {(Object.keys(languageInfo) as Array<'rust' | 'c'>).map((key) => {
                const { label, icon: TabIcon } = languageInfo[key];
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setActiveTab(key)}
                    className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                      activeTab === key
                        ? 'bg-gold/15 text-gold'
                        : 'text-slate-400 hover:bg-slate-700/50 hover:text-cream'
                    }`}
                    aria-pressed={activeTab === key}
                  >
                    <TabIcon className="h-4 w-4" aria-hidden="true" />
                    {label}
                  </button>
                );
              })}
            </div>
            <button
              type="button"
              onClick={handleCopy}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-400 hover:text-gold transition-colors"
              aria-label="Copy code to clipboard"
            >
              {copied ? <Check className="h-4 w-4" aria-hidden="true" /> : <Copy className="h-4 w-4" aria-hidden="true" />}
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>

          <div className="relative p-4 sm:p-6">
            <div className="absolute left-0 top-0 h-full w-12 border-r border-slate-400/10 bg-slate-800/30 sm:w-14">
              <div className="py-4 text-right pr-3 sm:pr-4 font-mono text-xs text-slate-400 select-none">
                {Array.from({ length: codeExamples[activeTab].split('\n').length }).map((_, i) => (
                  <div key={i}>{i + 1}</div>
                ))}
              </div>
            </div>

            <motion.div
              key={activeTab}
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.2 }}
              className="pl-14 sm:pl-16"
            >
              <pre className="overflow-x-auto font-mono text-sm leading-relaxed">
                <code className="block text-slate-200">
                  {codeExamples[activeTab].split('\n').map((line, index) => (
                    <span key={index} className="block">
                      {highlightLine(line)}
                    </span>
                  ))}
                </code>
              </pre>
            </motion.div>
          </div>
        </div>
      </div>
    </section>
  );
}

function highlightLine(line: string): JSX.Element {
  const tokens: JSX.Element[] = [];
  let key = 0;

  const keywords = new Set([
    'use', 'pub', 'struct', 'impl', 'fn', 'unsafe', 'let', 'if', 'return', 'match', 'enum', 'const', 'volatile',
    '#include', '#ifndef', '#define', '#ifdef', '#endif', 'typedef', 'extern',
  ]);

  const types = new Set(['u32', 'uint32_t', 'ReluLayer', 'FlightEnvelope', 'GuidanceCommand', 'CommandDecision', 'relu_layer_t', 'relu_decision_t', 'relu_envelope_t']);

  const commentColor = 'text-slate-400';
  const stringColor = 'text-green-400';
  const keywordColor = 'text-gold';
  const typeColor = 'text-cyan-400';
  const numberColor = 'text-purple-400';

  if (line.startsWith('//')) {
    return <span className={commentColor}>{line}</span>;
  }

  const words = line.split(/(\s+|[{}()\[\]<>;:,.*&|=])/);

  for (const word of words) {
    if (!word) continue;

    if (word.startsWith('"') && word.endsWith('"')) {
      tokens.push(<span key={key++} className={stringColor}>{word}</span>);
    } else if (/^\d+$/.test(word)) {
      tokens.push(<span key={key++} className={numberColor}>{word}</span>);
    } else if (keywords.has(word)) {
      tokens.push(<span key={key++} className={keywordColor}>{word}</span>);
    } else if (types.has(word)) {
      tokens.push(<span key={key++} className={typeColor}>{word}</span>);
    } else {
      tokens.push(<span key={key++}>{word}</span>);
    }
  }

  return <>{tokens}</>;
}
