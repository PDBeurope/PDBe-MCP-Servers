from typing import Any


def format_graph_info(graph_data: dict[str, Any]) -> str:
    output = []

    # Format Nodes
    output.append("Nodes\n" + "=" * 5 + "\n")

    for node in graph_data.get("nodes", []):
        output.append(f"Label: {node['label']}")
        output.append(f"Description: {node['description']}")
        output.append("Properties:")

        if node.get("properties"):
            for prop in node["properties"]:
                name = prop.get("name", "<No name>")
                value = prop.get("value", "<No description>")
                output.append(f"  - {name}: {value}")
        else:
            output.append("  None")

        output.append("")  # Blank line between nodes

    # Format Edges (Relationships)
    output.append("Relationships\n" + "=" * 12 + "\n")

    for edge in graph_data.get("edges", []):
        output.append(f"Label: {edge['label']}")
        output.append(f"Description: {edge['description']}")
        output.append(f"From Node ID: {edge['from']}")
        output.append(f"To Node ID: {edge['to']}")
        output.append("Properties:")

        if edge.get("properties"):
            for prop in edge["properties"]:
                name = prop.get("name", "<No name>")
                value = prop.get("value", "<No description>")
                output.append(f"  - {name}: {value}")
        else:
            output.append("  None")

        output.append("")  # Blank line between edges

    return "\n".join(output)
