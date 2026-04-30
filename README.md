# PDBe MCP Servers

A set of Model Context Protocol (MCP) servers that provides seamless access to the Protein Data Bank in Europe (PDBe) API and PDBe Search. These servers expose PDBe's comprehensive structural biology data as MCP tools, enabling direct integration with Claude Desktop and other AI-powered applications.

The package also includes an advanced PDBe Graph server for users who run their own local PDBe-KB Neo4j graph database. PDBe does not provide a public running graph database instance for this MCP server to query, so most users should start with the API and Search servers.

**Features:**
- **PDBe API Server**: Access core structural data through REST API endpoints
- **PDBe Search Server**: Perform advanced Solr-based searches across structural data
- **PDBe Graph Server**: Inspect the graph schema and, with a local PDBe-KB Neo4j setup, query complex relationships and molecular interactions

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

## Claude Desktop Integration

### Configuration

1. **Locate your Claude Desktop configuration file:**
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
   - **Linux**: `~/.config/Claude/claude_desktop_config.json`

2. **Add the recommended PDBe MCP server configuration:**

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

3. **Restart Claude Desktop** to load the new configuration.

### Using in Claude

Once configured, you can access PDBe tools directly in your Claude conversations:

- **Search for protein structures**: "Find structures for UniProt accession P12345"
- **Query structure releases**: "Show me all structures released this month grouped by experimental method"
- **Advanced search queries**: "Find all X-ray crystal structures with resolution better than 2.0 Å from 2024"

The tools will appear in Claude's tools interface, where you can enable or disable them as needed.

### Server Types

- **`pdbe_api_server`**: Core PDBe REST API access with essential structural data
- **`pdbe_search_server`**: Advanced Solr-based search capabilities for complex structural queries and data analysis
- **`pdbe_graph_server`**: Advanced/local server for inspecting the PDBe-KB graph schema and optionally executing read-only Cypher queries against a locally configured Neo4j database

## Tool Reference

### API Server Tools

The `pdbe_api_server` generates tools from the PDBe API OpenAPI specification. Use this server for core PDBe REST API data, such as entries, assemblies, molecules, ligands, publications, and validation information.

### Search Server Tools

#### `get_search_schema`
Retrieves the complete Solr search schema showing all available fields, data types, and descriptions. Use this to understand what fields you can search and filter on.

**Example usage:**
```
"Show me the search schema for PDBe structures"
```

#### `run_search_query`
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

Use `get_search_schema` to discover all available fields and their descriptions.

## Development and Advanced Usage

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

### Claude Desktop Graph Configuration

Add this server only when the environment variables above are available to Claude Desktop.

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

- **stdio**: Default mode - Optimal for direct client integration like Claude Desktop
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
- Verify the full path to `uv` in your Claude Desktop configuration

**Missing tools in Claude:**
- Restart Claude Desktop after configuration changes
- Check the Claude Desktop logs for MCP server errors
- Verify JSON syntax in your configuration file

## Resources

- **[Model Context Protocol](https://modelcontextprotocol.org/)** - Official MCP documentation and specifications
- **[PDBe API Documentation](https://www.ebi.ac.uk/pdbe/api/v2/)** - Complete API reference and examples
- **[PDBe Graph Database](https://www.ebi.ac.uk/pdbe/pdbe-kb/graph)** - Advanced querying and relationship mapping
- **[Claude Desktop](https://claude.ai/desktop)** - Download and setup instructions

## License

This project is licensed under the Apache License, Version 2.0 - see the [LICENSE](LICENSE) file for details.

## Support

For questions, bug reports, or feature requests:
- **Issues**: Use the [GitHub Issues](https://github.com/PDBeurope/PDBe-MCP-Servers/issues) tracker
- **PDBe Helpdesk**: Visit the [PDBe Help & Support](https://www.ebi.ac.uk/about/contact/support/pdbe) pages
