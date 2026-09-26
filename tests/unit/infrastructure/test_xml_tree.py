from exodus.infrastructure.config.xml_tree import parse_xml


def test_keeps_line_numbers_and_strips_namespaces() -> None:
    root = parse_xml(
        '<?xml version="1.0" encoding="utf-16"?>\n'
        '<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">\n'
        "  <PropertyGroup>\n"
        "    <TargetFrameworkVersion>v4.0</TargetFrameworkVersion>\n"
        "  </PropertyGroup>\n"
        "</Project>\n"
    )
    assert root is not None
    assert root.tag == "Project"
    [framework] = root.iter("TargetFrameworkVersion")
    assert (framework.line, framework.text) == (4, "v4.0")
    assert root.find_all("PropertyGroup/TargetFrameworkVersion") == [framework]
    assert root.children[0].child_text("TargetFrameworkVersion") == "v4.0"
    assert root.child_text("Missing") is None


def test_bom_is_ignored_and_malformed_returns_none() -> None:
    assert parse_xml("﻿<a/>") is not None
    assert parse_xml("<a><b></a>") is None
    assert parse_xml("") is None
    assert parse_xml('<!DOCTYPE a [<!ENTITY x "expanded">]><a>&x;</a>') is None
