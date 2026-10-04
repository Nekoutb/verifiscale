#!/usr/bin/env bash
# =============================================================================
# One-shot bootstrap of the DEV instance (dev.verifiscale.com) on this server.
# Idempotent: safe to re-run. Touches NOTHING belonging to production.
#
#   sudo bash /srv/cmimpot/deploy/bootstrap-dev.sh
#
# Dev gets its OWN checkout (/srv/cmimpot-dev on branch `dev`), its OWN Postgres
# container + volume, its OWN storage volume and its OWN ports. Prod stays on
# /srv/cmimpot / branch main. They cannot share one working tree because they
# track different branches.
#
# This script NEVER builds an image: the host has ~1.5 GB free RAM and a nearly
# full swap, and a Next.js build wants 1.5-2 GB — building here is what OOMs the
# box and takes the other ~12 tenants down with it. Bootstrap reuses the images
# production already built; deploy-verifiscale.sh handles builds with a guard.
# =============================================================================
set -euo pipefail

PROD_REPO=/srv/cmimpot
DEV_REPO=/srv/cmimpot-dev
PROJECT=cmimpot-dev
# Use the SAME remote the production checkout uses — it already authenticates to
# GitHub (that is how deploys pull). A bare public HTTPS URL fails on a private
# repo with "repository not found". Fall back to the public URL only if prod has
# no origin for some reason.
ORIGIN="$(git -C /srv/cmimpot remote get-url origin 2>/dev/null \
          || echo https://github.com/Nekoutb/verifiscale.git)"

say() { printf '\n== %s\n' "$*"; }
die() { printf '\n!! %s\n' "$*" >&2; exit 1; }

# --- 0. Dev checkout ---------------------------------------------------------
say "Checkout dev (branche dev) dans $DEV_REPO"
echo "   origin: $ORIGIN"
if [ ! -d "$DEV_REPO/.git" ]; then
  # Surface the real git error (do NOT swallow stderr — that hid an auth failure).
  git clone --branch dev "$ORIGIN" "$DEV_REPO" \
    || die "Clone impossible depuis $ORIGIN. Vérifiez que la prod accède bien à
    GitHub (git -C /srv/cmimpot fetch) et que la branche 'dev' est poussée."
else
  git -C "$DEV_REPO" fetch origin --prune
  git -C "$DEV_REPO" checkout dev
  git -C "$DEV_REPO" pull --ff-only
fi
echo "   dev @ $(git -C "$DEV_REPO" rev-parse --short HEAD)"

COMPOSE="docker compose -p $PROJECT -f $DEV_REPO/docker-compose.dev.yml --env-file $DEV_REPO/.env.dev"

# --- 1. Preconditions --------------------------------------------------------
say "Verification des prerequis"
if [ ! -f "$DEV_REPO/.env.dev" ]; then
  cp "$DEV_REPO/.env.dev.example" "$DEV_REPO/.env.dev"
  chmod 600 "$DEV_REPO/.env.dev"
  die "$DEV_REPO/.env.dev vient d'etre cree depuis le modele.
    RENSEIGNEZ-LE puis relancez : POSTGRES_PASSWORD et JWT_SECRET doivent etre
    des valeurs aleatoires DIFFERENTES de la prod. Suggestion :
      openssl rand -base64 36"
fi

# A shared JWT secret would make a production token valid on dev.
p=$(grep -m1 '^JWT_SECRET=' "$PROD_REPO/.env.prod" 2>/dev/null | cut -d= -f2- || true)
d=$(grep -m1 '^JWT_SECRET=' "$DEV_REPO/.env.dev" | cut -d= -f2- || true)
[ -n "$d" ] && [ "$d" != "change_me_generate_a_long_random_value" ] || die ".env.dev : JWT_SECRET non renseigne."
[ -z "$p" ] || [ "$p" != "$d" ] || die ".env.dev : JWT_SECRET IDENTIQUE a la prod — un jeton de prod serait valide sur dev."

pdb=$(grep -m1 '^POSTGRES_DB=' "$PROD_REPO/.env.prod" 2>/dev/null | cut -d= -f2- || true)
ddb=$(grep -m1 '^POSTGRES_DB=' "$DEV_REPO/.env.dev" | cut -d= -f2- || true)
[ -z "$pdb" ] || [ "$pdb" != "$ddb" ] || die ".env.dev : POSTGRES_DB identique a la prod ($ddb)."

# Metered services must stay blank: anything dev sends is REAL.
for k in MAILERSEND_API_KEY ANTHROPIC_API_KEY; do
  v=$(grep -m1 "^$k=" "$DEV_REPO/.env.dev" | cut -d= -f2- || true)
  [ -z "$v" ] || printf '   ATTENTION: %s est renseigne — dev enverra/facturera POUR DE VRAI.\n' "$k"
done

for img in cmimpot-api:latest cmimpot-web:latest; do
  docker image inspect "$img" >/dev/null 2>&1 \
    || die "Image $img absente. Le bootstrap ne construit pas (risque OOM)."
done

for port in 8081 8444; do
  if ss -tln 2>/dev/null | grep -qE "[:.]${port}[[:space:]]"; then
    docker ps --format '{{.Ports}}' | grep -q ":${port}->" \
      || die "Port $port deja occupe par un service non-dev."
  fi
done
echo "   prerequis OK"

# --- 2. Apache vhost --------------------------------------------------------
say "Installation du vhost dev.verifiscale.com"
a2enmod headers proxy proxy_http rewrite ssl >/dev/null 2>&1 || true
install -m 0644 "$DEV_REPO/deploy/dev.verifiscale.com.conf" \
                /etc/apache2/sites-available/dev.verifiscale.com.conf
a2ensite dev.verifiscale.com.conf >/dev/null
# Validate BEFORE reload — a broken config would take down all ~12 vhosts.
apachectl configtest || die "configtest a echoue — Apache NON recharge, production intacte."
systemctl reload apache2
echo "   vhost actif, Apache recharge"

# --- 3. Dev stack -----------------------------------------------------------
say "Demarrage du stack dev (images existantes, aucun build)"
$COMPOSE up -d --no-build

say "Attente de Postgres dev"
for i in $(seq 1 40); do
  $COMPOSE exec -T postgres pg_isready >/dev/null 2>&1 && { echo "   pret"; break; }
  sleep 2
done

say "Migrations sur la base DEV"
for i in $(seq 1 20); do
  $COMPOSE exec -T api alembic upgrade head && { echo "   migrations appliquees"; break; }
  echo "   api pas encore prete ($i)"; sleep 3
done

# --- 4. Verification --------------------------------------------------------
say "Conteneurs dev"; $COMPOSE ps
say "Sante interne (nginx dev :8081)"
curl -s -o /dev/null -w '   /login  -> %{http_code}\n' -H 'Host: dev.verifiscale.com' http://127.0.0.1:8081/login || true
curl -s -o /dev/null -w '   /health -> %{http_code}\n' -H 'Host: dev.verifiscale.com' http://127.0.0.1:8081/health || true

say "Isolation: la base dev doit etre vide (0 utilisateur de prod)"
$COMPOSE exec -T postgres psql -U "$ddb" -d "$ddb" -Atc \
  "select count(*) from users;" 2>/dev/null | sed 's/^/   utilisateurs en base dev: /' \
  || echo "   (table users absente)"

echo
echo "== Bootstrap termine. Testez https://dev.verifiscale.com/login"
echo "   HTTP 526 => Cloudflare est en 'Full (strict)' : certificat dedie requis"
echo "   certbot certonly --webroot -w /var/www/certbot -d dev.verifiscale.com"
