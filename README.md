# PDBe MCP Servers

A set of Model Context Protocol (MCP) servers that provides seamless access to the Protein Data Bank in Europe (PDBe) API and [PDBe Graph Database](https://www.ebi.ac.uk/pdbe/pdbe-kb/graph). This server exposes PDBe's comprehensive structural biology data as MCP tools, enabling direct integration with Claude Desktop and other AI-powered applications.

## Prerequisites

- **Python 3.10+** - Required for the server runtime
- **[uv](https://github.com/astral-sh/uv)** - Fast Python package manager and dependency resolver
- **Node.js** (optional) - For using the MCP Inspector development tool

## Installation

### Quick Start

1. **Clone and navigate to the repository:**
   ```bash
   git clone https://github.com/PDBeurope/PDBe-MCP-Servers.git
   cd pdbe-mcp-server
   ```

2. **Install with uv:**
   ```bash
   uv pip install .
   ```

### Development Installation

For contributing or development work:
```bash
uv pip install -e ".[dev]"
```

## Usage

### Starting the Server

Choose between two server types based on your needs:

#### PDBe API Server
Provides access to core PDBe REST API endpoints:
```bash
uv run pdbe-mcp-server --server-type pdbe_api_server --transport sse
```

#### PDBe Graph Database Server
Enables complex relationship queries and network analysis:
```bash
uv run pdbe-mcp-server --server-type pdbe_graph_server --transport sse
```

The server will start at `http://localhost:8000/sse` by default.

### Development and Testing

Explore available tools and test API responses:
```bash
npx @modelcontextprotocol/inspector
```

The MCP Inspector provides an interactive interface to browse tools, test queries, and validate responses before integrating with your application.

## Claude Desktop Integration

### Configuration

1. **Locate your Claude Desktop configuration file:**
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
   - **Linux**: `~/.config/Claude/claude_desktop_config.json`

2. **Add the PDBe MCP server configuration:**
   ```json
   {
     "mcpServers": {
       "PDBe API": {
         "command": "/usr/local/bin/uv",
         "args": [
           "run",
           "--directory",
           "/path/to/your/pdbe-mcp-server",
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
           "/path/to/your/pdbe-mcp-server",
           "pdbe-mcp-server",
           "--server-type",
           "pdbe_graph_server"
         ]
       }
     }
   }
   ```

3. **Restart Claude Desktop** to load the new configuration.

### Using in Claude

Once configured, you can access PDBe tools directly in your Claude conversations:

- **Search for protein structures**: "Find structures for UniProt accession P12345"
- **Explore molecular interactions**: "Show me ligand binding sites for this protein"

The tools will appear in Claude's "Search and tools" interface, where you can enable or disable them as needed.

## Server Configuration

### Transport Options

- **SSE (Server-Sent Events)**: `--transport sse` - Best for web-based clients and development
- **stdio**: Default mode - Optimal for direct client integration like Claude Desktop

### Server Types

- **`pdbe_api_server`**: Core PDBe REST API access with essential structural data
- **`pdbe_graph_server`**: Know more about the PDBe Graph Database and generate Cypher queries for accessing complex relationships and interactions.

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
