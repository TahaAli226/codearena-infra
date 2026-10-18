import json
import os
import subprocess
import urllib.request

code_arena_repos = ["/opt/code_arena/api", "/opt/code_arena/infra"]
deploy_script = "/opt/code_arena/infra/deploy/deploy.sh"
discord_hook = os.environ["DISCORD_WEBHOOK"]

def check_repo_updates() -> list:
    repos_to_update = []
    for repo in code_arena_repos:
          
        run(["git", "fetch", "origin", "dev"], repo)
        server_commit = run(["git", "rev-parse", "HEAD"], repo)
    
        latest_commit = run(["git", "rev-parse", "origin/dev"], repo)
     
        if server_commit.stdout.strip() != latest_commit.stdout.strip():
            repos_to_update.append(repo)
        
    return repos_to_update

def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=300)

def notify_discord(message):
    try:
        body = json.dumps({"content": message}).encode()
        discord_req = urllib.request.Request(
                discord_hook, data=body, 
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "codearena-deploy"
                }
        )
        urllib.request.urlopen(discord_req, timeout=10)
    except Exception as e:
        print(f"discrod notification failed: {e}")

def main():
    repo_list = check_repo_updates()
    updated_repos= []
    if not repo_list:
        return
    
    for repo in repo_list:
        run(["git", "reset", "--hard", "origin/dev"], repo)

    try:
        result = run([deploy_script], "/opt/code_arena/infra")
    except subprocess.TimeoutExpired:
        notify_discord("deploy timed out after 5 mintues")
        return 
    
    for repo in repo_list:
        output = run(["git", "log", "-1", "--oneline"], repo)
        updated_repos.append(output.stdout.strip())

    if result.returncode == 0:
        notify_discord("deploy_succeeded:\n" + "\n".join(updated_repos))
    else:
        notify_discord(f"deploy_failed:{result.stderr[-1000:]}")

if __name__ == "__main__":
    main()