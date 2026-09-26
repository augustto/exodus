from exodus.infrastructure.rendering.markdown_html import inline, to_html


def test_inline_markup_and_escaping() -> None:
    assert inline("**Web** uses `a<b>` and *inferred* [AWS](https://aws.amazon.com)") == (
        "<strong>Web</strong> uses <code>a&lt;b&gt;</code> and <em>inferred</em> "
        '<a href="https://aws.amazon.com">AWS</a>'
    )
    assert inline("`**not bold**`") == "<code>**not bold**</code>"


def test_markdown_link_cannot_inject_an_html_attribute() -> None:
    rendered = inline('[view](https://safe.example/"onmouseover="alert(1))')
    assert 'onmouseover="' not in rendered
    assert "&quot;onmouseover=&quot;" in rendered


def test_blocks_generated_by_exodus() -> None:
    markdown = """# Title

> A quoted
> note.

Some text
on two lines.

| Name | Engine |
|---|---|
| erp | SQL Server |

- one
  - nested
- two

1. first
2. second
"""
    assert to_html(markdown, shift=1).split("\n") == [
        "<h2>Title</h2>",
        "<blockquote>A quoted note.</blockquote>",
        "<p>Some text on two lines.</p>",
        "<table><thead><tr>",
        "<th>Name</th>",
        "<th>Engine</th>",
        "</tr></thead><tbody>",
        "<tr><td>erp</td><td>SQL Server</td></tr>",
        "</tbody></table>",
        "<ul>",
        "<li>one",
        "<ul>",
        "<li>nested</li>",
        "</ul>",
        "</li>",
        "<li>two",
        "</li>",
        "</ul>",
        "<ol>",
        "<li>first",
        "</li>",
        "<li>second",
        "</li>",
        "</ol>",
    ]
