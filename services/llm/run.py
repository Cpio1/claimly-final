"""Start only the internal LLM API; no backend, database or worker is started."""
import argparse
from pathlib import Path

from services.llm.envfile import load


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=Path(__file__).with_name('.env'))
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8001)
    args = parser.parse_args()
    load(args.env_file)
    import uvicorn
    uvicorn.run('services.llm.app.main:app', host=args.host, port=args.port, access_log=False)


if __name__ == '__main__':
    main()
