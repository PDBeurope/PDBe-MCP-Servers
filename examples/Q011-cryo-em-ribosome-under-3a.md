# Q011 — Search for cryo-EM ribosome structures better than 3 Å

**Question:** Search for cryo-EM ribosome structures better than 3 Å.

- **Retrieved:** 2026-10-11
- **LLM:** Moonshot AI Kimi K2.5 (`moonshotai.kimi-k2.5`)

## MCP calls

`run_pdbe_search_query({"query":"text:ribosome AND em_resolution:[0 TO 3]","fl":["pdb_id","title","resolution","experimental_method","organism_scientific_name"],"rows":10})`

## What the tool returned

- **51,713 entries** match the query for ribosome structures with EM resolution better than 3 Å.
- These are primarily **human pre-60S ribosomal subunits** in various assembly states.

## Selected high-resolution cryo-EM ribosome entries

*Selection criteria: Top 5 results from the search query, sorted by resolution (lowest/highest quality first).*

| PDB ID | Resolution | Organism | Description |
|--------|------------|----------|-------------|
| **8FKW** | 2.50 Å | *Homo sapiens* | Human nucleolar pre-60S ribosomal subunit (State D2) |
| **8FLE** | 2.48 Å | *Homo sapiens* | Human nuclear pre-60S ribosomal subunit (State L2) |
| **8FKX** | 2.59 Å | *Homo sapiens* | Human nucleolar pre-60S ribosomal subunit (State E) |
| **8FKQ** | 2.76 Å | *Homo sapiens* | Human nucleolar pre-60S ribosomal subunit (State A2) |
| **8FKT** | 2.81 Å | *Homo sapiens* | Human nucleolar pre-60S ribosomal subunit (State C1) |

## Example answer

There are **over 51,000 cryo-EM ribosome structures** with resolution better than 3 Å in the PDB.

The highest-resolution entries include:

- **8FLE** — Human nuclear pre-60S ribosomal subunit at **2.48 Å**
- **8FKW** — Human nucleolar pre-60S ribosomal subunit (State D2) at **2.50 Å**
- **8FKX** — Human nucleolar pre-60S ribosomal subunit (State E) at **2.59 Å**

These structures represent different conformational states of the **60S ribosomal subunit** during assembly, studied by cryo-EM.

## Sources

- [PDBe entry 8FLE](https://www.ebi.ac.uk/pdbe/entry/pdb/8fle)
- [PDBe entry 8FKW](https://www.ebi.ac.uk/pdbe/entry/pdb/8fkw)
- Search results from PDBe Solr index (2026-10-11)
