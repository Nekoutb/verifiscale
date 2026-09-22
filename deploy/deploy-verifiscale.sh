#!/usr/bin/env bash
# =============================================================================
# VerifiScale - gated deploy.  Run from your laptop (needs SSH key access).
#
#   deploy/deploy-verifiscale.sh dev  [ref]    # default ref: origin/dev
#   deploy/deploy-verifiscale.sh prod <sha>    # no default: be explicit
#
# THE GATE: a production deploy is REFUSED unless the sha is both
#   (a) reachable from origin/main, and
#   (b) present in the server-side dev-deploy log (it actually ran on dev).
# There is no flag to skip this. The hotfix path is the same path, just fast:
# deploy to dev, sanity-check, promote - minutes, not hours.
#
# Only pushed commits are ever deployed: the server checks out an exact sha it
# fetched from origin, so a dirty local tree can never reach an instance.
# =============================================================================
set -euo pipefail

HOST=root@45.32.150.96
PROD_REPO=/srv/cmimpot
DEV_REPO=/srv/cmimpot-dev
DEV_LOG=/srv/cmimpot/.deployed_dev_log       # append-only history of dev shas
PROD_STAMP=/srv/cmimpot/.deployed_sha        # what prod is actually running
DEV_STAMP=/srv/cmimpot-dev/.deployed_sha
MIN_BUILD_MB=800                             # below this a Next build will OOM

say()  { printf '\n== %s\n' "$*"; }
ok()   { printf '   %s\n' "$*"; }
warn() { printf '   WARN: %s\n' "$*"; }
die()  { printf '\n!! %s\n' "$*" >&2; exit 1; }

# A dropped SSH connection is NOT a failed deployment. Retry with backoff.
sshr() {
  local i out
  for i in 1 2 3 4 5; do
    if out=$(ssh -o ConnectTimeout=15 -o ServerAliveInterval=15 "$HOST" "$1" 2>&1); then
      printf '%s\n' "$out"; return 0
    fi
    if printf '%s' "$out" | grep -qE 'kex_exchange|banner exchange|Connection (reset|closed|timed)|Broken pipe'; then
      warn "SSH interrompu (tentative $i), nouvelle tentative"; sleep $((i * 4)); continue
    fi
    printf '%s\n' "$out"; return 1      # real command failure, not transport
  done
  die "SSH injoignable apres 5 tentatives"
}

# HTTP health check with retries - containers need a moment to come up.
health() {
  local url=$1 i code
  for i in $(seq 1 30); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$url" || echo 000)
    if [ "$code" = "200" ]; then ok "$url -> 200"; return 0; fi
    printf '   attente %s (%s) %d/30\r' "$url" "$code" "$i"; sleep 5
  done
  printf '\n'
  die "Health check ECHOUE: $url ne repond pas 200 (dernier code: $code)"
}

# --- Arguments ---------------------------------------------------------------
TARGET=${1:-}
REF=${2:-}
case "$TARGET" in
  dev)
    REF=${REF:-origin/dev}
    ;;
  prod)
    if [ -z "$REF" ]; then
      die "Pour la prod, indiquez explicitement le sha a promouvoir.
    Usage: deploy/deploy-verifiscale.sh prod <sha>"
    fi
    ;;
  *)
    die "Usage: deploy/deploy-verifiscale.sh <dev|prod> [ref]"
    ;;
esac

# --- Resolve the ref to an exact, pushed sha --------------------------------
say "Resolution de la reference"
git fetch origin --prune --quiet
SHA=$(git rev-parse --verify "${REF}^{commit}" 2>/dev/null) || die "Reference inconnue: $REF"
SHORT=${SHA:0:12}
ok "$REF -> $SHA"

if ! git branch -r --contains "$SHA" 2>/dev/null | grep -q .; then
  die "Le commit $SHORT figure sur AUCUNE branche distante. Poussez-le (git push)."
fi

# --- THE GATE (production only) ---------------------------------------------
if [ "$TARGET" = prod ]; then
  say "Controle de promotion (obligatoire)"

  if ! git merge-base --is-ancestor "$SHA" origin/main 2>/dev/null; then
    die "REFUS: $SHORT ne remonte pas a origin/main.
    Fusionnez-le: git checkout main && git merge --ff-only dev && git push"
  fi
  ok "$SHORT est bien sur origin/main"

  if ! sshr "grep -qx '$SHA' $DEV_LOG 2>/dev/null"; then
    die "REFUS: $SHORT na jamais ete deploye ni valide sur dev.
    Le journal $DEV_LOG ne le contient pas.

    Passez par dev - cest aussi le chemin des correctifs urgents:
      deploy/deploy-verifiscale.sh dev $SHORT
      (testez sur https://dev.verifiscale.com)
      deploy/deploy-verifiscale.sh prod $SHORT"
  fi
  ok "$SHORT figure dans le journal des deploiements dev"
fi

# --- Target-specific settings ------------------------------------------------
if [ "$TARGET" = dev ]; then
  REPO=$DEV_REPO
  COMPOSE="docker compose -p cmimpot-dev -f $DEV_REPO/docker-compose.dev.yml --env-file $DEV_REPO/.env.dev"
  URL=https://dev.verifiscale.com
else
  REPO=$PROD_REPO
  COMPOSE="docker compose -f $PROD_REPO/docker-compose.prod.yml --env-file $PROD_REPO/.env.prod"
  URL=https://verifiscale.com
fi

say "Cible: $TARGET  ($URL)"
sshr "cd $REPO && git rev-parse --short HEAD" | sed 's/^/   sha actuel sur la cible: /'

# --- Backup before ANY production change ------------------------------------
PREV_SHA=""
if [ "$TARGET" = prod ]; then
  say "Sauvegarde verifiee de la base de production (avant toute modification)"
  BK=/srv/backups/verifiscale
  TS=$(date -u +%Y%m%dT%H%M%SZ)
  DUMP="$BK/prod-${TS}-pre-${SHORT}.sql.gz"
  sshr "mkdir -p $BK && cd $PROD_REPO && PGUSER=\$(grep -m1 '^POSTGRES_USER=' .env.prod | cut -d= -f2-) && docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres pg_dumpall -U \$PGUSER | gzip -9 > $DUMP" >/dev/null

  # A backup nobody verified is not a backup: check size and gzip integrity.
  SIZE=$(sshr "stat -c%s $DUMP 2>/dev/null || echo 0" | tr -d '[:space:]')
  if [ "${SIZE:-0}" -lt 20000 ]; then
    die "Sauvegarde suspecte ($SIZE octets) - deploiement ANNULE, prod intacte."
  fi
  sshr "gzip -t $DUMP" >/dev/null || die "Sauvegarde corrompue (gzip -t) - deploiement ANNULE."
  ok "sauvegarde verifiee: $DUMP ($((SIZE/1024)) Ko, gzip valide)"

  PREV_SHA=$(sshr "cat $PROD_STAMP 2>/dev/null || echo ''" | tr -d '[:space:]')
  ok "sha precedent (rollback): ${PREV_SHA:-inconnu}"
fi

# --- Ship the exact sha ------------------------------------------------------
say "Deploiement du sha $SHORT sur $TARGET"
sshr "cd $REPO && git fetch origin --prune --quiet && git checkout --detach $SHA --quiet && git rev-parse HEAD" | sed 's/^/   checkout: /'

# --- Build, with a memory guard ---------------------------------------------
say "Construction des images"
AVAIL=$(sshr "free -m | awk '/^Mem:/{print \$7}'" | tr -d '[:space:]')
ok "memoire disponible: ${AVAIL} Mo"
if [ "${AVAIL:-0}" -lt "$MIN_BUILD_MB" ]; then
  warn "sous le seuil de ${MIN_BUILD_MB} Mo, liberation du cache puis nouvelle mesure"
  sshr "sync; echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true" >/dev/null
  AVAIL=$(sshr "free -m | awk '/^Mem:/{print \$7}'" | tr -d '[:space:]')
  ok "apres liberation: ${AVAIL} Mo"
  if [ "${AVAIL:-0}" -lt "$MIN_BUILD_MB" ]; then
    die "Memoire insuffisante (${AVAIL} Mo < ${MIN_BUILD_MB} Mo).
    Un build Next.js ici ferait tomber les ~12 autres sites du serveur.
    Attendez une accalmie, ou construisez les images ailleurs."
  fi
fi
sshr "cd $REPO && $COMPOSE build" | tail -5

say "Bascule des conteneurs"
sshr "cd $REPO && $COMPOSE up -d" | tail -8

say "Migrations"
sshr "cd $REPO && for i in \$(seq 1 20); do $COMPOSE exec -T postgres pg_isready >/dev/null 2>&1 && break; sleep 2; done; for i in \$(seq 1 20); do $COMPOSE exec -T api alembic upgrade head && break; sleep 3; done" | tail -4

# --- Health check ------------------------------------------------------------
say "Verification de sante"
health "$URL/health"
health "$URL/login"

# --- Record success ---------------------------------------------------------
if [ "$TARGET" = dev ]; then
  say "Enregistrement dans le journal des deploiements dev"
  sshr "grep -qx '$SHA' $DEV_LOG 2>/dev/null || echo '$SHA' >> $DEV_LOG" >/dev/null
  sshr "echo '$SHA' > $DEV_STAMP" >/dev/null
  ok "$SHORT est desormais promouvable en production"
  echo
  echo "   Testez https://dev.verifiscale.com puis promouvez:"
  echo "     git checkout main && git merge --ff-only dev && git push"
  echo "     deploy/deploy-verifiscale.sh prod $SHA"
else
  say "Synchronisation du pointeur de production"
  sshr "echo '$SHA' > $PROD_STAMP" >/dev/null
  ok "production sur $SHORT"
  if [ -n "$PREV_SHA" ]; then
    echo "   rollback si besoin: deploy/deploy-verifiscale.sh prod $PREV_SHA"
  fi
fi

say "Termine - $TARGET sur $SHORT"
