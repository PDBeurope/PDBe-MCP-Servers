import logging
import os
import re
from typing import Any

try:
    from typing import LiteralString
except ImportError:
    from typing_extensions import LiteralString

import mcp.types as types
from omegaconf import DictConfig

from pdbe_mcp_server import get_config
from pdbe_mcp_server.utils import HTMLStripper, HTTPClient

logger = logging.getLogger(__name__)

conf: DictConfig = get_config()

# Pre-compiled regular expressions
_WRITE_PATTERN = re.compile(
    r"\b(MERGE|CREATE|DELETE|REMOVE|SET|ADD|LOAD\s+CSV|FOREACH)\b", re.IGNORECASE
)

_ALLOWED_START_PATTERN = re.compile(
    r"^(?:MATCH|OPTIONAL\s+MATCH|CALL\s*\{[^}]*\})", re.IGNORECASE
)

_WRITE_KEYWORDS = [
    "MERGE",
    "CREATE",
    "DELETE",
    "REMOVE",
    "SET",
    "ADD",
    "LOAD CSV",
    "FOREACH",
]


def _get_neo4j_config_from_env() -> dict[str, str] | None:
    """
    Get Neo4j configuration from environment variables.

    Returns:
        Dictionary with neo4j_url, neo4j_username, neo4j_password, and neo4j_database,
        or None if not all required variables are set.
    """
    neo4j_uri = os.getenv("NEO4J_URI")
    neo4j_username = os.getenv("NEO4J_USERNAME")
    neo4j_password = os.getenv("NEO4J_PASSWORD")
    neo4j_database = os.getenv("NEO4J_DATABASE")

    if neo4j_uri and neo4j_username and neo4j_password:
        config = {
            "neo4j_url": neo4j_uri,
            "neo4j_username": neo4j_username,
            "neo4j_password": neo4j_password,
        }
        if neo4j_database:
            config["neo4j_database"] = neo4j_database
        return config
    return None


def _neo4j_enabled() -> bool:
    """Check if Neo4j environment variables are set."""
    return _get_neo4j_config_from_env() is not None


def _toon_enabled() -> bool:
    """Check if TOON output is enabled."""
    return os.getenv("TOON_ENABLED", "").lower() in ("true", "1", "yes")


def _validate_cypher_query(query: str) -> tuple[bool, str | None]:
    """
    Validate a Cypher query to ensure it is read-only.

    Args:
        query: The Cypher query to validate.

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is None.
    """
    # Remove comments and normalize whitespace
    # //, /* */
    normalized = re.sub(r"/\*.*?\*/", "", query, flags=re.DOTALL)
    normalized = re.sub(r"//.*$", "", normalized, flags=re.MULTILINE)
    normalized = re.sub(r"--.*$", "", normalized, flags=re.MULTILINE)
    normalized = " ".join(normalized.split())

    # Check for any write operations
    if _WRITE_PATTERN.search(normalized):
        return (
            False,
            "Query contains potentially destructive operation",
        )

    # Verify query starts with allowed read operation
    if not _ALLOWED_START_PATTERN.search(normalized):
        return (
            False,
            "Query must start with MATCH, OPTIONAL MATCH, or CALL",
        )

    # Additional check: ensure no write operations after RETURN
    if "RETURN" in normalized.upper():
        return_parts = re.split(r"\bRETURN\b", normalized, flags=re.IGNORECASE)
        pre_return = return_parts[0]
        for keyword in _WRITE_KEYWORDS:
            if re.search(rf"\b{keyword}\b", pre_return, re.IGNORECASE):
                return (
                    False,
                    f"Query contains destructive operation '{keyword}' before RETURN",
                )

    return True, None


class GraphTools:
    """
    A class to handle PDBe graph-related operations.
    """

    WRITE_OPERATIONS = frozenset(_WRITE_KEYWORDS)

    def __init__(self) -> None:
        """
        Initialize the GraphTools object, load the graph schema, and prepare node and edge lists.
        Also initializes the Neo4j driver for reuse across all tool calls.
        """
        self.graph_schema: dict[str, Any] = self._get_graph_schema()
        self.node_dict: dict[Any, str] = {}
        self.nodes: list[dict[str, Any]] = self.get_nodes()
        self.edges: list[dict[str, Any]] = self.get_edges()

        # Initialize Neo4j driver once for reuse
        self._neo4j_driver: Any = None

    @property
    def neo4j_enabled(self) -> bool:
        """Check if Neo4j is configured."""
        return _neo4j_enabled()

    def get_pdbe_graph_nodes_tool(self) -> types.Tool:
        return types.Tool(
            name="pdbe_graph_nodes",
            description="""
    Retrieves metadata about all node types (also known as "labels") defined in the PDBe (PDBe-KB) graph database schema.
    This tool can be used to understand the different types of entities represented in the PDBe graph database, along with
    their properties and descriptions and then can be used to explore the graph more effectively by writing Cypher queries.
    This tool returns detailed information about each node label in the graph database. For every node label, it includes:
    - The label name (e.g., 'ValAngleOutlier', 'Antibody', 'Atom')
    - A human-readable description of the node type
    - A list of properties/parameters associated with this node type
    - For each property: the name and a brief description

    Expected Output Format (text):
    Label: ValAngleOutlier
    Description: Bond angle outliers based on wwPDB validation data.
    Properties:
      - ATOM0/1/2/3: Names of atoms involved in the angle which is an outlier.
      - MEAN: The ideal value of the bond angle.
      - OBS: The observed value of the bond angle.

    (Additional node labels follow the same format...)
    """,
            inputSchema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            annotations=types.ToolAnnotations(
                title="Get PDBe Graph Nodes",
                destructiveHint=False,
                readOnlyHint=True,
                idempotentHint=True,
            ),
        )

    def get_pdbe_graph_edges_tool(self) -> types.Tool:
        return types.Tool(
            name="pdbe_graph_edges",
            description="""
    Retrieves metadata about all relationship types (edges) defined in the PDBe (PDBe-KB) graph database schema.
    This tool can be used to understand the different types of relationships represented in the PDBe graph database, along with
    their start and end nodes, properties and descriptions and then can be used to explore the graph more effectively by writing Cypher queries.
    This tool returns detailed information about each relationship (edge) in the graph. For every relationship type, it includes:
    - The relationship label (e.g., 'HAS_OUTLIER', 'CONNECTS_TO')
    - A human-readable description of the relationship
    - The 'from' node label and 'to' node label, defining the direction and connectivity
    - A list of properties associated with the relationship
    - For each property: the name and a brief description

    Expected Output Format (text):
    Label: HAS_OUTLIER
    Description: Indicates a structure has validation outliers
    From: Structure
    To: ValAngleOutlier
    Properties:
      - since: The date when the outlier was detected
      - severity: The severity level of the outlier

    (Additional relationship types follow the same format...)
    """,
            inputSchema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            annotations=types.ToolAnnotations(
                title="Get PDBe Graph Edges",
                destructiveHint=False,
                readOnlyHint=True,
                idempotentHint=True,
            ),
        )

    def get_pdbe_graph_example_queries_tool(self) -> types.Tool:
        return types.Tool(
            name="pdbe_graph_example_queries",
            description="""
    Retrieves example Cypher queries for exploring the PDBe (PDBe-KB) graph database.
    This tool can be used to get sample queries that demonstrate how to interact with the PDBe graph database using Cypher.
    The tool returns a list of example queries, each with an question describing the purpose of the query and the corresponding Cypher query string.
    Expected Output Format (text):
    Question: Give me all the structures that are released in 2025.
    Query:
    MATCH (entry:Entry)
    WHERE entry.PDB_REV_DATE STARTS WITH '2025'
    RETURN entry.ID as PDB_ID,
        entry.TITLE as Title,
        entry.PDB_REV_DATE as Release_Date,
        entry.RESOLUTION as Resolution,
        entry.METHOD as Experimental_Method,
        entry.STATUS_CODE as Status
    ORDER BY entry.PDB_REV_DATE DESC
    (Additional example queries follow the same format...)
    """,
            inputSchema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            annotations=types.ToolAnnotations(
                title="Get PDBe Graph Example Queries",
                destructiveHint=False,
                readOnlyHint=True,
                idempotentHint=True,
            ),
        )

    def get_pdbe_graph_indexes_tool(self) -> types.Tool:
        """
        Tool to retrieve all indexes defined in the PDBe graph database schema.
        This helps in writing efficient Cypher queries by knowing which properties are indexed.
        """
        return types.Tool(
            name="pdbe_graph_indexes",
            description="""
    Retrieves metadata about all indexes defined in the PDBe (PDBe-KB) Neo4j graph database schema.
    This tool can be used to understand which node properties are indexed in the graph database, which is helpful
    when writing Cypher queries to ensure indexes are properly utilized for optimal performance.

    This tool returns detailed information about each index in the graph database. For every index, it includes:
    - The node label that the index applies to (e.g., 'Entry', 'Pfam', 'UniProt')
    - The property name that is indexed (e.g., 'ID', 'PFAM_ACCESSION', 'ACCESSION')

    Expected Output Format (text):
    Node: Entry
    Property: ID

    Node: Pfam
    Property: PFAM_ACCESSION

    Node: UniProt
    Property: ACCESSION

    (Additional indexes follow the same format...)
    """,
            inputSchema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            annotations=types.ToolAnnotations(
                title="Get PDBe Graph Indexes",
                destructiveHint=False,
                readOnlyHint=True,
                idempotentHint=True,
            ),
        )

    def get_pdbe_run_cypher_query_tool(self) -> types.Tool:
        return types.Tool(
            name="pdbe_run_cypher_query",
            description="""
    Execute a read-only Cypher query against the PDBe (PDBe-KB) Neo4j graph database.
    This tool allows you to run custom MATCH or OPTIONAL MATCH queries to explore complex relationships and data in the PDBe graph.
    Only read-only queries are allowed (MATCH, OPTIONAL MATCH, CALL {MATCH ...}).
    Write operations (MERGE, CREATE, DELETE, REMOVE, SET, LOAD CSV, FOREACH) are not permitted for safety.

    Parameters:
        cypher_query (required): The Cypher query to execute. Example: "MATCH (s:Structure) WHERE s.PDB_ID = '1abc' RETURN s"

    Expected Output Format:
        JSON array of result objects, or in TOON format if TOON_ENABLED is set.
        Each object represents a row in the result set with column names as keys.

    Example queries:
        MATCH (s:Structure) WHERE s.PDB_ID = '1abc' RETURN s.PDB_ID as id, s.TITLE as title
        MATCH (s:Structure)-[r:HAS_LIGAND]->(l:Ligand) WHERE s.PDB_ID = '1abc' RETURN l.name as ligand, count(r) as binding_count
        OPTIONAL MATCH (s:Structure) WHERE s.PDB_ID = '9xyz' RETURN s.PDB_ID as id, s.TITLE as title
    """,
            inputSchema={
                "type": "object",
                "properties": {
                    "cypher_query": {
                        "type": "string",
                        "description": "The Cypher query to execute. Only read-only operations are allowed.",
                    }
                },
                "required": ["cypher_query"],
                "additionalProperties": False,
            },
            annotations=types.ToolAnnotations(
                title="Run Cypher Query",
                destructiveHint=False,
                readOnlyHint=True,
                idempotentHint=True,
            ),
        )

    def _get_graph_schema(self) -> dict[str, Any]:
        """
        Retrieve the PDBe graph schema from the remote server and return it as a dictionary.
        Supports both HTTP(S) URLs and local file paths.
        """
        schema_url = conf.graph.schema_url

        if schema_url.startswith("file://"):
            file_path = schema_url[len("file://") :]
            with open(file_path, "r", encoding="utf-8") as f:
                import json

                return json.load(f)
        else:
            return HTTPClient.get(str(schema_url))

    def get_nodes(self) -> list[dict[str, Any]]:
        """
        Get the nodes from the graph schema, clean up their descriptions and titles, and store them in a list.
        Also populates the node_dict for quick label lookup.

        Returns:
            List of node dictionaries.
        """
        nodes = []
        for node in self.graph_schema.get("nodes", []):
            # clean up the node data
            node["description"] = HTMLStripper.strip_tags(node.get("description", ""))
            node["title"] = HTMLStripper.strip_tags(node.get("title", ""))
            for prop in node.get("properties", []):
                prop["value"] = HTMLStripper.strip_tags(prop.get("value", ""))
            nodes.append(node)

            # store the node label in a dictionary for quick access
            if node.get("id"):
                self.node_dict[node["id"]] = node.get("label", "Unknown")

        return nodes

    def get_edges(self) -> list[dict[str, Any]]:
        """
        Get the edges from the graph schema, clean up their descriptions and titles, and store them in a list.

        Returns:
            List of edge dictionaries.
        """
        edges = []
        for edge in self.graph_schema.get("edges", []):
            # clean up the edge data
            edge["description"] = HTMLStripper.strip_tags(edge.get("description", ""))
            edge["title"] = HTMLStripper.strip_tags(edge.get("title", ""))
            for prop in edge.get("properties", []):
                prop["value"] = HTMLStripper.strip_tags(prop.get("value", ""))
            edges.append(edge)

        return edges

    def format_nodes(self) -> str:
        """
        Format the nodes as a string for LLM or human-readable output.

        Returns:
            A formatted string listing all nodes and their properties.
        """
        return "\n\n".join(
            f"Label: {node['label']}\nDescription: {node.get('description', '')}\n"
            + (
                "Properties:\n"
                + "\n".join(
                    f"  - {prop.get('name', '')}: {prop.get('value', '')}"
                    for prop in node.get("properties", [])
                )
                if node.get("properties")
                else "Properties: None"
            )
            for node in self.nodes
        )

    def format_edges(self) -> str:
        """
        Format the edges as a string for LLM or human-readable output.

        Returns:
            A formatted string listing all edges and their properties.
        """
        return "\n\n".join(
            f"Label: {edge['label']}\n"
            f"Description: {edge.get('description', '')}\n"
            f"From: {self.node_dict.get(edge.get('from'), edge.get('from'))}\n"
            f"To: {self.node_dict.get(edge.get('to'), edge.get('to'))}\n"
            + (
                "Properties:\n"
                + "\n".join(
                    f"  - {prop.get('name', '')}: {prop.get('value', '')}"
                    for prop in edge.get("properties", [])
                )
                if edge.get("properties")
                else "Properties: None"
            )
            for edge in self.edges
        )

    def get_node_by_label(self, node_label: str) -> str | None:
        """
        Get a formatted string for a node by its label.

        Args:
            node_label: The label of the node to search for.

        Returns:
            A formatted string with node information, or None if not found.
        """
        for node in self.nodes:
            if node.get("label") == node_label:
                # format the node
                return f"""
                Label: {node_label}
                Description: {node.get("description")}
                """

        return None

    def get_edge_by_label(self, edge_label: str) -> dict[str, Any] | None:
        """
        Get an edge dictionary by its label.

        Args:
            edge_label: The label of the edge to search for.

        Returns:
            The edge dictionary if found, otherwise None.
        """
        for edge in self.edges:
            if edge.get("label") == edge_label:
                return edge
        return None

    def format_example_queries(self) -> str:
        """
        Format example queries as a string for LLM or human-readable output.

        Returns:
            A formatted string listing example queries.
        """
        return "\n\n".join(
            f"Question: {query.get('description', '')}\nQuery:\n{query.get('query', '')}"
            for query in self.graph_schema.get("examples", [])
        )

    def format_indexes(self) -> str:
        """
        Format indexes as a string for LLM or human-readable output.

        Returns:
            A formatted string listing all indexes defined in the graph database schema.
        """
        indexes = self.graph_schema.get("indexes", [])
        if not indexes:
            return "No indexes defined in the schema."

        return "\n\n".join(
            f"Node: {idx.get('node', '')}\nProperty: {idx.get('properties', '')}"
            for idx in indexes
        )

    def get_indexes(self) -> list[dict[str, str]]:
        """
        Get the indexes from the graph schema.

        Returns:
            List of index dictionaries, each containing 'node' and 'properties' keys.
        """
        return self.graph_schema.get("indexes", [])

    def _get_neo4j_config(self) -> dict[str, str]:
        """
        Get Neo4j configuration from environment variables.

        Returns:
            Dictionary with neo4j_url, neo4j_username, neo4j_password, and neo4j_database.

        Raises:
            RuntimeError: If Neo4j configuration is not available.
        """
        config = _get_neo4j_config_from_env()
        if not config:
            raise RuntimeError(
                "Neo4j configuration not found. Please set NEO4J_URL, "
                "NEO4J_USERNAME, and NEO4J_PASSWORD environment variables."
            )
        return config

    def _get_neo4j_driver(self) -> Any:
        """
        Get a Neo4j driver instance, compatible with both Neo4j 3.5 and 4.x+.
        This driver is reused across all tool calls to improve performance.

        Neo4j 3.5: Uses `GraphDatabase.driver(url, auth=...)` without database parameter
        Neo4j 4.0+: Uses `GraphDatabase.driver(url, auth=..., database=...)` with database parameter

        Returns:
            Neo4j Driver instance.

        Raises:
            RuntimeError: If Neo4j is not configured or neo4j driver is not installed.
        """
        if self._neo4j_driver is not None:
            return self._neo4j_driver

        try:
            from neo4j import AsyncGraphDatabase

            config = self._get_neo4j_config()

            # Try Neo4j 4+ API first (with database parameter if set)
            try:
                driver_kwargs = {
                    "url": config["neo4j_url"],
                    "auth": (config["neo4j_username"], config["neo4j_password"]),
                }
                if "neo4j_database" in config:
                    driver_kwargs["database"] = config["neo4j_database"]

                self._neo4j_driver = AsyncGraphDatabase.driver(**driver_kwargs)
                return self._neo4j_driver
            except TypeError as e:
                # Neo4j 3.5 doesn't accept 'database' parameter
                if "database" not in str(e).lower():
                    raise
                # Fall back to Neo4j 3.5 API
                logger.warning(
                    "Neo4j 3.5 detected (no database parameter support). "
                    "Using default database. If this is Neo4j 4+, consider setting NEO4J_DATABASE=neo4j"
                )
                self._neo4j_driver = AsyncGraphDatabase.driver(
                    config["neo4j_url"],
                    auth=(config["neo4j_username"], config["neo4j_password"]),
                )
                return self._neo4j_driver
        except ImportError as e:
            raise RuntimeError(
                "neo4j driver is not installed. Please install it with: pip install neo4j"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Failed to create Neo4j driver: {e}") from e

    async def execute_cypher_query(self, query: LiteralString) -> str:
        """
        Execute a Cypher query against the Neo4j database.

        Args:
            query: The Cypher query to execute.

        Returns:
            Formatted query results as a string.

        Raises:
            ValueError: If the query is not read-only.
            RuntimeError: If Neo4j is not configured or query execution fails.
        """
        # Validate the query first
        is_valid, error_message = _validate_cypher_query(query)
        if not is_valid:
            raise ValueError(
                f"Query validation failed: {error_message}. "
                "Only MATCH and OPTIONAL MATCH queries are allowed. "
                "MERGE, CREATE, DELETE, REMOVE, SET, LOAD CSV, and FOREACH operations are not allowed."
            )

        driver = None
        try:
            driver = self._get_neo4j_driver()
            async with driver.session() as session:
                result = await session.run(query)
                records = await result.data()
                keys = result.keys() if records else []

                # Convert to list of dictionaries
                results = [dict(zip(keys, record.values())) for record in records]

                # Format TOON or JSON output
                if _toon_enabled():
                    try:
                        import toon

                        result_text = toon.encode(results)
                        if not isinstance(result_text, str):
                            result_text = str(result_text)
                    except Exception as e:
                        logger.warning(
                            "TOON encoding failed, falling back to JSON: %s", e
                        )
                        import json

                        result_text = "TOON failed; JSON fallback:\n" + json.dumps(
                            results, indent=2, default=str
                        )
                else:
                    import json

                    result_text = json.dumps(results, indent=2, default=str)

                return result_text

        except Exception as e:
            logger.error("Neo4j query execution failed: %s", e)
            raise RuntimeError(f"Neo4j query execution failed: {e}") from e

    def close(self):
        """
        Close the Neo4j driver connection.
        """
        if self._neo4j_driver is not None:
            try:
                self._neo4j_driver.close()
            except Exception:
                logger.warning("Error closing Neo4j driver", exc_info=True)
            finally:
                self._neo4j_driver = None

    def __del__(self) -> None:
        """Cleanup on destruction."""
        self.close()

    def __enter__(self) -> "GraphTools":
        """Enter context manager."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager, ensuring cleanup."""
        self.close()
