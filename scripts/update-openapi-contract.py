from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
OUTPUT = ROOT / "docs" / "openapi-v1.json"

sys.path.insert(0, str(SERVER))

from app.main import app  # noqa: E402


def main() -> int:
    contract = app.openapi()
    OUTPUT.write_text(
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Updated {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
