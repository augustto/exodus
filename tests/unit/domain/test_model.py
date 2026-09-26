import pytest
from pydantic import ValidationError

from exodus.domain.model import (
    Evidence,
    Node,
    NodeKind,
    Relationship,
    RelKind,
    merge_evidence,
)

EV = Evidence(file="app/web.config", line=3, snippet="<add .../>")


def test_node_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        Node(id="system:a", kind=NodeKind.SYSTEM, name="a", evidence=())


def test_relationship_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        Relationship(source_id="a", target_id="b", kind=RelKind.CALLS, label="calls", evidence=())


def test_merge_evidence_dedupes_keeping_order() -> None:
    other = Evidence(file="x.cs", line=1, snippet="x")
    assert merge_evidence((EV, other), (other, EV)) == (EV, other)
