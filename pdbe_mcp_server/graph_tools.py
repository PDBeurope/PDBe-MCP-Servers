from typing import Any

import mcp.types as types
from omegaconf import DictConfig

from pdbe_mcp_server import get_config
from pdbe_mcp_server.utils import HTMLStripper, HTTPClient

conf: DictConfig = get_config()


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

    def _get_graph_schema(self) -> dict[str, Any]:
        """
        Retrieve the PDBe graph schema from the remote server and return it as a dictionary.
        """
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
