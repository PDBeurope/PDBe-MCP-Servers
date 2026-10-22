# PDBe MCP Servers

Access Protein Data Bank in Europe (PDBe) structural biology data from any
AI client that supports the Model Context Protocol (MCP).

| Server | Purpose |
| --- | --- |
| `pdbe_api_server` | Entries, assemblies, molecules, ligands, publications, and validation data |
| `pdbe_search_server` | Solr searches with filtering, facets, grouping, and pagination |
| `pdbe_apps_server` | Interactive structure inspection, comparison, and MolViewSpec scenes |
| `pdbe_graph_server` | PDBe-KB graph schema and queries against your local Neo4j database |
| `all` | All tools in one server |

Start with the API and Search servers. Graph queries require your own PDBe-KB
Neo4j database; PDBe does not provide a public running instance.

## Quick start

Requires **Python 3.10+** and **[uv](https://github.com/astral-sh/uv)**.
Run directly from PyPI without a separate installation:

```bash
uvx pdbe-mcp-server
```

This starts the API server over stdio. To use Search instead:

```bash
uvx pdbe-mcp-server --server-type pdbe_search_server
```

## Connect your AI client

For clients using a JSON `mcpServers` configuration, add:

```json
{
  "mcpServers": {
    "PDBe API": {
      "command": "uvx",
      "args": ["pdbe-mcp-server", "--server-type", "pdbe_api_server"]
    },
    "PDBe Search": {
      "command": "uvx",
      "args": ["pdbe-mcp-server", "--server-type", "pdbe_search_server"]
    }
  }
}
```

Ensure `uvx` is in your client's PATH, then restart or reload the client.
Clients with a settings UI can use the same commands and arguments.

Try asking:

- “Find structures for UniProt accession P12345.”
- “Show structures released this month, grouped by experimental method.”
- “Find X-ray structures with resolution better than 2.0 Å.”

See [worked examples](examples/) for questions involving protein function,
ligand interactions, glycosylation, cryo-EM structures, and EMDB maps.

## Molecular workspace

In an MCP Apps client, the Apps server provides a shared Mol* workspace for:

- **Structure Explorer:** inspect chains, ligands, residues, and annotations.
- **Structure Comparison:** view PDBe's precomputed superpositions and
  PDBe/SIFTS residue correspondence.
- **MolViewSpec Builder:** create custom scenes and multi-scene molecular stories.

Add another client entry using `--server-type pdbe_apps_server`, or use `all`.
The host needs MCP Apps support, WebGL, and access to `https://www.ebi.ac.uk`.
Clients without UI support receive text and structured data fallbacks.

Comparisons use supplied PDBe transforms and mappings; the app does not
calculate a new fit, RMSD, or proximity-derived binding sites. Chain selectors
use label chain IDs (`struct_asym_id`).

See the [molecular workspace guide](docs/molecular-workspace.md) for setup,
tool examples, annotations, saved workspaces, updates, and host routing.
The Apps and aggregate servers also expose the `molview-spec` skill as MCP
resources for scene-building guidance.

## Remote HTTP server

From a local checkout, start Streamable HTTP with:

```bash
uv run pdbe-mcp-remote-server --all
```

Connect to `http://127.0.0.1:8000/api/`, `/search/`, `/apps/`, or `/graph/`.
The `--all` flag also exposes `/all/`. Use `ROOT_PREFIX` for a path prefix.

See the [server reference](docs/server-reference.md) for Docker, legacy SSE,
search parameters, graph setup, and experimental TOON output.

## Local development

Clone the repository and install dependencies:

```bash
git clone https://github.com/PDBeurope/PDBe-MCP-Servers.git
cd PDBe-MCP-Servers
uv sync --all-extras --dev
```

Build the molecular UI with **Node.js 22.12+** before running the Apps server
or building a Python distribution:

```bash
cd apps/structure-explorer
npm ci
npm run build
cd ../..
```

For a local client connection, replace `uvx` with `uv` and use arguments like:

```json
["run", "--directory", "/path/to/PDBe-MCP-Servers", "pdbe-mcp-server", "--server-type", "pdbe_api_server"]
```

Rebuild the UI after UI changes. Python distributions include the generated
HTML artifacts. See [Development](DEVELOPMENT.md) for testing and packaging,
and [Contributing](CONTRIBUTING.md) for contribution guidance.

## Documentation and support

- [Molecular workspace guide](docs/molecular-workspace.md)
- [Server and tool reference](docs/server-reference.md)
- [Worked examples](examples/)
- [PDBe API documentation](https://www.ebi.ac.uk/pdbe/api/v2/)
- [PDBe-KB graph documentation](https://www.ebi.ac.uk/pdbe/pdbe-kb/graph)
- [Model Context Protocol](https://modelcontextprotocol.org/)
- [GitHub issues](https://github.com/PDBeurope/PDBe-MCP-Servers/issues)
- [PDBe Help & Support](https://www.ebi.ac.uk/about/contact/support/pdbe)

Licensed under [Apache 2.0](LICENSE).
