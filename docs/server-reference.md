# Server Reference

[Project README](../README.md)

## API and Search tools


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

## Advanced Graph Server Configuration


The `pdbe_graph_server` is intended for users who have downloaded and configured the PDBe-KB graph database in their own environment. PDBe does not provide a public running Neo4j instance for this MCP server to query.

To set up the graph database locally, follow the PDBe-KB graph documentation:
https://www.ebi.ac.uk/pdbe/pdbe-kb/graph

Once your local Neo4j database is running, set these environment variables before starting the graph server:

- `NEO4J_URI`: The Neo4j database URL (e.g., `bolt://localhost:7687`)
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
        "NEO4J_URI": "bolt://localhost:7687",
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
        "NEO4J_URI": "bolt://localhost:7687",
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
  --env NEO4J_URI=bolt://localhost:7687 \
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

## Transports and deployment

Stdio is the default for `pdbe-mcp-server`. Choose a server with `--server-type`:
`pdbe_api_server`, `pdbe_search_server`, `pdbe_graph_server`, `pdbe_apps_server`,
or `all`.

For Streamable HTTP:

```bash
uv run pdbe-mcp-remote-server --all
```

Connect to `http://127.0.0.1:8000/api/`, `/search/`, `/graph/`, or `/apps/`.
The `--all` flag also exposes `/all/`. `ROOT_PREFIX` applies to these paths.
Health endpoints are `/health` and `/ready`.

For legacy SSE, select a server and add `--transport sse`:

```bash
uv run pdbe-mcp-server --server-type pdbe_search_server --transport sse
```

The SSE endpoint is `http://localhost:8000/sse`.

### Docker

The Dockerfile builds the molecular app and runs the Streamable HTTP server
with all servers enabled:

```bash
docker build -t pdbe-mcp-servers:latest .
docker run --rm -p 8000:8000 pdbe-mcp-servers:latest
```

Use the HTTP endpoints above on port 8000.

## Output format


You can enable experimental TOON-formatted output for PDBe API tool responses and Neo4j Cypher query results by setting
the environment variable `TOON_ENABLED=true`.
See the TOON format specification at https://toonformat.dev/.

- If TOON encoding fails for any reason, the server falls back to JSON output.
- This feature is experimental and intended for opt-in usage only.


## Troubleshooting

- **Command not found:** ensure `uv` and `uvx` are in your client's PATH, or use
  the full executable path in the client configuration.
- **Missing tools:** reload the client, check its MCP logs, and validate the
  configuration JSON.
- **Inspect tools:** run `npx @modelcontextprotocol/inspector` to browse tools
  and test responses.
