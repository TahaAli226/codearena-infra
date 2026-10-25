import json
import os
import subprocess
import urllib.request
from pathlib import Path
import socket

server = os.environ.get("SERVER_NAME", socket.gethostname())
code_arena_repos = {"infra": "/opt/code_arena/infra"}
code_arena_images = {
    "api": "ghcr.io/techies-lab-projects-07-codearena/codearena-api:dev",
    "dashboard": "ghcr.io/techies-lab-projects-07-codearena/codearena-frontend:dev",
    "apk": "ghcr.io/techies-lab-projects-07-codearena/codearena-apk:dev",
}
discord_hook = os.environ["DISCORD_WEBHOOK"]
state_dir = Path(os.environ.get("STATE_DIRECTORY", "/var/lib/codearena-deploy"))
compose_dir = code_arena_repos["infra"]
critical_files = ("compose.yml", "Caddyfile")
services = ["caddy", "api", "dashboard", "apk"]  
runner_pip = f"{compose_dir}/runner/.venv/bin/pip"


def run(cmd: list[str], cwd: str = compose_dir) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False, timeout=300)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", "timed out after 5 minutes")


def notify_discord(message: str) -> None:
    print(message)
    try:
        body = json.dumps({"content": message[:1900]}).encode()
        discord_req = urllib.request.Request(
            discord_hook,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "codearena-deploy"},
        )
        urllib.request.urlopen(discord_req, timeout=10)
    except Exception as e:
        print(f"discord notification failed: {e}")


def read_state(name: str) -> str | None:
    file = state_dir / name
    return file.read_text().strip() if file.exists() else None


def write_state(name: str, value: str) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / name).write_text(value)


def which_mode(path: str) -> str:
    if path in critical_files:
        return "hard"
    if path.startswith(("docs/", "systemd/", "ansible/", "deploy/")) or path.endswith(".md"):
        return "pull-only"
    return "normal"


def server_image_id(image: str) -> str:
    return run(["docker", "image", "inspect", "--format", "{{.Id}}", image]).stdout.strip()

def image_commit(image: str) -> str:
    command = '{{index .Config.Labels "org.opencontainers.image.revision"}}'
    return run(["docker", "image", "inspect", "--format", command, image]).stdout.strip()

def main() -> None:
    changed = {}  
    mode = "pull-only"
    runner_changed = False        
    requirements_changed = False  

    for name, path in code_arena_repos.items():
        if run(["git", "fetch", "origin", "dev"], cwd=path).returncode != 0:
            print(f"{name}: fetch failed")
            continue
        new_check = run(["git", "rev-parse", "origin/dev"], cwd=path).stdout.strip()
        last_good_check = read_state(name) or run(["git", "rev-parse", "HEAD"], cwd=path).stdout.strip()
        if new_check == last_good_check:
            continue
        files = run(["git", "diff", "--name-only", last_good_check, new_check], cwd=path).stdout.split()
        modes = {which_mode(file) for file in files}
        if name == "infra":
            runner_changed = any(f.startswith("runner/") and which_mode(f) != "pull-only" for f in files)
            requirements_changed = "runner/requirements.txt" in files
        if "hard" in modes:
            mode = "hard"
        elif "normal" in modes and mode == "pull-only":
            mode = "normal"
        changed[name] = new_check

    for name, image in code_arena_images.items():
        current_image = server_image_id(image)
        if run(["docker", "pull", image]).returncode != 0:
            print(f"{name}: pull failed")
            continue
        new_image = server_image_id(image)
        if new_image != (read_state(name) or current_image):
            changed[name] = new_image
            if mode == "pull-only":
                mode = "normal"

    if not changed:
        return
    
    commits = {}
    for name, path in code_arena_repos.items():
        if name in changed:
            run(["git", "reset", "--hard", "origin/dev"], cwd=path)
            commits[name] = run(["git", "log", "-1", "--format=%s"], cwd=path).stdout.strip()

    deploy_message = []
    for name, ver in changed.items():
        short = ver.split(":")[-1][:7]
        if name in commits:
            deploy_message.append(f"- {name} {short}: {commits[name]}")
        else:
            commit = image_commit(code_arena_images[name])[:7]
            deploy_message.append(f"- {name} {short} (commit {commit})")
    label = "\n".join(deploy_message)


    result = subprocess.CompletedProcess([], 0, "", "")
    if mode == "normal":
        result = run(["docker", "compose", "up", "-d", "--remove-orphans"])
    elif mode == "hard":
        result = run(["docker", "compose", "up", "-d", "--remove-orphans", "--force-recreate", *services])

    if runner_changed and result.returncode == 0:
        if requirements_changed:
            result = run([runner_pip, "install", "-r", "runner/requirements.txt"])
        if result.returncode == 0:
            result = run(["sudo", "-n", "systemctl", "restart", "runner"])
        mode = f"{mode} + runner"

    if result.returncode == 0:
        for name, version in changed.items():
            write_state(name, version)
        write_state("failed", "")
        if mode != "pull-only":
            run(["docker", "image", "prune", "-f"])
            notify_discord(f"[{server}] deploy successful ({mode}):\n{label}")
        return

    if read_state("failed") != label:
        error = "\n".join(result.stderr.strip().splitlines()[-5:])
        notify_discord(f"[{server}] deploy failed ({mode}):\n{label}\n{error}")
        write_state("failed", label)


if __name__ == "__main__":
    main()