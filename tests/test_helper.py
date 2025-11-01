from pdbe_mcp_server.helper import format_graph_info


def test_format_graph_info_empty_dict():
    """Test with an empty dictionary."""
    graph_data = {}
    result = format_graph_info(graph_data)

    assert "Nodes\n=====\n" in result
    assert "Relationships\n============\n" in result


def test_format_graph_info_with_nodes_no_properties():
    """Test with nodes that have no properties."""
    graph_data = {"nodes": [{"label": "Node1", "description": "First node"}]}
    result = format_graph_info(graph_data)

    assert "Label: Node1" in result
    assert "Description: First node" in result
    assert "Properties:\n  None" in result


def test_format_graph_info_with_nodes_with_properties():
    """Test with nodes that have properties."""
    graph_data = {
        "nodes": [
            {
                "label": "Protein",
                "description": "A protein node",
                "properties": [
                    {"name": "id", "value": "P12345"},
                    {"name": "name", "value": "Hemoglobin"},
                ],
            }
        ]
    }
    result = format_graph_info(graph_data)

    assert "Label: Protein" in result
    assert "Description: A protein node" in result
    assert "  - id: P12345" in result
    assert "  - name: Hemoglobin" in result


def test_format_graph_info_with_edges_no_properties():
    """Test with edges that have no properties."""
    graph_data = {
        "edges": [
            {
                "label": "BINDS_TO",
                "description": "Binding relationship",
                "from": "node1",
                "to": "node2",
            }
        ]
    }
    result = format_graph_info(graph_data)

    assert "Label: BINDS_TO" in result
    assert "Description: Binding relationship" in result
    assert "From Node ID: node1" in result
    assert "To Node ID: node2" in result
    assert "Properties:\n  None" in result


def test_format_graph_info_with_edges_with_properties():
    """Test with edges that have properties."""
    graph_data = {
        "edges": [
            {
                "label": "INTERACTS_WITH",
                "description": "Interaction edge",
                "from": "protein1",
                "to": "protein2",
                "properties": [
                    {"name": "affinity", "value": "high"},
                    {"name": "confidence", "value": "0.95"},
                ],
            }
        ]
    }
    result = format_graph_info(graph_data)

    assert "Label: INTERACTS_WITH" in result
    assert "  - affinity: high" in result
    assert "  - confidence: 0.95" in result


def test_format_graph_info_complete_graph():
    """Test with both nodes and edges."""
    graph_data = {
        "nodes": [
            {
                "label": "Protein",
                "description": "A protein",
                "properties": [{"name": "id", "value": "P001"}],
            },
            {"label": "Ligand", "description": "A ligand", "properties": []},
        ],
        "edges": [
            {
                "label": "BINDS",
                "description": "Binding",
                "from": "P001",
                "to": "L001",
                "properties": [{"name": "strength", "value": "strong"}],
            }
        ],
    }
    result = format_graph_info(graph_data)

    assert "Label: Protein" in result
    assert "Label: Ligand" in result
    assert "Label: BINDS" in result
    assert "  - id: P001" in result
    assert "  - strength: strong" in result


def test_format_graph_info_missing_property_fields():
    """Test with properties missing name or value fields."""
    graph_data = {
        "nodes": [
            {
                "label": "TestNode",
                "description": "Test",
                "properties": [{"name": "prop1"}, {"value": "val2"}, {}],
            }
        ]
    }
    result = format_graph_info(graph_data)

    assert "  - prop1: <No description>" in result
    assert "  - <No name>: val2" in result
    assert "  - <No name>: <No description>" in result


def test_format_graph_info_multiple_nodes_and_edges():
    """Test with multiple nodes and edges."""
    graph_data = {
        "nodes": [
            {"label": "Node1", "description": "First"},
            {"label": "Node2", "description": "Second"},
        ],
        "edges": [
            {"label": "Edge1", "description": "First edge", "from": "1", "to": "2"},
            {"label": "Edge2", "description": "Second edge", "from": "2", "to": "3"},
        ],
    }
    result = format_graph_info(graph_data)

    assert result.count("Label: Node") == 2
    assert result.count("Label: Edge") == 2
    assert "From Node ID: 1" in result
    assert "To Node ID: 3" in result
