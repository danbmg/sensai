import ast
import subprocess
from pathlib import Path

from .security import WorkspaceSecurity


IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
}


def inspect_project(
    security: WorkspaceSecurity,
    max_files: int = 200,
) -> dict:
    """
    Return a structured overview of the workspace.
    """

    files = []
    extensions = {}

    for path in security.workspace.rglob("*"):
        if any(
            part in IGNORED_DIRECTORIES
            for part in path.parts
        ):
            continue

        if not path.is_file():
            continue

        relative = path.relative_to(
            security.workspace
        )

        try:
            security.resolve(str(relative))
        except Exception:
            continue

        extension = path.suffix or "<no extension>"

        extensions[extension] = (
            extensions.get(extension, 0) + 1
        )

        files.append(str(relative))

        if len(files) >= max_files:
            break

    return {
        "workspace": security.workspace.name,
        "files": files,
        "file_count_returned": len(files),
        "extensions": extensions,
        "truncated": len(files) >= max_files,
    }

def inspect_directory(
    security: WorkspaceSecurity,
    path: str = ".",
    max_depth: int = 2,
    max_entries: int = 100,
) -> dict:
    """
    Inspect the structure of a directory inside the workspace.
    """

    directory = security.resolve(path)

    if not directory.exists():
        raise ValueError(
            f"Directory does not exist: {path}"
        )

    if not directory.is_dir():
        raise ValueError(
            f"Not a directory: {path}"
        )

    entries = []

    base_depth = len(directory.parts)

    for item in sorted(directory.rglob("*")):
        relative_depth = len(item.parts) - base_depth

        if relative_depth > max_depth:
            continue

        relative = item.relative_to(
            security.workspace
        )

        try:
            security.resolve(str(relative))
        except Exception:
            continue

        entries.append(
            {
                "path": str(relative),
                "type": (
                    "directory"
                    if item.is_dir()
                    else "file"
                ),
            }
        )

        if len(entries) >= max_entries:
            break

    return {
        "directory": path,
        "entries": entries,
        "count": len(entries),
        "truncated": len(entries) >= max_entries,
    }

def read_source_file(
    security: WorkspaceSecurity,
    path: str,
    max_chars: int = 20_000,
) -> dict:
    """
    Safely read a text file from the workspace.
    """

    file_path = security.require_file(path)

    try:
        content = file_path.read_text(
            encoding="utf-8"
        )
    except UnicodeDecodeError:
        return {
            "path": path,
            "error": "File is not valid UTF-8 text.",
        }

    truncated = len(content) > max_chars

    if truncated:
        content = content[:max_chars]

    return {
        "path": path,
        "content": content,
        "truncated": truncated,
    }


def search_code(
    security: WorkspaceSecurity,
    query: str,
    max_results: int = 30,
) -> dict:
    """
    Search text inside source files.
    """

    results = []

    allowed_extensions = {
        ".py",
        ".js",
        ".ts",
        ".java",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".md",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
    }

    query_lower = query.lower()

    for file_path in security.workspace.rglob("*"):
        if len(results) >= max_results:
            break

        if not file_path.is_file():
            continue

        if file_path.suffix.lower() not in allowed_extensions:
            continue

        relative = file_path.relative_to(
            security.workspace
        )

        try:
            security.require_file(
                str(relative)
            )
        except Exception:
            continue

        try:
            lines = file_path.read_text(
                encoding="utf-8"
            ).splitlines()
        except (UnicodeDecodeError, OSError):
            continue

        for line_number, line in enumerate(
            lines,
            start=1,
        ):
            if query_lower in line.lower():
                results.append(
                    {
                        "path": str(relative),
                        "line": line_number,
                        "content": line.strip()[:500],
                    }
                )

                if len(results) >= max_results:
                    break

    return {
        "query": query,
        "matches": results,
        "count": len(results),
    }


def analyze_python(
    security: WorkspaceSecurity,
    path: str,
) -> dict:
    """
    Analyze a Python source file using the AST.
    """

    file_path = security.require_file(path)

    if file_path.suffix != ".py":
        raise ValueError(
            "analyze_python only accepts .py files."
        )

    source = file_path.read_text(
        encoding="utf-8"
    )

    try:
        tree = ast.parse(
            source,
            filename=str(file_path),
        )

    except SyntaxError as error:
        return {
            "path": path,
            "valid_python": False,
            "syntax_error": {
                "line": error.lineno,
                "offset": error.offset,
                "message": error.msg,
            },
        }

    functions = []
    classes = []
    imports = []

    for node in ast.walk(tree):

        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            functions.append(
                {
                    "name": node.name,
                    "line": node.lineno,
                    "arguments": [
                        arg.arg
                        for arg in node.args.args
                    ],
                }
            )

        elif isinstance(node, ast.ClassDef):
            classes.append(
                {
                    "name": node.name,
                    "line": node.lineno,
                }
            )

        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)

        elif isinstance(node, ast.ImportFrom):
            imports.append(
                node.module or ""
            )

    return {
        "path": path,
        "valid_python": True,
        "lines": len(source.splitlines()),
        "functions": functions,
        "classes": classes,
        "imports": sorted(set(imports)),
    }


def _run_command(
    security: WorkspaceSecurity,
    command: list[str],
    timeout: int = 30,
) -> dict:
    """
    Execute one of our predefined commands.

    Never accepts a raw shell command from the LLM.
    """

    try:
        process = subprocess.run(
            command,
            cwd=security.workspace,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )

        return {
            "command": command,
            "return_code": process.returncode,
            "stdout": process.stdout[-15_000:],
            "stderr": process.stderr[-15_000:],
        }

    except subprocess.TimeoutExpired:
        return {
            "command": command,
            "error": (
                f"Command exceeded the "
                f"{timeout}s timeout."
            ),
        }

    except FileNotFoundError:
        return {
            "command": command,
            "error": (
                f"Executable not found: "
                f"{command[0]}"
            ),
        }


def run_tests(
    security: WorkspaceSecurity,
) -> dict:
    """
    Run the project's Python tests.

    The LLM cannot provide arbitrary shell arguments.
    """

    return _run_command(
        security,
        [
            "python",
            "-m",
            "pytest",
            "-q",
        ],
        timeout=60,
    )


def git_status(
    security: WorkspaceSecurity,
) -> dict:
    return _run_command(
        security,
        [
            "git",
            "status",
            "--short",
        ],
    )


def git_diff(
    security: WorkspaceSecurity,
) -> dict:
    return _run_command(
        security,
        [
            "git",
            "diff",
            "--",
        ],
    )