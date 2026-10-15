LANGUAGES = {
    "python": {
        "image": "python:3.13-slim",
        "filename": "solution.py",
        "compile": None,
        "run": ["python", "/code/solution.py"],
    },
    "cpp": {
        "image": "codearena-cpp:1",
        "filename": "solution.cpp",
        "compile": ["g++", "-O2", "-o", "/code/solution", "/code/solution.cpp"],
        "run": ["/code/solution"],
},
}