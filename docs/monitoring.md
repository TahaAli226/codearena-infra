# Monitoring

## Overview
Monitoring runs on its own server (myvm), so it can still report when the app server is down. lab07 **pushes** its metrics to myvm, because the shared lab gateway doesn't expose lab07's ports for scraping.

| Server | Component | Job |
|---|---|---|
| lab07 | node-exporter `v1.10.2` | Host metrics (CPU, RAM, disk), on the internal Docker bridge only |
| lab07 | Prometheus agent `v3.15.1` | Scrapes node-exporter and Caddy, pushes to myvm with basic auth |
| myvm | Caddy | HTTPS; basic auth on the metrics push endpoint |
| myvm | Prometheus `v3.15.1` | Receives pushed metrics, keeps 15 days |
| myvm | blackbox-exporter `v0.29.1` | Probes the site, the API and the monitoring site from outside |
| myvm | Grafana `13.2.3` | Dashboard and alerts to Discord |

## Everything from files
Grafana is provisioned entirely from the repo: data source, contact point, notification policy, alert rules and the dashboard. A rebuilt myvm comes back identical (tested).
- Provisioned items are read-only in the UI. To change one: edit the file, then `docker compose up -d --force-recreate grafana` on myvm.
- myvm has no deploy timer: update it with `git pull` + recreate the changed service.
- **Don't rename the data source** (`Prometheus`): the alert rules reference an ID derived from its name.
- The dashboard is stored as classic dashboard JSON; newer export formats aren't loaded by file provisioning.

## Dashboard
"CodeArena overview" follows the four golden signals:

| Signal | Panels |
|---|---|
| Saturation | CPU, RAM and disk gauges (yellow at 80%, red at 90%) |
| Latency | p50 and p95 response time (from Caddy) |
| Traffic | Requests per minute |
| Errors | Server errors (5xx) per minute |

Plus status panels for the server, the dashboard and the API (UP/DOWN).

## Alerts
Five rules, evaluated every minute, sent to Discord:

| Alert | Fires when | For |
|---|---|---|
| Site down | A probe fails | 2 min |
| Disk almost full | Disk on `/` > 85% | 5 min |
| Memory high | RAM > 90% | 5 min (stays firing 5 min to avoid flapping) |
| Cert expires soon | Certificate expires in < 14 days | 10 min |
| Server not reporting | lab07 sent no metrics for 3 min | 2 min |

The steps for each alert are below. Tested end to end: Site down fired and resolved in Discord.

## When an alert fires
Commands run on **lab07** in `/opt/code_arena/infra` unless noted. On **myvm**, monitoring lives in `/opt/code_arena/infra/monitoring` (use `sudo`).

### Site down
**Means:** the blackbox probe from myvm got no 2xx response for 2+ minutes. The alert names the URL: the site, `/api/problems` or the monitoring site.

**Check, in order:**
1. **Which URL?** The monitoring URL → the problem is on myvm (`sudo docker compose ps`, Caddy logs). `/` down but `/api/problems` up → dashboard container. `/api/...` down but `/` up → API or database.
2. **lab07 reachable?** `ssh lab07`. If not: the VM or the gateway is down → contact the lab admins; worst case, rebuild and restore on a new server (`server_setup.md`, `backup.md`).
3. **Containers:** `docker compose ps` → anything not Up? `docker compose logs --tail 50 <service>`
4. **Caddy:** `docker compose logs caddy | grep -i error`. Certificate problems → see "Cert expires soon".
5. **DNS:** `dig +short codearena-iq.duckdns.org` must return the app server's public IP.

**Fix:**
- A crashed container: `docker compose up -d <service>`
- After a bad deploy: roll back to the previous image SHA (`deploy.md`)

**After:** note the cause and the fix in the incident log below.

### Disk almost full
**Means:** `/` has been over 85% full for 5+ minutes. Backups refuse to run below 500 MB free, to protect Postgres.

**Check, in order:**
1. `df -h /` → how full, how fast is it growing?
2. `docker system df` → images or containers taking the space?
3. `sudo du -sh /var/backups/codearena` → backups
4. `sudo journalctl --disk-usage` → logs

**Fix:**
- Old images: `docker image prune -f` (removes only untagged images)
- Logs: `sudo journalctl --vacuum-size=200M`
- Backups: 14 are kept automatically. Don't delete or add files by hand (the cleanup relies on the names); copy older ones off the server first if you must.
- **Never** delete the `pgdata` volume.

**After:** run a backup to confirm there's room (`sudo systemctl start codearena-backup.service`), then log it below.

### Memory high
**Means:** RAM has been over 90% for 5+ minutes.

**Check, in order:**
1. `free -h` → how much is left?
2. `docker stats --no-stream` → which container? (normal: API ~100 MB, everything else under 50 MB)
3. `systemctl status runner --no-pager` → many sandboxes running at once?

**Fix:**
- One container far above normal: `docker compose restart <service>`
- A burst of submissions: it passes on its own. If it keeps happening, lower `RUNNER_MAX_CONCURRENT`.

**After:** the alert stays firing for 5 minutes after recovery (anti-flapping), then resolves. Log it below.

### Cert expires soon
**Means:** a certificate expires in less than 14 days. Caddy renews automatically about 30 days before expiry, so this means **renewal is failing**. The alert names the certificate: app or monitoring.

**Check, in order:**
1. On the server that owns it: `docker compose logs caddy | grep -iE 'error|obtain|renew' | tail -20`
2. `DuckDNS API token must be a 36 characters long UUID` → the token in the vault is wrong.
3. Other DNS errors → is DuckDNS itself up?

**Fix:** correct the token in the vault, rerun the playbook for that server (`--limit`), then `docker compose up -d --force-recreate caddy`.

**After:** look for `certificate obtained successfully` in the Caddy logs, then log it below.

### Server not reporting
**Means:** myvm received no metrics from lab07 for 3+ minutes: lab07 is down, or its agent stopped pushing.

**Check, in order:**
1. `ssh lab07` fails → the server is down (Site down usually fires too). Contact the lab admins.
2. `docker compose ps prometheus-agent` → is it running?
3. `docker compose logs prometheus-agent --tail 30` → `401` means the push password on lab07 doesn't match the hash on myvm.

**Fix:**
- Agent stopped: `docker compose up -d prometheus-agent`
- `401`: both copies of the push password come from the vault; rerun the playbook for both servers.

**After:** the alert resolves within a few minutes. Log it below.

### Incident log
| Date | What happened | Cause | Fix |
|---|---|---|---|
| 2026-10-29 | myvm rebuild: app certificate failed | DuckDNS token missing a character in the vault | Corrected the vault, reran the playbook |

## Decisions
- **Separate monitoring server:** monitoring that lives on the server it watches goes down with it.
- **Push instead of scrape:** the only option behind the shared gateway; basic auth protects the push endpoint.
- **Probes from outside:** blackbox checks what a user sees (HTTPS, certificates, the API answering), not just whether processes run.

## Known limitations
- **Monitoring can't alert about itself:** if myvm is down, nothing reports it.
- **"Server status" lags after a reboot:** it's based on pushed data, and when lab07 stops pushing, the last value counts as current for up to 5 minutes. The "Server not reporting" alert already handles this correctly. Future: base the panel on `max_over_time(up[1m])`.
- **CPU panel lags 30–60 seconds** (30-second scrapes + rate calculation). Accepted.
- **429s don't show as errors:** rate-limited requests are 4xx, not 5xx. Future: a "rate-limited requests" panel.
- **The agent's instance name `lab07` is hardcoded** in `agent.yml`. Future: template it per server.
- **Alerts don't link to their steps yet.** Future: set each alert's Runbook URL to a public troubleshooting page, so the steps are one click away from the Discord message.