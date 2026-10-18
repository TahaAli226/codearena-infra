import json
import logging
import os
import subprocess
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from .config import (
    MAX_CPU_UTILIZATION,
    MAX_FILE_SIZE,
    MAX_OUTPUT,
    MAX_PIDS,
    MAX_TMPFS_SIZE,
)
from .languages import LANGUAGES

log = logging.getLogger(__name__)

def exec_time(docker_time: str):
    main, frac = docker_time.rstrip("Z").split(".")
    return datetime.fromisoformat(f"{main}.{frac[:6]}+00:00")

def inspect_container_time(name: str) -> dict:
    default = {"execution_time_ms": None, "oom_killed": False}
    try:
        out = subprocess.run(
            ["docker", "inspect", "--format", "{{json .State}}", name],
            capture_output=True, text=True, timeout=10,
        )
    except subprocess.TimeoutExpired:
        return default
    if out.returncode != 0:
       return default
    try:
        state = json.loads(out.stdout)
        started = exec_time(state["StartedAt"])
        finished = exec_time(state["FinishedAt"])
    except (ValueError,KeyError):
        return default
    return {
        "execution_time_ms": int((finished - started).total_seconds() * 1000),
        "oom_killed": state["OOMKilled"],
    }

def status_map(exit_code: int, hit_memory_limit: bool = False) -> str:
    if hit_memory_limit:
        return "oom"
    elif exit_code == 0: 
        return "ok"
    elif exit_code in (125,126,127):
        return "internal_error"
    elif exit_code == 124: 
        return "timed_out"
    else:
        return "runtime_error"
    
def run_container(image: str, command: list[str], work_dir: str, stdin: str = "", time_limit_ms: int = 1000, memory_limit_mb: int =256, read_only: bool = True) -> dict:
        name = f"run-{uuid.uuid4().hex[:10]}"
        permission = "ro" if read_only else "rw"

        try:
            output = subprocess.run(["docker", "run", "-i", "-v", f"{work_dir}:/code:{permission},Z", "--name", name,
                                "--network", "none", "--memory", f"{memory_limit_mb}m", "--memory-swap",
                                f"{memory_limit_mb}m", "--cpus", f"{MAX_CPU_UTILIZATION}", "--ulimit", f"fsize={MAX_FILE_SIZE}",
                                "--cap-drop", "ALL", "--security-opt","no-new-privileges","--user",f"{os.getuid()}:{os.getgid()}",
                                "--pids-limit", f"{MAX_PIDS}", "--read-only", "--tmpfs", f"/tmp:size={MAX_TMPFS_SIZE}m,mode=1777","--label", "codearena",
                                image,"timeout", f"{time_limit_ms / 1000}", *command ],
                                input=stdin , capture_output=True, text=True, timeout=time_limit_ms / 1000 + 10, encoding="utf-8", errors="replace"
                       )
            check = inspect_container_time(name)
            return {
                "stdout": output.stdout[:MAX_OUTPUT],
                "stderr": output.stderr[:MAX_OUTPUT],
                "exit_code": output.returncode,
                "status": status_map(output.returncode, check["oom_killed"]),
                "execution_time_ms": check["execution_time_ms"]
                }
        
        except subprocess.TimeoutExpired:
            try:
                subprocess.run(["docker", "kill", name], capture_output=True, timeout=10)
            except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                log.warning("cleanup failed: %s", e)

            return {
                "stdout": "",
                "stderr": "",
                "exit_code": None,
                "status": "timed_out",
                "execution_time_ms": None
                    }
        
        except FileNotFoundError:
            return {
            "stdout": "",
            "stderr": "docker does not exist on the system's path",
            "exit_code": None,
            "status": "internal_error",
            "execution_time_ms": None
            }

        finally:
            try:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=10)
            except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                log.warning("cleanup failed: %s", e)
           
        
def run_code(language: str, code: str, inputs: list[str], time_limit_ms: int = 1000, memory_limit_mb: int =256) -> dict:
    config = LANGUAGES[language]

    with tempfile.TemporaryDirectory() as tmp:
        code_file = Path(tmp) / config["filename"]
        code_file.write_text(code)
        results = []

        if config["compile"]: 
            compiled = run_container(image=config["image"],command=config["compile"], work_dir=tmp,
                                    time_limit_ms=10000, memory_limit_mb=512, read_only=False)

            if compiled["status"] != "ok":
                status = "internal_error" if compiled["status"] == "internal_error" else "compile_error"
                for test_input in inputs:
                    results.append({"stdout": "", "stderr": compiled["stderr"], "exit_code": compiled["exit_code"], "status": status, "execution_time_ms": None
                    })
                return {"results": results} 
                

        for test_input in inputs: 
           results.append(run_container(image=config["image"],command=config["run"], work_dir=tmp, stdin=test_input,
                                        time_limit_ms=time_limit_ms, memory_limit_mb=memory_limit_mb))
        return {"results": results}
        

        


