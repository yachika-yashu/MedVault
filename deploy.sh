#!/usr/bin/env bash
# MedVault — Production Deploy Script
# ─────────────────────────────────────────────────────────────────────────────
# Usage:
#   First deploy:  ./deploy.sh --build --ssl-init
#   Updates:       ./deploy.sh --build
#   No rebuild:    ./deploy.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

COMPOSE="docker compose -f docker-compose.prod.yml"
IMAGE="medvault:latest"
ENV_FILE=".env.production"
ENV_EXAMPLE=".env.production.example"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
step()  { echo -e "\n${BOLD}──── $* ────${NC}"; }

# ─── Parse flags ─────────────────────────────────────────────────────────────
DO_BUILD=false
DO_SSL_INIT=false
for arg in "$@"; do
    case $arg in
        --build)    DO_BUILD=true ;;
        --ssl-init) DO_SSL_INIT=true ;;
        *) warn "Unknown flag: $arg" ;;
    esac
done

# ─── Preflight checks ────────────────────────────────────────────────────────
step "Preflight"

command -v docker >/dev/null 2>&1 || error "Docker not installed."
docker compose version >/dev/null 2>&1 || error "Docker Compose v2 not found (need 'docker compose', not 'docker-compose')."

if [[ ! -f "$ENV_FILE" ]]; then
    warn "$ENV_FILE not found — creating from example..."
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    error "Edit $ENV_FILE with real values, then re-run this script."
fi

# Load env file into current shell so docker compose can use ${DOMAIN} etc.
set -a; source "$ENV_FILE"; set +a

[[ -z "${DOMAIN:-}"          ]] && error "DOMAIN is not set in $ENV_FILE"
[[ -z "${OPENAI_API_KEY:-}"  ]] && error "OPENAI_API_KEY is not set in $ENV_FILE"
[[ -z "${JWT_SECRET_KEY:-}"  ]] && error "JWT_SECRET_KEY is not set in $ENV_FILE"
[[ "${JWT_SECRET_KEY}" == *"replace"* ]] && error "JWT_SECRET_KEY still has a placeholder value. Generate one with: python -c \"import secrets; print(secrets.token_hex(64))\""
[[ "${POSTGRES_PASSWORD:-}" == *"replace"* ]] && error "POSTGRES_PASSWORD still has a placeholder value."

info "Target domain: ${DOMAIN}"

# ─── Build image ─────────────────────────────────────────────────────────────
if $DO_BUILD || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    step "Building Docker image"
    docker build -t "$IMAGE" .
    info "Image built: $IMAGE"
fi

# ─── SSL certificate init (first deploy only) ─────────────────────────────────
if $DO_SSL_INIT; then
    step "SSL certificate init (Let's Encrypt)"

    # Temporarily serve HTTP without a redirect so certbot can reach /.well-known/
    # Start only nginx (it can start without API being healthy for cert issuance)
    info "Starting nginx for ACME challenge..."
    $COMPOSE up -d nginx

    sleep 5

    info "Requesting certificate for ${DOMAIN}..."
    $COMPOSE run --rm certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        --email "admin@${DOMAIN}" \
        --agree-tos \
        --no-eff-email \
        -d "${DOMAIN}"

    info "Certificate issued. Reloading nginx..."
    $COMPOSE exec nginx nginx -s reload
    info "SSL ready."
fi

# ─── Deploy all services ──────────────────────────────────────────────────────
step "Starting services"
$COMPOSE up -d --remove-orphans
info "All services started."

# ─── Wait for API health ──────────────────────────────────────────────────────
step "Health check"
info "Waiting for API to become healthy (up to 90s)..."
for i in $(seq 1 45); do
    if $COMPOSE exec -T api curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1; then
        info "API is healthy."
        break
    fi
    if [[ $i -eq 45 ]]; then
        error "API did not become healthy. Check logs: $COMPOSE logs api"
    fi
    sleep 2
done

# ─── Status summary ───────────────────────────────────────────────────────────
step "Deployment complete"
$COMPOSE ps
echo ""
info "Dashboard: https://${DOMAIN}"
info "API docs:  disabled (ENABLE_DOCS=false in production)"
info "Logs:      docker compose -f docker-compose.prod.yml logs -f [service]"
info "Status:    docker compose -f docker-compose.prod.yml ps"

# ─── Cert renewal reminder ────────────────────────────────────────────────────
echo ""
warn "Add monthly cert renewal to crontab (run: crontab -e):"
echo "    0 3 1 * *  cd $(pwd) && docker compose -f docker-compose.prod.yml run --rm certbot renew && docker compose -f docker-compose.prod.yml exec nginx nginx -s reload >> /var/log/certbot-renew.log 2>&1"

# ─── Backup reminder ──────────────────────────────────────────────────────────
echo ""
warn "Set up daily database backups:"
echo "    0 2 * * *  docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U \${POSTGRES_USER} \${POSTGRES_DB} | gzip > /backups/medvault-\$(date +%Y%m%d).sql.gz"
