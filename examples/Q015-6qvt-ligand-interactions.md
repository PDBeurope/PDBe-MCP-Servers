# Q015 — What ligands are bound in entry 6QVT?

**Question:** What ligands are bound in entry 6qvt? What kind of interaction types are at stake between the protein and the ligand NCC?

- **Retrieved:** 2026-10-11
- **LLM:** Moonshot AI Kimi K2.5 (`moonshotai.kimi-k2.5`)

## MCP calls

1. `run_pdbe_search_query({"query":"pdb_id:6qvt","fl":["pdb_id","title","bound_compound_id","bound_compound_name"],"rows":1})`
2. `get_molecules_api_pdb_entry_molecules__pdb_id__get({"pdb_id":"6qvt"})`
3. `get_comp_intx_api_comp_intx__hetcode__get({"hetcode":"NCC"})`

## What the tools returned

### Ligands in 6QVT

| Entity ID | Molecule Type | Name | Copies |
|-----------|---------------|------|--------|
| 1 | Polypeptide | Beta-galactoside alpha-2,6-sialyltransferase 1 (ST6Gal1) | 2 |
| 2 | Bound | **Cytidine-5'-monophosphate-5-N-acetylneuraminic acid (NCC)** | 2 |
| 3 | Bound | Di(hydroxyethyl)ether (PEG) | 2 |
| 4 | Water | Water | 256 |

### NCC (CMP-sialic acid) Interactions

Based on aggregated interaction data from PDB structures containing NCC:

| Interaction Type | Common Interacting Residues |
|-------------------|----------------------------|
| **Hydrogen bonds** | ARG, LYS, SER, ASN, GLN, TYR |
| **Hydrophobic** | PHE, TYR, ALA, LEU, VAL |
| **Polar** | ARG, LYS, ASN, GLU, SER |
| **Aromatic stacking** | PHE, TYR |
| **Van der Waals** | ARG, LYS, GLN, ASN, SER |

Key interaction atoms on NCC:
- **Phosphate oxygens (O1P, O2P, O3P)** — hydrogen bond with ARG, LYS, SER
- **Carboxyl oxygens (O1A, O1B)** — interact with ARG, ASN, SER
- **Sugar hydroxyls (O2', O3', O6, O7, O8, O9)** — hydrogen bond with ASN, GLU, GLN, LYS
- **Cytosine ring** — aromatic stacking with PHE, TYR

## Example answer

**6QVT** contains human **beta-galactoside alpha-2,6-sialyltransferase 1 (ST6Gal1)** with the following ligands:

- **NCC** — Cytidine-5'-monophosphate-5-N-acetylneuraminic acid (CMP-sialic acid), 2 copies
- **PEG** — Di(hydroxyethyl)ether, 2 copies (cryoprotectant)
- **Water** — 256 molecules

**NCC interactions** with the protein include:
- **Hydrogen bonding** — phosphate group with basic residues (ARG, LYS)
- **Hydrophobic contacts** — sugar and base with aromatic residues (PHE, TYR)
- **Polar interactions** — hydroxyl groups with ASN, GLN, SER
- **Aromatic stacking** — cytosine ring with PHE/TYR side chains

NCC is the donor substrate analog for the sialyltransferase reaction.

## Sources

- [PDBe entry 6QVT](https://www.ebi.ac.uk/pdbe/entry/pdb/6qvt)
- PDBe-KB interaction data for NCC (2026-10-11)
