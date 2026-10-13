
"""Serveur MCP local de SENSAI pour les outils développeur.

Ces outils sont destinés au développement et au diagnostic.
Ils ne doivent pas être exposés automatiquement à un assistant médical.
"""

import argparse

from mcp.server.mcpserver import MCPServer

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

security: WorkspaceSecurity | None = None


def get_security() -> WorkspaceSecurity:
    if security is None:
        raise RuntimeError(
            "Workspace security is not initialized."
        )
    return security


@mcp.tool()
def project_overview() -> dict:
    """Return an overview of the authorized project."""
    return inspect_project(get_security())


@mcp.tool()
def inspect_project_directory(
    path: str = ".",
    max_depth: int = 2,
) -> dict:
    """Inspect directories within the authorized workspace."""
    return inspect_directory(
        get_security(),
        path=path,
        max_depth=max_depth,
    )


@mcp.tool()
def read_project_file(file_path: str) -> dict:
    """Read a file within the authorized workspace."""
    return read_source_file(
        get_security(),
        file_path,
    )


@mcp.tool()
def find_in_code(query: str) -> dict:
    """Search for text in project source files."""
    return search_code(
        get_security(),
        query,
    )


@mcp.tool()
def inspect_python_file(file_path: str) -> dict:
    """Analyze a Python source file using AST."""
    return analyze_python(
        get_security(),
        file_path,
    )


@mcp.tool()
def execute_tests() -> dict:
    """Run project tests in a trusted development workspace."""
    return run_tests(get_security())


@mcp.tool()
def repository_status() -> dict:
    """Return the Git working-tree status."""
    return git_status(get_security())


@mcp.tool()
def repository_diff() -> dict:
    """Return uncommitted Git changes."""
    return git_diff(get_security())


def main() -> None:
    global security

    parser = argparse.ArgumentParser(
        description="Sensai Developer MCP Server"
    )
    parser.add_argument(
        "--workspace",
        required=True,
        help="Authorized project directory",
    )
    args = parser.parse_args()

    security = WorkspaceSecurity(args.workspace)

    mcp.run()


if __name__ == "__main__":
    main()