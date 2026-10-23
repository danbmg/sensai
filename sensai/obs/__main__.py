"""Résumé des métriques en terminal : python -m sensai.obs [--days 7] [--json]."""
import argparse
import json
from pathlib import Path

from sensai.core.config import ConfigError
from sensai.obs.metrics import load_entries, render, summarize
from sensai.obs.settings import load_log_settings


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m sensai.obs", description=__doc__)
    parser.add_argument("--config", help="fichier de configuration (défaut : config.toml du projet)")
    parser.add_argument("--dir", type=Path, help="dossier des logs (défaut : [logging] directory)")
    parser.add_argument("--days", type=int, help="limiter aux N derniers jours")
    parser.add_argument("--json", action="store_true", help="sortie JSON brute")
    args = parser.parse_args(argv)
    try:
        directory = args.dir or Path(load_log_settings(args.config).directory)
    except ConfigError as error:
        parser.exit(1, f"{error}\n")
    entries, skipped = load_entries(directory, args.days)
    summary = summarize(entries)
    print(json.dumps(summary, ensure_ascii=False, indent=2) if args.json else render(summary, skipped))


if __name__ == "__main__":
    main()
