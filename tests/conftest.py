"""Pytest configuration and shared fixtures for PDBe MCP server tests."""

from typing import Any
from unittest.mock import MagicMock

import pytest
import requests


@pytest.fixture
def mock_openapi_spec() -> dict[str, Any]:
    """Mock OpenAPI specification for testing."""
    return {
        "openapi": "3.0.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/test/{id}": {
                "get": {
                    "operationId": "get_test",
                    "enableMCP": True,
                    "summary": "Get test data",
                    "description": "Retrieve test data by ID",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {
                                "type": "string",
                                "description": "Test ID",
                            },
                        },
                        {
                            "name": "format",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string", "enum": ["json", "xml"]},
                            "description": "Response format",
                        },
                    ],
                }
            },
            "/disabled": {
                "get": {
                    "operationId": "disabled_endpoint",
                    "enableMCP": False,
                    "summary": "Disabled endpoint",
                }
            },
        },
    }


@pytest.fixture
def mock_graph_schema() -> dict[str, Any]:
    """Mock graph schema for testing."""
    return {
        "nodes": [
            {
                "id": 1,
                "label": "Structure",
                "title": "PDB Structure",
                "description": "A <b>protein</b> structure",
                "properties": [
                    {"name": "pdb_id", "value": "PDB identifier"},
                    {"name": "title", "value": "Structure title"},
                ],
            },
            {
                "id": 2,
                "label": "Ligand",
                "title": "Ligand",
                "description": "A small molecule",
                "properties": [],
            },
        ],
        "edges": [
            {
                "label": "HAS_LIGAND",
                "title": "Has Ligand",
                "description": "Structure contains <i>ligand</i>",
                "from": 1,
                "to": 2,
                "properties": [{"name": "count", "value": "Number of ligands"}],
            }
        ],
        "examples": [
            {
                "query": "Give me all the structures that are released in 2025.",
                "description": "MATCH (entry:Entry)\n    WHERE entry.PDB_REV_DATE STARTS WITH '2025'\n    RETURN entry.ID as PDB_ID, \n        entry.TITLE as Title,\n        entry.PDB_REV_DATE as Release_Date,\n        entry.RESOLUTION as Resolution,\n        entry.METHOD as Experimental_Method,\n        entry.STATUS_CODE as Status\n    ORDER BY entry.PDB_REV_DATE DESC",
            },
            {
                "query": "Find all residues that are part of a given Pfam domain.",
                "description": "MATCH (residue:PDBResidue)-[:HAS_PFAM]->(pfam:PFAM)\n    WHERE pfam.ACCESSION = 'PF00069'\n    RETURN residue.AUTH_ASYM_ID as Chain_ID,\n        residue.AUTH_SEQ_ID as Residue_Number,\n        residue.PDB_ID as PDB_ID,\n        pfam.ACCESSION as Pfam_Accession,\n        pfam.NAME as Pfam_Name\n    ORDER BY residue.PDB_ID, residue.AUTH_ASYM_ID, residue.AUTH_SEQ_ID",
            },
        ],
    }


@pytest.fixture
def mock_search_schema() -> dict[str, Any]:
    """Mock search schema for testing."""
    return {
        "fields": {
            "pdb_id": {
                "type": "string",
                "stored": True,
                "indexed": True,
                "description": "PDB identifier",
            },
            "title": {
                "type": "text",
                "stored": True,
                "indexed": True,
                "description": "Structure title",
            },
            "resolution": {
                "type": "float",
                "stored": True,
                "indexed": True,
                "description": "Resolution in Angstroms",
            },
        }
    }


@pytest.fixture
def mock_search_response() -> dict[str, Any]:
    """Mock search API response for testing."""
    return {
        "response": {
            "numFound": 2,
            "start": 0,
            "docs": [
                {
                    "pdb_id": "1cbs",
                    "title": "Test Structure 1",
                    "resolution": 2.5,
                },
                {
                    "pdb_id": "2xyz",
                    "title": ["Test Structure 2", "Alternative Title"],
                    "resolution": 1.8,
                },
            ],
        }
    }


@pytest.fixture
def mock_http_get(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock HTTP GET requests."""
    mock = MagicMock()
    mock.return_value.status_code = 200
    mock.return_value.json.return_value = {"test": "data"}

    def mock_session_get(*args: Any, **kwargs: Any) -> MagicMock:
        return mock.return_value

    # Patch requests.Session.get
    monkeypatch.setattr("requests.Session.get", mock_session_get)
    return mock


@pytest.fixture
def mock_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock HTTP requests to raise an error."""

    def mock_session_get(*args: Any, **kwargs: Any) -> None:
        response = MagicMock()
        response.status_code = 404
        response.text = "Not Found"
        raise requests.HTTPError(response=response)

    monkeypatch.setattr("requests.Session.get", mock_session_get)
