"""Comparison data from the shared API executor and PDBe superposition matrices."""

import math
import re
from datetime import datetime, timezone
from typing import Any

from pdbe_mcp_server.api_tools import OpenAPIToMCPGenerator
from pdbe_mcp_server.utils import HTTPClient


def comparison_input_schema() -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for side in ("reference", "mobile"):
        properties[f"{side}_pdb_id"] = {
            "type": "string",
            "pattern": "^[1-9][A-Za-z0-9]{3}$",
        }
        properties[f"{side}_chain_id"] = {
            "type": "string",
            "minLength": 1,
            "description": "Exact label chain ID (struct_asym_id); case sensitive.",
        }
    properties["uniprot_accession"] = {
        "type": "string",
        "minLength": 1,
        "description": "Shared UniProt accession; required if mappings are ambiguous.",
    }
    properties["segment_index"] = {
        "type": "integer",
        "minimum": 1,
        "description": "1-based PDBe segment index; required if several cover both chains.",
    }
    for option in ("include_annotations", "include_ligands"):
        properties[option] = {
            "type": "boolean",
            "default": False,
            "description": "Optional supplied data; omitted from the initial protein comparison unless requested.",
        }
    return {
        "type": "object",
        "properties": properties,
        "required": [
            f"{side}_{field}"
            for side in ("reference", "mobile")
            for field in ("pdb_id", "chain_id")
        ],
        "additionalProperties": False,
    }


def _chain(structure: dict[str, Any], chain_id: str) -> dict[str, Any]:
    matches = [c for c in structure["chains"] if c["label_asym_id"] == chain_id]
    if len(matches) != 1 or "polypeptide" not in matches[0]["molecule_type"].lower():
        raise ValueError(
            f"Choose a protein label chain in {structure['pdb_id']}: "
            + ", ".join(
                c["label_asym_id"]
                for c in structure["chains"]
                if "polypeptide" in c["molecule_type"].lower()
            )
        )
    return matches[0]


def _positions(
    records: list[dict[str, Any]], chain: dict[str, Any], warnings: list[str]
) -> dict[int, dict[str, Any]]:
    residues = {r["label_seq_id"]: r for r in chain["residues"]}
    positions: dict[int, set[int]] = {}
    for m in records:
        if (
            m.get("struct_asym_id") != chain["label_asym_id"]
            or str(m.get("entity_id")) != chain["entity_id"]
        ):
            continue
        start, end = (
            m.get("start", {}).get("residue_number"),
            m.get("end", {}).get("residue_number"),
        )
        us, ue = m.get("unp_start"), m.get("unp_end")
        if (
            not isinstance(start, int)
            or not isinstance(end, int)
            or not isinstance(us, int)
            or not isinstance(ue, int)
            or any(isinstance(v, bool) for v in (start, end, us, ue))
            or end < start
            or ue < us
            or end - start != ue - us
        ):
            warnings.append("Skipped a non-linear or incomplete SIFTS mapping segment.")
            continue
        for label in range(start, end + 1):
            if label in residues:
                positions.setdefault(us + label - start, set()).add(label)
    # Both directions must be unique; repeated/chimeric mappings must not silently pair.
    inverse: dict[int, set[int]] = {}
    for unp, labels in positions.items():
        for label in labels:
            inverse.setdefault(label, set()).add(unp)
    result = {}
    for unp, labels in positions.items():
        if len(labels) == 1 and len(inverse[next(iter(labels))]) == 1:
            result[unp] = residues[next(iter(labels))]
        else:
            warnings.append("Skipped an ambiguous SIFTS residue correspondence.")
    return result


def _matrix(record: Any, pdb_id: str, chain: dict[str, Any]) -> list[list[float]]:
    if (
        not isinstance(record, dict)
        or record.get("pdb_id") != pdb_id
        or record.get("auth_asym_id") != chain["auth_asym_id"]
        or record.get("struct_asym_id") != chain["label_asym_id"]
    ):
        raise ValueError(f"No exact PDBe matrix for {pdb_id}/{chain['label_asym_id']}.")
    matrix = record.get("matrix")
    if (
        not isinstance(matrix, list)
        or len(matrix) != 4
        or any(not isinstance(row, list) or len(row) != 4 for row in matrix)
        or any(
            not isinstance(v, (float, int))
            or isinstance(v, bool)
            or not math.isfinite(v)
            for row in matrix
            for v in row
        )
        or any(abs(matrix[3][i] - [0, 0, 0, 1][i]) > 1e-6 for i in range(4))
    ):
        raise ValueError("PDBe returned an invalid transformation matrix.")
    return matrix


def comparison_data(
    arguments: dict[str, Any],
    structures: list[dict[str, Any]],
    generator: OpenAPIToMCPGenerator,
) -> dict[str, Any]:
    """Use SIFTS correspondence and existing PDBe transforms; perform no fitting."""
    chains = [
        _chain(s, arguments[f"{side}_chain_id"])
        for side, s in zip(("reference", "mobile"), structures)
    ]
    warnings = [w for s in structures for w in s["warnings"]]
    sources = {url for s in structures for url in s["sources"]}
    mappings = []
    for s in structures:
        result = generator.execute_api_tool(
            "/mappings/{accession}", {"accession": s["pdb_id"]}
        )
        mappings.append(result["data"].get(s["pdb_id"], {}).get("UniProt", {}))
        sources.add(result["source"])
    accessions = []
    for mapping, chain in zip(mappings, chains):
        accessions.append(
            {
                a
                for a, r in mapping.items()
                if any(
                    m.get("struct_asym_id") == chain["label_asym_id"]
                    and str(m.get("entity_id")) == chain["entity_id"]
                    for m in r.get("mappings", [])
                )
            }
        )
    shared = sorted(accessions[0] & accessions[1])
    accession = str(arguments.get("uniprot_accession", "")).strip().upper()
    if not accession and len(shared) == 1:
        accession = shared[0]
    if accession not in shared:
        raise ValueError(
            "Choose a shared UniProt accession: "
            + (", ".join(shared) or "none; this pair has no shared SIFTS mapping")
        )
    if not re.fullmatch(r"[A-Z0-9]+(?:-\d+)?", accession):
        raise ValueError("Invalid UniProt accession.")
    result = generator.execute_operation(
        "get",
        "/uniprot/superposition/{uniprot_accession}",
        {"uniprot_accession": accession},
    )
    sources.add(result["source"])
    segments = result["data"].get(accession, [])
    if not isinstance(segments, list):
        raise ValueError("PDBe superposition segments are unavailable.")
    candidates = []
    for i, segment in enumerate(segments, 1):
        memberships = []
        for structure, chain in zip(structures, chains):
            memberships.append(
                [
                    j
                    for j, cluster in enumerate(segment.get("clusters", []), 1)
                    if any(
                        m.get("pdb_id") == structure["pdb_id"]
                        and m.get("struct_asym_id") == chain["label_asym_id"]
                        and m.get("auth_asym_id") == chain["auth_asym_id"]
                        and str(m.get("entity_id")) == chain["entity_id"]
                        for m in cluster
                    )
                ]
            )
        if all(memberships):
            candidates.append(
                {
                    "index": i,
                    "start": segment["segment_start"],
                    "end": segment["segment_end"],
                    "clusters": memberships,
                }
            )
    chosen = arguments.get("segment_index")
    if chosen is None and len(candidates) == 1:
        chosen = candidates[0]["index"]
    segment = next((s for s in candidates if s["index"] == chosen), None)
    if segment is None:
        raise ValueError(
            "Choose a PDBe segment containing both exact chains: "
            + (
                ", ".join(f"{s['index']} ({s['start']}–{s['end']})" for s in candidates)
                or "none available; PDBe has no precomputed superposition for this pair"
            )
        )
    matrix_url = f"https://www.ebi.ac.uk/pdbe/static/superpose/matrices/{accession}"
    # This static file is not an OpenAPI operation; reuse the server's HTTP client.
    matrices = HTTPClient.get(matrix_url)
    if not isinstance(matrices, dict):
        raise ValueError("PDBe superposition matrices are unavailable.")
    sources.add(matrix_url)
    sides = []
    positions = []
    for i, (s, chain, mapping) in enumerate(zip(structures, chains, mappings)):
        matrix = _matrix(
            matrices.get(f"{s['pdb_id']}_{chain['auth_asym_id']}"), s["pdb_id"], chain
        )
        sides.append(
            {
                "pdb_id": s["pdb_id"],
                "title": s["title"],
                "chain": {k: v for k, v in chain.items() if k != "residues"},
                "coordinate_url": s["coordinate_url"],
                "entry_url": s["entry_url"],
                "matrix": matrix,
                "cluster_indices": segment["clusters"][i],
            }
        )
        positions.append(
            _positions(mapping[accession].get("mappings", []), chain, warnings)
        )
    matched = sorted(
        p
        for p in positions[0].keys() & positions[1].keys()
        if segment["start"] <= p <= segment["end"]
    )
    if not matched:
        raise ValueError(
            "No unambiguous SIFTS residue pairs inside the selected PDBe segment."
        )
    pairs = [
        {"uniprot_position": p, "reference": positions[0][p], "mobile": positions[1][p]}
        for p in matched
    ]
    return {
        "reference": sides[0],
        "mobile": sides[1],
        "uniprot_accession": accession,
        "segment": segment,
        "pairs": pairs,
        "mapped_pair_count": len(pairs),
        "method": "PDBe precomputed superposition matrices; residue correspondence from unambiguous equal-length SIFTS mapping segments; first deposited coordinate model. The viewer applies the supplied transforms. No app-calculated RMSD, per-residue displacement, or binding-site neighbourhoods.",
        "sources": sorted(sources),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "warnings": sorted(set(warnings)),
    }


def comparison_text(data: dict[str, Any]) -> str:
    return (
        f"PDBe structure comparison: {data['reference']['pdb_id']}/{data['reference']['chain']['label_asym_id']} "
        f"and {data['mobile']['pdb_id']}/{data['mobile']['chain']['label_asym_id']}.\n"
        f"UniProt {data['uniprot_accession']}; segment {data['segment']['index']} "
        f"({data['segment']['start']}–{data['segment']['end']}); {data['mapped_pair_count']} mapped pairs.\n"
        + data["method"]
        + "\nResidue correspondence is supplied from PDBe/SIFTS mappings; the app does not calculate geometric scores.\nSources: "
        + ", ".join(data["sources"])
        + "\n"
        + "\n".join(data["warnings"])
    )
