import argparse

from mcp.server import MCPServer

from .security import WorkspaceSecurity
from .developer_tools import (
    inspect_project,
    inspect_directory,
    read_source_file,
    search_code,
    analyze_python,
    run_tests,
    git_status,
    git_diff,
)


mcp = MCPServer("sensai-developer")


# Initialized in main().
security: WorkspaceSecurity | None = None


def get_security() -> WorkspaceSecurity:
    if security is None:
        raise RuntimeError(
            "Workspace security is not initialized."
        )

    return security


@mcp.tool()
def project_overview() -> dict:
    """
    Inspect the current software project.

    Returns files, file types and general project structure.
    """

    return inspect_project(
        get_security()
    )

@mcp.tool()
def inspect_project_directory(
    path: str = ".",
    max_depth: int = 2,
) -> dict:
    """
    Inspect the structure of a directory in the project.

    Use this tool when the user asks about the contents
    or structure of a directory.

    Args:
        path: Relative directory path inside the workspace.
              Example: "tools", "core" or "mcp_server".
        max_depth: Maximum recursive depth to inspect.

    Returns:
        Files and subdirectories contained in the directory.
    """

    return inspect_directory(
        get_security(),
        path=path,
        max_depth=max_depth,
    )

@mcp.tool()
def read_project_file(file_path: str) -> dict:
    """
    Read a source file from the authorized workspace.

    Args:
        file_path: Relative path to the file.
                   Example: "tools/registry.py".
    """
    return read_source_file(
        get_security(),
        file_path,
    )


@mcp.tool()
def find_in_code(query: str) -> dict:
    """
    Search for text across source files in the project.
    """

    return search_code(
        get_security(),
        query,
    )


@mcp.tool()
def inspect_python_file(file_path: str) -> dict:
    """
    Analyze the structure of a Python source file.

    Args:
        file_path: Relative path to the Python file.
                   Example: "tools/registry.py".
    """
    return analyze_python(
        get_security(),
        file_path,
    )


@mcp.tool()
def execute_tests() -> dict:
    """
    Execute the project's pytest test suite.
    """

    return run_tests(
        get_security()
    )


@mcp.tool()
def repository_status() -> dict:
    """
    Return the current Git working-tree status.
    """

    return git_status(
        get_security()
    )


@mcp.tool()
def repository_diff() -> dict:
    """
    Return uncommitted Git changes.
    """

    return git_diff(
        get_security()
    )


def main():
    global security

    parser = argparse.ArgumentParser(
        description="Sensai Developer MCP Server"
    )

    parser.add_argument(
        "--workspace",
        required=True,
        help="Directory that MCP is allowed to inspect",
    )

    args = parser.parse_args()

    security = WorkspaceSecurity(
        args.workspace
    )

    mcp.run()


if __name__ == "__main__":
    main()