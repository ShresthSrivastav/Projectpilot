# Troubleshooting

## Deployment Fails: "missing server host"

**Cause**: `OCI_HOST` secret not configured.

**Fix**: Add `OCI_HOST` with your VM's public IP in GitHub repo secrets.

## Deployment Fails: "Permission denied (publickey)"

**Cause**: SSH key mismatch between GitHub secret and VM.

**Fix**:
```bash
# Verify key is on VM
ssh -i your-key deploy@<IP> "cat ~/.ssh/authorized_keys"

# Re-add key if needed
ssh-copy-id -i ~/.ssh/oci_projectpilot deploy@<IP>
```

## Docker Login Fails on VM

**Cause**: `GHCR_PAT` secret not set or token lacks `write:packages` scope.

**Fix**: Create a new PAT with `write:packages` permission, add as `GHCR_PAT` secret.

## Terraform Apply Fails: "Out of host capacity"

**Cause**: OCI region has no available capacity for the shape.

**Fix**: Wait 5 minutes and retry, or try a different availability domain. Free Tier shapes are shared across all users.

## Terraform Plan Fails: "expected image_id, got source_id"

**Cause**: OCI provider version mismatch. Provider v5 uses `source_id`.

**Fix**: Ensure `providers.tf` has `version = ">= 5.0.0, < 6.0.0"`.

## Container Health Check Fails

**Symptoms**: Deploy script reports "backend failed health check".

**Diagnosis**:
```bash
ssh deploy@<VM_IP>
cd /opt/projectpilot
docker compose -f docker-compose.prod.yml logs backend --tail=50
```

Common causes:
- `.env` file missing or misconfigured
- Port 8000 already in use
- Ollama not running (if using local models)

## Application Returns 502 Bad Gateway

**Cause**: Nginx can't reach the backend container.

**Fix**:
```bash
# Check if backend is running
docker ps | grep projectpilot_backend

# Check backend logs
docker logs projectpilot_backend --tail=50

# Restart
cd /opt/projectpilot
docker compose -f docker-compose.prod.yml restart backend
```

## Frontend Can't Connect to Backend

**Cause**: Backend not healthy or network issue.

**Fix**: The frontend uses `BACKEND_URL=http://127.0.0.1:8000`. Ensure backend is on the same Docker network.

## Nginx Shows Default Page

**Cause**: Nginx config not linked.

**Fix**:
```bash
sudo ln -sf /etc/nginx/sites-available/projectpilot.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## Disk Space Issues

**Fix**:
```bash
# Check disk usage
df -h

# Clean Docker
docker system prune -af

# Clean old logs
sudo find /var/log/projectpilot -name "*.log" -mtime +7 -delete
```

## SSH Connection Refused

**Causes**:
1. UFW blocking: `sudo ufw status` — should allow 22, 80, 443
2. Instance stopped: check OCI console
3. Wrong IP: `terraform output instance_public_ip`

## Terraform State Issues

If state gets corrupted:
```bash
cd terraform
rm -f terraform.tfstate terraform.tfstate.backup
terraform import oci_core_vcn.main <vcn-ocid>
```

## Rollback to Previous Version

```bash
ssh deploy@<VM_IP>
cd /opt/projectpilot
IMAGE_TAG=previous docker compose -f docker-compose.prod.yml up -d --force-recreate
```

## CI Tests Pass Locally But Fail on GitHub

**Known issues**:
- CI has Starlette 1.3.1 (returns 401) vs local Starlette 0.36.3 (returns 403) — `test_get_me_unauthenticated` handles both
- Benchmark tests skip on CI via `@requires_benchmarks` marker
- Ollama not available on CI — `SKIP_AUTH=true` skips model wait

## Getting Help

1. Check GitHub Actions logs for the specific failing step
2. SSH into VM and check container logs
3. Check nginx error log: `sudo tail -50 /var/log/nginx/error.log`
4. Open an issue at the repository with logs attached
