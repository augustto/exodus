import pytest

from exodus.domain.identity import (
    DataStoreRef,
    QueueRef,
    datastore_ref,
    endpoint_matches,
    engine_family,
    engine_from_provider,
    queue_ref,
    url_host,
    url_protocol,
)


@pytest.mark.parametrize(
    ("raw", "hint", "expected"),
    [
        ("Data Source=DBSRV01;Initial Catalog=ERP", None, ("sqlserver", "dbsrv01", "erp")),
        ("jdbc:sqlserver://dbsrv01:1433;databaseName=ERP", None, ("sqlserver", "dbsrv01", "erp")),
        ("mssql+pyodbc://app:secret@dbsrv01/ERP", None, ("sqlserver", "dbsrv01", "erp")),
        (
            "mongodb+srv://app:secret@cluster0.example.net/Shop",
            None,
            ("mongodb", "cluster0.example.net", "shop"),
        ),
        ("redis://cache01:6379/orders", None, ("redis", "cache01", "orders")),
        ("jdbc:mysql://mysql01:3306/portal", None, ("mysql", "mysql01", "portal")),
        ("jdbc:oracle:thin:@ora01:1521:ORCL", None, ("oracle", "ora01", "orcl")),
        ("sqlite:///data/app.db", None, ("sqlite", "localhost", "app.db")),
        ("Server=x;Database=y", None, ("unknown", "x", "y")),
        ("Server=x;Database=y", "postgresql", ("postgresql", "x", "y")),
    ],
)
def test_datastore_ref_normalizes_supported_forms(
    raw: str, hint: str | None, expected: tuple[str, str, str]
) -> None:
    assert datastore_ref(raw, hint) == DataStoreRef(
        engine=expected[0], host=expected[1], database=expected[2]
    )


@pytest.mark.parametrize("raw", ["", "just text", "https://example.com/x"])
def test_datastore_ref_ignores_non_database_values(raw: str) -> None:
    assert datastore_ref(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (".\\private$\\invoices", QueueRef(technology="msmq", name="invoices")),
        ("jms/OrdersQueue", QueueRef(technology="jms", name="OrdersQueue")),
        ("amqp://rabbit01/orders", QueueRef(technology="amqp", name="orders")),
        ("plain", None),
    ],
)
def test_queue_ref_recognizes_supported_queues(raw: str, expected: QueueRef | None) -> None:
    assert queue_ref(raw) == expected


@pytest.mark.parametrize(
    ("called", "exposed", "expected"),
    [
        ("http://billing/BillingService.svc/Invoices", "/billingservice.svc", True),
        ("http://orders/api/orders/42", "/api/orders/*", True),
        ("http://orders/api/customers", "/api/orders/*", False),
        ("http://orders/api", "/api/orders", False),
    ],
)
def test_endpoint_matching_respects_paths(called: str, exposed: str, expected: bool) -> None:
    assert endpoint_matches(called, exposed) is expected


def test_identity_helpers_keep_public_host_and_engine_family() -> None:
    assert url_host("http://user:secret@Billing.Intranet:8080/x") == "billing.intranet"
    assert url_protocol("https://api.example.com/v1") == "HTTPS"
    assert url_protocol("net.tcp://h:808/Billing") == "WCF net.tcp"
    assert engine_from_provider("System.Data.SqlClient") == "sqlserver"
    assert engine_family("mongodb") == "document"
    assert engine_family("redis") == "cache"
