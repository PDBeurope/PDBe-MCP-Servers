import functools
from typing import Any, Dict, List, Optional

import requests

from pdbe_mcp_server.utils import HTMLStripper


class GraphTools:
    """
    A class to handle PDBe graph-related operations.
    """

    def __init__(self) -> None:
        """
        Initialize the GraphTools object, load the graph schema, and prepare node and edge lists.
        """
        self.graph_schema: Dict[str, Any] = self._get_graph_schema()
        self.node_dict: Dict[Any, str] = {}
        self.nodes: List[Dict[str, Any]] = self.get_nodes()
        self.edges: List[Dict[str, Any]] = self.get_edges()

    @functools.lru_cache(maxsize=None)
    def _get_graph_schema(self) -> Dict[str, Any]:
        """
        Retrieve the PDBe graph schema from the remote server and return it as a dictionary.
        Uses LRU cache to avoid repeated downloads.
        """
        r = requests.get("https://www.ebi.ac.uk/pdbe/static/files/graph_schema.json")
        r.raise_for_status()
        return r.json()

    def get_nodes(self) -> List[Dict[str, Any]]:
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

    def get_edges(self) -> List[Dict[str, Any]]:
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

    def get_node_by_label(self, node_label: str) -> Optional[str]:
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

    def get_edge_by_label(self, edge_label: str) -> Optional[Dict[str, Any]]:
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
