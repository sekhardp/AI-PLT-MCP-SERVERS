import pytest
from sales_products_server.main import get_dataset_metadata


def test_smoke_check() -> None:
    meta = get_dataset_metadata()
    assert meta["dataset_id"] == "sales_products"
    assert len(meta["tables"]) == 5


if __name__ == "__main__":
    test_smoke_check()
    print("smoke-test-ok")
