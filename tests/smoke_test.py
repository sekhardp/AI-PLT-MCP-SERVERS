import pytest
from sgs_bq_server.main import startup_smoke_check, _health_payload


def test_smoke_check() -> None:
    startup_smoke_check()
    payload = _health_payload()
    assert payload["service"] == "sgs-bq-server"
    assert payload["status"] == "ok"


if __name__ == "__main__":
    test_smoke_check()
    print("smoke-test-ok")
