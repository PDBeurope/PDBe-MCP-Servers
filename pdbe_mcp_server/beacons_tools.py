"""3D-Beacons tools for predicted and experimental structure models.

Predicted models fill the gap where PDBe has no experimental structure. Use
``provider`` to select one source and ``exclude_provider`` to omit one.
"""

import re
import time
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import quote, urljoin

import mcp.types as types
import requests

from pdbe_mcp_server import get_config
from pdbe_mcp_server.api_tools import format_result_text
from pdbe_mcp_server.execution import ToolDeadlineExceeded, remaining_seconds
from pdbe_mcp_server.utils import HTTPClient

conf = get_config()

PROVIDERS = (
    "pdbe",
    "ped",
    "swissmodel",
    "alphafold",
    "sasbdb",
    "alphafill",
    "hegelab",
    "modelarchive",
    "isoformio",
    "levylab",
    "bindome",
)
ANNOTATION_PROVIDERS = ("pdbe", "alphafold")
FEATURE_TYPES = (
    "CARBOHYD",
    "DOMAIN",
    "ACT_SITE",
    "METAL",
    "BINDING",
    "NON_STD",
    "MOD_RES",
    "DISULFID",
    "MUTAGEN",
    "HELIX",
    "STRAND",
    "DISORDERED",
    "INTERFACE",
    "CHANNEL",
)
SEQUENCE_ID_TYPES = ("sequence", "crc64", "md5")
SEQUENCE_ACTIONS = ("submit", "result", "summary")

TOOL_UNIPROT_SUMMARY = "pdbe_3dbeacons_uniprot_summary"
TOOL_ENSEMBL_SUMMARY = "pdbe_3dbeacons_ensembl_summary"
TOOL_ANNOTATIONS = "pdbe_3dbeacons_annotations"
TOOL_SEQUENCE = "pdbe_3dbeacons_sequence"

POLL_INTERVAL_SECONDS = 2.0
# Keep budget for formatting the response after the last poll.
POLL_RESERVE_SECONDS = 5.0

# 3D-Beacons reports "AlphaFold DB"; the request enum uses "alphafold".
PROVIDER_NAME_ALIASES = {"alphafolddb": "alphafold"}

PROVIDER_PRECEDENCE = (
    "Results include PDBe experimental structures (provider 'pdbe', "
    "model_category 'EXPERIMENTALLY DETERMINED'). Use the PDBe API tools for "
    "experimental structures, or set provider to 'pdbe' to get only them. Set "
    "exclude_provider to 'pdbe' to get predicted and other non-PDBe models, for "
    "example after the PDBe tools have already returned experimental structures. "
    "Report predicted models as predictions, with their confidence scores "
    "(pLDDT or QMEANDisCo), not as experimental structures."
)


VIEWER_GUIDANCE = (
    " To show a model in MCP Apps, follow the molview-spec skill: models whose host is "
    "an allowed coordinate origin (PDBe, AlphaFold DB, and other 3D-Beacons providers) "
    "can be opened in the viewer; otherwise share the model_url as a link."
)


class ToolArgumentError(ValueError):
    """The arguments are valid JSON but not valid for the requested action."""


def _tool(
    name: str, description: str, properties: dict, required: list[str]
) -> types.Tool:
    return types.Tool(
        name=name,
        description=description,
        inputSchema={
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
        annotations=types.ToolAnnotations(
            readOnlyHint=True, destructiveHint=False, openWorldHint=True
        ),
    )


def beacons_tools() -> list[types.Tool]:
    provider = {
        "type": "string",
        "enum": list(PROVIDERS),
        "description": "Only return models from this provider.",
    }
    exclude_provider = {
        "type": "string",
        "enum": list(PROVIDERS),
        "description": "Omit models from this provider.",
    }
    return [
        _tool(
            TOOL_UNIPROT_SUMMARY,
            "Structure models for UniProt accessions from the 3D-Beacons Network, "
            "covering experimental and predicted structures. Use this as a fallback "
            "when PDBe has no experimental structure for the protein: predicted models "
            "from providers such as AlphaFold DB, SWISS-MODEL and ModelArchive fill "
            "the gap. " + PROVIDER_PRECEDENCE + VIEWER_GUIDANCE,
            {
                "accessions": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "minItems": 1,
                    "description": "UniProtKB accessions, for example P38398.",
                },
                "provider": provider,
                "exclude_provider": exclude_provider,
            },
            ["accessions"],
        ),
        _tool(
            TOOL_ENSEMBL_SUMMARY,
            "Structure models for an Ensembl gene or transcript identifier, for example "
            "ENSG00000288864, mapped to UniProt accessions by 3D-Beacons. Use this as a "
            "fallback when PDBe has no experimental structure for the protein and the "
            "caller has an Ensembl ID instead of a UniProt accession. "
            + PROVIDER_PRECEDENCE
            + VIEWER_GUIDANCE,
            {
                "ensembl_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Ensembl gene or transcript identifier.",
                },
                "provider": provider,
                "exclude_provider": exclude_provider,
            },
            ["ensembl_id"],
        ),
        _tool(
            TOOL_SEQUENCE,
            "Structure models for a protein sequence through 3D-Beacons, for use when "
            "no UniProt accession is known. Use this as a fallback when PDBe has no "
            "experimental structure for the sequence: predicted models fill the gap. "
            "Actions: 'submit' sends a sequence and "
            "waits for the results; 'result' fetches results for a job_id; 'summary' "
            "returns models for a sequence, or for a CRC64 or MD5 checksum given with "
            "id and id_type. If results are still pending, the response includes the "
            "job_id: call action 'result' with it later. "
            + PROVIDER_PRECEDENCE
            + VIEWER_GUIDANCE,
            {
                "action": {
                    "type": "string",
                    "enum": list(SEQUENCE_ACTIONS),
                    "description": "submit, result, or summary.",
                },
                "sequence": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Protein sequence for 'submit', or for 'summary'.",
                },
                "job_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Job identifier returned by 'submit', for 'result'.",
                },
                "id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "CRC64 or MD5 checksum, for 'summary' with id_type.",
                },
                "id_type": {
                    "type": "string",
                    "enum": list(SEQUENCE_ID_TYPES),
                    "description": "Type of id. Defaults to 'sequence'.",
                },
                "exclude_provider": exclude_provider,
            },
            ["action"],
        ),
        _tool(
            TOOL_ANNOTATIONS,
            "Residue-level annotations for a UniProt accession from 3D-Beacons, such as "
            "domains, binding sites, helices, and disulfide bonds. This describes "
            "features of a protein; it does not look up structures. Annotations from "
            "'alphafold' are predictions. Set provider to select one source, or "
            "exclude_provider to omit one.",
            {
                "uniprot_accession": {
                    "type": "string",
                    "minLength": 1,
                    "description": "UniProtKB accession, for example Q14676.",
                },
                "type": {
                    "type": "string",
                    "enum": list(FEATURE_TYPES),
                    "description": "Annotation type to return.",
                },
                "provider": {
                    "type": "string",
                    "enum": list(ANNOTATION_PROVIDERS),
                    "description": "Only return annotations from this source.",
                },
                "exclude_provider": {
                    "type": "string",
                    "enum": list(ANNOTATION_PROVIDERS),
                    "description": "Omit annotations from this source. Cannot be combined with provider.",
                },
                "range": {
                    "type": "string",
                    "minLength": 1,
                    "description": "UniProt residue range, for example 1-100.",
                },
            },
            ["uniprot_accession", "type"],
        ),
    ]


BEACONS_TOOL_NAMES = frozenset(
    {TOOL_UNIPROT_SUMMARY, TOOL_ENSEMBL_SUMMARY, TOOL_SEQUENCE, TOOL_ANNOTATIONS}
)


def _url(path: str) -> str:
    return urljoin(str(conf.beacons.base_url), path)


def _path_value(value: str) -> str:
    return quote(value, safe="")


def _envelope(source: str, parameters: dict[str, Any], data: Any) -> dict[str, Any]:
    return {
        "data": data,
        "source": source,
        "parameters": parameters,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


def _provider_key(name: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    return PROVIDER_NAME_ALIASES.get(key, key)


def _is_provider(item: Any, key: str) -> bool:
    summary = item.get("summary") if isinstance(item, dict) else None
    name = summary.get("provider") if isinstance(summary, dict) else None
    return isinstance(name, str) and _provider_key(name) == key


def _without_provider(node: Any, key: str) -> Any:
    """Remove structure entries from one provider, wherever they appear."""
    if isinstance(node, list):
        return [_without_provider(item, key) for item in node]
    if not isinstance(node, dict):
        return node
    cleaned: dict[str, Any] = {}
    for field, value in node.items():
        if field == "structures" and isinstance(value, list):
            value = [item for item in value if not _is_provider(item, key)]
        cleaned[field] = _without_provider(value, key)
    return cleaned


def _exclude(data: Any, exclude_provider: str | None) -> Any:
    if not exclude_provider:
        return data
    return _without_provider(data, _provider_key(exclude_provider))


def normalize_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Drop blank values, which clients often send for fields they do not use."""
    return {key: value for key, value in arguments.items() if value not in (None, "")}


def _reject_fields(
    arguments: dict[str, Any], fields: tuple[str, ...], action: str
) -> None:
    for field in fields:
        if arguments.get(field):
            raise ToolArgumentError(f"'{field}' is not used by action '{action}'.")


def get_uniprot_summary(arguments: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {"accessions": arguments["accessions"]}
    for field in ("provider", "exclude_provider"):
        if arguments.get(field) is not None:
            body[field] = arguments[field]
    url = _url("uniprot/summary")
    # Read-only POST, so retries are safe.
    data = HTTPClient.post(url, json=body, max_retries=2)
    return _envelope(url, body, data)


def _applied_filters(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        field: arguments[field]
        for field in ("provider", "exclude_provider")
        if arguments.get(field)
    }


def get_ensembl_summary(arguments: dict[str, Any]) -> dict[str, Any]:
    applied = _applied_filters(arguments)
    url = _url(f"ensembl/summary/{_path_value(arguments['ensembl_id'])}.json")
    params = {"provider": applied["provider"]} if "provider" in applied else None
    data = HTTPClient.get(url, params=params)
    data = _exclude(data, applied.get("exclude_provider"))
    return _envelope(url, applied, data)


def get_annotations(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = arguments.get("provider")
    exclude = arguments.get("exclude_provider")
    if provider and exclude:
        raise ToolArgumentError("Use either provider or exclude_provider, not both.")
    params: dict[str, Any] = {"type": arguments["type"]}
    if provider:
        params["provider"] = provider
    elif exclude:
        # Annotations carry no provider field to filter on, so exclusion means
        # selecting the only other source.
        params["provider"] = next(p for p in ANNOTATION_PROVIDERS if p != exclude)
    if arguments.get("range"):
        params["range"] = arguments["range"]
    url = _url(f"annotations/{_path_value(arguments['uniprot_accession'])}.json")
    data = HTTPClient.get(url, params=params)
    return _envelope(url, params, data)


def _seconds_left() -> float:
    try:
        return remaining_seconds()
    except ToolDeadlineExceeded:
        return 0.0


def _poll_result(job_id: str, exclude_provider: str | None) -> dict[str, Any]:
    url = _url("sequence/result")
    params = {"job_id": job_id}
    while True:
        try:
            data = HTTPClient.get(url, params=params)
        except ToolDeadlineExceeded:
            data = None
        if isinstance(data, list):
            return _envelope(
                url,
                params,
                {
                    "job_id": job_id,
                    "status": "complete",
                    "results": _exclude(data, exclude_provider),
                },
            )
        if _seconds_left() <= POLL_RESERVE_SECONDS + POLL_INTERVAL_SECONDS:
            return _envelope(
                url,
                params,
                {
                    "job_id": job_id,
                    "status": "in_progress",
                    "message": (
                        "The sequence search is still running. Call "
                        "pdbe_3dbeacons_sequence with action 'result' and this job_id "
                        "later."
                    ),
                },
            )
        time.sleep(POLL_INTERVAL_SECONDS)


def run_sequence(arguments: dict[str, Any]) -> dict[str, Any]:
    action = arguments["action"]
    exclude = arguments.get("exclude_provider")

    if action == "submit":
        if not arguments.get("sequence"):
            raise ToolArgumentError("'sequence' is required for action 'submit'.")
        _reject_fields(arguments, ("job_id", "id", "id_type"), action)
        url = _url("sequence/search")
        # Submission creates a job, so it must not be retried.
        job = HTTPClient.post(url, json={"sequence": arguments["sequence"]})
        if not isinstance(job, dict) or not job.get("job_id"):
            raise ValueError("3D-Beacons did not return a job_id for the submission.")
        return _poll_result(str(job["job_id"]), exclude)

    if action == "result":
        if not arguments.get("job_id"):
            raise ToolArgumentError("'job_id' is required for action 'result'.")
        _reject_fields(arguments, ("sequence", "id", "id_type"), action)
        return _poll_result(arguments["job_id"], exclude)

    if arguments.get("sequence") and arguments.get("id"):
        raise ToolArgumentError(
            "Use either 'sequence' or 'id' for action 'summary', not both."
        )
    if arguments.get("sequence"):
        _reject_fields(arguments, ("id_type",), action)
        identifier, id_type = arguments["sequence"], "sequence"
    elif arguments.get("id"):
        identifier = arguments["id"]
        id_type = arguments.get("id_type") or "sequence"
    else:
        raise ToolArgumentError(
            "Action 'summary' needs 'sequence', or 'id' with 'id_type'."
        )
    _reject_fields(arguments, ("job_id",), action)
    url = _url("sequence/summary")
    params = {"id": identifier, "type": id_type}
    data = HTTPClient.get(url, params=params)
    data = _exclude(data, exclude)
    return _envelope(url, {**params, **_applied_filters(arguments)}, data)


def _http_error_message(tool: str, error: requests.HTTPError) -> str:
    status = error.response.status_code if error.response is not None else None
    if status == 400:
        return (
            f"3D-Beacons rejected the {tool} request (HTTP 400). Check the identifier. "
            "For sequence jobs, the job_id may be unknown; submit the sequence again."
        )
    if status == 404:
        return f"3D-Beacons has no data for this {tool} request (HTTP 404)."
    return f"3D-Beacons request failed with HTTP {status}."


HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    TOOL_UNIPROT_SUMMARY: get_uniprot_summary,
    TOOL_ENSEMBL_SUMMARY: get_ensembl_summary,
    TOOL_ANNOTATIONS: get_annotations,
    TOOL_SEQUENCE: run_sequence,
}


def call_beacons_tool(name: str, arguments: dict[str, Any]) -> str:
    handler = HANDLERS[name]
    try:
        envelope = handler(arguments)
    except ValueError as error:
        return f"Error: {error}"
    except ToolDeadlineExceeded:
        raise
    except requests.HTTPError as error:
        return _http_error_message(name, error)
    except requests.RequestException as error:
        return f"3D-Beacons request failed: {error}"
    return format_result_text(envelope)
