# OCI Setup Guide

Step-by-step guide for setting up Oracle Cloud Infrastructure for ProjectPilot deployment.

## Prerequisites

- Oracle Cloud Free Tier account
- Terraform >= 1.5.0 installed locally
- OCI API key pair generated
- SSH key pair generated for VM access

## 1. Generate OCI API Key

If you haven't already:

```bash
# Generate API key
openssl genrsa -out oci_api_key.pem 2048
openssl rsa -pubout -in oci_api_key.pem -out oci_api_key_public.pem

# Add to OCI console: Profile → API Keys → Add API Key
# Copy the fingerprint shown after upload
```

## 2. Generate SSH Key for VM Access

```bash
ssh-keygen -t ed25519 -C "projectpilot-deploy" -f ~/.ssh/oci_projectpilot
```

## 3. Configure terraform.tfvars

Edit `terraform/terraform.tfvars`:

```hcl
# OCI Authentication
oci_tenancy_ocid     = "ocid1.tenancy.oc1..aaaaaaa..."
oci_user_ocid        = "ocid1.user.oc1..aaaaaaa..."
oci_fingerprint      = "xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx"
oci_private_key_path = "C:/Users/you/Downloads/oci_api_key.pem"

# OCI Resources
compartment_ocid = "ocid1.tenancy.oc1..aaaaaaa..."  # Same as tenancy for free tier
oci_region       = "ap-mumbai-1"

# SSH
ssh_public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI..."
```

**Note**: `compartment_ocid` is typically the same as `oci_tenancy_ocid` for Free Tier.

## 4. Provision Infrastructure

```bash
cd terraform

terraform init
terraform plan
terraform apply
```

Save the outputs:
```bash
terraform output instance_public_ip
terraform output ssh_connection_string
```

## 5. SSH into VM

```bash
ssh -i ~/.ssh/oci_projectpilot deploy@<INSTANCE_PUBLIC_IP>
```

## 6. Create .env on VM

```bash
sudo mkdir -p /opt/projectpilot
sudo nano /opt/projectpilot/.env
```

Add from `.env.example`:

```
ADMIN_API_KEY=<generate: python -c "import secrets; print(secrets.token_urlsafe(32))">
USER_API_KEY=<generate: python -c "import secrets; print(secrets.token_urlsafe(32))">
GOOGLE_API_KEY=your-gemini-key
CHROMA_PATH=/opt/projectpilot/data/chroma_data
GENERATED_PROJECTS_DIR=/opt/projectpilot/data/generated_projects
MEMORY_STORE_DIR=/opt/projectpilot/data/memory_store
BACKEND_URL=http://127.0.0.1:8000
LOG_LEVEL=INFO
RATE_LIMIT_ENABLED=true
SKIP_AUTH=false
```

```bash
sudo chown deploy:deploy /opt/projectpilot/.env
sudo chmod 600 /opt/projectpilot/.env
```

## 7. Configure GitHub Secrets

### Required Secrets

| Secret | How to get |
|--------|-----------|
| `OCI_HOST` | `terraform output -raw instance_public_ip` |
| `OCI_USER` | `deploy` |
| `OCI_SSH_PRIVATE_KEY` | `cat ~/.ssh/oci_projectpilot` (private key contents) |
| `GHCR_PAT` | GitHub → Settings → Developer settings → PATs → `write:packages` |

### Optional Secrets

| Secret | Purpose |
|--------|---------|
| `DOMAIN_NAME` | Enables HTTPS with certbot |

### Creating GHCR PAT

1. GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
2. Generate new token
3. Repository access: select `Projectpilot`
4. Permissions: Repository permissions → Contents (read), Packages (write)
5. Copy the token → add as `GHCR_PAT` secret

## 8. Trigger Deployment

Push to `main`:
```bash
git push origin main
```

Or manual trigger:
```bash
gh workflow run cd.yml
```

## Free Tier Resources

| Resource | Limit | Our Usage |
|----------|-------|-----------|
| Compute | 4 OCPUs, 24 GB RAM | 1 OCPU, 1 GB RAM |
| Storage | 200 GB boot volume | ~50 GB |
| Network | 10 TB/month outbound | Minimal |
| Database | Not included | SQLite + ChromaDB (local) |
