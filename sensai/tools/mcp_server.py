"""Serveur MCP médical stdio, connecté à la base patients locale."""
import argparse
import json
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from sensai.memory.patients import PatientStore
from sensai.tools.patient_tools import register_patient_tools
from sensai.tools.registry import ToolRegistry

Field = Literal["allergies", "treatments", "medical_history"]


def create_server(db_path: str) -> MCPServer:
    # Les outils MCP délèguent au même registre que le mode local : mêmes validations.
    registry = ToolRegistry()
    register_patient_tools(registry, PatientStore(db_path))
    server = MCPServer("sensai-medical", log_level="WARNING")

    def run(tool_name: str, **args) -> dict:
        result = registry.call(tool_name, args)
        if result.is_error:
            raise ToolError(result.content)
        return json.loads(result.content)

    @server.tool()
    def create_patient(name: str, birth_date: str = "") -> dict:
        """Crée un patient ; le client doit obtenir la confirmation du médecin. Date AAAA-MM-JJ facultative."""
        return run("create_patient", name=name, birth_date=birth_date)

    @server.tool()
    def delete_patient(patient: str) -> dict:
        """Supprime définitivement le dossier sans ambiguïté ; confirmation du médecin requise."""
        return run("delete_patient", patient=patient)

    @server.tool()
    def get_patient(patient: str) -> dict:
        """Consulte un dossier patient local par nom complet ou identifiant."""
        return run("get_patient", patient=patient)

    @server.tool()
    def find_patients(query: str) -> dict:
        """Cherche les patients dont le nom contient le texte donné (nom et identifiant)."""
        return run("find_patients", query=query)

    @server.tool()
    def add_patient_note(patient: str, note: str) -> dict:
        """Ajoute une note textuelle ; le client doit obtenir la confirmation du médecin."""
        return run("add_patient_note", patient=patient, note=note)

    @server.tool()
    def add_patient_entry(patient: str, field: Field, value: str) -> dict:
        """Ajoute une allergie, un traitement ou un antécédent ; confirmation du médecin requise."""
        return run("add_patient_entry", patient=patient, field=field, value=value)

    @server.tool()
    def remove_patient_entry(patient: str, field: Field, value: str) -> dict:
        """Retire une allergie, un traitement ou un antécédent ; confirmation du médecin requise."""
        return run("remove_patient_entry", patient=patient, field=field, value=value)

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    create_server(args.db).run()


if __name__ == "__main__":
    main()
