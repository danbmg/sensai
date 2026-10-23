"""Lance l'interface web : python -m sensai.web [--demo] [--mcp] [--port 8000]."""
import argparse
import sys

import uvicorn

from sensai.app.runtime import RuntimeOptions, Settings, StartupError, Stores, add_runtime_arguments
from sensai.core.config import ConfigError
from sensai.web.api import create_app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m sensai.web", description=__doc__)
    add_runtime_arguments(parser)
    parser.add_argument("--host", default="127.0.0.1", help="adresse d'écoute (défaut : locale uniquement)")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    options = RuntimeOptions.from_args(args)
    # Vérifié avant de démarrer le serveur : un message clair plutôt qu'une trace d'uvicorn.
    try:
        Settings.load(options)
        Stores.open(options.db, options.demo)
    except (ConfigError, StartupError) as error:
        sys.exit(f"Sensai indisponible : {error}")
    print(f"Sensai web : http://{args.host}:{args.port}", flush=True)
    uvicorn.run(create_app(options), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
