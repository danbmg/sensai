from pathlib import Path


class WorkspaceSecurityError(Exception):
    pass


class WorkspaceSecurity:
    """
    Restricts filesystem operations to one workspace.

    Sensitive files and directories are denied even if
    they are located inside the workspace.
    """

    BLOCKED_FILES = {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        "id_rsa",
        "id_ed25519",
        "credentials.json",
        "secrets.json",
    }

    BLOCKED_SUFFIXES = {
        ".pem",
        ".key",
        ".p12",
        ".pfx",
    }

    BLOCKED_DIRECTORIES = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
    }

    def __init__(self, workspace: str):
        self.workspace = Path(workspace).resolve()

        if not self.workspace.exists():
            raise WorkspaceSecurityError(
                f"Workspace does not exist: {self.workspace}"
            )

        if not self.workspace.is_dir():
            raise WorkspaceSecurityError(
                "Workspace must be a directory."
            )

    def resolve(self, user_path: str) -> Path:
        """
        Resolve a user path and verify that it stays inside
        the authorized workspace.
        """

        requested = (
            self.workspace / user_path
        ).resolve()

        try:
            requested.relative_to(self.workspace)
        except ValueError:
            raise WorkspaceSecurityError(
                "Access denied: path is outside the workspace."
            )

        relative = requested.relative_to(self.workspace)

        for part in relative.parts:
            if part in self.BLOCKED_DIRECTORIES:
                raise WorkspaceSecurityError(
                    f"Access denied to directory: {part}"
                )

        if requested.name in self.BLOCKED_FILES:
            raise WorkspaceSecurityError(
                f"Access denied to sensitive file: {requested.name}"
            )

        if requested.suffix.lower() in self.BLOCKED_SUFFIXES:
            raise WorkspaceSecurityError(
                f"Access denied to sensitive file type: "
                f"{requested.suffix}"
            )

        return requested

    def require_file(self, user_path: str) -> Path:
        path = self.resolve(user_path)

        if not path.exists():
            raise WorkspaceSecurityError(
                f"File does not exist: {user_path}"
            )

        if not path.is_file():
            raise WorkspaceSecurityError(
                f"Not a file: {user_path}"
            )

        return path