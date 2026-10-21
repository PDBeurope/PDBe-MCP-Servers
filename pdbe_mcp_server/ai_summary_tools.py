"""Fetch and render the pre-generated PDBe AI entry summaries."""

import re
from typing import Any

import mcp.types as types
import requests

from pdbe_mcp_server.utils import HTTPClient

AI_SUMMARY_ROOT = "https://ftp.ebi.ac.uk/pub/databases/msd/ai-summaries/entries"
PDB_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{4}$")
REFERENCE_MARKER_PATTERN = re.compile(
    r"<<ref:([A-Za-z0-9_.-]+)>>|<ref:([A-Za-z0-9_.-]+)>"
)


def _reference_anchor(reference_id: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", reference_id.lower()).strip("-")


def _normalize_summary_text(text: str) -> str:
    """Join wrapped prose lines while retaining Markdown list item boundaries."""
    blocks: list[str] = []
    prose_lines: list[str] = []

    def flush_prose() -> None:
        if prose_lines:
            blocks.append(" ".join(prose_lines))
            prose_lines.clear()

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.match(r"^(?:[-*+]\s+|\d+[.)]\s+)", line):
            flush_prose()
            blocks.append(line)
        else:
            prose_lines.append(line)
    flush_prose()
    return "\n\n".join(blocks)


def ai_summary_tool() -> types.Tool:
    return types.Tool(
        name="pdbe_get_ai_summary",
        description=(
            "Retrieve the pre-generated AI summary for a four-character PDB entry. "
            "Use this for an entry overview instead of writing a new summary. "
            "Returns the available summary sections and abstract key points, "
            "preserving inline reference markers and listing their PDBe source "
            "URLs and fields. A summary may not exist for every entry."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "pdb_id": {
                    "type": "string",
                    "pattern": "^[A-Za-z0-9]{4}$",
                    "description": "Four-character PDB entry ID, for example 1rio.",
                }
            },
            "required": ["pdb_id"],
            "additionalProperties": False,
        },
        annotations=types.ToolAnnotations(
            readOnlyHint=True, destructiveHint=False, openWorldHint=True
        ),
    )


def summary_url(pdb_id: str) -> str:
    normalized = pdb_id.strip().lower()
    if not PDB_ID_PATTERN.fullmatch(normalized):
        raise ValueError("pdb_id must be a four-character PDB entry ID")
    shard = normalized[-3:-1]
    return f"{AI_SUMMARY_ROOT}/{shard}/{normalized}.json"


def format_ai_summary(pdb_id: str, document: dict[str, Any]) -> str:
    """Format summary sections and their source references as readable text."""
    references = document.get("references", [])
    reference_ids = (
        {
            str(reference.get("id"))
            for reference in references
            if isinstance(reference, dict) and reference.get("id") is not None
        }
        if isinstance(references, list)
        else set()
    )

    def link_reference_markers(text: str) -> str:
        def replace_marker(match: re.Match) -> str:
            reference_id = match.group(1) or match.group(2)
            if reference_id not in reference_ids:
                return match.group(0)
            return f"[{reference_id}](#reference-{_reference_anchor(reference_id)})"

        return REFERENCE_MARKER_PATTERN.sub(replace_marker, text)

    lines: list[str] = []
    rendered_sections = 0
    sections = document.get("summary_sections", [])
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            name, text = section.get("section"), section.get("text")
            if (
                not isinstance(name, str)
                or not isinstance(text, str)
                or not text.strip()
            ):
                continue
            normalized_text = _normalize_summary_text(text.strip())
            lines.extend(
                [
                    "",
                    f"## {name.replace('_', ' ').title()}",
                    link_reference_markers(normalized_text),
                ]
            )
            rendered_sections += 1

    key_points = document.get("abstract_key_points", [])
    if isinstance(key_points, list):
        points = [
            link_reference_markers(_normalize_summary_text(point.strip()))
            for point in key_points
            if isinstance(point, str) and point.strip()
        ]
        if points:
            lines.extend(["", "## Abstract key points"])
            lines.extend(f"- {point}" for point in points)
            rendered_sections += 1

    if rendered_sections == 0:
        return f"No summary content is available for PDB entry {pdb_id.upper()}."

    if isinstance(references, list) and references:
        lines.extend(["", "## References"])
        for reference in references:
            if not isinstance(reference, dict):
                continue
            reference_id = reference.get("id")
            endpoint = reference.get("endpoint")
            url = reference.get("url")
            fields = reference.get("fields", [])
            if reference_id is None:
                continue
            anchor = _reference_anchor(str(reference_id))
            if not anchor:
                continue
            lines.extend(
                [
                    "",
                    f'<a id="reference-{anchor}"></a>',
                    f"### Reference {reference_id}",
                ]
            )
            if isinstance(endpoint, str) and endpoint:
                lines.append(f"- Endpoint: `{endpoint}`")
            if isinstance(url, str) and url:
                lines.append(f"- Source: [PDBe API]({url})")
            if isinstance(fields, list):
                field_names = [field for field in fields if isinstance(field, str)]
                if field_names:
                    lines.append(f"- Fields: {', '.join(field_names)}")

    return "\n".join(lines)


def get_ai_summary(arguments: dict[str, Any]) -> str:
    """Fetch one summary using a URL constructed only from a validated PDB ID."""
    pdb_id = arguments.get("pdb_id")
    if not isinstance(pdb_id, str):
        return "pdb_id must be a four-character PDB entry ID."
    try:
        url = summary_url(pdb_id)
    except ValueError as error:
        return str(error)

    normalized = pdb_id.strip().lower()
    try:
        document = HTTPClient.get(url, max_retries=1, retry_delay=0.25, timeout=10)
    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code == 404:
            return f"No pre-generated AI summary is available for PDB entry {normalized.upper()}."
        return f"Could not retrieve the AI summary for PDB entry {normalized.upper()}."
    except requests.RequestException:
        return f"Could not retrieve the AI summary for PDB entry {normalized.upper()}."

    if not isinstance(document, dict):
        return (
            f"The AI summary for PDB entry {normalized.upper()} has an invalid format."
        )
    return format_ai_summary(normalized, document)
