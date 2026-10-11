import subprocess 


def run_code(code):
    output = subprocess.run(["docker", "run", "--rm", "-i", "python:3.13-slim", "python", "-"],
                        input=code , capture_output=True, text=True, timeout=10
                       )
    return {
        "stdout": output.stdout,
        "stderr": output.stderr,
        "exit_code": output.returncode
        }

print(run_code('print("hello world")'))
print(run_code('print(1/0)'))


