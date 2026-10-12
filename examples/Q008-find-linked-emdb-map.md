# Q008 — How do I find the EMDB map linked to a PDB entry?

**Question:** How do I find the EMDB map linked to a PDB entry?

- **Retrieved:** 2026-10-11
- **LLM:** Moonshot AI Kimi K2.5 (`moonshotai.kimi-k2.5`)

## MCP calls

1. `run_pdbe_search_query({"query":"experimental_method:\"Electron Microscopy\" AND pdb_id:7k00","fl":["pdb_id","title","experimental_method","emdb_id"],"rows":5})`
2. `run_pdbe_search_query({"query":"experimental_method:\"Electron Microscopy\" AND pdb_id:6zgi","fl":["pdb_id","title","experimental_method","emdb_id"],"rows":3})`

## What the tools returned

- **Call 1 →** EMDB entries are linked to PDB entries via the **`emdb_id`** field in the PDBe search index. Query for entry **7K00** returned `emdb_id: emd-22586`.
- **Call 2 →** Query for entry **6ZGI** returned `emdb_id: emd-11207`.

Both calls demonstrate that the `emdb_id` field contains the linked EMDB map identifier for electron microscopy entries.

## Example answer

To find the EMDB map linked to a PDB entry, query PDBe Search for the PDB ID with the `emdb_id` field included in the response.

**Example results:**

| PDB ID | EMDB ID | Entry Title |
|--------|---------|-------------|
| [7K00](https://www.ebi.ac.uk/pdbe/entry/pdb/7k00) | [EMD-22586](https://www.ebi.ac.uk/emdb/entry/emd-22586) | Structure of the Bacterial Ribosome at 2 Angstrom Resolution |
| [6ZGI](https://www.ebi.ac.uk/pdbe/entry/pdb/6zgi) | [EMD-11207](https://www.ebi.ac.uk/emdb/entry/emd-11207) | Furin Cleaved Spike Protein of SARS-CoV-2 in Closed Conformation |

The EMDB ID follows the pattern `emd-XXXXX` and can be used to access the map directly at `https://www.ebi.ac.uk/emdb/entry/emd-XXXXX`.

## Sources

- [PDBe entry 7K00](https://www.ebi.ac.uk/pdbe/entry/pdb/7k00)
- [EMDB entry EMD-22586](https://www.ebi.ac.uk/emdb/entry/emd-22586)
- [PDBe entry 6ZGI](https://www.ebi.ac.uk/pdbe/entry/pdb/6zgi)
- [EMDB entry EMD-11207](https://www.ebi.ac.uk/emdb/entry/emd-11207)
