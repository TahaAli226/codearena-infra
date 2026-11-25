# Runner

## Overview
The runner executes code submitted by CodeArena users. The API calls the runner's FastAPI endpoint with the language, the user's code and the test inputs. Each input runs in its own isolated, short-lived container, and the runner returns the output and status for each.

The runner is a systemd service (`runner.service`) running as the `runner` user. Sandboxes run in **rootless Podman** as that user: `runner` has no login shell, no sudo and is not in the docker group, so even an escape from a sandbox lands as an unprivileged user.

## How a run works
```
POST /run → main.py → run_code() → run_container() (per input) → results
```

### API (`main.py`)
- Validates the request (language, code size, input count, limits)
- Checks the secret key in the request header
- Takes a slot or waits for one: only `RUNNER_MAX_CONCURRENT` runs execute at once, the rest queue
- Calls `run_code()` and releases the slot when it finishes

### Engine (`run_code.py`)
`run_code()`
- Looks up the language in `languages.py`
- Creates a temp dir and writes the code file into it
- C++ is compiled once for all inputs; on failure every input returns `compile_error`
- Calls `run_container()` for each input
- The temp dir is deleted automatically

`run_container()`
- Gives each container a unique name and mounts the temp dir as `/code`
- Starts the container with the flags below
- Measures the program's run time
- Maps the exit code to a status
- Removes the container

## Limits

| Limit | Value | Why |
|---|---|---|
| Network | none | User code can't reach the server, the internet or other containers |
| Memory | 64 MB (`--memory` = `--memory-swap`) | Caps RAM; equal swap stops it spilling onto disk |
| CPU | 0.5 (`--cpus`) | Half a core's worth of CPU time, so one run can't starve the server |
| Processes | 32 (`--pids-limit`) | Stops fork bombs |
| Time | per problem (`timeout` in the container + host backstop) | Ends infinite loops |
| File size | `<value>` (`--ulimit fsize`) | Stops code from filling the disk |
| `/tmp` | `<value>` (`--tmpfs`) | Caps scratch space |
| Concurrent runs | 2 (`RUNNER_MAX_CONCURRENT`) | Caps total load; extra runs queue |

## Container flags
- `--network none`: no network access, only loopback
- `--memory` + `--memory-swap`: maximum memory; swap set to the same value so the container can't use disk as memory
- `--cpus`: maximum CPU time. It's an amount of CPU time, not specific cores
- `--ulimit fsize`: maximum size of any single file the code writes
- `--pids-limit`: maximum number of processes (protects against fork bombs)
- `--read-only`: the whole container filesystem is read-only, except mounts named in the command
- `--tmpfs /tmp`: a small in-memory `/tmp` with a size cap
- `--cap-drop ALL`: drops every Linux capability the runtime grants by default, so even root inside the container can't do privileged operations
- `--security-opt no-new-privileges`: the program can never gain more privileges than it started with
- `--user uid:gid`: runs the program as a non-root user inside the container
- `/code` mounted `:ro` (read-write only for compiling), `:Z`: read-only during execution; `:Z` gives the mount the SELinux label the container needs
- `timeout` inside the container: stops the user's program after the time limit

## Protection layers
| Layer | Where | Limits |
|---|---|---|
| Rate limit | API (backend) | Per user: run 10/min, submit 5/min. Per IP: login 30/min, register 100/hour |
| Concurrency | Runner (`RUNNER_MAX_CONCURRENT`) | Runs at once, server-wide; the rest queue |
| Container limits | Each sandbox | Memory, CPU, processes, time, no network (table above) |

CPU limits are ceilings: if the CPU is full, runs get slower, not killed. Memory is what kills, so memory caps must add up to less than the server's RAM.

## Decisions
- **Rootless Podman for sandboxes:** untrusted code never touches a root daemon. The rest of the stack uses Docker with trusted CI images.
- **gVisor evaluated and declined:** with rootless Podman it couldn't enforce limits (a 1 GB allocation succeeded inside a 256 MB limit), and running it under root Docker would make the runner root-equivalent again. Rootless Podman with enforced limits is the safer choice.
- **One container per test input:** each test gets its own verdict, so a crash on test 2 doesn't stop the remaining tests.
- **Checking the `OOMKilled` flag:** exit code 137 means any SIGKILL, including a program killing itself. The flag removes the ambiguity, so only a real out-of-memory gets reported as one.
- **Runner reachable only locally, with a secret key:** it listens on the Docker bridge (`172.17.0.1:9500`), not the internet, and the key stops other local services from using it.
- **Startup time not counted:** the clock starts when the user's program starts, not when the container is being created.
- **Time limit inside the container + host backstop:** `timeout` is the normal path; if it fails, a host-side timer ends the run.

## Service vs. job
- Cleanup of leftover containers runs in `ExecStartPre`, so only when the service starts. That makes it safe with more than one concurrent run.
- Runs in progress during a runner restart are lost.
- The unit file is generated from `ansible/templates/runner.service.j2`.

## Known limitations
- `RUNNER_MAX_CONCURRENT` (2) × CPU per sandbox (0.5) = a whole core on lab07's single vCPU, so bursts of submissions slow the site. Option: concurrency 1 on lab07.
- Runner throughput (jobs per minute) not measured yet.
- **Output is fully buffered before truncation.** `subprocess.run(capture_output=True)`
  reads all output into the runner before `MAX_OUTPUT` (64 KB) is applied, outside the
  sandbox limits. On lab07 a print loop pushed the runner from 43 MB to 668 MB, and
  about 230 MB stayed allocated until restart.
  - **Mitigation:** `MemoryMax=400M`, `MemorySwapMax=0` and concurrency 1. A flood
    OOM-kills the runner, which restarts in 5 s; affected users see "runner unavailable"
    and queued runs are lost. Not in Ansible yet.
  - **Fix:** stream output with `subprocess.Popen` and kill the container once it passes
    `MAX_OUTPUT`.
- **The secret check fails open.** If `RUNNER_SECRET_KEY` is unset, the check is skipped.
  Fix: refuse to start without it.
- **Podman 6 sends rootless users to root's storage.** An unattended `dnf-automatic`
  run (Nov 17, 2026) upgraded Podman to 6.1.1 (ALSA-2026:98554). Podman 6 applies
  `graphroot`/`runroot` from the packaged `/usr/share/containers/storage.conf` to
  rootless users too, so every run failed with `internal_error` (exit 125,
  `mkdir /var/lib/containers/storage/libpod: permission denied`) while the service
  showed active and the API returned 200.
  - **Fix:** explicit paths in `/home/runner/.config/containers/storage.conf` (owned by
    `runner`): `graphroot = "/home/runner/.local/share/containers/storage"`,
    `runroot = "/run/user/994/containers"`. Not in Ansible yet.
  - **Mitigation:** `dnf-automatic.timer` disabled Nov 18 to Dec 4 for the testing
    freeze; afterwards, re-enable it and versionlock the Podman stack. Security-only
    updates would not have helped, because the rebase shipped as a security advisory.
  - **Gap:** a 200 response doesn't prove that runs work. A smoke test that checks for
    `"status":"ok"` would have caught this.