import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


def main() -> None:
    server.startup_smoke_check()
    payload = server._health_payload()
    assert payload["service"] == "suntory-gcp-productivity-bqclient-mcp"
    assert payload["status"] == "ok"
    print("smoke-test-ok")


if __name__ == "__main__":
    main()
