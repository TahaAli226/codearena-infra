import os

# 64MB max file size written in a container 
MAX_FILE_SIZE = 64 * 1024 * 1024   
# 64KB stdout/stderr per run
MAX_OUTPUT = 64 * 1024    

# cpu utlization limit
MAX_CPU_UTILIZATION = os.environ.get("RUNNER_CPU_CORES", "1")
# the number of pids the runner can create default set to 22 
MAX_PIDS = os.environ.get("RUNNER_PIDS_LIMIT", "22")    
# default set to 26MB max size of the container's /tmp
MAX_TMPFS_SIZE = os.environ.get("RUNNER_TMPFS_SIZE_MB", "26")
# the number of containers that can exist at once
MAX_CONCURRENT = int(os.environ.get("RUNNER_MAX_CONCURRENT", "1"))
# pick between docker(rootful in this setup) or podman(rootless) 
CONTAINER_CLI = os.environ.get("CONTAINER_CLI", "docker") 