"""Serveur MCP médical stdio, connecté à la base patients locale."""
import argparse
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from sensai.memory.patients import PatientStore
from sensai.tools.patient_tools import register_patient_tools
from sensai.tools.registry import ToolRegistry


def create_server(db_path: str) -> MCPServer:
    patients = PatientStore(db_path)
    registry = ToolRegistry()
    register_patient_tools(registry, patients)
    server = MCPServer("sensai-medical", log_level="WARNING")

    @server.tool()
    def get_patient(patient: str) -> dict:
        """Consulte un dossier patient local par nom complet ou identifiant."""
        try:
            return patients.resolve_patient(patient)
        except (LookupError, ValueError) as error:
            raise ToolError(f"Patient introuvable ou ambigu : {error}") from error

    @server.tool()
    def add_patient_note(patient: str, note: str) -> dict:
        """Ajoute une note textuelle ; le client doit obtenir la confirmation du médecin."""
        result = registry.call("add_patient_note", {"patient": patient, "note": note})
        if result.is_error:
            raise ToolError(result.content)
        import json
        return json.loads(result.content)

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    create_server(args.db).run()


if __name__ == "__main__":
    main()
