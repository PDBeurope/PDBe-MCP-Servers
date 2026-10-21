# PDBe MCP Servers

A set of Model Context Protocol (MCP) servers that provides seamless access to the Protein Data Bank in Europe (PDBe) API and PDBe Search. These servers expose PDBe's comprehensive structural biology data as MCP tools, enabling direct integration with any AI client that supports MCP.

The package also includes an advanced PDBe Graph server for users who run their own local PDBe-KB Neo4j graph database. PDBe does not provide a public running graph database instance for this MCP server to query, so most users should start with the API and Search servers.

**Features:**
- **PDBe API Server**: Access core structural data through REST API endpoints
- **PDBe Search Server**: Perform advanced Solr-based searches across structural data
- **PDBe Graph Server**: Inspect the graph schema and, with a local PDBe-KB Neo4j setup, query complex relationships and molecular interactions


## Structure Explorer MCP App

The Structure Explorer adds an embedded PDBe Mol* viewer to MCP Apps clients.
Ask **“Open PDB 4HHB”**, then toggle chains, select a ligand instance or residue,
focus the selection, and inspect its identifiers in the evidence panel. Clicking
in 3D updates the panel and matching list entry. **Ask about selection** sends
the selected identifiers to the MCP client for follow-up prompts.
Clients without app rendering receive structure metadata and ligand information
as text.

The interface uses plain TypeScript, HTML, and CSS with the official MCP Apps
browser SDK. PDBe Mol* is embedded using its published browser bundle (Mol*
internally uses React; this app has no React components or React app dependency).

Build the UI with Node.js 22.12+ before starting the server or building a Python
distribution:

```bash
cd apps/structure-explorer
npm ci
npm run build
cd ../..
uv sync
```

The build creates `pdbe_mcp_server/ui/structure-explorer.html`,
`pdbe_mcp_server/ui/structure-comparison.html`, and
`pdbe_mcp_server/ui/mvs-viewer.html`, including the viewer, styles, SDK,
and third-party license notices. Python wheels and source
distributions include these artifacts when built. Rebuild them after UI
changes; publishing a Python package requires this build step.

For a local stdio connection, configure your MCP Apps client with:

```json
{
  "mcpServers": {
    "PDBe Structure Explorer": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/PDBe-MCP-Servers", "pdbe-mcp-server", "--server-type", "pdbe_apps_server"]
    }
  }
}
```

For Streamable HTTP, run `uv run pdbe-mcp-remote-server` and connect the client
to `http://127.0.0.1:8000/apps/`. With `--all`, the app tool and its UI resource
are also available at `/all/`. `ROOT_PREFIX` applies to both paths. For legacy
SSE, use `--server-type pdbe_apps_server --transport sse` on the stdio executable.

The model-visible tool is `pdbe_open_structure(pdb_id, assembly_id?, chain_id?)`.
`chain_id` is a **label chain ID** (`struct_asym_id`); the UI shows both author
and label identifiers. Omit `assembly_id` to view the deposited asymmetric unit.
The first coordinate model is loaded. Assembly views may omit entry chains or
show symmetry copies; list selections apply to all copies, while 3D clicks retain
the clicked instance. Residue lists come from deposited-entry PDBe annotations,
and unobserved residues cannot be highlighted. Non-polymer selections use author
residue numbers and insertion codes rather than PDBe's internal residue index.

Only public PDBe endpoints on `https://www.ebi.ac.uk` are needed for browser
network access. Their origin is declared in the UI resource CSP. The host needs
MCP Apps support, WebGL, and network access to that origin. The evidence panel
lists source endpoints and retrieval time. Missing optional annotations produce
a warning; coordinate failures offer a retry through **Open structure**.

Structure inspection, precomputed structure comparisons, and custom MVS scenes are available.

### Custom MolViewSpec scenes

`ebi-pdbe-build_mvs` builds and displays a custom molecular scene in the
MolViewSpec App (`ui://pdbe/mvs-viewer`). Supply a PDB entry and scene components,
such as a cartoon representation for the polymer and ball-and-stick for a ligand:

```json
{
  "version": 1,
  "builder": {
    "pdb_id": "1cbs",
    "title": "Protein and ligand",
    "components": [
      {"selector": "polymer", "representation": "cartoon"},
      {"selector": "ligand", "representation": "ball_and_stick", "focus": true}
    ]
  }
}
```

Scenes support common molecular representations, selection and styling options,
annotations, camera settings, and additional structures or primitives. The App
can restore and export scenes as MVSJ. See the `molview-spec` skill for supported
builder fields and examples.

### Molecular stories

`ebi-pdbe-build_mvs_story` creates a multi-scene molecular story in the same App.
Provide a title and an ordered set of scenes, each with its own scene definition.
Stories support playback, transitions, and MVSJ export.

### Remote molecular visualization skill

The Apps and aggregate servers provide the `molview-spec` skill and its reference
files as MCP resources. MCP clients can discover the skill and retrieve its
guidance when needed.

### Structure Comparison Workbench

`pdbe_compare_structures` opens `ui://pdbe/structure-comparison` in MCP Apps
clients. For example, compare deoxyhaemoglobin and oxyhaemoglobin alpha chains:

```json
{
  "reference_pdb_id": "4hhb",
  "reference_chain_id": "A",
  "mobile_pdb_id": "1hho",
  "mobile_chain_id": "A"
}
```

Chain selectors use exact, case-sensitive **label chain IDs**. Both chains must
have a shared UniProt mapping and occur in the same PDBe superposition segment.
If several mappings or segments qualify, supply `uniprot_accession` or the
1-based `segment_index` reported in the error. Unsupported pairs return a clear
unavailable result.

The shared API executor retrieves chain metadata, the generated SIFTS mappings
tool, and the registered `/uniprot/superposition/{uniprot_accession}` operation.
The existing HTTP client retrieves PDBe's static matrix file at
`https://www.ebi.ac.uk/pdbe/static/superpose/matrices/{accession}`; this file is
outside the OpenAPI schema. Both source matrices are applied unchanged in Mol*.
There is no additional structural fitting or coordinate-processing dependency.

The plain TypeScript interface shows a two-chain overlay, visibility controls,
per-residue displacement colours and an interactive chart/table. Selecting a
mapped residue in either structure highlights its partner and makes the pair
available in MCP context. CSV export includes residue IDs, insertion codes, alternate
locations, source links and retrieval time; selectable text is also provided.

**PDBe supplies the alignment and Mol* supplies all geometric calculations.**
Mol* `Mat4.ofRows` converts the supplied matrices for MolViewSpec, which applies
them to the structures. The app reads displayed coordinates through Mol*
`unit.conformation.position`, measures each pair with `Vec3.distance`, and uses
Mol* `arrayRms` for the aligned Cα RMSD. No additional fitting is performed.
Camera bounds and displacement colours also use Mol* functions.

Scores use Mol*'s residue trace-atom selection in the first deposited model,
retaining only occupied Cα atoms with finite positions. This follows Mol*'s
alternate-location choice; the app does not choose alternates by occupancy.
Only unambiguous, equal-length SIFTS segments establish residue correspondence.
Coverage displays observed and mapped pair counts alongside the source segment
range; the app does not calculate coverage percentages. Missing Cα pairs remain
in the table and export; RMSD requires at least three observed pairs. Full chains
are displayed, while scores cover the selected segment. MCP context and CSV
include the calculation providers. Non-UI clients receive mapping counts,
transforms and provenance; Mol* metrics become available when the app loads.

### API reuse and annotations

The API MCP tools and Structure Explorer share the `OpenAPIToMCPGenerator`
executor. It resolves registered GET operations from the configured OpenAPI
schema and returns raw JSON with source and retrieval time. API tools format
that JSON as text or TOON; the app normalizes it directly. The HTTP server
shares one executor instance between `/api/`, `/apps/`, and `/all/`.
`enableMCP` controls model-visible tools; schema GET operations such as residue
listing can also be called internally by the app. This shares request handling
and schema loading, but does not cache API responses across calls.

For each polymer entity, the app retrieves domains, residue annotations,
binding sites, and UniProt mapping tracks through that executor. Choose a source
under **Domains & residue annotations** to colour the structure. Clicking a
feature focuses its mapped segments. Hover tooltips and **Annotations at
selection** retain source labels, accessions, scores, and evidence links.
Selecting or clearing a residue preserves the chosen annotation colour layer.

Track PDB indices are mapped to label residue positions, preserving separate
segments of discontinuous domains. Tracks restricted to a best chain retain
that chain scope. Binding-site segments carrying a bound molecule ID use that
instance's author chain. UniProt positions are translated only through explicit,
equal-length SIFTS segments covering the requested interval. Ambiguous,
unsupported, or unmappable segments are omitted with a warning; missing optional
annotation services do not prevent structure loading. The full annotation data
is delivered in tool-result metadata; the model receives a compact summary and
annotation evidence for the selected residue. Mol* renders the supplied data;
its independent domain-annotation fetching is not enabled.

Run the annotation mapping checks with:

```bash
uv run pytest tests/test_api_tools.py tests/test_apps.py -o addopts=''
cd apps/structure-explorer
node --experimental-strip-types --test tests/annotations.test.mjs
```

## Worked Examples

See the [`examples/`](examples/) directory for worked examples showing how an LLM can answer real structural-biology questions by combining PDBe API and PDBe Search MCP tools. These examples demonstrate:

- Finding protein functions, organisms, and ligands
- Searching for specific structure types (cryo-EM, high-resolution)
- Finding related entries and EMDB maps
- Understanding ligand interactions and glycosylation


## Prerequisites

- **Python 3.10+** - Required for the server runtime
- **[uv](https://github.com/astral-sh/uv)** - Fast Python package manager and dependency resolver

## Installation

### Quick Start

**Run directly from PyPI:**
```bash
uvx pdbe-mcp-server
```

The tool is available on PyPI and can be run directly with `uvx` without any installation step.

### Alternative: Local Development Installation

For development work or customization:

1. **Clone and navigate to the repository:**
   ```bash
   git clone https://github.com/PDBeurope/PDBe-MCP-Servers.git
   cd PDBe-MCP-Servers
   ```

2. **Create a virtual environment:**
   ```bash
   uv venv
   ```

3. **Install with uv:**
   ```bash
   uv pip install .
   ```

## AI Client Integration

### Configuration

1. **Open your AI client's MCP configuration.**

   MCP-compatible clients use different settings locations and file formats. Many JSON-based clients use an `mcpServers` object, while some clients provide commands or a settings UI for adding servers.

2. **Add the recommended PDBe MCP server configuration.**

   For JSON-based clients that support `mcpServers`, add:

   **For PyPI installation (recommended):**
   ```json
   {
     "mcpServers": {
       "PDBe API Server": {
         "command": "uvx",
         "args": [
           "pdbe-mcp-server",
           "--server-type",
           "pdbe_api_server"
         ]
       },
       "PDBe Search Server": {
         "command": "uvx",
         "args": [
           "pdbe-mcp-server",
           "--server-type",
           "pdbe_search_server"
         ]
       }
     }
   }
   ```

   **For local development installation:**
   ```json
   {
     "mcpServers": {
       "PDBe API": {
         "command": "/usr/local/bin/uv",
         "args": [
           "run",
           "--directory",
           "/path/to/your/PDBe-MCP-Servers",
           "pdbe-mcp-server",
           "--server-type",
           "pdbe_api_server"
         ]
       },
       "PDBe Search": {
         "command": "/usr/local/bin/uv",
         "args": [
           "run",
           "--directory",
           "/path/to/your/PDBe-MCP-Servers",
           "pdbe-mcp-server",
           "--server-type",
           "pdbe_search_server"
         ]
       }
     }
   }
   ```

  > **Note:**
  > - For the PyPI installation method, ensure `uvx` is available in your PATH (this comes with uv)
  > - For local development, ensure that `uv` is installed and the `/path/to/your/PDBe-MCP-Servers` matches your actual directory

   Add the graph server only if you have a local PDBe-KB Neo4j graph database configured. See [Advanced Graph Server Configuration](#advanced-graph-server-configuration).

3. **Restart or reload your AI client** to load the new configuration.

### Antigravity Example

In Antigravity, open **Manage MCP Servers** and select **View raw config**, or edit `~/.gemini/antigravity/mcp_config.json`, then add the PDBe server entries:

```json
{
  "mcpServers": {
    "PDBe API Server": {
      "command": "uvx",
      "args": [
        "pdbe-mcp-server",
        "--server-type",
        "pdbe_api_server"
      ]
    },
    "PDBe Search Server": {
      "command": "uvx",
      "args": [
        "pdbe-mcp-server",
        "--server-type",
        "pdbe_search_server"
      ]
    }
  }
}
```

### Codex Example

In Codex, add the PDBe MCP servers with the CLI:

```bash
codex mcp add pdbe-api -- uvx pdbe-mcp-server --server-type pdbe_api_server
codex mcp add pdbe-search -- uvx pdbe-mcp-server --server-type pdbe_search_server
codex mcp list
```

For a local development checkout, point Codex at the repository directory:

```bash
codex mcp add pdbe-api-local -- uv run --directory /path/to/your/PDBe-MCP-Servers pdbe-mcp-server --server-type pdbe_api_server
codex mcp add pdbe-search-local -- uv run --directory /path/to/your/PDBe-MCP-Servers pdbe-mcp-server --server-type pdbe_search_server
```

### Using in an AI Client

Once configured, you can access PDBe tools directly in your AI client conversations:

- **Search for protein structures**: "Find structures for UniProt accession P12345"
- **Query structure releases**: "Show me all structures released this month grouped by experimental method"
- **Advanced search queries**: "Find all X-ray crystal structures with resolution better than 2.0 Å from 2024"

The tools will appear in your AI client's tools interface, where you can enable or disable them as needed.

### Server Types

- **`pdbe_api_server`**: Core PDBe REST API access with essential structural data
- **`pdbe_search_server`**: Advanced Solr-based search capabilities for complex structural queries and data analysis
- **`pdbe_graph_server`**: Advanced/local server for inspecting the PDBe-KB graph schema and optionally executing read-only Cypher queries against a locally configured Neo4j database

## Tool Reference

### API Server Tools

The `pdbe_api_server` generates tools from the PDBe API OpenAPI specification. Use this server for core PDBe REST API data, such as entries, assemblies, molecules, ligands, publications, and validation information.

### Search Server Tools

#### `get_pdbe_search_schema`
Retrieves the complete Solr search schema showing all available fields, data types, and descriptions. Use this to understand what fields you can search and filter on.

**Example usage:**
```
"Show me the search schema for PDBe structures"
```

#### `run_pdbe_search_query`
Execute Solr-style search queries with flexible field selection, filter queries, facets, grouping, sorting, and pagination options.

**Parameters:**
- `query` (required): Raw Solr query string passed as `q` (e.g., `*:*`, `pdb_id:1cbs`, `text:*kinase*`, `resolution:[0 TO 2.0]`)
- `fl` (optional): Field list as a string or array of field names to include in results
- `filters` (optional): Backwards-compatible alias for `fl`
- `fq` (optional): Filter query string or array of filter query strings
- `sort` (optional): Sort criteria (e.g., `release_date desc`, `resolution asc`)
- `start` (optional): Starting index for pagination (default: 0)
- `rows` (optional): Number of results to return (default: 10)
- `facet` (optional): Enable Solr faceting
- `facet_fields` (optional): Field facet string or array, sent as `facet.field`
- `facet_queries` (optional): Query facet string or array, sent as `facet.query`
- `facet_limit`, `facet_mincount`, `facet_sort` (optional): Common facet controls
- `group` (optional): Enable Solr grouping
- `group_field` (optional): Grouping field string or array, sent as `group.field`
- `group_limit`, `group_offset`, `group_sort` (optional): Common grouping controls
- `params` (optional): Object of additional Solr parameters for advanced use

**Example queries:**
```
{
  "query": "*:*",
  "fq": ["release_date:[2025-10-01T00:00:00Z TO 2025-10-31T23:59:59Z]"],
  "group": true,
  "group_field": "experimental_method",
  "rows": 0
}

{
  "query": "*:*",
  "fq": ["experimental_method:\"X-ray diffraction\"", "resolution:[0 TO 2.0]"],
  "fl": ["pdb_id", "title", "resolution", "experimental_method"],
  "sort": "resolution asc",
  "rows": 20
}

{
  "query": "text:*ATP*",
  "facet": true,
  "facet_fields": ["ligand_name", "experimental_method"],
  "facet_mincount": 1,
  "rows": 10
}
```

### Search Field Examples

Common searchable fields include:
- `pdb_id`: PDB entry identifier
- `experimental_method`: Structure determination method
- `release_date`: Structure release date
- `resolution`: Structure resolution (Å)
- `molecule_type`: Type of molecule (protein, DNA, RNA, etc.)
- `organism_scientific_name`: Source organism
- `ligand_name`: Bound ligands
- `title`: Structure title/description

Use `get_pdbe_search_schema` to discover all available fields and their descriptions.

## Development and Advanced Usage
### Docker (single container with Nginx)

Build and run all three MCP servers behind Nginx using the included Dockerfile:

```bash
docker build -t pdbe-mcp-servers:latest .
docker run --rm -p 8080:8080 pdbe-mcp-servers:latest
```

Endpoints:
- `http://localhost:8080/api/sse` and `http://localhost:8080/api/messages/`
- `http://localhost:8080/graph/sse` and `http://localhost:8080/graph/messages/`
- `http://localhost:8080/search/sse` and `http://localhost:8080/search/messages/`
- Health: `http://localhost:8080/health`


### Development Installation

For contributing or development work, first clone the repository and then install in editable mode:
```bash
git clone https://github.com/PDBeurope/PDBe-MCP-Servers.git
cd PDBe-MCP-Servers
uv sync --all-extras --dev
```

**Node.js** (optional) - For using the MCP Inspector development tool

### Starting the Server Manually

Most users should run the API server, the Search server, or both.

#### PDBe API Server
Provides access to core PDBe REST API endpoints:

**Using PyPI installation:**
```bash
uvx pdbe-mcp-server --server-type pdbe_api_server --transport sse
```

**Using local development:**
```bash
uv run pdbe-mcp-server --server-type pdbe_api_server --transport sse
```

<<<<<<< HEAD
#### PDBe Graph Database Server
Enables complex relationship queries and network analysis:

**Using PyPI installation:**
```bash
uvx pdbe-mcp-server --server-type pdbe_graph_server --transport sse
```

**Using local development:**
```bash
uv run pdbe-mcp-server --server-type pdbe_graph_server --transport sse
```

### Neo4j Cypher Query Support

This server supports executing custom Cypher queries against a Neo4j graph database. The `pdbe_run_cypher_query` tool is only available when the following environment variables are set:

- `NEO4J_URI`: The Neo4j database URL (e.g., `bolt://localhost:7687`)
- `NEO4J_USERNAME`: The Neo4j username
- `NEO4J_PASSWORD`: The Neo4j password
- `NEO4J_DATABASE` (optional): The database name. When set, this is passed to the Neo4j driver for Neo4j 4+. For Neo4j 3.5 compatibility, omit this variable to use the default database.

To use this feature, install the neo4j driver:
```bash
pip install neo4j
```

**Security:** Only read-only queries are allowed (MATCH, OPTIONAL MATCH). Write operations (MERGE, CREATE, DELETE, REMOVE, SET, LOAD CSV, FOREACH) are blocked to prevent accidental data modification.

**Example usage:**
```
Execute query: MATCH (s:Structure) WHERE s.PDB_ID = '1abc' RETURN s.PDB_ID as id, s.TITLE as title
```

The tool response is formatted as JSON by default, but can be converted to TOON format by setting `TOON_ENABLED=true`.

=======
>>>>>>> main
#### PDBe Search Server
Provides advanced Solr-based search and analytics capabilities:

**Using PyPI installation:**
```bash
uvx pdbe-mcp-server --server-type pdbe_search_server --transport sse
```

**Using local development:**
```bash
uv run pdbe-mcp-server --server-type pdbe_search_server --transport sse
```

The server will start at `http://localhost:8000/sse` by default.

## Advanced Graph Server Configuration

The `pdbe_graph_server` is intended for users who have downloaded and configured the PDBe-KB graph database in their own environment. PDBe does not provide a public running Neo4j instance for this MCP server to query.

To set up the graph database locally, follow the PDBe-KB graph documentation:
https://www.ebi.ac.uk/pdbe/pdbe-kb/graph

Once your local Neo4j database is running, set these environment variables before starting the graph server:

- `NEO4J_URL`: The Neo4j database URL (e.g., `bolt://localhost:7687`)
- `NEO4J_USERNAME`: The Neo4j username
- `NEO4J_PASSWORD`: The Neo4j password
- `NEO4J_DATABASE` (optional): The database name. When set, this is passed to the Neo4j driver for Neo4j 4+. For Neo4j 3.5 compatibility, omit this variable to use the default database.

The Neo4j driver is included in this package's dependencies.

### MCP Client Graph Configuration

Add this server only when the environment variables above are available to your AI client.

**For PyPI installation:**
```json
{
  "mcpServers": {
    "PDBe Graph Server": {
      "command": "uvx",
      "args": [
        "pdbe-mcp-server",
        "--server-type",
        "pdbe_graph_server"
      ],
      "env": {
        "NEO4J_URL": "bolt://localhost:7687",
        "NEO4J_USERNAME": "neo4j",
        "NEO4J_PASSWORD": "your-password"
      }
    }
  }
}
```

**For local development installation:**
```json
{
  "mcpServers": {
    "PDBe Graph": {
      "command": "/usr/local/bin/uv",
      "args": [
        "run",
        "--directory",
        "/path/to/your/PDBe-MCP-Servers",
        "pdbe-mcp-server",
        "--server-type",
        "pdbe_graph_server"
      ],
      "env": {
        "NEO4J_URL": "bolt://localhost:7687",
        "NEO4J_USERNAME": "neo4j",
        "NEO4J_PASSWORD": "your-password"
      }
    }
  }
}
```

**Codex example:**
```bash
codex mcp add pdbe-graph \
  --env NEO4J_URL=bolt://localhost:7687 \
  --env NEO4J_USERNAME=neo4j \
  --env NEO4J_PASSWORD=your-password \
  -- uvx pdbe-mcp-server --server-type pdbe_graph_server
```

### Starting the Graph Server Manually

**Using PyPI installation:**
```bash
uvx pdbe-mcp-server --server-type pdbe_graph_server --transport sse
```

**Using local development:**
```bash
uv run pdbe-mcp-server --server-type pdbe_graph_server --transport sse
```

### Graph Server Tools

#### `pdbe_graph_nodes`
Retrieves metadata about all node types (labels) defined in the PDBe graph database schema. This uses the public graph schema and does not require local Neo4j credentials.

**Example usage:**
```
"Show me all node types in the PDBe graph database"
```

#### `pdbe_graph_edges`
Retrieves metadata about all relationship types (edges) defined in the PDBe graph database schema. This uses the public graph schema and does not require local Neo4j credentials.

**Example usage:**
```
"Show me all relationship types in the PDBe graph database"
```

#### `pdbe_graph_node_relationships`
Verifies selected node labels and returns the incoming, outgoing, and self-loop relationship patterns defined for each label. This uses the public graph schema and does not require local Neo4j credentials.

**Parameters:**
- `node_labels` (required): List of exact, case-sensitive node labels to verify.

**Example usage:**
```
"Verify relationships for Entry, Entity, and UniProt"
```

#### `pdbe_graph_example_queries`
Retrieves example Cypher queries that demonstrate how to interact with the PDBe graph database. This uses the public graph schema and does not require local Neo4j credentials.

**Example usage:**
```
"Give me example Cypher queries for exploring the PDBe graph"
```

#### `pdbe_run_cypher_query`
Execute custom read-only Cypher queries against your configured Neo4j graph database. This tool is only available when Neo4j environment variables are configured.

**Parameters:**
- `cypher_query` (required): The Cypher query to execute. Only MATCH and OPTIONAL MATCH queries are allowed.

**Example usage:**
```
"Execute query: MATCH (s:Structure) WHERE s.PDB_ID = '1abc' RETURN s.TITLE as title"
"Find ligands: MATCH (s:Structure)-[:HAS_LIGAND]->(l:Ligand) WHERE s.PDB_ID = '1abc' RETURN l.name"
```

**Security:** Only read-only queries are allowed (MATCH, OPTIONAL MATCH). Write operations (MERGE, CREATE, DELETE, REMOVE, SET, LOAD CSV, FOREACH) are blocked to prevent accidental data modification.

The tool response is formatted as JSON by default, but can be converted to TOON format by setting `TOON_ENABLED=true`.

## Development and Testing

Explore available tools and test API responses:
```bash
npx @modelcontextprotocol/inspector
```

The MCP Inspector provides an interactive interface to browse tools, test queries, and validate responses before integrating with your application.

## Server Configuration

### Transport Options

- **stdio**: Default mode - Optimal for direct MCP client integration
- **SSE (Server-Sent Events)**: `--transport sse` - Best for web-based clients and development

### Experimental TOON Output

You can enable experimental TOON-formatted output for PDBe API tool responses and Neo4j Cypher query results by setting
the environment variable `TOON_ENABLED=true`.
See the TOON format specification at https://toonformat.dev/.

- If TOON encoding fails for any reason, the server falls back to JSON output.
- This feature is experimental and intended for opt-in usage only.

## Troubleshooting

### Common Issues

**"Command not found" errors:**
- Ensure `uv` is installed and in your PATH
- Verify the full path to `uv` in your AI client's MCP configuration

**Missing tools in your AI client:**
- Restart or reload your AI client after configuration changes
- Check your AI client's MCP server logs for errors
- Verify JSON syntax in your configuration file

## Resources

- **[Model Context Protocol](https://modelcontextprotocol.org/)** - Official MCP documentation and specifications
- **[PDBe API Documentation](https://www.ebi.ac.uk/pdbe/api/v2/)** - Complete API reference and examples
- **[PDBe Graph Database](https://www.ebi.ac.uk/pdbe/pdbe-kb/graph)** - Advanced querying and relationship mapping
- **[Antigravity MCP Documentation](https://antigravity.google/docs/mcp)** - MCP setup instructions for Antigravity
- **[OpenAI Docs MCP](https://platform.openai.com/docs/docs-mcp)** - Codex MCP configuration examples

## License

This project is licensed under the Apache License, Version 2.0 - see the [LICENSE](LICENSE) file for details.

## Support

For questions, bug reports, or feature requests:
- **Issues**: Use the [GitHub Issues](https://github.com/PDBeurope/PDBe-MCP-Servers/issues) tracker
- **PDBe Helpdesk**: Visit the [PDBe Help & Support](https://www.ebi.ac.uk/about/contact/support/pdbe) pages
