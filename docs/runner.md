# Runner-Overview 

- The runner executes code submitted by CodeArena users. The Backend calls the runner's Fastapi endpoint with the desired programming language,
  the user's code and the test inputs, with each input running in its own isolated docker container and returns the output for each.


# How a run works 

```
POST /run → main.py → run_code() → run_container() (per input) → results
```

## API (main.py)

- Validates the request (language, code size, input count, limits )

- Checks the secret-key inside the header 

- Takes a slot or waits for a slot (implemented to not overwhelm the runner by allowing only a limited number of runs running at once)

- Call `run_code()` and release the slot after finishing 

## Engine (run_code.py)

### `run_code()`

- Looks up the language in `languages.py` 

- Creates a temp dir and write the code file into it 

- For C++ compile once for all inputs (on failure it returns `compile_error` per input)

- For each input `run_container()` is called 

- The temp dir gets deleted automatically 

### `run_container()`

- Each container gets a unique name, and gets a mounted temp dir as /code 

- Container runs with limited privileges set by the flags

- Read the container's time 

- Map exit code to status 

- The container gets removed 

### Container-Flags

- `--network none`: doesnt allow network access only loopback 

- `--memory` + `--memory-swap`: set the maximum amount of memory a single container can use with memory swap set to the same value to not start eating from storage

- `--cpus`: sets the maximum cpu time a container can use

- `--ulimit fsize`: sets the maximum file size for any single file the code writes 

- `--pids-limit`: limits the number of processes the container can create (protects against fork bombs)

- `--read-only`: makes the whole container read only including root allowing only directories that are specified during the docker run command 

- `--tmpfs /tmp`: limits the total size /tmp directory inside the container

- `--cap-drop ALL`: docker by default gives a container 14 of the 40 capabilities linux provides for root this drops all capabilities so even if a user somehow gained 
   root access it would be useless inside the container

- `--security-opt no-new-privileges`: to prevent a user from getting any privileges aside from what he already has when the container starts

- `--user uid:gid`: runs the container as a user because docker by default runs it as root 

- `/code` mounted `:ro` (rw only for compile), `:Z`: mounts the directory  as read-only for code execution and read-write for compilation and allow  the container 
   to reach the mounted directory through selinux 

- `timeout` inside the container: stops the users program after a certain amount of time  

# Runner Design Decisions

- why: why check OOMKilled flag from docker 

  ans: oom exits with code 137  which is shared with any SIGKILL or a user killing his own program by checking the flag we remove this ambiguity 

- why: one container per input(test) 

  ans: each test gets its own verdict so that if test 2 hits an error the rest of the tests get to run otherwise it wont

- why: why is the runner only reachable locally and with a secret key 

  ans: a security layer to prevent malicious attempts to exploit the runner to get access to the server and the secret key is to prevent 
       other services from getting access to the runner 

- why: startup time isn’t counted against the user

  ans: so that we dont count the time docker takes to create the container, the clock starts when the user's program starts not when docker begins
       creating the container 

- why: set time limit inside the container + host backstop  

  ans: the normal path is the timeout inside the container in case that failed to prevent an infinite loop we have a host backstop timer to end the process