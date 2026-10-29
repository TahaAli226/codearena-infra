# Security

## Checklist
| Item | How |
|---|---|
| SELinux enforcing on every server | Set and verified by the playbook on both servers; container volumes use `:Z` labels |
| Only needed ports open | firewalld: lab07 SSH + 4000/4007, myvm SSH + 443. Cockpit closed. The API, DB, runner and node-exporter publish no public ports |
| DB not reachable from the internet | The DB container publishes no port; only the API reaches it on the internal compose network |
| No secrets in any repo | All secrets live in the Ansible vault (AES-256 encrypted). Env files are written on the servers; repos hold only `.example` files; CI uses dummy values |
| HTTPS everywhere | Caddy with Let's Encrypt certificates for the app and monitoring. Domains are free subdomains from **DuckDNS**, a third-party DNS service; certificates are issued through its API (DNS-01) |
| HTTP → HTTPS | HTTPS only: plain HTTP on the app port is refused. The public IP belongs to the lab's shared gateway, which forwards one port per team (ours: 4007 → lab07:4000). Port 80 isn't ours to use, so there's no HTTP port to redirect from. With our own server and IP, Caddy would redirect port 80 to HTTPS automatically |
| Backups readable only by admin | `/var/backups/codearena` is owned by `student`, mode 700; backup files are 600 |

## Edge: Caddy
*Owner: Taha*
- **Single entry point:** browser → Caddy (HTTPS) → `/api/*` to the API, `/downloads/*` to the APK server, everything else to the dashboard. The API's own port is closed.
- **Real client IP** is passed to the API, so per-IP limits work.
- **Per-IP limit on `/api/*`:** 300 requests per 10 seconds. Tested: 400 requests from one IP gave exactly 300 × 200 and 100 × 429. Blocked requests are answered by Caddy and never reach the API.

## Backend: application limits
*Owner: Abdallah*
| Endpoint | Limit | Per |
|---|---|---|
| `POST /run` | 10 per minute | user |
| `POST /submissions` (normal + contest, shared) | 5 per minute | user |
| `POST /auth/login` | 30 per minute | IP |
| `POST /auth/register` | 100 per hour | IP |

Over the limit, the API returns a 429 JSON response and the frontend shows a message.

## API container
*Owner: Taha*
- Runs as its own user (`10001:10001`), not root and not shared with any other component
- `cap_drop: ALL`, `no-new-privileges`
- Limits: 300 MB memory (uses about 100 MB under load), 0.5 CPU, 200 processes (uses 2–7)
- Tested after hardening: login, admin panel, create a challenge, run, submit, no permission errors

## Runner and sandboxes
*Owner: Taha.* Details and every limit: `runner.md`.
- The runner listens only on the Docker bridge (`172.17.0.1:9500`) and requires a secret key, so only the API can call it.
- Sandboxes run in **rootless Podman** as the `runner` user: no login shell, no sudo, not in the docker group.
- Each run: no network, memory/CPU/process/file-size caps, read-only filesystem, all capabilities dropped, no privilege escalation, time limit.

### Threat model: escaping the sandbox
| Step | Attacker's goal | What stops it |
|---|---|---|
| 1 | Run malicious code | Allowed (that's the product), but inside the limits |
| 2 | Break out of the container | Default seccomp profile, `--cap-drop ALL`, `no-new-privileges`, non-root user, read-only filesystem. Requires a kernel exploit |
| 3 | Touch host files | SELinux confines containers, even root inside them |
| 4 | Become root on the host | Rootless: container root is the unprivileged `runner` user. Requires a second, privilege-escalation exploit |

Sandboxes share the host kernel, so a kernel exploit is the main residual risk. That's what gVisor would add (below).

### gVisor: evaluated, not adopted
1. `runsc` rejects SELinux labels.
2. With rootless Podman it can't create cgroups in the user's delegated hierarchy.
3. Its workaround (`--ignore-cgroups` + an external systemd scope) started, but didn't enforce limits: a 1 GB allocation succeeded inside a 256 MB scope.

Running it under rootful Docker instead would make the runner root-equivalent again. Decision: rootless Podman with enforced limits. Future: a minimal root-owned launcher, or Kubernetes with a gVisor RuntimeClass.

## Server baseline
*Owner: Taha.* Both servers are managed by the Ansible playbook (`server_setup.md`).
- SELinux enforcing
- firewalld with only the needed ports
- sshd: key login only, no root login, no password login
- dnf-automatic installs security updates automatically

## Secrets
- **One source:** the Ansible vault. Each service gets only its own env file (the README lists where each secret goes).
- Env files are readable only by their owner (600); the monitoring push password permission is set to (400).
- The metrics push password exists in two forms: plaintext on lab07 (the client) and a bcrypt hash on myvm (the verifier).

## Availability
| Layer | Stops |
|---|---|
| Caddy per-IP limit | One source flooding the API |
| Backend rate limits | One user flooding runs, submissions or logins |
| Runner concurrency cap | Total judging overload; extra runs queue |
| Sandbox limits | One job taking over the server |

Capacity (see `optimization.md`): about 114 requests per second on `/api/problems` with 25 constant clients, 0 errors. Under heavy load the site gets slower, not broken. Judging, not reading, is the real bottleneck.

## Known risks and future work
- **Distributed attacks (many IPs)** aren't stopped by per-IP limits. Needs a proxy/CDN like Cloudflare, which needs our own domain.
- **Kernel exploits:** sandboxes share the host kernel (see gVisor above).
- **Runner key leak:** lets an attacker skip the API and call the runner directly. Code would still run inside the sandbox, so it's an access and availability risk, not an escape.
- **Misconfiguration:** one wrong flag removes a layer. Mitigated by keeping configs in git and building servers from the playbook.
- **Supply chain:** monitoring images are pinned to exact versions, but `postgres:17-alpine`, the sandbox's `python:3.13-slim` and the Caddy base images only pin the major/minor version, and the Caddy plugins aren't pinned. Future: pin those to exact versions or digests.
- **GHCR token** belongs to a personal account and expires around Nov 19. Future: rotate it, and move it to a machine account owned by the org.
- **Off-site backups.** Future: encrypted off-site backups with the key in a secret manager.
- **HTTP → HTTPS redirect** on the app port is possible with Caddy's `http_redirect` listener wrapper. Future.
- **API docs** are public at `/api/docs` (accepted).
- **Third-party DNS (DuckDNS):** we don't control our DNS. If DuckDNS is down, the site can't be reached by name and certificates can't renew. The DuckDNS token controls both where the name points and certificate issuance, so whoever has it could redirect the site or get a valid certificate for it. That's why it lives only in the vault. Free subdomains also share a domain's reputation (see the Safe Browsing false positive). Future: our own domain, which also makes a CDN like Cloudflare possible.