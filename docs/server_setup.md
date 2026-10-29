# Server setup

## Overview
| Server | Inventory name | Role | Runs |
|---|---|---|---|
| **lab07** | `vm7` | Production | Caddy, dashboard, API, PostgreSQL, APK downloads, runner + sandboxes, deploy and backup timers, node-exporter, Prometheus agent |
| **myvm** | `myvm` | Monitoring | Caddy, Prometheus, Grafana, blackbox-exporter |
Both servers are managed by the Ansible playbook (`ansible/site.yml`). myvm was built from a fresh install; lab07 was built by hand and brought under Ansible later on.

## How it works

### Step 0: bootstrap (manual, once per fresh server)
As root on the new server:
```bash
useradd -m -G wheel <admin>
passwd <admin>           # the password -K asks for
```
From the admin PC:
```bash
ssh-keygen -R <server-ip>                      # after a reinstall, forget the old host key
ssh-copy-id -i ~/.ssh/<key>.pub <admin>@<server-ip>
ssh -t <host> 'sudo -v && echo ok'             # key login + sudo work
```

### Running the playbook
From `infra/ansible/` on the control node (the admin PC that runs Ansible). Secrets come from the vault (`group_vars/all/vault.yml`); its password is in `~/.ansible_vault_pass` on the control node, never on the servers.
```bash
ansible-playbook site.yml -K --check --diff --limit <host>   # dry run: what would change
ansible-playbook site.yml -K --limit <host>                  # real run
```
- A real run names the hosts and asks you to type `yes`; anything else aborts with nothing changed.
- Always use `--limit`: the inventory includes prod.

### What each play does
- **all (base):** packages, full upgrade (+ reboot if needed), dnf-automatic for security updates, sshd hardening, SELinux enforcing (with relabel), firewalld (cockpit closed), Docker, deploy key, GHCR login, clone the infra repo.
- **servers (app):** runner user (nologin, no sudo, not in the docker group), rootless Podman, ports 4000/4007, cgroup delegation + linger, app folders, sudoers rule to restart the runner, env files from the vault, start the stack, runner venv + sandbox images, `runner.service` (`templates/runner.service.j2`), deploy + backup timers.
- **monitoring:** port 443, monitoring env files, start the monitoring stack.

### After a build
- Compose commands need `student` or sudo: env files are readable only by their owner.
- Grafana login: `admin` + the password from the vault.
- A fresh server has an empty DB unless a backup is restored (see `backup.md`).

## Rebuild test: myvm (2026-10-29)
myvm was reinstalled and rebuilt with the playbook: **all 3 plays `failed=0`**, API answered over HTTPS with a valid certificate, Grafana login, 5 alert rules Normal, dashboard provisioned, Discord test alert delivered.

## Bringing lab07 under Ansible (2026-10-29)
A dry run showed lab07 differed from the playbook mainly in its env files, so it was moved under Ansible in separate, reversible steps:

1. **Safety net:** copied the env files to `/root/pre-ansible` (root-only), took a fresh DB backup and saved the images, all copied off the server.
2. **Test reboot:** all containers, the runner and both timers came back on their own, on the new kernel.
3. **Packages by hand:** `dnf upgrade` + reboot, so the playbook run had nothing to upgrade or reboot.
4. **Dry run:** `--check --diff --limit vm7`, every change reviewed.
5. **Real run** with a second SSH session open (in case the sshd change blocked new logins): `failed=0`, no reboot.
6. **Verified:** API connected to the DB, runner active, Run and Submit in C++ and Python, admin panel.

**Rollback:** copy the files back from `/root/pre-ansible`, then `docker compose up -d --force-recreate` (and `sudo systemctl restart runner` for `runner.env`).

### What the run changed on lab07
- sshd hardening drop-in added (same effective config as before)
- cockpit closed in the firewall
- dead SSH aliases removed (`github-api`, `github-dashboard`)
- sudoers drop-in added for the runner restart
- `.env` and `runner.env` rewritten from the vault (values compatible: DB login and judging verified)
- `push_password` fixed from world-readable (0644) to 0400
- `runner.service` replaced with the templated unit

## Decisions
- **One playbook, three plays:** every server gets the same base; the app and monitoring roles are added by inventory group, so a server's role is one line in `inventory.ini`.
- **Secrets only in the vault:** each service gets only its own env file, written by the playbook (see the README for where each secret lives).
- **A typed `yes` guard on real runs:** a run against the wrong host stops before changing anything.
- **Package changes separate from config changes on prod:** upgrade and reboot by hand first, then run the playbook, so a failure points at one cause.

## Known limitations
- **Every run upgrades all packages** and reboots if a core package changed. Right for fresh servers; on prod, upgrade by hand first. Future: gate upgrades behind a variable or tag.
- **`--check` on a fresh server** fails at tasks that need packages not installed yet (dnf-automatic timer, pip). Do a real run first; use `--check --diff` on existing servers.
- **`--start-at-task "<name>"` skips the `yes` guard.** Only use it with `--limit`.
- **The DuckDNS token is stored twice in the vault.** Future: one shared `vault_duckdns_token`.
- **Two tasks always report `changed`** (building the C++ image, pulling the Python image), so a rerun is never fully `changed=0`.
- **A playbook run ends a deploy freeze:** its last task enables and starts the deploy timer. Don't run it on a frozen server.