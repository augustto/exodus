from exodus.domain.facts import DataObjectUsed
from exodus.infrastructure.parsing.data_access import DataAccessExtractor
from tests.unit.infrastructure.helpers import extract

EXTRACTOR = DataAccessExtractor((".cs", ".java", ".py"))


def found(path: str, text: str) -> list[tuple[str, str, int]]:
    facts = extract(EXTRACTOR, path, text)
    assert all(isinstance(f, DataObjectUsed) for f in facts)
    return [(f.kind, f.name, f.evidence.line) for f in facts if isinstance(f, DataObjectUsed)]


def test_sql_in_string_literals_gives_tables_and_procedures() -> None:
    source = """class InvoiceRepository {
    // select the invoices from the ERP (a comment, not SQL)
    const string Open = "SELECT i.Id FROM [dbo].[Invoices] i JOIN Customers c ON c.Id = i.C";
    void Save() => Run(@"INSERT INTO dbo.Invoices (Id) VALUES (@id)");
    void Close() => Run("UPDATE Invoices SET Closed = 1; DELETE FROM InvoiceLocks");
    void Proc() => Run("EXEC usp_CloseInvoice @id");
    string Text = "Pick one from the list";
}
"""
    assert found("s/InvoiceRepository.cs", source) == [
        ("table", "dbo.Invoices", 3),
        ("table", "Customers", 3),
        ("table", "dbo.Invoices", 4),
        ("table", "Invoices", 5),
        ("table", "InvoiceLocks", 5),
        ("procedure", "usp_CloseInvoice", 6),
    ]


def test_sql_in_java_and_python_strings() -> None:
    assert found("s/Dao.java", 'jdbc.query("select * from orders where id = ?");') == [
        ("table", "orders", 1)
    ]
    assert found("s/dao.py", "cur.execute('''\n  CALL close_order(%s)\n''')") == [
        ("procedure", "close_order", 2)
    ]


def test_sql_script_reads_the_whole_file_including_create() -> None:
    script = """CREATE TABLE dbo.Invoices (Id INT);
GO
CREATE OR ALTER PROCEDURE [dbo].[usp_CloseInvoice] AS
    UPDATE dbo.Invoices SET Closed = 1
"""
    facts = extract(DataAccessExtractor((".cs",)), "s/db/schema.sql", script)
    assert [(f.kind, f.name, f.evidence.line) for f in facts if isinstance(f, DataObjectUsed)] == [
        ("table", "dbo.Invoices", 1),
        ("procedure", "dbo.usp_CloseInvoice", 3),
        ("table", "dbo.Invoices", 4),
    ]


def test_mongo_collections_from_shell_and_drivers() -> None:
    source = """var orders = database.GetCollection<Order>("orders");
db.customers.find({})
MongoCollection<Document> c = db.getCollection("parcels");
const vehicles = client.db("x").collection('vehicles');
"""
    assert found("s/Mongo.cs", source) == [
        ("collection", "orders", 1),
        ("collection", "customers", 2),
        ("collection", "parcels", 3),
        ("collection", "vehicles", 4),
    ]
