# Q003 — What is the role of haemoglobin?

**Question:** What is the role of haemoglobin? How does oxygen binding change its structure? Can you point me to a related PDB entry?

- **Retrieved:** 2026-10-11
- **LLM:** Moonshot AI Kimi K2.5 (`moonshotai.kimi-k2.5`)

## MCP calls

1. `run_pdbe_search_query({"query":"text:hemoglobin AND text:oxygen AND experimental_method:\"X-ray diffraction\"","fl":["pdb_id","title","organism_scientific_name","bound_compound_id","bound_compound_name"],"rows":5})`
2. `run_pdbe_search_query({"query":"pdb_id:1hho OR pdb_id:2hhb","fl":["pdb_id","title","organism_scientific_name","biological_function","biological_process","bound_compound_id","bound_compound_name"],"rows":3})`

## What the tools returned

- **Call 1 →** Search for hemoglobin entries with oxygen-related annotations and X-ray diffraction method returned multiple PDB entries including 1HHO and 2HHB.
- **Call 2 →** Detailed entry information:
  - **Biological function** includes: heme binding, iron ion binding, oxygen binding, oxygen carrier activity, peroxidase activity, and protein binding.
  - **Biological processes** include: oxygen transport, carbon dioxide transport, erythrocyte development, cellular oxidant detoxification, and inflammatory response.
  - **Human deoxyhaemoglobin (2HHB)**: Deoxy form (no oxygen bound), 1.74 Å resolution.
  - **Human oxyhaemoglobin (1HHO)**: Oxygen-bound form, 2.1 Å resolution, contains molecular oxygen (`OXY`) ligand.

## Example answer

**Haemoglobin** is the oxygen-transport protein in red blood cells. PDBe annotations list its functions as **oxygen binding**, **oxygen carrier activity**, and **heme/iron ion binding**, with roles in **oxygen transport**, **carbon dioxide transport**, and **erythrocyte development**.

Oxygen binding triggers a **conformational change** between the T (tense, deoxy) and R (relaxed, oxy) states. Comparing related entries shows this:

- **2HHB** — Human deoxyhaemoglobin (T state), no oxygen bound, 1.74 Å
- **1HHO** — Human oxyhaemoglobin (R state), oxygen bound, 2.1 Å

These two structures illustrate the structural transition upon oxygen binding.

## Sources and notes

- [PDBe entry 1HHO (oxy)](https://www.ebi.ac.uk/pdbe/entry/pdb/1hho)
- [PDBe entry 2HHB (deoxy)](https://www.ebi.ac.uk/pdbe/entry/pdb/2hhb)
- The functional summary uses PDBe annotations; structural comparison requires visual inspection of the coordinate files.
