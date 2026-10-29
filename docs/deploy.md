# Deploy

## Overview
Deploys are **pull-based**: a systemd timer on the server runs `deploy.py` every minute. Nothing pushes to the server; the server fetches what changed and applies it. Every deploy that changes what's running is reported to Discord, labeled `[server]`.

Two things trigger a deploy:
- **A new commit in the infra repo** (compose file, Caddyfile, configs, scripts)
- **A new image on GHCR** (api, dashboard, apk, caddy), built by each repo's CI and tagged `dev`

## How it works
Every run, `deploy.py`:
1. Fetches the infra repo and compares it with the **last successfully deployed commit** (kept in a state file). The state is only updated after a successful deploy, so a failed deploy is retried on the next run.
2. Picks a mode from the files that changed (below).
3. Pulls the `dev` images. Images are pulled by tag, not by SHA, so the server always gets the newest build.
4. After a successful deploy, `deploy.py` prunes untagged images (the old versions left behind by each pull) so they don't fill the disk.

### Modes
| Mode | When | What it does |
|---|---|---|
| **Hard** | Critical files changed: `compose.yml`, `Caddyfile`, `monitoring/agent/agent.yml` | Pull + force-recreate every service except the database |
| **Normal** | Anything else that affects the stack, or a new image | Pull + `docker compose up -d` (recreates only what changed) |
| **Pull-only** | Only `docs/`, `systemd/`, `ansible/`, `deploy/`, `monitoring/` or `*.md` changed | Updates the checkout, restarts nothing |
| **+ runner** | `runner/` changed (adds to any mode) | Restarts the runner (via a narrow sudoers rule); reinstalls its dependencies only if `runner/requirements.txt` changed |

The file lists are configuration in `deploy.py`: moving a path into a different mode is a one-line change.

### Access
- **Infra repo:** cloned over SSH with a read-only deploy key.
- **Images:** pulled from GHCR with a read-only token. The api and dashboard repos don't need deploy keys anymore, since their code arrives as images.

## Freeze (before the presentation)
```bash
sudo systemctl disable --now codearena-deploy.timer       # no more deploys
docker compose images                            # record what's running (below)
sudo systemctl start codearena-backup.service    # fresh DB backup
# docker save the app images + copy them and the backup off the server
```
Unfreeze: `sudo systemctl enable --now codearena-deploy.timer`.

### Version presented (2026-10-30)
| Container | Image | Tag | Image ID |
|---|---|---|---|
| caddy | codearena-caddy | dev | 20637d1f1713 |
| api | codearena-api | dev | e5058c33f113 |
| apk | codearena-apk | dev | 2cb3d150a0cf |
| dashboard | codearena-frontend | dev | 30fb76c70245 |
| db | postgres | 17-alpine | b0f9560a2de0 |
| node-exporter | prom/node-exporter | v1.10.2 | 3ac34ce007ac |
| prometheus-agent | prom/prometheus | v3.15.1 | fa3302279710 |

## Rollback
- **Bad infra change:** `git revert` the commit and push; the next deploy applies the revert.
- **Bad app image, fast:** deploy one of the last 3 `sha-…` tags kept on GHCR instead of `dev` (stop the deploy timer first so it doesn't pull `dev` back).
- **Emergency:** stop the deploy timer, then `docker load` the images saved at the freeze.

## Decisions
- **Pull-based deploy:** the server needs no inbound access from CI and holds only read-only credentials. A compromised CI can't push to the server.
- **Modes by changed files:** a docs change never restarts anything, and only real config changes force-recreate containers.
- **Retry by state:** recording only successful deploys makes a failed deploy retry itself.
- **Tag `dev` + prune:** always the newest build, without old images filling a small disk.
- **No Discord message for pull-only deploys:** they only update docs and config that nothing running uses, so a message would be noise. Discord reports only deploys that change what's running.
- **One alert per failure:** a failing deploy notifies Discord once, not every minute, until it succeeds or fails differently.
- **Hard mode never restarts the database:** force-recreate covers every service except `db`.


## Known limitations
- **CI gates differ by repo:** the api image is built only after lint, type checks and tests pass (with a real Postgres); the APK only after analyze and tests; the dashboard image only if the app builds (no lint or tests on push). In the **infra repo** CI is advisory: the Caddy image workflow and the deploy don't wait for it, so a config change deploys even if CI fails. Future: `needs:` in the Caddy image workflow, a CI status check in `deploy.py`, and lint/tests for the dashboard.
- **Limited image history:** the server prunes old images after each deploy, but GHCR keeps the last 3 versions of each app image with `sha-…` tags. Rolling back to one of those means deploying its SHA tag. Future: deploy pinned SHA tags instead of `dev`.
- **`deploy.py` exits 0 even when a deploy fails**, so systemd reports success. The Discord message is the real signal.
- **`git fetch` and `git reset` failures are silent:** fetch only logs to the journal, and the reset's result isn't checked, so a failed reset could record a deploy whose files never changed.
- **The GHCR token belongs to a personal account** and expires around Nov 19. Future: rotate it and move to an org-level token. Note: the playbook logs in only once (`creates: config.json`), so after rotating, delete `~student/.docker/config.json` before rerunning it.