"""Markdown → HTML for the subset the Exodus renderers write (headings, paragraphs, tables,
lists with one nesting level, blockquotes, bold, italics, code spans and links). Not a general
Markdown parser: it only has to read the documents generated here."""

import html
import re

_INLINE = [
    (re.compile(r"`([^`]+)`"), r"<code>\1</code>"),
    (re.compile(r"\*\*([^*]+)\*\*"), r"<strong>\1</strong>"),
    (re.compile(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])"), r"<em>\1</em>"),
    (re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)"), r'<a href="\2">\1</a>'),
]


def inline(text: str) -> str:
    """Inline markup of one line; code spans are kept literal."""
    pieces = re.split(r"(`[^`]+`)", html.escape(text, quote=True))
    out = []
    for piece in pieces:
        if piece.startswith("`") and piece.endswith("`") and len(piece) > 1:
            out.append(f"<code>{piece[1:-1]}</code>")
            continue
        for pattern, replacement in _INLINE[1:]:
            piece = pattern.sub(replacement, piece)
        out.append(piece)
    return "".join(out)


def to_html(markdown: str, shift: int = 0) -> str:
    """HTML of a document; headings go `shift` levels down (to nest it in a report)."""
    out: list[str] = []
    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif heading := re.match(r"^(#{1,6})\s+(.*)$", line):
            level = min(6, len(heading.group(1)) + shift)
            out.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
            i += 1
        elif line.startswith("|"):
            i = _table(lines, i, out)
        elif line.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i].lstrip("> ").rstrip())
                i += 1
            out.append(f"<blockquote>{inline(' '.join(quote))}</blockquote>")
        elif _item(line):
            i = _list(lines, i, out)
        else:
            paragraph = []
            while i < len(lines) and lines[i].strip() and not _block_start(lines[i]):
                paragraph.append(lines[i].strip())
                i += 1
            out.append(f"<p>{inline(' '.join(paragraph))}</p>")
    return "\n".join(out)


def _block_start(line: str) -> bool:
    return line.startswith(("#", "|", ">")) or _item(line) is not None


def _item(line: str) -> re.Match[str] | None:
    return re.match(r"^(\s*)(-|\d+\.)\s+(.*)$", line)


def _list(lines: list[str], i: int, out: list[str]) -> int:
    first = _item(lines[i])
    assert first is not None
    tag = "ol" if first.group(2)[0].isdigit() else "ul"
    out.append(f"<{tag}>")
    open_item = False
    nested = False
    while i < len(lines) and (item := _item(lines[i])):
        if item.group(1):  # indented: one nesting level
            if not nested:
                out.append("<ul>")
                nested = True
            out.append(f"<li>{inline(item.group(3))}</li>")
        else:
            if nested:
                out.append("</ul>")
                nested = False
            if open_item:
                out.append("</li>")
            out.append(f"<li>{inline(item.group(3))}")
            open_item = True
        i += 1
    if nested:
        out.append("</ul>")
    if open_item:
        out.append("</li>")
    out.append(f"</{tag}>")
    return i


def _table(lines: list[str], i: int, out: list[str]) -> int:
    rows = []
    while i < len(lines) and lines[i].startswith("|"):
        if not re.fullmatch(r"\|(\s*:?-+:?\s*\|)+", lines[i].strip()):  # not the separator
            rows.append([cell.strip() for cell in lines[i].strip().strip("|").split(" | ")])
        i += 1
    body = rows[1:]
    out.append("<table><thead><tr>")
    out.extend(f"<th>{inline(cell)}</th>" for cell in rows[0])
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append("<tr>" + "".join(f"<td>{inline(cell)}</td>" for cell in row) + "</tr>")
    out.append("</tbody></table>")
    return i
