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

**Install directly as a uv tool:**
```bash
uv tool install git+https://github.com/PDBeurope/PDBe-MCP-Servers.git
```

This installs `pdbe-mcp-server` as a global tool that can be used directly with `uvx`.

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

   **For tool installation (recommended):**
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
   }
   ```

  > **Note:**
  > - For the tool installation method, ensure `uvx` is available in your PATH (this comes with uv)
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

**Using tool installation:**
```bash
uvx pdbe-mcp-server --server-type pdbe_api_server --transport sse
```

**Using local development:**
```bash
uv run pdbe-mcp-server --server-type pdbe_api_server --transport sse
```

#### PDBe Graph Database Server
Enables complex relationship queries and network analysis:

**Using tool installation:**
```bash
uvx pdbe-mcp-server --server-type pdbe_graph_server --transport sse
```

**Using local development:**
```bash
uv run pdbe-mcp-server --server-type pdbe_graph_server --transport sse
```

#### PDBe Search Server
Provides advanced Solr-based search and analytics capabilities:

**Using tool installation:**
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
