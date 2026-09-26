"""Tree-sitter facts for Java source files."""

from exodus.infrastructure.parsing.tree_sitter_extractor import TreeSitterExtractor

JAVA_QUERIES = """
(package_declaration (scoped_identifier) @module)
(import_declaration (scoped_identifier) @import)
(class_declaration name: (identifier) @class)
(interface_declaration name: (identifier) @class)
(enum_declaration name: (identifier) @class)
(record_declaration name: (identifier) @class)
"""


def java_extractor() -> TreeSitterExtractor:
    return TreeSitterExtractor("Java", "java", (".java",), JAVA_QUERIES)
