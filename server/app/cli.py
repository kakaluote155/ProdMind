from __future__ import annotations

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ProdMind API server.")
    parser.add_argument("--host", default=os.getenv("PRODMIND_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PRODMIND_API_PORT", "8088")),
    )
    parser.add_argument("--log-level", default=os.getenv("PRODMIND_LOG_LEVEL", "info"))
    args = parser.parse_args()
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level.lower(),
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
