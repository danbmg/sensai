"""Profils médecins persistants. Gestion : python -m sensai.memory.profiles --help."""
import argparse
from dataclasses import asdict, dataclass, field
import json
import sqlite3
from pathlib import Path

from sensai.memory.database import SQLiteDatabase


@dataclass
class DoctorProfile:
    profile_id: str = "default"
    specialty: str = ""
    preferences: list[str] = field(default_factory=list)
    instructions: str = ""


class ProfileNotFoundError(LookupError):
    pass


class DoctorProfileStore(SQLiteDatabase):
    def __init__(self, path: str | Path):
        super().__init__(path)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS doctor_profiles (
                profile_id TEXT PRIMARY KEY, specialty TEXT NOT NULL,
                preferences TEXT NOT NULL, instructions TEXT NOT NULL)""")

    def save(self, profile: DoctorProfile) -> None:
        for key in ("profile_id", "specialty", "instructions"):
            if not isinstance(getattr(profile, key), str):
                raise ValueError(f"{key} doit être du texte.")
        if not profile.profile_id.strip():
            raise ValueError("L'identifiant du profil est obligatoire.")
        if not isinstance(profile.preferences, list) or any(
            not isinstance(value, str) or not value.strip() for value in profile.preferences
        ):
            raise ValueError("Les préférences doivent être une liste de textes non vides.")
        with self.connect() as db:
            db.execute("""INSERT INTO doctor_profiles VALUES (?, ?, ?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET specialty=excluded.specialty,
                preferences=excluded.preferences, instructions=excluded.instructions""",
                       (profile.profile_id, profile.specialty,
                        json.dumps(profile.preferences, ensure_ascii=False), profile.instructions))

    def load(self, profile_id: str) -> DoctorProfile:
        with self.connect() as db:
            row = db.execute("SELECT * FROM doctor_profiles WHERE profile_id=?", (profile_id,)).fetchone()
        if row is None:
            raise ProfileNotFoundError(f"Profil médecin introuvable : {profile_id}")
        return DoctorProfile(row["profile_id"], row["specialty"], json.loads(row["preferences"]), row["instructions"])

    def list_profiles(self) -> list[str]:
        with self.connect() as db:
            return [row[0] for row in db.execute("SELECT profile_id FROM doctor_profiles ORDER BY profile_id")]

    def ensure_default(self) -> DoctorProfile:
        try:
            return self.load("default")
        except ProfileNotFoundError:
            profile = DoctorProfile()
            self.save(profile)
            return profile


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path(".sensai/memory.sqlite3"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    show = commands.add_parser("show")
    show.add_argument("profile_id")
    save = commands.add_parser("set")
    save.add_argument("profile_id")
    save.add_argument("--specialty", default="")
    save.add_argument("--preference", action="append", default=[])
    save.add_argument("--instructions", default="")
    args = parser.parse_args(argv)
    try:
        store = DoctorProfileStore(args.db)
        if args.command == "list":
            print("\n".join(store.list_profiles()) or "Aucun profil enregistré.")
        else:
            if args.command == "set":
                store.save(DoctorProfile(args.profile_id, args.specialty, args.preference, args.instructions))
            print(json.dumps(asdict(store.load(args.profile_id)), ensure_ascii=False, indent=2))
    except (OSError, ValueError, LookupError, sqlite3.Error) as error:
        parser.exit(1, f"Profil : {error}\n")


if __name__ == "__main__":
    main()
