# Deployment Guide

ProjectPilot deploys to Oracle Cloud Infrastructure (OCI) Always Free Tier using Terraform for infrastructure and GitHub Actions for CI/CD.

## Architecture

```
GitHub Actions → GHCR (Docker Image)
                     ↓
              SSH → OCI VM (Ubuntu 24.04, ARM)
                     ↓
              Nginx (port 80) → Docker Compose
                     ↓
         ┌───────────┴───────────┐
    Backend (FastAPI)      Frontend (Streamlit)
    port 5000               port 8501
         └───────────┬───────────┘
              SQLite + ChromaDB
```

- **Compute**: OCI `VM.Standard.A1.Flex` (1 OCPU, 1 GB RAM) — Always Free eligible (ARM)
- **Registry**: GitHub Container Registry (GHCR)
- **Proxy**: Nginx reverse proxy (port 80, optional HTTPS with certbot)
- **Storage**: Local SQLite + ChromaDB on the VM (persistent volumes)

## Quick Start

### 1. Provision Infrastructure

```bash
cd terraform

# Set your OCI API key path
export OCI_PRIVATE_KEY_PATH="C:/Users/shres/Downloads/shresthsrivastav01@gmail.com-2026-06-23T09_46_49.016Z.pem"

# Initialize and apply
terraform init
terraform plan -var="oci_private_key_path=$OCI_PRIVATE_KEY_PATH"
terraform apply -var="oci_private_key_path=$OCI_PRIVATE_KEY_PATH"
```

Save the outputs:
```bash
terraform output instance_public_ip   # → VM IP address
terraform output ssh_connection_string # → ssh deploy@<IP>
```

### 2. Configure GitHub Secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|--------|-------|
| `OCI_HOST` | VM public IP from `terraform output` |
| `OCI_USER` | `deploy` |
| `OCI_SSH_PRIVATE_KEY` | Contents of `ssh-key-2026-06-21.key` (private key) |
| `GHCR_PAT` | GitHub PAT with `write:packages` scope |
| `DOMAIN_NAME` | (optional) Your domain for HTTPS |

For Terraform CI (optional):

| Secret | Value |
|--------|-------|
| `OCI_TENANCY_OCID` | `ocid1.tenancy.oc1..aaaaaaaa...` |
| `OCI_USER_OCID` | `ocid1.user.oc1..aaaaaaa...` |
| `OCI_FINGERPRINT` | `xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx` |
| `OCI_PRIVATE_KEY` | Contents of your OCI API private key `.pem` file |
| `OCI_REGION` | `ap-mumbai-1` |
| `COMPARTMENT_OCID` | Same as tenancy OCID |
| `SSH_PUBLIC_KEY` | Contents of `ssh-key-2026-06-21.key.pub` |

### 3. Create .env on VM

```bash
ssh deploy@<VM_IP>
sudo mkdir -p /opt/projectpilot
sudo nano /opt/projectpilot/.env
```

Copy from `.env.example` and fill in your API keys.

### 4. Deploy

Push to `main` branch. GitHub Actions will:
1. Run lint + tests
2. Build Docker image (ARM) → push to GHCR
3. SSH into OCI VM → pull image → restart containers → health check

Manual deploy:
```bash
gh workflow run cd.yml -f tag=latest
```

## Files

| File | Purpose |
|------|---------|
| `terraform/main.tf` | VCN, subnet, internet gateway, route table, compute, NSG |
| `terraform/variables.tf` | All configurable variables with defaults |
| `terraform/outputs.tf` | `instance_public_ip`, `ssh_connection_string`, `instance_id` |
| `terraform/terraform.tfvars` | Your OCI credentials and configuration |
| `terraform/providers.tf` | OCI provider v5 with version constraints |
| `terraform/cloud-init.yaml` | VM bootstrap: Docker, nginx, firewall, deploy user |
| `terraform/modules/compute/` | OCI instance with cloud-init |
| `terraform/modules/nsg/` | Network security group (SSH, HTTP, HTTPS) |
| `docker-compose.prod.yml` | Backend + frontend services with health checks |
| `scripts/deploy.sh` | Deploy/rollback script executed on the VM |
| `.github/workflows/cd.yml` | CI/CD pipeline |
| `.github/workflows/terraform.yml` | Terraform plan/apply/destroy |
| `.env.example` | Environment variable template |

## Rollback

If a deployment fails, `deploy.sh` automatically rolls back to the previous image.

Manual rollback:
```bash
ssh deploy@<VM_IP>
cd /opt/projectpilot
IMAGE_TAG=latest docker compose -f docker-compose.prod.yml up -d --force-recreate
```

## Destroy Infrastructure

```bash
cd terraform
terraform destroy -var="oci_private_key_path=$OCI_PRIVATE_KEY_PATH"
```

Or via GitHub Actions:
```
Actions → Terraform Infrastructure → Run workflow → action: destroy
```
