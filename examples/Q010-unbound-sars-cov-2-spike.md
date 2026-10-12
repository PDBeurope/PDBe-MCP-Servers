# Q010 — Which entries contain unbound SARS-CoV-2 spike?

**Question:** Which entries contain unbound SARS-CoV-2 spike? Which one is the best?

- **Retrieved:** 2026-10-11
- **LLM:** Moonshot AI Kimi K2.5 (`moonshotai.kimi-k2.5`)

## MCP calls

1. `run_pdbe_search_query({"query":"text:\"SARS-CoV-2\" AND text:\"spike\" AND (text:\"unbound\" OR text:\"apo\" OR text:\"closed\")","fl":["pdb_id","title","resolution","experimental_method","em_resolution"],"rows":10})`
2. `run_pdbe_search_query({"query":"text:\"SARS-CoV-2\" AND text:\"spike\" AND (text:\"closed\" OR text:\"unbound\")","fl":["pdb_id","title","resolution","experimental_method"],"sort":"resolution asc","rows":5})`

## What the tools returned

- **Call 1 →** **73 entries** match "SARS-CoV-2 spike" with "closed" or "unbound" conformation. The search finds entries with titles containing "apo", "closed", or "unbound" — indicating uncomplexed spike protein.
- **Call 2 →** Same query sorted by resolution ascending, returning the highest-resolution entries first. Results include entries 12JZ (2.35 Å), 6ZGE (2.6 Å), 13BD (2.65 Å), 6ZP0 (3.0 Å), and 6ZGI (2.9 Å).

## Selected unbound SARS-CoV-2 spike entries

| PDB ID | Resolution | Method | Description |
|--------|------------|--------|-------------|
| **12JZ** | 2.35 Å | Cryo-EM | SARS-CoV-2 BA.3.2.1 Spike with K852A mutation, closed conformation |
| **6ZGE** | 2.6 Å | Cryo-EM | Uncleavable Spike Protein of SARS-CoV-2 in Closed Conformation |
| **13BD** | 2.65 Å | Cryo-EM | Local refinement of RBD and NTD in closed BA.3.2.1 spike with N529Q mutant |
| **6ZP0** | 3.0 Å | Cryo-EM | SARS-CoV-2 Spike Protein Trimer in Closed State |
| **6ZGI** | 2.9 Å | Cryo-EM | Furin Cleaved Spike Protein of SARS-CoV-2 in Closed Conformation |

## Example answer

There are **73 PDB entries** containing SARS-CoV-2 spike in unbound/closed conformation.

**Which is "best"?** This depends on your criteria:

- **Highest resolution (closed conformation)**: **12JZ** at **2.35 Å** (cryo-EM), BA.3.2.1 variant with K852A mutation
- **Wild-type closed conformation**: **6ZGE** at **2.6 Å** (cryo-EM), uncleavable spike
- **Classical closed state**: **6ZGI** at **2.9 Å** (cryo-EM), furin-cleaved spike

The "best" entry depends on whether you prioritize resolution, specific variant, or functional state. 12JZ has the highest resolution among closed conformations.

## Sources

- [PDBe entry 12JZ](https://www.ebi.ac.uk/pdbe/entry/pdb/12jz)
- [PDBe entry 6ZGE](https://www.ebi.ac.uk/pdbe/entry/pdb/6zge)
- [PDBe entry 6ZGI](https://www.ebi.ac.uk/pdbe/entry/pdb/6zgi)
- Search results from PDBe Solr index (2026-10-11)
