from exodus.domain.facts import (
    ClassDeclared,
    EndpointCalled,
    ImportFound,
    MessageConsumed,
    MessageDeclared,
    MessagePublished,
    ModuleDeclared,
    SourceFileDetected,
)
from exodus.infrastructure.parsing.csharp import csharp_extractor
from exodus.infrastructure.parsing.java import java_extractor
from exodus.infrastructure.parsing.url_literals import UrlLiteralExtractor
from tests.unit.infrastructure.helpers import extract

CSHARP = """using System;
using Alias = Acme.Core.Things;
using static System.Math;

namespace Acme.Web
{
    [ServiceContract(Namespace = "http://tempuri.org/")]
    public class HomePage : Page { }
    interface IThing { }
}
"""


def test_csharp_extractor_emits_modules_classes_and_imports_with_lines() -> None:
    facts = extract(csharp_extractor(), "s/Home.cs", CSHARP)
    assert isinstance(facts[0], SourceFileDetected)
    assert facts[0].language == "C#"
    summary = {
        (type(f).__name__, getattr(f, "name", getattr(f, "module", "")), f.evidence.line)
        for f in facts[1:]
    }
    assert summary == {
        ("ImportFound", "System", 1),
        ("ImportFound", "Acme.Core.Things", 2),
        ("ImportFound", "System.Math", 3),
        ("ModuleDeclared", "Acme.Web", 5),
        ("ClassDeclared", "HomePage", 8),
        ("ClassDeclared", "IThing", 9),
    }
    assert all(isinstance(f, ImportFound | ModuleDeclared | ClassDeclared) for f in facts[1:])


def test_csharp_file_scoped_namespace() -> None:
    facts = extract(csharp_extractor(), "s/X.cs", "namespace Acme.Jobs;\nclass Nightly {}\n")
    assert [f.name for f in facts if isinstance(f, ModuleDeclared)] == ["Acme.Jobs"]


JAVA = """package com.acme.orders.api;
import com.acme.orders.domain.Order;
import java.util.List;

public class OrderController {}
interface OrderService {}
enum Status { OPEN }
record OrderResponse(String id) {}
"""


def test_java_extractor_emits_packages_classes_and_imports_with_lines() -> None:
    facts = extract(java_extractor(), "s/OrderController.java", JAVA)
    assert isinstance(facts[0], SourceFileDetected)
    assert facts[0].language == "Java"
    summary = {
        (type(f).__name__, getattr(f, "name", getattr(f, "module", "")), f.evidence.line)
        for f in facts[1:]
    }
    assert summary == {
        ("ModuleDeclared", "com.acme.orders.api", 1),
        ("ImportFound", "com.acme.orders.domain.Order", 2),
        ("ImportFound", "java.util.List", 3),
        ("ClassDeclared", "OrderController", 5),
        ("ClassDeclared", "OrderService", 6),
        ("ClassDeclared", "Status", 7),
        ("ClassDeclared", "OrderResponse", 8),
    }


CONVEY = """namespace Orders.Application.Events.External
{
    [Message("deliveries")]
    public class DeliveryCompleted : IEvent { }

    [Message("orders")]
    public class ApproveOrder : Convey.CQRS.Commands.ICommand { }

    [Contract]
    public class OrderApproved : IEvent { }
}

public static class Extensions
{
    public static IApplicationBuilder UseApp(this IApplicationBuilder app)
    {
        app.UseRabbitMq()
            .SubscribeCommand<ApproveOrder>()
            .SubscribeEvent<Events.External.DeliveryCompleted>();
        return app;
    }
}
"""


def test_csharp_messages_routed_to_an_exchange_and_subscriptions() -> None:
    facts = extract(csharp_extractor(), "s/Messages.cs", CONVEY)
    declared = [(f.message, f.exchange, f.is_command, f.evidence.line) for f in facts
                if isinstance(f, MessageDeclared)]  # fmt: skip
    assert declared == [("DeliveryCompleted", "deliveries", False, 3),
                        ("ApproveOrder", "orders", True, 6)]  # fmt: skip
    consumed = [(f.message, f.exchange, f.evidence.line) for f in facts
                if isinstance(f, MessageConsumed)]  # fmt: skip
    assert consumed == [("ApproveOrder", None, 18), ("DeliveryCompleted", None, 19)]


BUS = """namespace Shop.Billing
{
    public class OrderSubmittedConsumer : IConsumer<Contracts.OrderSubmitted>
    {
        public async Task Consume(ConsumeContext<OrderSubmitted> context)
        {
            await context.Publish<InvoiceCreated>(new { Id = 1 });
            await _bus.Send(new ChargeCard(context.Message.Id));
        }
    }

    public class OrderPlacedHandler : IHandleMessages<OrderPlaced>
    {
        public Task Handle(OrderPlaced message, IMessageHandlerContext context)
            => context.Publish(new OrderBilled());
    }
}
"""


def test_csharp_masstransit_and_nservicebus_consumers_and_publishers() -> None:
    facts = extract(csharp_extractor(), "s/Bus.cs", BUS)
    consumed = [(f.message, f.evidence.line) for f in facts if isinstance(f, MessageConsumed)]
    assert consumed == [("OrderSubmitted", 3), ("OrderPlaced", 12)]
    published = [(f.message, f.evidence.line) for f in facts if isinstance(f, MessagePublished)]
    assert published == [("InvoiceCreated", 7), ("ChargeCard", 8), ("OrderBilled", 15)]


def test_url_literals_skip_xml_namespaces_and_keep_line() -> None:
    text = 'var a = "http://tempuri.org/";\n\nvar b = "https://api.acme.com/v1/items?x=1";\n// see http://www.w3.org/x\n'
    [call] = extract(UrlLiteralExtractor((".cs",)), "s/X.cs", text)
    assert isinstance(call, EndpointCalled)
    assert (call.url, call.protocol, call.evidence.line) == (
        "https://api.acme.com/v1/items?x=1",
        "HTTPS",
        3,
    )
    assert not UrlLiteralExtractor((".cs",)).matches(__import__("pathlib").PurePosixPath("a.md"))
