# Q006 — Can you find all entries of sialyltransferases?

**Question:** Can you find all entries of sialyltransferases? Which ones are from human? Which ones have a sugar substrate present?

- **Retrieved:** 2026-10-11
- **LLM:** Moonshot AI Kimi K2.5 (`moonshotai.kimi-k2.5`)

## MCP calls

1. `run_pdbe_search_query({"query":"text:sialyltransferase","fl":["pdb_id","title","organism_scientific_name","bound_compound_id","bound_compound_name"],"rows":10})`
2. `run_pdbe_search_query({"query":"text:sialyltransferase","fq":["organism_scientific_name:\"Homo sapiens\""],"fl":["pdb_id","title","organism_scientific_name","bound_compound_id","bound_compound_name"],"rows":10})`
3. `run_pdbe_search_query({"query":"text:sialyltransferase AND (bound_compound_id:NAG OR bound_compound_id:GAL OR bound_compound_id:MAN)","fq":["organism_scientific_name:\"Homo sapiens\""],"fl":["pdb_id","title","bound_compound_id","bound_compound_name"],"rows":5})`

## What the tools returned

- **60 total entries** match "sialyltransferase" in the search index.
- **14 human entries** (`organism_scientific_name: "Homo sapiens"`).
- Several entries contain **N-acetylglucosamine (NAG)** or related sugar ligands.

## Human sialyltransferase entries (examples)

| PDB ID | Title | Ligands |
|--------|-------|---------|
| **5BO6** | Structure of human sialyltransferase ST8SiaIII in complex with CDP | CDP, NAG |
| **5BO7** | Structure of human sialyltransferase ST8SiaIII in complex with CTP | CTP, NAG |
| **5BO8** | Structure of human sialyltransferase ST8SiaIII | Citrate, NAG |
| **5BO9** | Structure of human sialyltransferase ST8SiaIII in complex with CMP-3FNeu5Ac and Sia-6S-LacNAc | CSF, NAG |
| **6QVT** | CMP-Sialic acid bound structure of human ST6Gal1 | NCC, PEG |
| **4JS1** | Human ST6Gal1 in complex with cytidine and phosphate | CTN, PO4 |

## Example answer

There are **60 PDB entries** matching "sialyltransferase". Of these, **14 are from human** (*Homo sapiens*).

Human entries that contain **sugar-like ligands** include:
- **5BO6**, **5BO7**, **5BO8**, **5BO9** — Human ST8SiaIII with N-acetylglucosamine (NAG) bound
- **6QVT** — Human ST6Gal1 with CMP-sialic acid derivative (NCC)

Note: NAG (N-acetylglucosamine) is a sugar derivative often found in these structures, either as substrate, product, or part of the active site environment.

## Sources

- Search results from PDBe Solr index (2026-10-11)
- [PDBe entry 5BO6](https://www.ebi.ac.uk/pdbe/entry/pdb/5bo6)
- [PDBe entry 6QVT](https://www.ebi.ac.uk/pdbe/entry/pdb/6qvt)
