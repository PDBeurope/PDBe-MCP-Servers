# Q001 — What is the biological function of PDB entry 1CBS?

**Question:** What is the biological function of PDB entry 1CBS? Which organism does it come from? What ligands are present?

- **Retrieved:** 2026-10-11
- **LLM:** Moonshot AI Kimi K2.5 (`moonshotai.kimi-k2.5`)

## MCP calls

1. `get_pdbe_search_schema()` — inspected available search fields before constructing the Solr query.
2. `run_pdbe_search_query({"query":"pdb_id:1cbs","fl":["pdb_id","title","biological_function","organism_scientific_name","bound_compound_id","bound_compound_name","biological_process"],"rows":10})`
3. `get_molecules_api_pdb_entry_molecules__pdb_id__get({"pdb_id":"1cbs"})`

## What the tools returned

- **Call 1 →** Inspected available search fields to understand what biological function and organism data can be retrieved.
- **Call 2 →** Search annotations list **retinoic acid binding** and other lipid/retinoid and protein-binding functions; associated biological processes include fatty-acid transport and transcriptional regulation. The protein entity is **cellular retinoic acid-binding protein 2 (CRABP2)**, from *Homo sapiens*. The expression host is *E. coli* BL21(DE3), which is distinct from the protein's source organism.
- **Call 3 →** The structure contains **retinoic acid** (CCD code `REA`) and **water**. The entry title describes the structural study of cellular retinoic-acid-binding proteins in complex with all-trans-retinoic acid and a synthetic retinoid.

## Example answer

PDB **1CBS** contains human **cellular retinoic acid-binding protein 2 (CRABP2)**. PDBe's functional annotations include retinoic-acid binding and retinoid/lipid transport-related functions. The listed non-water ligand in this entry is **retinoic acid (`REA`)**. Although the protein was expressed in *E. coli*, its source organism is human.

## Sources and notes

- [PDBe entry 1CBS](https://www.ebi.ac.uk/pdbe/entry/pdb/1cbs)
- The function summary uses PDBe annotations; it is not a direct assay of the structure.
