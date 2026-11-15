import json
import re

import pytest

from pdbe_mcp_server.mvs import build_mvs

SWISSMODEL_CIF = (
    "https://swissmodel.expasy.org/3d-beacons/uniprot/P38398.cif"
    "?range=1-103&template=1jm7.1.A&provider=swissmodel"
)


def _parse_formats(result):
    return re.findall(r'"format": "([a-z0-9]+)"', json.dumps(result["mvsj"]))


def test_cif_url_without_format_is_parsed_as_mmcif():
    result = build_mvs(
        {"builder": {"structure": {"url": SWISSMODEL_CIF, "type": "model"}}}
    )
    assert result["builder"]["structure"]["format"] == "mmcif"
    assert "bcif" not in _parse_formats(result)
    assert "mmcif" in _parse_formats(result)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://alphafold.ebi.ac.uk/files/AF-Q9I1F6-F1-model_v6.bcif", "bcif"),
        ("https://www.ebi.ac.uk/pdbe/static/entry/1gq4_updated.cif", "mmcif"),
        ("https://www.ebi.ac.uk/pdbe/static/entry/1gq4_updated.pdb", "pdb"),
    ],
)
def test_format_is_inferred_from_the_url_extension(url, expected):
    result = build_mvs({"builder": {"pdb_id": "1gq4", "structure": {"url": url}}})
    assert result["builder"]["structure"].get("format", "bcif") == expected


def test_declared_format_that_contradicts_the_url_extension_is_rejected():
    with pytest.raises(ValueError, match="URL ends in .mmcif"):
        build_mvs({"builder": {"structure": {"url": SWISSMODEL_CIF, "format": "bcif"}}})


def test_declared_format_matching_the_url_is_kept():
    result = build_mvs(
        {"builder": {"structure": {"url": SWISSMODEL_CIF, "format": "MMCIF"}}}
    )
    assert result["builder"]["structure"]["format"] == "mmcif"


def test_pdbe_entry_without_url_still_defaults_to_bcif():
    result = build_mvs({"builder": {"pdb_id": "1cbs"}})
    assert result["builder"]["structure"].get("format", "bcif") == "bcif"


def test_url_without_known_extension_keeps_the_bcif_default():
    result = build_mvs(
        {"builder": {"structure": {"url": "https://www.ebi.ac.uk/pdbe/entry-files/x"}}}
    )
    assert result["builder"]["structure"].get("format", "bcif") == "bcif"
