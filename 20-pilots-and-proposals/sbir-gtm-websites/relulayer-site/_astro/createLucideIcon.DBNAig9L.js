import{r as a}from"./index.CVf8TyFT.js";var l={exports:{}},i={};/**
 * @license React
 * react-jsx-runtime.production.min.js
 *
 * Copyright (c) Facebook, Inc. and its affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */var w=a,x=Symbol.for("react.element"),y=Symbol.for("react.fragment"),v=Object.prototype.hasOwnProperty,E=w.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentOwner,k={key:!0,ref:!0,__self:!0,__source:!0};function c(t,e,o){var r,s={},n=null,u=null;o!==void 0&&(n=""+o),e.key!==void 0&&(n=""+e.key),e.ref!==void 0&&(u=e.ref);for(r in e)v.call(e,r)&&!k.hasOwnProperty(r)&&(s[r]=e[r]);if(t&&t.defaultProps)for(r in e=t.defaultProps,e)s[r]===void 0&&(s[r]=e[r]);return{$$typeof:x,type:t,key:n,ref:u,props:s,_owner:E.current}}i.Fragment=y;i.jsx=c;i.jsxs=c;l.exports=i;var g=l.exports;/**
 * @license lucide-react v0.424.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const R=t=>t.replace(/([a-z0-9])([A-Z])/g,"$1-$2").toLowerCase(),f=(...t)=>t.filter((e,o,r)=>!!e&&r.indexOf(e)===o).join(" ");/**
 * @license lucide-react v0.424.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */var b={xmlns:"http://www.w3.org/2000/svg",width:24,height:24,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:2,strokeLinecap:"round",strokeLinejoin:"round"};/**
 * @license lucide-react v0.424.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const h=a.forwardRef(({color:t="currentColor",size:e=24,strokeWidth:o=2,absoluteStrokeWidth:r,className:s="",children:n,iconNode:u,...p},m)=>a.createElement("svg",{ref:m,...b,width:e,height:e,stroke:t,strokeWidth:r?Number(o)*24/Number(e):o,className:f("lucide",s),...p},[...u.map(([d,_])=>a.createElement(d,_)),...Array.isArray(n)?n:[n]]));/**
 * @license lucide-react v0.424.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const j=(t,e)=>{const o=a.forwardRef(({className:r,...s},n)=>a.createElement(h,{ref:n,iconNode:e,className:f(`lucide-${R(t)}`,r),...s}));return o.displayName=`${t}`,o};export{j as c,g as j};
