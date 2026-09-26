from exodus.infrastructure.parsing.tree_sitter_extractor import TreeSitterExtractor

# namespaces, types and usings; messages routed by Convey ([Message("exchange")] on a message
# class); messages consumed (Convey SubscribeEvent<T>/SubscribeCommand<T>, MassTransit
# IConsumer<T>, NServiceBus IHandleMessages<T>) and published/sent by type (Publish/Send, generic
# or with a new message)

CSHARP_QUERIES = """
(namespace_declaration name: (_) @module)
(file_scoped_namespace_declaration name: (_) @module)
(using_directive (qualified_name) @import)
(using_directive !name (identifier) @import)
(class_declaration name: (identifier) @class)
(interface_declaration name: (identifier) @class)
((class_declaration
   (attribute_list (attribute
     name: (identifier) @_attribute
     (attribute_argument_list
       (attribute_argument (string_literal (string_literal_content) @exchange)))))
   name: (identifier) @message
   (base_list (_) @base)?)
 (#eq? @_attribute "Message"))
((invocation_expression
   function: (member_access_expression
     name: (generic_name (identifier) @_method (type_argument_list (_) @consumes))))
 (#match? @_method "^Subscribe(Event|Command)$"))
((class_declaration
   (base_list (generic_name (identifier) @_interface (type_argument_list (_) @consumes))))
 (#match? @_interface "^(IConsumer|IHandleMessages)$"))
((invocation_expression
   function: (member_access_expression
     name: (generic_name (identifier) @_method (type_argument_list (_) @publishes))))
 (#match? @_method "^(Publish|Send)(Async)?$"))
((invocation_expression
   function: (member_access_expression name: (identifier) @_method)
   arguments: (argument_list . (argument (object_creation_expression type: (_) @publishes))))
 (#match? @_method "^(Publish|Send)(Async)?$"))
"""


def csharp_extractor() -> TreeSitterExtractor:
    return TreeSitterExtractor("C#", "csharp", (".cs",), CSHARP_QUERIES)
