import pytest

from pdbe_mcp_server.structure_sources import (
    allowed_coordinate_origins,
    app_connect_domains,
    validate_coordinate_url,
)


def test_builtin_coordinate_origins_include_pdbe_and_alphafold():
    assert "https://www.ebi.ac.uk" in allowed_coordinate_origins()
    assert "https://alphafold.ebi.ac.uk" in allowed_coordinate_origins()
    assert validate_coordinate_url(
        "https://alphafold.ebi.ac.uk/files/model.bcif"
    ).endswith("model.bcif")


def test_custom_coordinate_origins_are_exact_and_used_in_app_csp(monkeypatch):
    monkeypatch.setenv(
        "PDBe_MCP_STRUCTURE_ORIGINS",
        "https://models.example.org, https://coordinates.example.net",
    )
    url = "https://models.example.org/path/model.cif"
    assert validate_coordinate_url(url) == url
    assert "https://models.example.org" in app_connect_domains()
    assert "https://coordinates.example.net" in app_connect_domains()
    with pytest.raises(ValueError, match="not configured"):
        validate_coordinate_url("https://sub.models.example.org/model.cif")


@pytest.mark.parametrize(
    "url",
    [
        "http://alphafold.ebi.ac.uk/model.bcif",
        "https://user@alphafold.ebi.ac.uk/model.bcif",
        "https://alphafold.ebi.ac.uk:8443/model.bcif",
        "https://alphafold.ebi.ac.uk/model.bcif?token=secret",
        "https://alphafold.ebi.ac.uk/model.bcif#fragment",
        "https://alphafold.ebi.ac.uk.evil.example/model.bcif",
    ],
)
def test_coordinate_urls_reject_unsafe_or_unregistered_locations(url):
    with pytest.raises(ValueError):
        validate_coordinate_url(url)


@pytest.mark.parametrize(
    "origin",
    [
        "http://models.example.org",
        "https://*.example.org",
        "https://models.example.org/path",
        "https://models.example.org:8443",
        "https://user@models.example.org",
    ],
)
def test_custom_origin_configuration_rejects_wildcards_and_non_origins(
    monkeypatch, origin
):
    monkeypatch.setenv("PDBe_MCP_STRUCTURE_ORIGINS", origin)
    with pytest.raises(ValueError, match="HTTPS origins"):
        allowed_coordinate_origins()
