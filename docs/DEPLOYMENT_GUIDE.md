# ProjectPilot Production Deployment Guide

## Architecture

```
Internet → Nginx (HTTPS) → Backend (FastAPI :5000)
                         → Frontend (Streamlit :8501)
                         → PostgreSQL (Managed)
```

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Terraform | >= 1.5.0 | https://developer.hashicorp.com/terraform/install |
| Docker | 24+ | https://docs.docker.com/engine/install/ |
| GitHub Account | — | For GHCR and Actions |

## Deployment Architecture

### Workflows

```
PR → ci.yml (lint + test, 3.11 + 3.12)
                         ↓
merge to main ──────────────────┐
                                ↓
                         cd.yml ──────────────────────────
                         ├── lint-and-test (same as ci)   │
                         ├── docker-build (GHCR push)    │
                         └── deploy (SSH → OCI VM)       │
                              ├── pull latest image       │
                              ├── docker compose up        │
                              ├── health check (300s)      │
                              ├── verify public endpoint   │
                              └── rollback on failure     │
```

### Concurrency

`cd.yml` uses `concurrency: cd-main` with `cancel-in-progress: false`. If two merges happen rapidly, the second deployment waits for the first to finish (queued, not cancelled).

## 1. GitHub Secrets Setup

Add these secrets in **Settings → Secrets and variables → Actions**:

### Required (CD pipeline)

| Secret | Description |
|--------|-------------|
| `OCI_HOST` | OCI VM public IP |
| `OCI_USER` | SSH username (e.g. `ubuntu`) |
| `OCI_SSH_PRIVATE_KEY` | SSH private key for OCI VM |
| `OCI_ENV_FILE` | `.env` file content (base64 encoded) |
| `DOMAIN_NAME` | Your domain (e.g., `app.example.com`) |

### Optional (Terraform)

| Secret | Description |
|--------|-------------|
| `OCI_TENANCY_OCID` | OCI tenancy OCID |
| `OCI_USER_OCID` | OCI user OCID |
| `OCI_FINGERPRINT` | OCI API key fingerprint |
| `OCI_REGION` | Region (e.g. `ap-mumbai-1`) |
| `OCI_PRIVATE_KEY` | OCI API private key |

## 2. OCI VM Setup

### Create VM

1. Create an OCI Compute VM (Ubuntu 22.04+, minimum recommended: VM.Standard.E2.1.Micro for free tier, VM.Standard.E4.Flex for production)
2. Configure security list to allow ports 22 (SSH), 80 (HTTP), 443 (HTTPS), 5000 (App)
3. Note the public IP and set `OCI_HOST`

### Initial Setup

```bash
ssh ubuntu@YOUR_VM_IP

# Install Docker
curl -fsSL https://get.docker.com | sudo bash
sudo usermod -aG docker ubuntu

# Create project directory
sudo mkdir -p /opt/projectpilot
sudo chown ubuntu:ubuntu /opt/projectpilot
```

### Copy files to VM

```bash
# From local machine
scp docker-compose.prod.yml ubuntu@YOUR_VM_IP:/opt/projectpilot/
scp -r scripts/ ubuntu@YOUR_VM_IP:/opt/projectpilot/
scp -r nginx/ ubuntu@YOUR_VM_IP:/opt/projectpilot/

# Create .env and set as secret OCI_ENV_FILE (base64 encoded)
export OCI_ENV_FILE=$(cat .env.production | base64 -w0)

# Apply .env
ssh ubuntu@YOUR_VM_IP 'echo "$OCI_ENV_FILE" | base64 -d > /opt/projectpilot/.env'
```

## 3. CD Pipeline

The `cd.yml` workflow runs automatically on every push to `main`:

1. **lint-and-test**: Runs ruff + pytest on Python 3.11 and 3.12 (same as `ci.yml`)
2. **docker-build**: Builds Docker image and pushes to `ghcr.io/shresthsrivastav/projectpilot:latest`
3. **deploy**: SSHes into OCI VM, runs `scripts/deploy.sh`

### Deploy Script (`scripts/deploy.sh`)

```bash
bash /opt/projectpilot/scripts/deploy.sh [tag]
```

- Saves current `:latest` as `:previous` for rollback
- Pulls new image
- Runs `docker compose up -d --force-recreate`
- Polls `docker health` / HTTP health check for 300s
- On failure: restores `:previous` image and restarts

## 4. GHCR Setup

### Automatic (via CI)

Every push to `main` triggers `cd.yml` which builds and pushes to `ghcr.io/shresthsrivastav/projectpilot`.

### Manual push

```bash
echo $GITHUB_TOKEN | docker login ghcr.io -u ShresthSrivastav --password-stdin
docker build -t ghcr.io/shresthsrivastav/projectpilot:latest .
docker push ghcr.io/shresthsrivastav/projectpilot:latest
```

## 5. Environment Variables

Create `/opt/projectpilot/.env` on the VM:

```bash
ADMIN_API_KEY=ak-admin-your-admin-key
USER_API_KEY=ak-user-your-user-key
TOKEN_ENCRYPTION_KEY=your-encryption-key
OLLAMA_BASE_URL=http://localhost:11434
MODEL_FAST=qwen2.5-coder:1.5b
MODEL_BALANCED=qwen2.5-coder:7b
MODEL_POWERFUL=qwen2.5-coder:14b
GOOGLE_API_KEY=your-google-api-key
BACKEND_PORT=5000
FRONTEND_PORT=8501
CHROMA_PATH=./chroma_data
GENERATED_PROJECTS_DIR=./generated_projects
MEMORY_STORE_DIR=./memory_store
LOG_LEVEL=INFO
RATE_LIMIT_ENABLED=true
RATE_LIMIT_GENERATE=5
RATE_LIMIT_DEFAULT=60
```

## 6. SSL Certificate with Let's Encrypt

```bash
# SSH into VM
ssh ubuntu@YOUR_VM_IP

# Install certbot
sudo apt install -y certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d app.example.com --non-interactive --agree-tos --email admin@example.com

# Verify renewal
sudo certbot renew --dry-run
```

## 7. Verify Deployment

```bash
# Health check
curl https://app.example.com/health

# API docs
curl https://app.example.com/docs

# Frontend
open https://app.example.com/
```

## 8. Rollback

### Automatic (CD pipeline)

If the deploy step fails, `cd.yml` automatically SSHes into the VM and runs `scripts/deploy.sh previous` to restore the prior image.

### Manual rollback

```bash
# SSH into VM
ssh ubuntu@YOUR_VM_IP
cd /opt/projectpilot

# List images
docker images ghcr.io/shresthsrivastav/projectpilot

# Deploy previous
bash scripts/deploy.sh previous

# Or deploy specific version
export IMAGE_TAG=v1.0.0
docker compose -f docker-compose.prod.yml up -d --force-recreate
```

### Rollback Infrastructure

```bash
cd terraform
terraform plan -out=tfplan
terraform apply tfplan
```

## 9. Troubleshooting

| Problem | Solution |
|---------|----------|
| Container won't start | `docker logs projectpilot_backend` |
| Port 80/443 blocked | Check OCI security list rules |
| SSL not working | Verify cert: `certbot certificates` |
| Database connection failed | Check `.env` DATABASE_URL |
| Out of memory | Increase VM shape or add swap |
| GHCR auth failed | Re-login: `docker login ghcr.io` |
| CD workflow stuck | Check GitHub Actions logs; verify `concurrency: cd-main` |

### Logs

```bash
# Backend logs
docker logs -f projectpilot_backend

# Frontend logs
docker logs -f projectpilot_frontend

# Nginx logs
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log

# System logs
journalctl -u projectpilot -f

# Deploy logs
ls -la /opt/projectpilot/logs/
```

### Disk Cleanup

```bash
# Remove old images
docker image prune -af

# Remove unused volumes
docker volume prune -f

# Check disk usage
df -h
```

## 10. Monitoring

```bash
# Container stats
docker stats

# System resources
htop

# Network connections
ss -tlnp

# Process list
ps aux | grep docker
```

## File Structure

```
terraform/
├── main.tf                    # Root module
├── providers.tf               # Provider config
├── versions.tf                # Version constraints + backend
├── variables.tf               # Input variables
├── outputs.tf                 # Output values
├── terraform.tfvars           # OCI API key fingerprint
├── terraform.tfvars.example   # Variable template
├── cloud-init.yaml            # Server provisioning
├── environments/
│   ├── dev.tfvars
│   ├── staging.tfvars
│   └── prod.tfvars
└── modules/
    ├── droplet/               # Droplet + Reserved IP
    ├── firewall/              # Firewall rules
    └── database/              # Managed PostgreSQL

.github/workflows/
├── terraform.yml              # IaC pipeline
├── cd.yml                     # CD pipeline (build + push + deploy)
└── ci.yml                     # PR checks (lint + test)

scripts/
└── deploy.sh                  # OCI VM deploy + rollback

docker-compose.prod.yml        # Production compose
nginx/nginx.conf               # Nginx config
```
