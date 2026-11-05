from unittest.mock import Mock

import pytest
import requests

from pdbe_mcp_server.ai_summary_tools import (
    ai_summary_tool,
    format_ai_summary,
    get_ai_summary,
    summary_url,
)


def test_summary_url_uses_two_characters_before_final_character():
    assert (
        summary_url("1RIO")
        == "https://ftp.ebi.ac.uk/pub/databases/msd/ai-summaries/entries/ri/1rio.json"
    )


@pytest.mark.parametrize("pdb_id", ["1rio/other", "abc", "pdb_00001abc", "   "])
def test_summary_url_rejects_invalid_ids(pdb_id):
    with pytest.raises(ValueError):
        summary_url(pdb_id)


def test_formatter_keeps_sections_key_points_and_references():
    text = format_ai_summary(
        "1rio",
        {
            "schema_version": "1.0.0",
            "generated_at": "2026-10-09T23:48:10Z",
            "summary_sections": [
                {"section": "introduction", "text": "Entry overview <<ref:1>>"}
            ],
            "abstract_key_points": ["Key point <<ref:9>>"],
            "references": [
                {
                    "id": 1,
                    "endpoint": "pdb/entry/summary",
                    "url": "https://www.ebi.ac.uk/pdbe/api/v2/pdb/entry/summary/1rio",
                    "fields": ["title"],
                },
                {
                    "id": 9,
                    "endpoint": "pdb/entry/publications",
                    "url": "https://www.ebi.ac.uk/pdbe/api/v2/pdb/entry/publications/1rio",
                    "fields": ["abstract"],
                },
            ],
        },
    )

    assert "Pre-generated AI summary" not in text
    assert "Schema version:" not in text
    assert "Generated at:" not in text
    assert "## Introduction\nEntry overview [1](#reference-1)" in text
    assert "## Abstract key points\n- Key point [9](#reference-9)" in text
    assert '<a id="reference-9"></a>' in text
    assert "### Reference 9\n- Endpoint: `pdb/entry/publications`" in text
    assert (
        "- Source: [PDBe API](https://www.ebi.ac.uk/pdbe/api/v2/pdb/entry/publications/1rio)"
        in text
    )
    assert "- Fields: abstract" in text


def test_formatter_joins_wrapped_prose_and_preserves_list_items():
    text = format_ai_summary(
        "1rio",
        {
            "summary_sections": [
                {
                    "section": "introduction",
                    "text": "First wrapped line\ncontinues here.\n\n- First item\n- Second item",
                }
            ],
            "references": [],
        },
    )

    assert "First wrapped line continues here." in text
    assert "First wrapped line\ncontinues" not in text
    assert "- First item\n\n- Second item" in text


def test_formatter_handles_empty_optional_sections():
    assert "No summary content" in format_ai_summary(
        "1rio", {"summary_sections": [], "abstract_key_points": []}
    )


def test_fetch_formats_the_fixed_url_response(monkeypatch):
    response = {
        "summary_sections": [{"section": "introduction", "text": "Overview."}],
        "abstract_key_points": ["A key point."],
        "references": [],
    }
    get = Mock(return_value=response)
    monkeypatch.setattr("pdbe_mcp_server.ai_summary_tools.HTTPClient.get", get)

    text = get_ai_summary({"pdb_id": "1RIO"})

    get.assert_called_once_with(
        "https://ftp.ebi.ac.uk/pub/databases/msd/ai-summaries/entries/ri/1rio.json",
        max_retries=1,
        retry_delay=0.25,
        timeout=10,
    )
    assert "## Abstract key points\n- A key point." in text


def test_missing_summary_returns_clear_unavailable_message(monkeypatch):
    response = Mock(status_code=404)
    get = Mock(side_effect=requests.HTTPError(response=response))
    monkeypatch.setattr("pdbe_mcp_server.ai_summary_tools.HTTPClient.get", get)

    result = get_ai_summary({"pdb_id": "1rio"})

    assert "No pre-generated AI summary is available" in result


def test_tool_is_read_only_and_constrains_entry_id():
    tool = ai_summary_tool()
    assert tool.annotations.readOnlyHint is True
    assert tool.inputSchema["properties"]["pdb_id"]["pattern"] == "^[A-Za-z0-9]{4}$"
