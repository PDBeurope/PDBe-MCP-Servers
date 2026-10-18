# Q002 — How was structure 7K00 determined?

**Question:** How was structure 7K00 determined? What is the resolution? What are the limitations of this method?

- **Retrieved:** 2026-10-11
- **LLM:** Moonshot AI Kimi K2.5 (`moonshotai.kimi-k2.5`)

## MCP call

`run_pdbe_search_query({"query":"pdb_id:7k00","fl":["pdb_id","title","experimental_method","em_method","resolution","em_resolution","structure_determination_method","em_3d_reconst_details"],"rows":1})`

## What the tool returned

- Title: "Structure of the Bacterial Ribosome at 2 Angstrom Resolution".
- Experimental method: **Electron Microscopy**.
- EM method: **single particle**.
- Reported resolution: **1.98 Å**.
- Reconstruction details include **Ewald-sphere correction in RELION**.

## Example answer

PDB **7K00** was determined by **single-particle cryo-electron microscopy (cryo-EM)**, at a reported resolution of **1.98 Å**.

Cryo-EM limitations are method-level context rather than entry-specific fields returned by the query. Resolution is a global summary and local detail can vary; particle flexibility, conformational mixtures, preferred orientations, and sample preparation can affect the reconstruction. A deposited model is a structural snapshot and does not by itself show the molecule's full dynamics.

## Source

- [PDBe entry 7K00](https://www.ebi.ac.uk/pdbe/entry/pdb/7k00)
