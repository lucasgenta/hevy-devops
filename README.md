# Hevy DevOps — Production-Grade Containerized Deployment

**Demonstrates modern DevOps practices using Docker, CI/CD, and infrastructure-as-code.**

> A real-world fitness tracking application (Hevy API scraper + Streamlit dashboard) wrapped in production-grade DevOps tooling. Deploy with a single command.

---

## 📋 Table of Contents

- [Architecture](#-architecture)
- [DevOps Practices Demonstrated](#-devops-practices-demonstrated)
- [Quick Start](#-quick-start)
- [Service Overview](#-service-overview)
- [CI/CD Pipeline](#-cicd-pipeline)
- [Makefile Targets](#-makefile-targets)
- [Project Structure](#-project-structure)
- [Scaling](#-scaling)
- [Security](#-security)

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Docker Compose Stack                         │
│                                                                     │
│  Internet                                                           │
│     │                                                               │
│     ▼                                                               │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                     GATEWAY (nginx:1.27-alpine)              │   │
│  │   • Reverse proxy              • Rate limiting (10 r/s)      │   │
│  │   • Load balancing upstream     • WebSocket support          │   │
│  │   • Security headers            • /healthz endpoint          │   │
│  │   Port 80 ────► http://dashboard_backend                     │   │
│  └──────────────────────┬───────────────────────────────────────┘   │
│                         │                                           │
│                         ▼                                           │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                  DASHBOARD (Streamlit)                       │   │
│  │   • Training analytics     • AI Coach (Deepseek)             │   │
│  │   • Muscle analysis        • Nutrition tracking              │   │
│  │   • Personal records       • Meal logging                    │   │
│  │   • Body measurements      • PWA support                     │   │
│  │   Port 8501 — reads from shared volume                       │   │
│  └──────────────────────┬───────────────────────────────────────┘   │
│                         │                                           │
│                         ▼                                           │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                   SCRAPER (Periodic sync)                    │   │
│  │   • Scrapes Hevy API on startup + every 6h                  │   │
│  │   • Writes structured JSON to persistent volume             │   │
│  │   • Health check on pid 1                                   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │           VOLUME: hevy_scraped_data (persistent)             │   │
│  │   Survives restarts • Shared between scraper + dashboard     │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  Network: hevy_network (bridge)   Env: .env (gitignored)           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 DevOps Practices Demonstrated

| Practice | Implementation |
|----------|---------------|
| **Containerization** | Multi-stage Dockerfiles for each service. Builder pattern separates dependency installation from runtime, maximizing layer caching and minimizing final image size. |
| **Orchestration** | Docker Compose defines the entire stack as code. Services communicate over a dedicated bridge network with DNS-based service discovery. |
| **Gateway / Reverse Proxy** | Nginx acts as the single entry point, routing traffic to the dashboard, handling WebSocket upgrades (required by Streamlit), and adding security headers. |
| **Load Balancing** | Nginx `upstream` block configured for horizontal scaling. Add more dashboard replicas with `make scale N=3`. |
| **Rate Limiting** | Nginx `limit_req` zones protect both the dashboard and health endpoint from traffic spikes. |
| **Health Checks** | Every service has a Docker `HEALTHCHECK` with appropriate intervals, timeouts, and start periods. The gateway's `/healthz` provides a zero-dependency liveness probe. |
| **Scheduled Jobs** | The scraper runs on a configurable interval (default: 6h) via a simple loop in the entrypoint. Can also run once with `SCRAPE_ONCE=1`. |
| **Secrets Management** | API keys in `.env` (gitignored), with `.env.example` as the documented template. Docker Compose injects via `env_file`. |
| **Persistent Data** | Named Docker volume `hevy_scraped_data` survives container restarts and is shared between scraper (write) and dashboard (read). |
| **CI/CD Pipeline** | GitHub Actions runs linting, multi-stage Docker builds, smoke tests, and vulnerability scanning on every push. |
| **Security Scanning** | Trivy scans all Docker images for HIGH/CRITICAL CVEs in CI. Results uploaded as GitHub SARIF artifacts. |
| **Dev/Prod Parity** | `docker-compose.override.yml` adds live-reload mounts and debug logging for development without changing the main compose file. |
| **Developer Experience** | Makefile with common targets (`make up`, `make test`, `make logs`, `make scale N=3`). |

---

## 🚀 Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (with Compose v2)
- A [Hevy API key](https://hevy.com/settings?developer) (free)

### 1. Clone and configure

```bash
git clone https://github.com/lucasgenta/hevy-devops.git
cd hevy-devops
cp .env.example .env
```

Edit `.env` and add your `HEVY_API_KEY`.

### 2. Start the stack

```bash
make up
```

Or equivalently:

```bash
docker compose up -d
```

### 3. Open the dashboard

Visit **[http://localhost](http://localhost)** — the Nginx gateway proxies to the Streamlit dashboard.

### 4. Verify everything is healthy

```bash
make info
curl http://localhost/healthz    # should return "OK"
```

### 5. (Optional) Trigger a manual scrape

```bash
make run-scrape
```

---

## 📦 Service Overview

### Gateway (`services/gateway/`)
- **Base image**: `nginx:1.27-alpine`
- **Port**: `80` (exposed to host)
- **Health check**: `wget --spider http://localhost/80/healthz`
- **Config**: Custom `nginx.conf` with WebSocket support, rate limiting, security headers

### Dashboard (`services/dashboard/`)
- **Base image**: `python:3.12-slim` (multi-stage from `builder`)
- **Framework**: Streamlit (training analytics, AI coach, nutrition tracking)
- **Port**: `8501` (internal, exposed via gateway)
- **Health check**: TCP connection to `localhost:8501`

### Scraper (`services/scraper/`)
- **Base image**: `python:3.12-slim` (multi-stage from `builder`)
- **Purpose**: Periodic Hevy API data sync
- **Schedule**: On startup + every `SCRAPE_INTERVAL` seconds (default: 6h)
- **Health check**: Null signal to pid 1 (verifies process is alive)

---

## 🔄 CI/CD Pipeline

On every push/PR to `main`:

```
Lint (ruff) → Build Images (Docker Buildx) → Smoke Test (deploy + healthcheck) → Security Scan (Trivy)
```

The pipeline:
1. **Lint**: Static analysis with `ruff` across all Python source
2. **Build**: Parallel multi-stage Docker builds via `docker compose build --parallel`
3. **Smoke Test**: Deploys the full stack, waits for health checks, verifies the gateway responds
4. **Security Scan**: Trivy scans for HIGH/CRITICAL CVEs. Results uploaded to GitHub Security tab.

---

## 🛠 Makefile Targets

| Target | Description |
|--------|-------------|
| `make build` | Build all Docker images |
| `make up` | Start all services (daemon) |
| `make down` | Stop all services |
| `make restart` | Restart the stack |
| `make logs` | Tail logs from all services |
| `make ps` | Show container status |
| `make info` | Show deployment info & URLs |
| `make test` | Run CI checks locally |
| `make run-scrape` | Trigger one-off scrape |
| `make scale N=3` | Scale dashboard to N replicas |
| `make clean` | Remove volumes (deletes data) |
| `make shell-dashboard` | Open shell in dashboard container |

---

## 📁 Project Structure

```
hevy-devops/
│
├── .github/workflows/
│   └── ci.yml                 # CI/CD pipeline (lint → build → test → scan)
│
├── services/
│   ├── gateway/
│   │   ├── Dockerfile         # Nginx with custom config
│   │   └── nginx.conf         # Reverse proxy + rate limiting + WebSocket
│   ├── dashboard/
│   │   ├── Dockerfile         # Multi-stage Streamlit build
│   │   └── requirements.txt
│   └── scraper/
│       ├── Dockerfile         # Multi-stage Python build
│       ├── entrypoint.sh      # Periodic scrape loop
│       └── requirements.txt
│
├── hevy/                      # Core library (Hevy API client + analytics)
├── nutrition/                 # Nutrition tracking + meal planning
├── pwa/                       # Progressive Web App files
├── scripts/                   # CLI entry points + healthcheck
├── data/                      # Data directory (mounted as volume)
│
├── docker-compose.yml         # Main stack definition
├── docker-compose.override.yml # Dev overrides (auto-reload, debug)
├── Makefile                   # Developer experience targets
├── .env.example               # Template for environment variables
└── README.md                  # This file
```

---

## 📈 Scaling

The gateway supports horizontal scaling of the dashboard service. To run multiple dashboard replicas:

```bash
make scale N=3
```

This starts 3 dashboard containers. The Nginx `upstream` block load-balances across them:

```nginx
upstream dashboard_backend {
    server dashboard:8501;
    server dashboard-1:8501;
    server dashboard-2:8501;
}
```

> **Note**: In production, you would use Swarm or Kubernetes for true orchestration with auto-healing, rolling updates, and declarative scaling. This setup demonstrates the **pattern** without the overhead of a full orchestrator.

---

## 🔒 Security

| Measure | Implementation |
|---------|---------------|
| **Secrets in `.env`** | API keys never committed. `.env` is in `.gitignore`. |
| **HTTP security headers** | `X-Frame-Options`, `X-Content-Type-Options`, `X-XSS-Protection` set by Nginx. |
| **Rate limiting** | Nginx `limit_req` prevents abuse (10 requests/second). |
| **Minimal base images** | `python:3.12-slim` and `nginx:1.27-alpine` reduce attack surface. |
| **Non-root user** | Containers run without unnecessary privileges. |
| **CVE scanning** | Trivy scans all images in CI. |
| **Path blocking** | Nginx blocks access to `.env`, `.git`, and dotfiles. |
| **Private Temp** | Docker containers get isolated tmpfs for temporary files. |

---

## 📝 What This Demonstrates to Interviewers

This repo shows I understand the **full lifecycle** of a cloud-native application:

1. **Development** — Clean project structure, Makefile for DX, dev/prod parity
2. **Containerization** — Multi-stage builds, layer caching, slim images
3. **Orchestration** — Docker Compose with networks, volumes, health checks
4. **Networking** — Reverse proxy, load balancing, WebSocket support, rate limiting
5. **CI/CD** — Automated linting, building, testing, and security scanning
6. **Security** — Secrets management, CVE scanning, security headers
7. **Operations** — Health checks, logging, scheduled jobs, scaling
8. **Documentation** — Architecture diagram, setup instructions, rationale

---

## 🏗 Production Considerations

For a production deployment, the next steps would be:

| Concern | Solution |
|---------|----------|
| Orchestration | Kubernetes (k3s/k8s) with Helm charts |
| High Availability | Multi-node cluster, pod anti-affinity |
| Monitoring | Prometheus + Grafana dashboards |
| Logging | ELK/Loki + structured JSON logging |
| Certificate | Let's Encrypt via cert-manager |
| Database | PostgreSQL for structured data (replace JSON files) |
| Image Registry | GitHub Container Registry or Docker Hub |
| GitOps | ArgoCD or Flux for declarative deployments |
| Secrets | Vault or external secrets operator |

---

## 📄 License

MIT

