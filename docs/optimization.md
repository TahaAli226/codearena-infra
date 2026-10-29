# Optimization

## Overview
lab07 is small: 1 vCPU, 1.67 GB RAM, about 7 GB of disk. Everything below exists to fit the stack on it and keep it stable under load.

## Resource optimizations
- **Small images:** Alpine/slim bases wherever possible. The C++ sandbox image is a small distro with only `g++`, without the extra build packages.
- **Multi-stage frontend build:** Node exists only in the build stage; the shipped dashboard image is Caddy + static files (~100 MB).
- **Images built in CI, not on the server:** GitHub Actions builds every image and pushes it to GHCR; the server only pulls. No compiling or `npm install` on a 1 vCPU box.
- **Pruning:** after a deploy pulls a new image, untagged old images are pruned so they don't fill the disk. Sandbox containers are removed after every run, and leftovers are cleaned when the runner starts.
- **Capped judging:** `RUNNER_MAX_CONCURRENT` limits how many runs execute at once, and every sandbox has CPU and memory caps (`runner.md`).
- **API capped at 0.5 CPU and 300 MB:** the API can never take the whole CPU away from the runner and the database.

### Memory use (lab07, measured)
| Container | Memory |
|---|---|
| api | ~100 MB |
| db | ~41 MB |
| prometheus-agent | ~39 MB |
| caddy | ~31 MB |
| node-exporter | ~22 MB |
| apk | ~20 MB |
| dashboard | ~15 MB |
| **Total** | **~270 MB of 1.67 GB** |

## Load tests
Tool: `oha` from a pc against `/api/problems` (a read endpoint), 30 seconds per step.

`-c` is the number of clients sending requests **nonstop**. 25 clients ≠ 25 people; a real user sends a request every few seconds.

### Before API limits
| Clients | Req/s | p50 | p95 | Errors |
|---|---|---|---|---|
| 10 | 112 | 85 ms | 108 ms | 0 |
| 25 | 151 | 160 ms | 211 ms | 0 |
| 50 | 150 | 325 ms | 619 ms | 0 |

Throughput plateaus at **~150 req/s**: going from 25 to 50 clients doubled the wait but added no throughput. The bottleneck is CPU. Zero errors at every step: under overload the site gets slower, not broken. About 70 ms of every request is network (the fastest request).

### After API limits (0.5 CPU, 300 MB)
| Clients | Req/s | p50 | p95 | Errors |
|---|---|---|---|---|
| 25 | 114 | 206 ms | 303 ms | 0 |

About 24% less peak read throughput, in exchange for guaranteed CPU for judging and the database. Accepted.

### Side finding: deploys cost CPU
A 50-client run during a frontend deploy gave 126 req/s instead of 150, about 16% less. Pulling and recreating images competes for the single CPU, so deploys shouldn't run during peak use.

### Per-IP rate limit
400 requests from one IP with 20 clients: exactly **300 × 200 and 100 × 429**. The limiter kicks in at the configured 300 per 10 seconds, and the blocked requests never reach the API.

### What this means in users
A rough estimate, not a measurement: if a browsing user makes about one API request every 5 seconds, 114 req/s is roughly 500+ people browsing at once. **Judging is the real bottleneck, not reading**, and it's limited on purpose.

## Decisions
- **Protect judging over peak reads:** the API cap costs about 24% of read throughput but keeps runs and the database responsive.
- **Build in CI, pull on the server:** the server's single CPU serves users instead of compiling.

## Known limitations
- **Runner throughput isn't measured yet.** "Run" uses only the sample tests; "Submit" runs every hidden test, so submits are slower.
- **Only the API has memory caps.** Without caps, any container can grow until RAM runs out, and then the kernel kills a process of its choosing, possibly Postgres or the runner. Future: caps for every container within a budget that adds up to less than RAM.
- **Scaling:** more vCPUs, or moving the runner to its own server so it stops competing with the API.