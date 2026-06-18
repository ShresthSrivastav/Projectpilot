# ProjectPilot Production Deployment Guide

## Architecture

```
Internet → Nginx (HTTPS) → Backend (FastAPI :8000)
                         → Frontend (Streamlit :8501)
                         → PostgreSQL (Managed)
```

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Terraform | >= 1.5.0 | https://developer.hashicorp.com/terraform/install |
| Docker | 24+ | https://docs.docker.com/engine/install/ |
| GitHub Account | — | For GHCR and Actions |

## 1. GitHub Secrets Setup

Add these secrets in **Settings → Secrets and variables → Actions**:

| Secret | Description |
|--------|-------------|
| `DO_TOKEN` | DigitalOcean API token |
| `DO_SSH_KEY_ID` | DigitalOcean SSH key ID |
| `DO_HOST` | Droplet IP (set after first apply) |
| `DO_USER` | SSH username (`deploy`) |
| `DOMAIN_NAME` | Your domain (e.g., `app.example.com`) |
| `SPACES_ACCESS_KEY_ID` | DigitalOcean Spaces access key |
| `SPACES_SECRET_ACCESS_KEY` | DigitalOcean Spaces secret key |

## 2. DigitalOcean Spaces (Terraform State)

1. Create a Spaces bucket: `projectpilot-terraform-state` in `nyc3`
2. Generate Spaces API keys: **API → Tokens → Spaces Keys**
3. Add keys to GitHub Secrets

## 3. Generate SSH Key

```bash
ssh-keygen -t ed25519 -f ~/.ssh/projectpilot -N ""
```

Upload to DigitalOcean:
```bash
# Using doctl CLI
doctl compute ssh-key create projectpilot --public-key-file ~/.ssh/projectpilot.pub
```

## 4. Terraform Deployment

### Initialize

```bash
cd terraform

# Copy and edit variables
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values

# Initialize
terraform init \
  -backend-config="access_key=$SPACES_ACCESS_KEY_ID" \
  -backend-config="secret_key=$SPACES_SECRET_ACCESS_KEY"

# Create workspace
terraform workspace new prod
terraform workspace select prod
```

### Plan

```bash
terraform plan \
  -var-file="environments/prod.tfvars" \
  -var="do_token=$DO_TOKEN" \
  -var="ssh_key_ids=[SSH_KEY_ID]" \
  -var="domain_name=app.example.com"
```

### Apply

```bash
terraform apply \
  -var-file="environments/prod.tfvars" \
  -var="do_token=$DO_TOKEN" \
  -var="ssh_key_ids=[SSH_KEY_ID]" \
  -var="domain_name=app.example.com"
```

### Output

After apply, get the droplet IP:
```bash
terraform output droplet_ip
terraform output ssh_command
```

## 5. Domain Setup

1. Point your domain A record to the droplet IP
2. Update `DO_HOST` secret with the droplet IP
3. Update `DOMAIN_NAME` secret with your domain

```bash
# Example DNS records
Type    Name    Value           TTL
A       app     192.168.1.100   300
CNAME   www     app.example.com 300
```

## 6. SSL Certificate

On the droplet:
```bash
# SSH into the droplet
ssh root@YOUR_DROPLET_IP

# Get SSL certificate
certbot --nginx -d app.example.com --non-interactive --agree-tos --email admin@example.com

# Verify auto-renewal
certbot renew --dry-run
```

## 7. GHCR Setup

The `build-and-push.yml` workflow automatically pushes to `ghcr.io/shresthsrivastav/projectpilot`.

To manually push:
```bash
# Login to GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u ShresthSrivastav --password-stdin

# Build and push
docker build -t ghcr.io/shresthsrivastav/projectpilot:latest .
docker push ghcr.io/shresthsrivastav/projectpilot:latest
```

## 8. Environment Variables

Create `/opt/projectpilot/.env` on the droplet:

```bash
ADMIN_API_KEY=ak-admin-your-admin-key
USER_API_KEY=ak-user-your-user-key
TOKEN_ENCRYPTION_KEY=your-encryption-key
OLLAMA_BASE_URL=http://localhost:11434
MODEL_FAST=qwen2.5-coder:1.5b
MODEL_BALANCED=qwen2.5-coder:7b
MODEL_POWERFUL=qwen2.5-coder:14b
GOOGLE_API_KEY=your-google-api-key
BACKEND_PORT=8000
FRONTEND_PORT=8501
CHROMA_PATH=./chroma_data
GENERATED_PROJECTS_DIR=./generated_projects
MEMORY_STORE_DIR=./memory_store
LOG_LEVEL=INFO
RATE_LIMIT_ENABLED=true
RATE_LIMIT_GENERATE=5
RATE_LIMIT_DEFAULT=60
```

## 9. Verify Deployment

```bash
# Health check
curl https://app.example.com/health

# API docs
curl https://app.example.com/docs

# Frontend
open https://app.example.com/
```

## 10. Rollback

### Rollback Application

```bash
# SSH into droplet
ssh root@YOUR_DROPLET_IP

# List available images
docker images ghcr.io/shresthsrivastav/projectpilot

# Deploy specific version
cd /opt/projectpilot
export IMAGE_TAG=v1.0.0
docker compose -f docker-compose.prod.yml up -d --force-recreate
```

### Rollback Infrastructure

```bash
cd terraform
terraform plan -out=tfplan
# Review changes
terraform apply tfplan
```

### Full Destroy

```bash
cd terraform
terraform destroy \
  -var-file="environments/prod.tfvars" \
  -var="do_token=$DO_TOKEN"
```

## 11. Troubleshooting

| Problem | Solution |
|---------|----------|
| Container won't start | `docker logs projectpilot_backend` |
| Port 80/443 blocked | Check firewall: `ufw status` |
| SSL not working | Verify cert: `certbot certificates` |
| Database connection failed | Check `.env` DATABASE_URL |
| Out of memory | Increase droplet size or add swap |
| GHCR auth failed | Re-login: `docker login ghcr.io` |

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

## 12. Monitoring

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
├── build-and-push.yml         # CI/CD + GHCR
├── deploy.yml                 # Deployment trigger
└── ci.yml                     # PR checks

docker-compose.prod.yml        # Production compose
nginx/nginx.conf               # Nginx config
```
