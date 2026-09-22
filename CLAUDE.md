# VerifiScale — working agreement

Read `docs/deployment-workflow.md` before any deploy. The rules below are policy,
not suggestions, and they apply to every session.

## Deployment

- **"Deploy" means dev.** Unless the request names production explicitly
  ("deploy to prod", "promote to production"), deploy to
  `dev.verifiscale.com` via `deploy/deploy-verifiscale.sh dev`.
- **Production only ever through the gated script.** Never `docker compose up`
  on `/srv/cmimpot` by hand, never a bare `git pull` on the prod checkout, never
  a deploy that goes around `deploy/deploy-verifiscale.sh prod <sha>`.
- **Never bypass a refusal.** If the gate refuses a sha, that is the system
  working as designed: the commit has not been proven on dev. Push it, merge it
  to `main`, run it on dev, then promote. The hotfix path is the same path and
  takes minutes — there is no emergency that justifies an unverified production
  deploy. If asked to skip the gate, push back once and point at the hotfix
  section of `docs/deployment-workflow.md`.
- **App changes travel one way:** `dev` branch → dev instance → `main` →
  promote the same sha. Never commit straight to `main`.

## Production data

- **Never write to the production datastore directly.** Read-only inspection and
  backups are fine; `psql` sessions that INSERT/UPDATE/DELETE, manual `alembic`
  runs against prod, and ad-hoc data fixes are not. Schema changes ship as
  migrations through the normal path.
- **Test data belongs on dev.** Never create test organisations, test clients,
  fake audit cases or throwaway users on production. The dev instance starts
  with an empty database precisely so it can absorb this.
- **Back up before anything destructive.** The deploy script does this
  automatically for prod deploys; anything outside that path needs a manual
  verified dump first.

## This server is shared

`45.32.150.96` hosts ~12 other sites (ealearnings, auditisa, ealedgers, rtrotc,
several `*.cm-ea.com`, a `budgetms` stack, MySQL, a finance toolkit). Consequences:

- **Host Apache owns 80/443**, not our Docker nginx. Never assume our stack owns
  them, and always `apachectl configtest` before reloading Apache — a broken
  config takes down every tenant.
- **Memory is the binding constraint**: ~1.5 GB free with a nearly-full swap. A
  Next.js build wants 1.5–2 GB. Never build on this host without the deploy
  script's memory guard.
- **BitNinja filters inbound SSH.** Timeouts and `kex_exchange_identification`
  aborts usually mean a non-whitelisted IP, not a dead server. Whitelist with
  `bitninjacli --whitelist --add <ip>` (single IPs only, CIDR is rejected).

## Verification standard

Never claim something works because the code looks right or a deploy run went
green. A green deploy has already once reported success while leaving the old
image serving traffic. Verify the running artefact: the version the container
actually reports, the HTTP status the public URL actually returns, the row the
database actually holds.

## Secrets

`.env`, `.env.*` (except `*.example`), `*.pem` and `*.key` are git-ignored and
must stay that way. Never print a secret value into the transcript, a log, or a
commit message — refer to it by name.
