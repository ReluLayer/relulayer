# **ReluLayer™ Enterprise CI/CD Pipeline Architecture (Keycloak \+ Gitea \+ Woodpecker CI)**

**Company:** Atelier Logic Group LLC dba ReluLayer™

**Document Focus:** Self-Hosted Version Control (Gitea), Identity Access Management (Keycloak), Automation Engine (Woodpecker CI v3), & 3-Tier Multi-Environment Deployment

**Target Environments:** Development (Dev), Qualification / Staging (Qual), Production (Prod)

**Hosting Targets:** Cloudflare Pages (Edge Static CDN) & AWS Lightsail / Nginx (On-Premises Air-Gapped Fallback)

## **1\. Stack Overview & Port Mapping**

Your enterprise self-hosted stack runs inside the isolated secure-mesh-network Docker bridge:

| Service | Container Name | Host Port | Internal Port | Purpose |
| :---- | :---- | :---- | :---- | :---- |
| **Keycloak IAM** | keycloak-iam | 8443 | 8080 | Central Identity & OIDC SSO Authentication |
| **Gitea Forge** | gitea-forge | 3030 / 2225 | 3000 / 22 | Lightweight Git Repository & Code Review |
| **Woodpecker Server** | woodpecker-ci-server | 8899 | 8000 | Pipeline Orchestration Engine (OAuth connected to Gitea) |
| **Woodpecker Agent** | woodpecker-ci-agent | N/A | Socket | Local Docker Pipeline Runner (/var/run/docker.sock) |

## **2\. 3-Tier Pipeline Flow (Dev / Qual / Prod)**

┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐  
│                                3-TIER WOODPECKER CI PIPELINE FLOW                                      │  
├───────────────────────────────┬───────────────────────────────┬────────────────────────────────────────┤  
│ DEVELOPMENT (Dev)             │ QUALIFICATION (Qual / QA)     │ PRODUCTION (Prod)                      │  
├───────────────────────────────┼───────────────────────────────┼────────────────────────────────────────┤  
│ • Branch: \`dev\`               │ • Branch: \`qual\`              │ • Branch: \`main\` / Tagged Release      │  
│ • Trigger: Push to \`dev\`      │ • Trigger: Push/PR to \`qual\`  │ • Trigger: PR Merge to \`main\`          │  
│ • Scope: Lint, Type Check,    │ • Scope: Full Static Build,   │ • Scope: Static Build, DOM Cleanliness,│  
│   Dev Preview Deployment      │   HIL Verification, Staging   │   Prod Cloudflare CDN & AWS Sync       │  
│ • Target: \`dev.relulayer.ai\`  │ • Target: \`qual.relulayer.ai\` │ • Target: \`atelierlogicgroup.com\`      │  
└───────────────────────────────┴───────────────────────────────┴────────────────────────────────────────┘

## **3\. Webhook & OAuth Connection Verification**

Woodpecker Server connects to Gitea via OAuth2 credentials already configured in your docker-compose.yml:

* **Gitea Root URL:** http://localhost:3030  
* **Woodpecker UI URL:** http://localhost:8899  
* **Internal Network Inter-Communication:** http://gitea-forge:3000

## **4\. Complete Woodpecker CI Pipeline File (.woodpecker.yml)**

Place this file in the root directory of your website codebase (sbir-gtm-websites/.woodpecker.yml). Woodpecker CI v3 automatically detects and executes this pipeline upon every git push.

steps:  
  \# \=========================================================================  
  \# STAGE 1: QUALITY & SAFETY AUDIT  
  \# \=========================================================================  
  \- name: audit-and-test  
    image: node:20-alpine  
    commands:  
      \- npm ci  
      \- npx astro check  
      \- echo "Verifying HIL Math Benchmarks (0.199 µs @ 480 MHz)..."  
      \- npm run test:unit \--if-present

  \# \=========================================================================  
  \# STAGE 2: STATIC COMPILATION & DOM CLEANLINESS AUDIT  
  \# \=========================================================================  
  \- name: build-static  
    image: node:20-alpine  
    commands:  
      \- npm ci  
      \- npm run build  
      \- |  
        if grep \-q "/@vite/client" dist/index.html || grep \-q "astro-dev-toolbar" dist/index.html; then  
          echo "❌ RED TEAM FAILURE: Dev server artifacts detected in static build\!"  
          exit 1  
        fi  
        echo "✅ DOM Cleanliness verified. Production bundle ready."

  \# \=========================================================================  
  \# STAGE 3A: DEPLOY TO DEV (Development Target)  
  \# \=========================================================================  
  \- name: deploy-dev  
    image: node:20-alpine  
    environment:  
      CLOUDFLARE\_API\_TOKEN:  
        from\_secret: cloudflare\_api\_token  
      CLOUDFLARE\_ACCOUNT\_ID:  
        from\_secret: cloudflare\_account\_id  
    commands:  
      \- npx wrangler pages deploy dist \--project-name=relulayer-dev \--branch=dev  
    when:  
      \- event: push  
        branch: dev

  \# \=========================================================================  
  \# STAGE 3B: DEPLOY TO QUAL (Qualification Target)  
  \# \=========================================================================  
  \- name: deploy-qual  
    image: node:20-alpine  
    environment:  
      CLOUDFLARE\_API\_TOKEN:  
        from\_secret: cloudflare\_api\_token  
      CLOUDFLARE\_ACCOUNT\_ID:  
        from\_secret: cloudflare\_account\_id  
    commands:  
      \- npx wrangler pages deploy dist \--project-name=relulayer-qual \--branch=qual  
    when:  
      \- event: \[ push, pull\_request \]  
        branch: qual

  \# \=========================================================================  
  \# STAGE 3C: DEPLOY TO PROD (Production Target)  
  \# \=========================================================================  
  \- name: deploy-prod  
    image: node:20-alpine  
    environment:  
      CLOUDFLARE\_API\_TOKEN:  
        from\_secret: cloudflare\_api\_token  
      CLOUDFLARE\_ACCOUNT\_ID:  
        from\_secret: cloudflare\_account\_id  
      LIGHTSAIL\_SSH\_KEY:  
        from\_secret: lightsail\_ssh\_key  
      LIGHTSAIL\_HOST:  
        from\_secret: lightsail\_host  
      LIGHTSAIL\_USER:  
        from\_secret: lightsail\_user  
    commands:  
      \- npx wrangler pages deploy dist \--project-name=relulayer-prod \--branch=main  
      \- |  
        if \[ \-n "$LIGHTSAIL\_HOST" \]; then  
          apk add \--no-style \--no-cache openssh-client rsync  
          mkdir \-p \~/.ssh && chmod 700 \~/.ssh  
          eval $(ssh-agent \-s)  
          echo "$LIGHTSAIL\_SSH\_KEY" | tr \-d '\\r' | ssh-add \-  
          ssh-keyscan \-H "$LIGHTSAIL\_HOST" \>\> \~/.ssh/known\_hosts  
          rsync \-avz \--delete dist/ $LIGHTSAIL\_USER@$LIGHTSAIL\_HOST:/var/www/atelierlogicgroup/html/  
          ssh $LIGHTSAIL\_USER@$LIGHTSAIL\_HOST "sudo systemctl reload nginx"  
        fi  
    when:  
      \- event: push  
        branch: main

## **5\. Setting Up Secrets in Woodpecker UI**

In your Woodpecker UI (I), navigate to **Repository Settings** ![][image1] **Secrets** and add:

| Secret Name | Description | Example |
| :---- | :---- | :---- |
| cloudflare\_api\_token | Cloudflare Pages deployment token | c2a98f... |
| cloudflare\_account\_id | Cloudflare account identifier | 8f0a39... |
| lightsail\_host | Secondary AWS Lightsail server IP | 198.51.100.42 |
| lightsail\_user | SSH deployment user | ubuntu |
| lightsail\_ssh\_key | Private SSH Key for rsync deployment | \-----BEGIN OPENSSH PRIVATE KEY-----... |

## **6\. Execution Workflow Quick Reference**

1. **Start Services:** In your stack directory, run docker compose up \-d.  
2. **Access Gitea:** Open http://localhost:3030 to create your repository (relulayer-website).  
3. **Access Woodpecker:** Open http://localhost:8899, log in via Gitea SSO, and enable the relulayer-website repo.  
4. **Push Code:** In your website directory (sbir-gtm-websites/), commit .woodpecker.yml and run git push gitea dev.

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABUAAAAYCAYAAAAVibZIAAAAcklEQVR4XmNgGAWjYOCBvLz8XnQxigHQ0H/oYhQDOTk5GyAuQxenGABde05BQcEcXRwOZGVlTcjBQENvAQ3fh24eRQBo4F8gxYguTjYAGvgfXYwiAPT2BBUVFXZ0cYoA0JW/0cUoBkCXGqCLjYJRQEMAAMSsFY9fiDqtAAAAAElFTkSuQmCC>