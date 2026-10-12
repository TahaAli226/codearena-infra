import subprocess 
import tempfile
from pathlib import Path
import uuid
from languages import LANGUAGES


def status_map(exit_code: int) -> str:
    if exit_code == 0: 
        return "ok"
    elif exit_code == 137:
        return "oom"
    elif exit_code in (125,126,127):
        return "internal_error"
    elif exit_code == 124: 
        return "timed_out"
    else:
        return "runtime_error"
    
def run_container(image: str, command: list[str], work_dir: str, stdin: str = "", time_limit_ms: int = 1000, memory_limit_mb: int =256) -> dict:
        name = f"run-{uuid.uuid4().hex[:10]}"
        try:
            output = subprocess.run(["docker", "run", "--rm", "-i", "-v", f"{work_dir}:/code:ro,Z", "--name", name,
                              "--network", "none", "--memory", f"{memory_limit_mb}m", "--memory-swap", f"{memory_limit_mb}m", "--cpus", "1",
                              image,"timeout", f"{time_limit_ms / 1000}", *command ],
                            input=stdin , capture_output=True, text=True, timeout=time_limit_ms / 1000 + 10, encoding="utf-8", errors="replace"
                       )

            return {
                "stdout": output.stdout,
                "stderr": output.stderr,
                "exit_code": output.returncode,
                "status": status_map(output.returncode)
                }
        
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", name],
                capture_output=True)
            return {
                "stdout": "",
                "stderr": "",
                "exit_code": None,
                "status": "timed_out"
                    }
        
        except FileNotFoundError:
            return {
            "stdout": "",
            "stderr": "docker does not exist on the system's path",
            "exit_code": None,
            "status": "internal_error"
            }
        
def run_code(language: str, code: str, inputs: list[str], time_limit_ms: int = 1000, memory_limit_mb: int =256) -> dict:
    config = LANGUAGES[language]

    with tempfile.TemporaryDirectory() as tmp:
        code_file = Path(tmp) / config["filename"]
        code_file.write_text(code)
        results = []
        for test_input in inputs: 
           results.append(run_container(image=config["image"],command=config["run"], work_dir=tmp, stdin=test_input, time_limit_ms=time_limit_ms, memory_limit_mb=memory_limit_mb))
        return {"results": results}

        
if __name__ == "__main__":
    print(run_code("python", 'print("hello world")', [""]))
    print(run_code("python", "n = int(input())\nprint(n * 2)", ["4", "10", "7"]))
    print(run_code("python", "while True: pass", [""]))





