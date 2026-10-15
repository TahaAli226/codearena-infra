import os 


MAX_FILE_SIZE = 64 * 1024 * 1024   # 64MB max file size written in a container 
MAX_OUTPUT = 64 * 1024    # 64KB stdout/stderr per run

MAX_CPU_UTILIZATION = os.environ.get("RUNNER_CPU_CORES", "1")     # cpu utlization limit
MAX_PIDS = os.environ.get("RUNNER_PIDS_LIMIT", "22")    # the number of pids the runner can create default set to 22 
MAX_TMPFS_SIZE = os.environ.get("RUNNER_TMPFS_SIZE_MB", "26") # 26MB max size of the container's /tmp
