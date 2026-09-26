from exodus.domain.facts import DocumentSection
from exodus.infrastructure.parsing.documents import DocumentExtractor
from tests.unit.infrastructure.helpers import extract

MARKDOWN = """# Billing

Billing issues the invoices of every order.

It runs every night.

## Glossary

NF-e: electronic invoice.
"""


def sections(path: str, text: str) -> list[tuple[str, str, int]]:
    facts = extract(DocumentExtractor(), path, text)
    assert all(isinstance(f, DocumentSection) for f in facts)
    return [(f.title, f.text, f.evidence.line) for f in facts if isinstance(f, DocumentSection)]


def test_markdown_is_split_by_heading_with_the_line_where_each_piece_starts() -> None:
    assert sections("b/docs/overview.md", MARKDOWN) == [
        ("Billing", "Billing issues the invoices of every order.\n\nIt runs every night.", 3),
        ("Glossary", "NF-e: electronic invoice.", 9),
    ]


def test_long_sections_are_cut_between_paragraphs() -> None:
    paragraph = "word " * 100  # 500 characters
    text = f"# Long\n\n{paragraph}\n\n{paragraph}\n\n{paragraph}\n"
    pieces = sections("b/README.md", text)
    assert [line for _, _, line in pieces] == [3, 5, 7]
    assert all(len(body) <= 800 for _, body, _ in pieces)


def test_underlined_headings_split_sections_too() -> None:
    text = (
        "**What is Pacco?**\n----------------\n\nPacco delivers parcels with limited resources.\n\n"
        "**What is Pricing?**\n================\n\nPricing computes the price of every order.\n"
    )
    assert sections("p/README.md", text) == [
        ("What is Pacco?", "Pacco delivers parcels with limited resources.", 4),
        ("What is Pricing?", "Pricing computes the price of every order.", 9),
    ]


def test_documentation_does_not_send_credential_lines_to_the_vector_store() -> None:
    text = (
        "# Setup\n\nThe service runs in the private network.\n"
        "DB_PASSWORD=audit-canary-123\n"
        "Production password: audit-canary-456 is stored here.\n"
    )
    pieces = sections("p/README.md", text)
    assert len(pieces) == 1
    assert pieces[0][1] == ("The service runs in the private network.\n[REDACTED]\n[REDACTED]")
