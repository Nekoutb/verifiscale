# Deployment workflow

Two instances, one promotion path. Nothing reaches production without having run
on dev first, and the deploy script enforces that rather than trusting anyone to
remember it.

## The two instances

| | Dev (staging) | Production |
|---|---|---|
| URL | https://dev.verifiscale.com | https://verifiscale.com |
| Branch | `dev` | `main` |
| Server directory | `/srv/cmimpot-dev` | `/srv/cmimpot` |
| Compose project | `cmimpot-dev` | (default) |
| Compose file | `docker-compose.dev.yml` | `docker-compose.prod.yml` |
| Env file | `.env.dev` | `.env.prod` |
| Docker nginx ports | 8081 / 8444 | 8080 / 8443 |
| Database | own container `fiscaudit-postgres-dev`, volume `pg_data_dev` | `fiscaudit-postgres`, volume `pg_data` |
| File storage | volume `api_storage_dev` | volume `api_storage` |
| Crawlers | `X-Robots-Tag: noindex, nofollow` on every response | indexable |
| Outbound email / AI | keys blank, so no real sends or charges | live keys |

Both sit behind the host Apache (which owns 80/443) and Cloudflare. Apache routes
by `ServerName`, so the exact `dev.verifiscale.com` vhost wins over the `*:443`
default (`bp.cm-ea.com`) — without that vhost, dev traffic would land on another
tenant's site entirely.

The two instances share only the Docker engine and the host. Separate database
containers mean a runaway dev migration cannot lock or bloat production's data,
and separate JWT secrets mean a production session token is invalid on dev and
vice versa.

## Day-to-day commands

Work on `dev`, deploy to dev, test, then promote the *same* sha.

```bash
# 1. work
git checkout dev
#    ... edit, commit ...
git push origin dev

# 2. deploy to dev  (defaults to origin/dev)
deploy/deploy-verifiscale.sh dev

# 3. test on https://dev.verifiscale.com

# 4. promote: fast-forward main to the tested commit
git checkout main
git merge --ff-only dev
git push origin main

# 5. deploy that exact sha to production
deploy/deploy-verifiscale.sh prod <sha>
```

Step 2 prints the exact `prod` command with the sha filled in, so step 5 is
copy-paste and you cannot accidentally promote a *different* commit than the one
you tested.

## What the script guarantees

- **Exact shas only.** The ref is resolved to a full sha and the server does
  `git checkout --detach <sha>` of a commit fetched from origin. A dirty local
  working tree can never reach an instance, and "what is deployed" is never
  ambiguous.
- **The production gate.** `prod` is refused unless the sha is *both* reachable
  from `origin/main` *and* present in `/srv/cmimpot/.deployed_dev_log`, the
  append-only list of shas that completed a successful dev deploy. There is no
  skip flag.
- **A verified backup before any production change.** `pg_dumpall` to
  `/srv/backups/verifiscale/`, then the script checks the file is non-trivial and
  that `gzip -t` passes. If either check fails the deploy aborts and production
  is untouched.
- **Health checks that distinguish failure from flakiness.** `/health` and
  `/login` must return 200, retried for up to 2.5 minutes. Separately, a dropped
  SSH connection is retried with backoff — this host's BitNinja agent aborts
  connections intermittently, and that is not a failed deployment.
- **A memory guard before building.** This host runs ~12 sites with ~1.5 GB free
  and a nearly-full swap; a Next.js build wants 1.5–2 GB. The script measures
  available memory, drops caches and re-measures, and refuses to build below
  800 MB rather than OOM-killing the other tenants.
- **A rollback pointer.** The previous production sha is printed before the swap,
  so rolling back is one command.

## Hotfix path

There is no bypass, because there does not need to be one — the gated path is
minutes, not hours:

```bash
git checkout dev && git cherry-pick <fix> && git push origin dev
deploy/deploy-verifiscale.sh dev          # ~2 min, then sanity-check dev
git checkout main && git merge --ff-only dev && git push
deploy/deploy-verifiscale.sh prod <sha>
```

If the gate refuses a deploy, that refusal is the system working. Fix the cause
(push the commit, merge it to main, run it on dev) rather than working around it.

## Rollback

```bash
# the previous sha is printed by every prod deploy, and stored server-side:
ssh root@45.32.150.96 'cat /srv/cmimpot/.deployed_sha'
deploy/deploy-verifiscale.sh prod <previous-sha>
```

A previously-deployed sha is already in the dev log, so the gate lets it through.
To restore data rather than code, the pre-deploy dumps are in
`/srv/backups/verifiscale/`.

## First-time setup

Once, on the server, after `dev` exists on origin:

```bash
ssh root@45.32.150.96
cd /srv/cmimpot && git pull
sudo bash deploy/bootstrap-dev.sh
```

`bootstrap-dev.sh` clones `/srv/cmimpot-dev`, creates `.env.dev` from the
template (and stops so you can fill in a distinct `POSTGRES_PASSWORD` and
`JWT_SECRET`), installs and validates the Apache vhost, then starts the dev
stack from production's existing images — no build, so no OOM risk. It refuses
to continue if dev would share a JWT secret or database name with production.
