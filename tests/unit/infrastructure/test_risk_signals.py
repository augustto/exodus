from pathlib import PurePosixPath

from exodus.application.ports import SourceFile
from exodus.application.use_cases.build_graph import build_graph
from exodus.application.use_cases.scan_projects import ProjectScan
from exodus.domain.facts import SecretFound, TechnologyUsed
from exodus.infrastructure.config.risk_signals import RiskSignalExtractor


def test_extracts_legacy_technologies_and_configuration_secrets() -> None:
    file = SourceFile(
        PurePosixPath("billing/Web.config"),
        """<configuration>
  <system.serviceModel />
  <add key=\"ApiKey\" value=\"not-a-placeholder\" />
  <add key=\"Password\" value=\"hunter2\" />
</configuration>""",
    )

    facts = list(RiskSignalExtractor().extract(file))

    assert facts == [
        TechnologyUsed(name="WCF", evidence=file.evidence(2)),
        SecretFound(name="ApiKey", evidence=file.evidence(3)),
        SecretFound(name="Password", evidence=file.evidence(4)),
    ]
    assert (
        "hunter2"
        not in build_graph([ProjectScan("billing", tuple(facts))]).to_document().model_dump_json()
    )


def test_ignores_secret_placeholders_and_detects_source_technologies() -> None:
    file = SourceFile(
        PurePosixPath("billing/Legacy.cs"),
        """var token = Environment.GetEnvironmentVariable(\"TOKEN\");
[OperationContract]
public void Send() {}
""",
    )

    facts = list(RiskSignalExtractor().extract(file))

    assert facts == [TechnologyUsed(name="WCF", evidence=file.evidence(2))]


def test_secret_signals_use_the_full_configuration_key() -> None:
    file = SourceFile(
        PurePosixPath("billing/settings.yml"),
        'DB_PASSWORD=audit-canary-123\n"jwtToken": "audit-canary-456"\n',
    )
    assert list(RiskSignalExtractor().extract(file)) == [
        SecretFound(name="DB_PASSWORD", evidence=file.evidence(1)),
        SecretFound(name="jwtToken", evidence=file.evidence(2)),
    ]


def test_grpc_service_host_is_not_wcf() -> None:
    grpc = SourceFile(
        PurePosixPath("ops/GrpcServiceHost.cs"),
        "public class GrpcServiceHost : GrpcOperationsService.GrpcOperationsServiceBase {}",
    )
    svc = SourceFile(PurePosixPath("shop/Orders.svc"), '<%@ ServiceHost Service="Orders" %>')

    assert list(RiskSignalExtractor().extract(grpc)) == []
    assert list(RiskSignalExtractor().extract(svc)) == [
        TechnologyUsed(name="WCF", evidence=svc.evidence(1))
    ]
