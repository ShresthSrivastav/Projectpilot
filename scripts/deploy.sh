#!/usr/bin/env bash
# ProjectPilot deployment script for OCI VM
# Usage: ./deploy.sh [tag]
#   tag: Docker image tag to deploy (default: latest)
set -euo pipefail

DEPLOY_DIR="/opt/projectpilot"
COMPOSE_FILE="docker-compose.prod.yml"
IMAGE="ghcr.io/shresthsrivastav/projectpilot"
TAG="${1:-latest}"
FULL_IMAGE="${IMAGE}:${TAG}"
ROLLBACK_TAG="previous"
TIMEOUT_SEC="${DEPLOY_TIMEOUT:-300}"
POLL_INTERVAL=10
LOG_FILE="${DEPLOY_DIR}/logs/deploy-$(date +%Y%m%d-%H%M%S).log"

mkdir -p "${DEPLOY_DIR}/logs"

log() {
    local level="$1"
    local msg="$2"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [${level}] ${msg}" | tee -a "$LOG_FILE"
}

cleanup() {
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        log "ERROR" "Deploy failed with exit code $exit_code"
    fi
    log "INFO" "Deploy finished at $(date)"
}
trap cleanup EXIT

log "INFO" "Starting deployment of ${FULL_IMAGE}"
log "INFO" "Log file: ${LOG_FILE}"

cd "$DEPLOY_DIR"

save_previous_version() {
    log "INFO" "Saving current image as ${IMAGE}:${ROLLBACK_TAG}"
    docker tag "${IMAGE}:latest" "${IMAGE}:${ROLLBACK_TAG}" 2>/dev/null || \
        log "WARN" "No previous :latest image to tag"
}

rollback() {
    log "WARN" "ROLLBACK: Restoring ${IMAGE}:${ROLLBACK_TAG}"
    docker tag "${IMAGE}:${ROLLBACK_TAG}" "${IMAGE}:latest" 2>/dev/null || true
    IMAGE_TAG="latest" docker compose -f "$COMPOSE_FILE" up -d --force-recreate --no-deps backend 2>/dev/null || \
        IMAGE_TAG="latest" docker compose -f "$COMPOSE_FILE" up -d --force-recreate
    log "INFO" "Rollback complete"
}

health_check() {
    local service="$1"
    local max_attempts=$((TIMEOUT_SEC / POLL_INTERVAL))
    local attempt=1

    log "INFO" "Waiting for ${service} to become healthy (timeout: ${TIMEOUT_SEC}s)"

    while [ $attempt -le "$max_attempts" ]; do
        local status
        status=$(docker inspect --format='{{json .State.Health.Status}}' \
            "projectpilot_${service}" 2>/dev/null || echo "\"starting\"")

        status=$(echo "$status" | tr -d '"')

        if [ "$status" = "healthy" ]; then
            log "INFO" "${service} is healthy (attempt ${attempt}/${max_attempts})"
            return 0
        fi

        if [ "$service" = "backend" ] && curl -sf "http://localhost:5000/health" > /dev/null 2>&1; then
            log "INFO" "${service} responded to health check via HTTP"
            return 0
        fi

        if [ "$service" = "frontend" ] && curl -sf "http://localhost:8501" > /dev/null 2>&1; then
            log "INFO" "${service} responded on port 8501"
            return 0
        fi

        if [ "$service" = "frontend_next" ] && curl -sf "http://localhost:3000" > /dev/null 2>&1; then
            log "INFO" "${service} responded on port 3000"
            return 0
        fi

        attempt=$((attempt + 1))
        sleep "$POLL_INTERVAL"
    done

    log "ERROR" "${service} failed health check after ${TIMEOUT_SEC}s"
    return 1
}

setup_nginx_ssl() {
    local domain="${DOMAIN_NAME:-}"
    if [ -z "$domain" ]; then
        log "INFO" "No DOMAIN_NAME set, using HTTP-only nginx config"
        return 0
    fi

    log "INFO" "Setting up SSL for domain: ${domain}"

    certbot --nginx -d "$domain" --non-interactive --agree-tos --email "admin@${domain}" || {
        log "WARN" "Certbot failed, keeping HTTP-only config"
        return 0
    }

    systemctl reload nginx
    log "INFO" "SSL setup complete for ${domain}"
}

verify_public_endpoint() {
    local ip
    ip=$(curl -sf http://ifconfig.me 2>/dev/null || echo "")
    if [ -z "$ip" ]; then
        log "WARN" "Could not determine public IP"
        return 0
    fi

    log "INFO" "Verifying public endpoint: http://${ip}/health"
    local max_attempts=12
    local attempt=1

    while [ $attempt -le "$max_attempts" ]; do
        if curl -sf "http://${ip}/health" > /dev/null 2>&1; then
            log "INFO" "Public endpoint is healthy at http://${ip}"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 10
    done

    log "WARN" "Public endpoint not reachable via HTTP, but container may be healthy"
    return 0
}

# ── Main ──

save_previous_version

log "INFO" "Pulling image: ${FULL_IMAGE}"
docker pull "${FULL_IMAGE}"

if [ ! -f .env ]; then
    log "WARN" "No .env file found; services may not start correctly"
fi

log "INFO" "Recreating containers with tag: ${TAG}"
IMAGE_TAG="${TAG}" docker compose -f "$COMPOSE_FILE" up -d --force-recreate --remove-orphans

log "INFO" "Waiting for containers to initialize..."
sleep 15

if health_check "backend"; then
    log "INFO" "Backend healthy!"
    health_check "frontend" || log "WARN" "Frontend not yet healthy (may need more time)"
    health_check "frontend_next" || log "WARN" "Frontend-next not yet healthy (may need more time)"
    log "INFO" "Deployment successful!"
    docker image prune -af --filter "until=24h" > /dev/null 2>&1 || true
    setup_nginx_ssl
    verify_public_endpoint
    exit 0
else
    log "ERROR" "Deployment failed. Initiating rollback..."
    rollback
    if health_check "backend"; then
        log "INFO" "Rollback successful, running previous version"
        exit 1
    else
        log "ERROR" "Rollback also failed! Manual intervention required."
        exit 1
    fi
fi
