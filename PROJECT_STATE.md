# FiscAudit Pro — Project State Snapshot

_Last updated: 2026-05-31 — verifiscale.com domain went live with SSL; cmimpot.cm
slated for removal in next session._

This file is a **safety net**, not living documentation. Update it whenever a
major architectural decision lands or the deploy/runbook changes.

---

## 1. Product

- **Name:** FiscAudit Pro
- **Customer:** Cameroon DGI (Direction Générale des Impôts)
- **Domain:** Fiscal audit SaaS — VGC, VP, CSP, CI, CT, EF cases
- **UI language:** French (primary), English (secondary). Full i18n via
  `apps/web/src/lib/i18n.ts`.
- **Accounting framework:** SYSCOHADA Révisé (classes 1–7); CGI Cameroun
  (notably Art. 7 — depreciation rates; Art. 7 bis — 100 000 FCFA HT cash
  payment ceiling, non-deductible above).
- **Public URL:** **https://verifiscale.com** (live with Let's Encrypt SSL
  since 2026-05-31).

## 2. Production environment

- **Host:** Vultr Paris instance, `45.32.150.96` (1 GB RAM / 953 MiB usable —
  memory is tight; OOM has bitten api workers during forced rebuilds).
- **Server folder:** `/srv/cmimpot/` (kept the old name to preserve Docker
  volume references — rename would require recreating named volumes).
- **Public URLs:**
  - **https://verifiscale.com** (primary, Let's Encrypt, expires 2026-08-29)
  - https://www.verifiscale.com (same cert)
  - http://45.32.150.96:8080 (direct, no Apache — for debug only)
  - http://cmimpot.cm + variants (legacy, scheduled for removal in Part H)
- **Front-door web server:** **Apache 2** on the host (ports 80/443), holds
  the SSL certs and vhost routing. It reverse-proxies every public domain
  to `localhost:8080`, which is the inner Docker nginx.
- **Apache vhost for verifiscale:**
  `/etc/apache2/sites-available/verifiscale.com.conf` (port 80, ACME challenge
  passthrough) +
  `/etc/apache2/sites-available/verifiscale.com-le-ssl.conf` (port 443,
  Certbot-generated). Both `a2ensite`-enabled.
- **Inner reverse proxy:** Docker nginx on `localhost:8080` → `web:3000` /
  `api:8000`.
- **Inner nginx `server_name`:** declares verifiscale.com + www +
  cmimpot.cm + www.cmimpot.cm + raw IP + `_` (catch-all).
- **CORS_ORIGINS (live):** `https://verifiscale.com,https://www.verifiscale.com,
  http://cmimpot.cm,http://www.cmimpot.cm,https://cmimpot.cm,
  https://www.cmimpot.cm,http://45.32.150.96:8080,http://45.32.150.96`
- **NEXT_PUBLIC_API_URL:** **empty** (browser uses same-origin via Apache;
  no rebuild needed when public URL changes).
- **Stack:** Docker Compose (`docker-compose.prod.yml`), 4 containers:
  `db` (postgres:16), `api` (FastAPI/uvicorn), `web` (Next.js 15 prod),
  `nginx`.
- **Login:** demo accounts `b.etoundi@dgi.cm` / `s.ngono@dgi.cm` /
  `j.mbarga@dgi.cm` / `admin@dgi.cm` — shared password `Password123!`.

### Other domains co-hosted on this server (Apache vhosts)

`ap.cm-ea.com`, `bms.cm-ea.com`, `bp.cm-ea.com`, `ealedgers.com` — separate
projects, separate SSL certs in `/etc/letsencrypt/live/`. Don't touch their
configs when modifying verifiscale.

### Memory caveat

Building the `web` image in-place reliably OOM-kills the `api` workers.
Two mitigations available:

1. **Stop web during build** — `docker compose stop web`, build, then
   `docker compose up -d web`. Drop page caches between (`echo 3 | sudo tee /proc/sys/vm/drop_caches`).
2. **Build locally, ship the image** — `docker save | ssh prod 'docker load'`.

Adding a 2 GB swapfile is the recommended long-term fix; not done yet.
**Force-recreating the api container under memory pressure** can also
trigger a silent worker-crash loop (workers SIGKILLed by OOM with no
traceback). Always stop the container first + drop caches before
restarting in tight-RAM conditions.

### Deploy runbook (current pattern)

```bash
# from prod server
cd /srv/cmimpot
git pull       # (when GitHub repo is set up — currently rsync from laptop)
docker compose -f docker-compose.prod.yml build api      # api alone is safe
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d api
# web — only when needed; stop web first to free RAM
docker compose -f docker-compose.prod.yml stop web
echo 3 | sudo tee /proc/sys/vm/drop_caches
docker compose -f docker-compose.prod.yml build web
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d web
# migrations
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
# reload Apache vhost or inner nginx after config changes
systemctl reload apache2
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

**Never** use `mv cmimpot cmimpot.bak` to swap dirs — nginx bind-mount inodes
break. Use `rsync -a --delete` instead.

**Editing `.env.prod`:** prefer `sed -i '/KEY=/d'` + `cat >> ... << 'EOF'`
heredoc to overwrite a single line. Multi-paste in nano historically caused
duplicate lines and comment-glued values. Always verify with
`grep -c KEY_NAME .env.prod` (must be `1`) afterwards.

### SSL renewal

Certbot auto-renewal via systemd timer. Apache configs and certs survive
container restarts because they live on the host, not in Docker. To verify:

```bash
certbot renew --dry-run
```

## 3. Stack

- **API:** FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16
- **Web:** Next.js 15 (App Router), React 19, TypeScript, Tailwind,
  Tanstack Query, Zustand
- **AI:** Anthropic SDK, model `claude-sonnet-4-5`, prompt caching enabled
- **API key (current):** stored in API container env. If a session loses it,
  reapply via env var in compose.

## 4. Database — migration head

**Head:** `0009_recon_cache`

Recent migrations:

- `0008_widen_gl` — VARCHAR widenings for Odoo exports (account_code 32→64,
  libelle to 2048, etc.)
- `0009_recon_cache` — single-row `reconciliation_cache(audit_case_id PK,
  computed_at, payload JSONB)`.

## 5. AI parsers (live)

All located in `apps/api/app/parsers/`:

| File | Purpose |
|------|---------|
| `general_ledger_ai.py` | GL parser. Sends 25-row preview to Claude. Identifies piece_number, effective date, debit/credit amounts, account code+description. **Hard requirement:** must find a piece_number column; raises `ValueError` otherwise — **no AUTO-NNN fallback**. Returns `(rows, report)`. |
| `trial_balance_ai.py` | TB parser. Identifies account_code, account_name, opening D/C, period D/C, closing D/C. Falls back to keyword parser if no API key. |
| `fixed_assets_ai.py` | FAR parser. `_rate_to_pct` handles months/years/decimal/unit_hint. `_imply_rate_from_dep` fallback when rate column missing. |
| `general_ledger.py` | Legacy keyword parser. `_split_code_and_name` helper splits "411100 Customers" cells; Odoo column aliases. |

### Parser conventions

- `piece_number` **must repeat across the lines of a single journal entry** —
  it is the source of truth for grouping. Never invent surrogate keys.
- After upload, the `DatasetOut.column_mapping` payload carries
  `{source, rationale, detected: {...}, column_indices, header_row_index}`
  for the UI detection chips.
- Total-row exclusion uses three layers: Claude `total_row_indices` + keyword
  scan + math sanity check.

## 6. Reconciliation cache

`apps/api/app/routers/reconciliations.py` reads cache first:

1. If `?refresh=true` is **not** set, look up `reconciliation_cache` row.
2. If `MAX(datasets.uploaded_at) <= computed_at`, return cached payload with
   `cached: true` and `computed_at`.
3. Otherwise recompute, then upsert into `reconciliation_cache`.

Front-end (`apps/web/src/app/(app)/rapprochements/page.tsx`):

- `refetchOnWindowFocus: false`, `staleTime: 5 * 60 * 1000`
- Removed 5-second auto-refetch
- "Refresh" button hits the endpoint with `?refresh=true` then refetches.

## 7. Controls (live)

- **C-CASH-100K** (Cash Payments, CGI Art. 7 bis) —
  `apps/api/app/controls/cash_payments.py` + `routers/cash_payments.py`.
  Tests debit prefixes `1/2/3/4/6`. Three triggers (per-line / per-piece /
  cash-credit), any qualifies. Writes `ControlFinding` in category `FISCAL_C`
  with code `C-CASH-100K`. **Note:** model field is `control_run_id`, not
  `run_id` — already fixed.
- **Amortissements** — CGI Art. 7 category mapping, accumulated depreciation
  + NBV columns, taux registre auto-detection.
- **Reconciliations** — AP/AR/Inventory auto-totals from sub-ledger;
  FAR ↔ TB (Σ gross / Σ accumulated / Σ year-dep against 2X / 28X / 68X).
  Categorisation uses the personal-Claude "reconciliation skill" methodology
  (timing / posting error / omission / FX / intercompany; aging + materiality).

## 8. Open issues / pending work

1. **Web container still on old image.** Backend AI parsers are live and
   actively used on uploads, **but** the post-upload detection-report chips
   on `/audit-data` (`ColumnDetectionReport` component at the bottom of
   `apps/web/src/app/(app)/audit-data/page.tsx`) need a web rebuild to be
   visible. Plan: stop web → drop caches → build → up. Or build locally and
   ship the image.
2. **Long-term memory fix.** Add a 2 GB swapfile on prod, or move the web
   build off-server entirely.
3. **Penalty calculations** for C-CASH-100K are deferred — user said
   "Penalty later".

## 9. Key files cheat-sheet

| File | Why it matters |
|------|----------------|
| `apps/api/alembic/versions/0009_recon_cache.py` | Current head |
| `apps/api/app/routers/reconciliations.py` | Cache read/upsert |
| `apps/api/app/routers/cash_payments.py` | C-CASH-100K finding emission |
| `apps/api/app/routers/datasets.py` | Switched to `general_ledger_ai` + `trial_balance_ai` |
| `apps/api/app/schemas.py` | `DatasetOut.column_mapping` |
| `apps/web/src/lib/types.ts` | `DatasetColumnMapping` interface |
| `apps/web/src/lib/i18n.ts` | `data.detect.*` keys (FR/EN) |
| `apps/web/src/app/(app)/audit-data/page.tsx` | `ColumnDetectionReport` chips (needs web rebuild) |
| `apps/web/src/app/(app)/rapprochements/page.tsx` | Cached reconciliations UI |
| `docker-compose.prod.yml` | 4-container prod topology |

## 10. Recurring pitfalls

- **Bad Gateway** after a dir-swap deploy → nginx bind-mount inode broke.
  Use `rsync -a --delete`, never `mv`.
- **`column audit_cases.audit_type does not exist`** is usually an OOM-killed
  worker, not a schema problem. Stop web, drop caches, restart api.
- **`DuplicateObject` on enum types** → use `postgresql.ENUM(..., create_type=False)`
  plus a raw-SQL `DO $$ ... CREATE TYPE IF NOT EXISTS ... $$;`.
- **`buildx` stuck on "no active session"** → `docker buildx prune -f` then
  `docker buildx use default`. Last resort: `sudo systemctl restart docker`.
- **TypeScript OOM on Windows** during typecheck → `NODE_OPTIONS="--max-old-space-size=4096"`.
