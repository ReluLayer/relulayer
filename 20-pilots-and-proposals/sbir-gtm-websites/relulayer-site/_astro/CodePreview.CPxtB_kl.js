import{c as p,j as e}from"./createLucideIcon.DBNAig9L.js";import{r as x}from"./index.CVf8TyFT.js";import{u as _,m as y}from"./use-reduced-motion.BcYjhwkl.js";import{C as v}from"./check.CImTLsWU.js";/**
 * @license lucide-react v0.424.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const g=p("Braces",[["path",{d:"M8 3H7a2 2 0 0 0-2 2v5a2 2 0 0 1-2 2 2 2 0 0 1 2 2v5c0 1.1.9 2 2 2h1",key:"ezmyqa"}],["path",{d:"M16 21h1a2 2 0 0 0 2-2v-5c0-1.1.9-2 2-2a2 2 0 0 1-2-2V5a2 2 0 0 0-2-2h-1",key:"e1hn23"}]]);/**
 * @license lucide-react v0.424.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const b=p("Copy",[["rect",{width:"14",height:"14",x:"8",y:"8",rx:"2",ry:"2",key:"17jyea"}],["path",{d:"M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2",key:"zix9uf"}]]);/**
 * @license lucide-react v0.424.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const C=p("FileCode2",[["path",{d:"M4 22h14a2 2 0 0 0 2-2V7l-5-5H6a2 2 0 0 0-2 2v4",key:"1pf5j1"}],["path",{d:"M14 2v4a2 2 0 0 0 2 2h4",key:"tnqrlb"}],["path",{d:"m5 12-3 3 3 3",key:"oke12k"}],["path",{d:"m9 18 3-3-3-3",key:"112psh"}]]),m={rust:`// relulayer/src/guardrail.rs
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
}`,c:`// relulayer/include/relulayer.h
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

#endif /* RELULAYER_H */`},u={rust:{label:"Rust Kernel",icon:g},c:{label:"C ABI Header",icon:C}};function k(){const o=_(),[t,r]=x.useState("rust"),[l,i]=x.useState(!1),c=async()=>{try{await navigator.clipboard.writeText(m[t]),i(!0),setTimeout(()=>i(!1),2e3)}catch{i(!1)}};return u[t].icon,e.jsx("section",{className:"py-16 sm:py-20",children:e.jsxs("div",{className:"mx-auto max-w-7xl px-4 sm:px-6 lg:px-8",children:[e.jsxs("div",{className:"max-w-3xl",children:[e.jsx("h2",{className:"section-heading",children:"Bare-Metal Integration"}),e.jsx("p",{className:"mt-4 section-subheading",children:"Drop the ReluLayer safety governor into your existing flight stack through a zero-allocation C ABI and memory-mapped register interface."})]}),e.jsxs("div",{className:"mt-12 overflow-hidden rounded-2xl border border-slate-400/10 bg-navy-300",children:[e.jsxs("div",{className:"flex items-center justify-between border-b border-slate-400/10 bg-slate-800/60 px-4 py-3 sm:px-6",children:[e.jsx("div",{className:"flex gap-2",children:Object.keys(u).map(a=>{const{label:n,icon:d}=u[a];return e.jsxs("button",{type:"button",onClick:()=>r(a),className:`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${t===a?"bg-gold/15 text-gold":"text-slate-400 hover:bg-slate-700/50 hover:text-cream"}`,"aria-pressed":t===a,children:[e.jsx(d,{className:"h-4 w-4","aria-hidden":"true"}),n]},a)})}),e.jsxs("button",{type:"button",onClick:c,className:"inline-flex items-center gap-1.5 text-xs font-medium text-slate-400 hover:text-gold transition-colors","aria-label":"Copy code to clipboard",children:[l?e.jsx(v,{className:"h-4 w-4","aria-hidden":"true"}):e.jsx(b,{className:"h-4 w-4","aria-hidden":"true"}),l?"Copied":"Copy"]})]}),e.jsxs("div",{className:"relative p-4 sm:p-6",children:[e.jsx("div",{className:"absolute left-0 top-0 h-full w-12 border-r border-slate-400/10 bg-slate-800/30 sm:w-14",children:e.jsx("div",{className:"py-4 text-right pr-3 sm:pr-4 font-mono text-xs text-slate-400 select-none",children:Array.from({length:m[t].split(`
`).length}).map((a,n)=>e.jsx("div",{children:n+1},n))})}),e.jsx(y.div,{initial:{opacity:0,x:8},animate:{opacity:1,x:0},transition:o?{duration:0}:{duration:.2},className:"pl-14 sm:pl-16",children:e.jsx("pre",{className:"overflow-x-auto font-mono text-sm leading-relaxed",children:e.jsx("code",{className:"block text-slate-200",children:m[t].split(`
`).map((a,n)=>e.jsx("span",{className:"block",children:j(a)},n))})})},t)]})]})]})})}function j(o){const t=[];let r=0;const l=new Set(["use","pub","struct","impl","fn","unsafe","let","if","return","match","enum","const","volatile","#include","#ifndef","#define","#ifdef","#endif","typedef","extern"]),i=new Set(["u32","uint32_t","ReluLayer","FlightEnvelope","GuidanceCommand","CommandDecision","relu_layer_t","relu_decision_t","relu_envelope_t"]),c="text-slate-400",h="text-green-400",a="text-gold",n="text-cyan-400",d="text-purple-400";if(o.startsWith("//"))return e.jsx("span",{className:c,children:o});const f=o.split(/(\s+|[{}()\[\]<>;:,.*&|=])/);for(const s of f)s&&(s.startsWith('"')&&s.endsWith('"')?t.push(e.jsx("span",{className:h,children:s},r++)):/^\d+$/.test(s)?t.push(e.jsx("span",{className:d,children:s},r++)):l.has(s)?t.push(e.jsx("span",{className:a,children:s},r++)):i.has(s)?t.push(e.jsx("span",{className:n,children:s},r++)):t.push(e.jsx("span",{children:s},r++)));return e.jsx(e.Fragment,{children:t})}export{k as default};
