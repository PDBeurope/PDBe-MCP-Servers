# PDBe MCP Servers

A set of Model Context Protocol (MCP) servers that provides seamless access to the Protein Data Bank in Europe (PDBe) API, [PDBe Graph Database](https://www.ebi.ac.uk/pdbe/pdbe-kb/graph), and PDBe Search. This server exposes PDBe's comprehensive structural biology data as MCP tools, enabling direct integration with Claude Desktop and other AI-powered applications.

**Features:**
- **PDBe API Server**: Access core structural data through REST API endpoints
- **PDBe Graph Server**: Query complex relationships and molecular interactions
- **PDBe Search Server**: Perform advanced Solr-based searches across structural data

## Prerequisites

- **Python 3.10+** - Required for the server runtime
- **[uv](https://github.com/astral-sh/uv)** - Fast Python package manager and dependency resolver

## Installation

### Quick Start

**Install directly from PyPI:**
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

2. **Add the PDBe MCP server configuration:**

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
       "PDBe Graph Server": {
         "command": "uvx",
         "args": [
           "pdbe-mcp-server",
           "--server-type",
           "pdbe_graph_server"
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
       "PDBe Graph": {
         "command": "/usr/local/bin/uv",
         "args": [
           "run",
           "--directory",
           "/path/to/your/PDBe-MCP-Servers",
           "pdbe-mcp-server",
           "--server-type",
           "pdbe_graph_server"
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

3. **Restart Claude Desktop** to load the new configuration.

### Using in Claude

Once configured, you can access PDBe tools directly in your Claude conversations:

- **Search for protein structures**: "Find structures for UniProt accession P12345"
- **Query structure releases**: "Show me all structures released this month grouped by experimental method"
- **Explore molecular interactions**: "Show me ligand binding sites for this protein"
- **Advanced search queries**: "Find all X-ray crystal structures with resolution better than 2.0 Å from 2024"

The tools will appear in Claude's "Search and tools" interface, where you can enable or disable them as needed.

### Server Types

- **`pdbe_api_server`**: Core PDBe REST API access with essential structural data
- **`pdbe_graph_server`**: Know more about the PDBe Graph Database and generate Cypher queries for accessing complex relationships and interactions
- **`pdbe_search_server`**: Advanced Solr-based search capabilities for complex structural queries and data analysis

## Search Server Features

The PDBe Search Server provides powerful querying capabilities through the PDBe Solr search interface:

### Available Tools

#### `pdbe_graph_nodes`
Retrieves metadata about all node types (labels) defined in the PDBe graph database schema. Use this to understand the different types of entities and their properties.

**Example usage:**
```
"Show me all node types in the PDBe graph database"
```

#### `pdbe_graph_edges`
Retrieves metadata about all relationship types (edges) defined in the PDBe graph database schema. Use this to understand how entities are connected.

**Example usage:**
```
"Show me all relationship types in the PDBe graph database"
```

#### `pdbe_graph_example_queries`
Retrieves example Cypher queries that demonstrate how to interact with the PDBe graph database.

**Example usage:**
```
"Give me example Cypher queries for exploring the PDBe graph"
```

#### `pdbe_run_cypher_query`
Execute custom read-only Cypher queries against a Neo4j graph database. Only available when Neo4j environment variables are configured.

**Parameters:**
- `cypher_query` (required): The Cypher query to execute. Only MATCH and OPTIONAL MATCH queries are allowed.

**Example usage:**
```
"Execute query: MATCH (s:Structure) WHERE s.PDB_ID = '1abc' RETURN s.TITLE as title"
"Find ligands: MATCH (s:Structure)-[:HAS_LIGAND]->(l:Ligand) WHERE s.PDB_ID = '1abc' RETURN l.name"
```

> **Note:** Write operations (MERGE, CREATE, DELETE, REMOVE, SET, LOAD CSV, FOREACH) are blocked for safety.

#### `get_search_schema`
Retrieves the complete Solr search schema showing all available fields, data types, and descriptions. Use this to understand what fields you can search and filter on.

**Example usage:**
```
"Show me the search schema for PDBe structures"
```

#### `run_search_query`
Execute advanced search queries with flexible filtering, sorting, and pagination options.

**Parameters:**
- `query` (required): Solr query string (e.g., `pdb_id:1cbs`, `experimental_method:"X-ray diffraction"`)
- `filters` (optional): Array of field names to include in results
- `sort` (optional): Sort criteria (e.g., `release_date desc`, `resolution asc`)
- `start` (optional): Starting index for pagination (default: 0)
- `rows` (optional): Number of results to return (default: 10)

**Example queries:**
```
"Find all structures released in October 2025 grouped by experimental method"
"Search for all X-ray crystal structures with resolution better than 2.0 Å"
"Show me the latest 20 cryo-EM structures sorted by release date"
"Find structures containing ligand 'ATP' with specific binding sites"
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
uv pip install -e ".[dev]"
```

**Node.js** (optional) - For using the MCP Inspector development tool

### Starting the Server Manually

Choose between two server types based on your needs:

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

### Development and Testing

Explore available tools and test API responses:
```bash
npx @modelcontextprotocol/inspector
```

The MCP Inspector provides an interactive interface to browse tools, test queries, and validate responses before integrating with your application.

### Server Configuration

#### Transport Options

- **stdio**: Default mode - Optimal for direct client integration like Claude Desktop
- **SSE (Server-Sent Events)**: `--transport sse` - Best for web-based clients and development

#### Experimental TOON Output

You can enable experimental TOON-formatted output for PDBe API tool responses by setting
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
