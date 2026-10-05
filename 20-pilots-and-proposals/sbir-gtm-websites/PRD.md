# **Product Requirements Document (PRD) — Atelier Logic Group LLC dba ReluLayer™**

> **Canonical entity identity:** `AtelierLogicGroup/00-governance/entity-identity.md`. Any edits to UEI, CAGE, NAICS, PSC, patent serials, or addresses must be synchronized with that file.
>
> **Version:** 1.1 — post-audit, 2026-08-25

> **Scope:** sbir-gtm-websites Astro monorepo and dual-domain deployment estate

> **Authoritative source of truth for:** system architecture, route inventory, corporate identifiers, cross-domain routing rules, and CI/CD/QA standards.

## **1\. System Overview & Strategic Objectives**

### **1.1 Purpose**

sbir-gtm-websites is the single source of truth for the public-facing web presence of **Atelier Logic Group LLC dba ReluLayer™**. The platform is split across two audiences and two primary live domains, backed by an edge redirect:

| Domain | Audience / Role | Purpose |
| :---- | :---- | :---- |
| https://atelierlogicgroup.com/ | Corporate, SBIR, defense contracting, and enterprise buyers | Corporate hub: capabilities, leadership, compliance, legal, capability statement, and SBLO lead capture. |
| https://relulayer.ai/ | Product, technical, and OEM evaluators | Product hub: deep technical specifications, interactive demos, pricing, and licensing for the ReluLayer™ deterministic safety kernel. |
| https://relulayer.com/ | Brand Entry Alias | Cloudflare 301 edge redirect to https://relulayer.ai/. |

### **1.2 Strategic Objectives**

1. **Dual-audience clarity** — separate the corporate/SBIR narrative from the deep technical product narrative without fragmenting brand identity.  
2. **Regulatory safe harbor** — publish authoritative, verifiable compliance positions (OMB M-24-10, CISA/ONCD, DoD 3000.09, EU AI Act, etc.).  
3. **Web accessibility & privacy compliance** — meet WCAG 2.1 AA / Section 508 / EN 301 549 for ADA and procurement audiences, and maintain accurate privacy notices for CCPA/CPRA, GDPR, and other applicable privacy regimes.  
4. **Lead capture** — route defense primes, SBLOs, and OEMs to the https://atelierlogicgroup.com/\#sblo-form anchor.  
5. **Technical credibility** — expose WCET, HIL, memory-safety, and patent-pending ACCSE™ evidence on the product domain.  
6. **Operational rigor** — enforce a build-and-link-check gate and automated CI/CD deployment via Gitea act\_runner to AWS Lightsail.

### **1.3 Repository Layout**

sbir-gtm-websites/  
├── .github/workflows/deploy.yml        \# Single root CI/CD pipeline for both domains  
├── astro.config.mjs                    \# atelierlogicgroup.com build config  
├── package.json  
├── PRD.md                              \# This document  
├── .cursorrules                        \# AI coding standards  
├── src/  
│   ├── layouts/BaseLayout.astro        \# Shared layout with Schema.org, canonical, OG  
│   ├── components/  
│   │   ├── sections/Navigation.astro   \# Cross-domain nav  
│   │   ├── sections/Footer.astro  
│   │   └── ...  
│   └── pages/                          \# All route pages (see §2)  
├── public/  
│   ├── docs/                           \# PDFs and static documents  
│   └── images/  
└── relulayer-site/                     \# Static product-domain deployment tree  
    ├── index.html                      \# Product-hub landing  
    ├── relulayer/index.html            \# Product page  
    └── ...

> **Important:** The root Astro project builds the corporate domain and is served from /var/www/atelierlogicgroup.com/. The relulayer-site/ directory is a static product-domain deployment tree served from /var/www/relulayer.ai/. Both domains are deployed by the single root CI/CD pipeline.

## **2\. Site Map & Page Architecture**

### **2.1 Astro Configuration**

File: astro.config.mjs

export default defineConfig({  
  site: 'https://atelierlogicgroup.com',  
  trailingSlash: 'always',  
  integrations: \[react(), tailwind({ applyBaseStyles: false })\],  
  output: 'static',  
  build: { format: 'directory' },  
});

Implications:

* Every route is emitted as dist/\<route\>/index.html.  
* Every internal relative link **must** end with a trailing slash: /relulayer/, /compliance/, /privacy/.  
* Links without trailing slashes (e.g., /relulayer) will 404 on the static host when trailingSlash: 'always' is enabled.

### **2.2 Route Inventory**

| \# | Route (public URL) | File | Theme | pageType | Primary Audience |
| :---- | :---- | :---- | :---- | :---- | :---- |
| 1 | https://atelierlogicgroup.com/ | src/pages/index.astro | Dark navy (\#0B192C) | corporate | Corporate / SBLO / enterprise buyers |
| 2 | https://atelierlogicgroup.com/relulayer/ | src/pages/relulayer/index.astro | Dark navy (\#0B192C) | product | Technical / OEM / defense evaluators |
| 2a | https://atelierlogicgroup.com/demo/ | src/pages/demo.astro | Dark navy (\#0B192C) | product | Product evaluators arriving from corporate site |
| 3 | https://atelierlogicgroup.com/capability-statement/ | src/pages/capability-statement.astro | Printable light | n/a (raw HTML) | Contracting officers, SBLOs, primes |
| 4 | https://atelierlogicgroup.com/compliance/ | src/pages/compliance.astro | Printable light inside dark layout | corporate | Legal, compliance, procurement reviewers |
| 5 | https://atelierlogicgroup.com/pitch-deck/ | src/pages/pitch-deck.astro | Full-screen dark 16:9 | corporate | Investors, program managers, briefings |
| 6 | https://atelierlogicgroup.com/cisa-memory-safety-audit/ | src/pages/cisa-memory-safety-audit.astro | Dark navy | corporate | Defense primes, CISOs, compliance leads |
| 7 | https://atelierlogicgroup.com/autonomous-flight-safety-governor/ | src/pages/autonomous-flight-safety-governor.astro | Dark navy | corporate | UAS autonomy leads, FAA/DOD evaluators |
| 8 | https://atelierlogicgroup.com/contested-ew-drone-guardrail/ | src/pages/contested-ew-drone-guardrail.astro | Dark navy | corporate | NAVAIR, AFWERX, DEVCOM, tactical UAS |
| 9 | https://atelierlogicgroup.com/do178c-rust-avionics/ | src/pages/do178c-rust-avionics.astro | Dark navy | corporate | FAA DERs, airworthiness release leads |
| 10 | https://atelierlogicgroup.com/privacy/ | src/pages/privacy.astro | Dark navy | corporate | General legal |
| 11 | https://atelierlogicgroup.com/terms/ | src/pages/terms.astro | Dark navy | corporate | General legal |
| 12 | https://atelierlogicgroup.com/business-card/ | src/pages/business-card.astro | Printable dark | n/a | Executive collateral / print-to-PDF |

### **2.3 Theme Rules**

* All pages routed through BaseLayout use the same dark navy theme (themeColor: '\#0B192C').  
* The pageType prop (corporate | product) is reserved for future theme differentiation; both resolve to the same dark theme.  
* Printable pages (capability-statement.astro, business-card.astro, compliance.astro) override the default layout with inline/global print media rules (@media print) and a light background for the document area.

## **3\. Cross-Domain Architecture & Routing Rules**

### **3.1 Domain Boundaries**

| Boundary | Canonical URL | Notes |
| :---- | :---- | :---- |
| Corporate Hub | https://atelierlogicgroup.com/ | Root domain; corporate, legal, compliance, and solution landing pages. |
| Product Hub | https://relulayer.ai/ | Standalone technical product domain; deep specs, pricing, licensing. |
| Brand Redirect | https://relulayer.com/ | Cloudflare 301 edge redirect to https://relulayer.ai/. |
| Capability Statement | https://atelierlogicgroup.com/capability-statement/ | Reachable from both domains for SBIR/proposal packets. |
| SBLO Contact Anchor | https://atelierlogicgroup.com/\#sblo-form | Primary lead-form destination. |

### **3.1a Domain Redirect & Nginx Purging Strategy**

* https://relulayer.com/\* is configured with a Cloudflare 301 Moved Permanently edge redirect to https://relulayer.ai/.  
* https://relulayer.ai/ and https://atelierlogicgroup.com/ both serve live 200 OK static pages from AWS Lightsail.  
* Nginx returns 410 Gone for all legacy /wp-\* and /feed/ requests on relulayer.ai to accelerate Google Search Console index purging.

### **3.2 Linking Rules (enforced)**

1. **Same-domain internal links** must use **trailing slashes** and be relative to the current domain:  
   * ✅ /compliance/  
   * ✅ /privacy/  
   * ✅ /terms/  
   * ✅ /relulayer/  
   * ❌ /compliance (will 404\)  
2. **Cross-domain links** must use **absolute URLs** with the correct domain:  
   * ✅ https://atelierlogicgroup.com/  
   * ✅ https://atelierlogicgroup.com/capability-statement/  
   * ✅ https://atelierlogicgroup.com/\#sblo-form  
   * ✅ https://relulayer.ai/  
   * ❌ /capability-statement/ when linking from relulayer.ai  
3. **Canonical URLs** in BaseLayout and individual page frontmatter must match the route exactly, including the trailing slash for directory routes:  
   * https://atelierlogicgroup.com/  
   * https://atelierlogicgroup.com/relulayer/  
   * https://atelierlogicgroup.com/capability-statement/  
   * https://relulayer.ai/

## **4\. Key Entity Data & Corporate Metadata**

### **4.1 Corporate Identifiers**

| Parameter | Value |
| :---- | :---- |
| Legal Entity Name | Atelier Logic Group LLC |
| DBA / Brand Name | Atelier Logic Group LLC dba ReluLayer™ |
| R\&D Headquarters | 32 Normandy Dr., Kenner, LA 70065 USA |
| Phone | (504) 233-8722 |
| UEI | G9WFN3AL69J3 |
| CAGE Code | 20JX8 |
| SAM.gov Status | Active Entity |
| Primary NAICS | 541715 — Research & Development in Physical, Engineering, and Life Sciences |
| Secondary NAICS | 541330 (Engineering Services), 541512 (Computer Systems Design), 541690 (Other Scientific/Technical Consulting) |
| Product Service Codes (PSC) | AC11 (primary), plus AC12, AJ12, AJ13, DA01, D302 |
| USPTO Patent Pending | Serial No. 64/127,611 (Attorney Docket RELU-001-PPA7, filed August 7, 2026); portfolio continuity from Provisionals I–VI (Serial Nos. 64/021,087 through 64/124,094) |

### **4.2 Leadership**

* **Principal Investigator & Founder:** Ishmael Ibrahim Amin, M.S.  
  * Northwestern University M.S. Data Science in Artificial Intelligence  
  * UC Santa Barbara B.S. Statistical Science  
  * Former leader of DXC Technology's 10,000-member global AI Guild  
  * Track record: $20M–$40M MILP aviation optimization ROI, $141.3M public-sector grant win (City of New Orleans data repository)

### **4.3 Partnerships & Testing**

* **LSU aiR Lab** — strategic academic testing partnership for physical embedded SWaP-C (Size, Weight, Power, and Cost) Hardware-in-the-Loop (HIL) validation.  
* All HIL stress testing is performed on-shore in Kenner, Louisiana.

### **4.4 Email & Contracting Channels**

| Channel | Address | Use |
| :---- | :---- | :---- |
| Defense & SBIR Proposals | proposals@atelierlogicgroup.com | SBIR/STTR, primes, federal contracting |
| Commercial & OEM Licensing | solutions@relulayer.ai or procurement@relulayer.ai | Product sales, OEM licensing, technical briefs |
| Legal & IP Disclosures | legal@atelierlogicgroup.com | Legal, IP, compliance questions |

## **5\. CI/CD & Build Pipeline Specifications**

### **5.1 Build & Quality Commands**

| Command | Purpose | When to run |
| :---- | :---- | :---- |
| npm install / npm ci | Install dependencies | CI, local first setup |
| npm run build | Static Astro build to dist/ | Every commit/PR and before deployment |
| npm run check | Astro type/lint check | CI build job (already combined with npm run build) |
| npx linkinator ./dist \--recurse --skip 'https://atelierlogicgroup.com\|https://relulayer.ai\|https://fonts.googleapis.com\|mailto:' | Recursively validate internal links in the built output; skip live external URLs to avoid 404s for pages that are not yet deployed | Mandatory pre-deployment gate |
| npm run verify | Convenience script: npm run build && npx linkinator ./dist \--recurse --skip 'https://atelierlogicgroup.com\|https://relulayer.ai\|https://fonts.googleapis.com\|mailto:' | Recommended local pre-commit/pre-PR command |

### **5.2 CI/CD Workflows & Runner Status**

* **Gitea Runner Daemon:** Active on pacificailab as act\_runner (wsl-deploy-runner v0.2.10) with labels \[ubuntu-latest, ubuntu-22.04, ubuntu-20.04\].  
* **Single Root Pipeline:** .github/workflows/deploy.yml (and mirrored under .gitea/workflows/) builds and deploys both domains to AWS Lightsail on main branch pushes.

## **6\. Development Standards & Component Rules**

### **6.1 Astro Component Standards**

* **Printable documents** (capability-statement.astro, business-card.astro, and any future print page) must use \<style is:inline\> or \<style is:global\> for all @media print and :root CSS.  
* **Global Tailwind overrides** live in src/styles/global.css and are imported in BaseLayout.astro via \<style is:global\>.  
* **Schema.org JSON-LD** remains in BaseLayout.astro with is:inline so it is emitted as raw JSON.

### **6.2 Accessibility & Privacy Compliance Standards**

All public pages across both domains must satisfy the following requirements:

* **WCAG 2.1 Level AA** is the baseline target for ADA Title III and state anti-discrimination compliance (e.g., California Unruh Act, New York HRL).  
* **U.S. Section 508** and **EN 301 549** conformance are required for federal and EU public-sector procurement audiences; this is enforced by using semantic HTML, programmatic labels, skip navigation, focus indicators, and color contrast ≥ 4.5:1 for normal text.  
* **Reduced motion** must be honored via `prefers-reduced-motion` for all animations, pulsing indicators, and Framer Motion transitions.  
* **Lead forms** must use programmatic label/input associations (`htmlFor`/`id`), live regions for submission status, and accessible error states.  
* **Privacy** — the SBLO lead form and any other data collection must be covered by an accurate privacy policy that discloses CCPA/CPRA rights, GDPR rights (for EU/EEA/UK visitors), and state privacy-law notices (Colorado CPA, Virginia CDPA, Connecticut CTDPA, Utah UCPA, Texas TDPSA).  
* **Accessibility statement** — a public `/accessibility/` page must be published, linked from the footer, and reference the WCAG/Section 508/EN 301 549 targets plus a feedback email.  
* **Cross-domain consistency** — because the product domain is deployed from the static `relulayer-site/` tree, any accessibility or privacy fix in the Astro source must be regenerated into `relulayer-site/` before the CI/CD pipeline runs.

## **7\. Known Issues & Next Release Backlog**

| Issue | Location | Priority | Status | Recommended Fix |
| :---- | :---- | :---- | :---- | :---- |
| relulayer-site canonicals point to atelierlogicgroup.com | relulayer-site/\*\*/\*.html | High | Resolved | Canonicals and OG URLs rebuilt to https://relulayer.ai/.... |
| Footer solution links omit trailing slashes | src/components/sections/Footer.astro | Medium | Resolved | Trailing slashes verified on all same-domain solution links. |
| No skip link to main content | src/layouts/BaseLayout.astro | High | Resolved | First-focusable skip link added targeting `<main id="main-content">`. |
| Lead form labels not programmatically associated | src/components/islands/SbloLeadForm.tsx | High | Resolved | `id`/`htmlFor` associations, `aria-live`, and `aria-busy` added. |
| Animations lack reduced-motion fallback | src/styles/global.css, interactive islands | High | Resolved | `prefers-reduced-motion` media query and Framer Motion `useReducedMotion` added. |
| Interactive demo toggles missing `aria-pressed` | src/components/islands/InteractiveGuardrail.tsx, GuardrailSandbox.tsx | Medium | Resolved | `aria-pressed` and `aria-hidden` icon markers added. |
| Color contrast not verified across dark theme | Tailwind theme, component classes | Medium | Resolved | `text-slate-500` adjusted to `text-slate-400` on dark surfaces; printable pages use darker text. |
| Privacy policy lacks CCPA/CPRA/GDPR specificity | docs/Privacy_and_Data_Policy_ReluLayer.md | Medium | Resolved | Jurisdiction-specific rights, data retention, and third-party disclosures added. |
| No public accessibility statement | src/pages/accessibility.astro | Medium | Resolved | `/accessibility/` page created and linked from footer. |
| relulayer-site static tree may drift from Astro source | relulayer-site/ | High | Resolved | Regenerated and URL-normalized from latest Astro build. |
| GSC Indexing lag on new sitemaps | Google Search Console | Low | Pending | Monitor Search Console over 24-72 hrs for full indexing validation. |

*End of PRD.*