import logging
import os
import re
from typing import Any

import mcp.types as types
from omegaconf import DictConfig

from pdbe_mcp_server import get_config
from pdbe_mcp_server.utils import HTMLStripper, HTTPClient

logger = logging.getLogger(__name__)

conf: DictConfig = get_config()


def _get_neo4j_config_from_env() -> dict[str, str] | None:
    """
    Get Neo4j configuration from environment variables.

    Returns:
        Dictionary with neo4j_url, neo4j_username, neo4j_password, and neo4j_database,
        or None if not all required variables are set.
    """
    neo4j_url = os.getenv("NEO4J_URL")
    neo4j_username = os.getenv("NEO4J_USERNAME")
    neo4j_password = os.getenv("NEO4J_PASSWORD")
    neo4j_database = os.getenv("NEO4J_DATABASE")

    if neo4j_url and neo4j_username and neo4j_password:
        config = {
            "neo4j_url": neo4j_url,
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
    return os.getenv("TOON_ENABLED", "false").lower() == "true"


def _validate_cypher_query(query: str) -> tuple[bool, str | None]:
    """
    Validate a Cypher query to ensure it is read-only (no write, delete, or update operations).

    Args:
        query: The Cypher query to validate.

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is None.
    """
    # Normalize the query: remove comments, extra whitespace, convert to uppercase for matching
    normalized = re.sub(r"/\*.*?\*/", "", query, flags=re.DOTALL)
    normalized = re.sub(r"--.*$", "", normalized, flags=re.MULTILINE)
    normalized = " ".join(normalized.upper().split())

    # Cypher keywords that indicate write, delete, or update operations
    write_patterns = [
        r"\bMERGE\b",
        r"\bCREATE\b",
        r"\bDELETE\b",
        r"\bREMOVE\b",
        r"\bSET\b",
        r"\bADD\b",
        r"\bREMOVE\b",
        r"\bSET\b",
        r"\bSET\s+[A-Za-z_][A-Za-z0-9_]*\s+=",
        r"\bMATCH\b.*\bMERGE\b",
        r"\bMERGE\b.*\bSET\b",
        r"\bCREATE\b.*\bSET\b",
        r"\bWITH\b.*\bMERGE\b",
        r"\bWITH\b.*\bCREATE\b",
        r"\bWITH\b.*\bDELETE\b",
        r"\bWITH\b.*\bSET\b",
        r"\bLOAD\s+CSV\b",
        r"\bFOREACH\b",
        r"\bREMOVE\b\b",
    ]

    for pattern in write_patterns:
        if re.search(pattern, normalized):
            return (
                False,
                f"Query contains potentially destructive operation (detected pattern: {pattern})",
            )

    # Additional check: allow only MATCH, OPTIONAL MATCH, CALL {MATCH ...}, RETURN
    # This is a safer approach - only allow queries that start with these read operations
    allowed_starts = [
        r"^(?:MATCH|OPTIONAL\s+MATCH|CALL\s*\{[^}]*\})",
    ]

    # Check if query matches allowed patterns
    has_allowed_pattern = any(re.search(p, normalized) for p in allowed_starts)

    # Additional check: if query contains write keywords after MATCH, it might be dangerous
    # This catches patterns like "MATCH ... RETURN ... MERGE"
    write_keywords = ["MERGE", "CREATE", "DELETE", "REMOVE", "SET"]
    if has_allowed_pattern:
        # Check if any write operation appears after the initial MATCH/MATCH+CALL
        parts = re.split(r"\bRETURN\b", normalized, flags=re.IGNORECASE)
        if len(parts) > 1:
            # Everything after RETURN is part of RETURN clause, check the rest
            pre_return = parts[0]
            for keyword in write_keywords:
                if re.search(rf"\b{keyword}\b", pre_return, re.IGNORECASE):
                    return (
                        False,
                        f"Query contains potentially destructive operation ({keyword}) after MATCH",
                    )
    elif not has_allowed_pattern:
        return (
            False,
            "Query does not start with allowed read operation (MATCH, OPTIONAL MATCH, or CALL)",
        )

    return True, None


class GraphTools:
    """
    A class to handle PDBe graph-related operations.
    """

    def __init__(self) -> None:
        """
        Initialize the GraphTools object, load the graph schema, and prepare node and edge lists.
        """
        self.graph_schema: dict[str, Any] = self._get_graph_schema()
        self.node_dict: dict[Any, str] = {}
        self.nodes: list[dict[str, Any]] = self.get_nodes()
        self.edges: list[dict[str, Any]] = self.get_edges()

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
                        "description": "The Cypher query to execute. Only MATCH and OPTIONAL MATCH queries are allowed. MERGE, CREATE, DELETE, REMOVE, SET, LOAD CSV, and FOREACH operations are not permitted.",
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
        if conf.graph.schema_url.startswith("file://"):
            file_path = conf.graph.schema_url[len("file://") :]
            with open(file_path, "r", encoding="utf-8") as f:
                import json

                return json.load(f)
        else:
            return HTTPClient.get(str(conf.graph.schema_url))

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
            self.node_dict[node.get("id")] = node["label"]

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

    def _get_neo4j_driver(self):
        """
        Get a Neo4j driver instance, compatible with both Neo4j 3.5 and 4.x+.

        Neo4j 3.5: Uses `GraphDatabase.driver(url, auth=...)` without database parameter
        Neo4j 4.0+: Uses `GraphDatabase.driver(url, auth=..., database=...)` with database parameter

        Returns:
            Neo4j Driver instance.

        Raises:
            RuntimeError: If Neo4j is not configured or neo4j driver is not installed.
        """
        try:
            from neo4j import Driver, GraphDatabase

            config = self._get_neo4j_config()

            # Try Neo4j 4+ API first (with database parameter if set)
            try:
                driver_kwargs = {
                    "url": config["neo4j_url"],
                    "auth": (config["neo4j_username"], config["neo4j_password"]),
                }
                if "neo4j_database" in config:
                    driver_kwargs["database"] = config["neo4j_database"]
                driver = GraphDatabase.driver(**driver_kwargs)
                # Driver is lazily validated on first use
                return driver
            except TypeError as e:
                # Neo4j 3.5 doesn't accept 'database' parameter
                if "database" not in str(e).lower():
                    raise
                # Fall back to Neo4j 3.5 API
                logger.warning(
                    "Neo4j 3.5 detected (no database parameter support). "
                    "Using default database. If this is Neo4j 4+, consider setting NEO4J_DATABASE=neo4j"
                )
                return GraphDatabase.driver(
                    config["neo4j_url"],
                    auth=(config["neo4j_username"], config["neo4j_password"]),
                )
        except ImportError as e:
            raise RuntimeError(
                "neo4j driver is not installed. Please install it with: pip install neo4j"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Failed to create Neo4j driver: {e}") from e

    def execute_cypher_query(self, query: str) -> str:
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
            with driver.session() as session:
                result = session.run(query)
                records = list(result)
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
        finally:
            if driver:
                driver.close()
