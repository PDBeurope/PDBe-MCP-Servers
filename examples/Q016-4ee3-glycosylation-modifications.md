# Q016 — Does structure 4EE3 have glycosylation or modified residues?

**Question:** Does the structure 4EE3 have glycosylation or modified residues?

- **Retrieved:** 2026-10-11
- **LLM:** Moonshot AI Kimi K2.5 (`moonshotai.kimi-k2.5`)

## MCP calls

1. `run_pdbe_search_query({"query":"pdb_id:4ee3","fl":["pdb_id","title","bound_compound_id","bound_compound_name","experimental_method"],"rows":1})`
2. `get_molecules_api_pdb_entry_molecules__pdb_id__get({"pdb_id":"4ee3"})`

## What the tools returned

### Entry summary
- **4EE3** — Crystal structure of human M340H-beta-1,4-galactosyltransferase-1 (M340H-B4GAL-T1) in complex with pentasaccharide
- **Method:** X-ray diffraction
- **Organism:** *Homo sapiens* (expressed in *E. coli*)

### Molecules in 4EE3

| Entity | Type | Name | Copies |
|--------|------|------|--------|
| 1 | Polypeptide | Beta-1,4-galactosyltransferase 1 | 3 |
| 2 | **Carbohydrate polymer** | **Pentasaccharide** | 15 |
| 3 | Bound | UDH (UDP-hexanolamine) | 3 |
| 4 | Bound | Manganese ion | 3 |
| 5 | Bound | Sulfate ion | 18 |
| 6 | Bound | Glycerol | 3 |
| 7 | Water | Water | 527 |

### Glycosylation

**Yes — 4EE3 contains a carbohydrate polymer:**
- A **pentasaccharide** (5-sugar chain) is present, 15 copies
- Composition includes: **BGC** (beta-D-glucose), **NAG** (N-acetylglucosamine), **GAL** (galactose)
- Full name: "beta-D-galactopyranose-(1-3)-2-acetamido-2-deoxy-beta-D-glucopyranose-(1-3)-[2-acetamido-2-deoxy-beta-D-glucopyranose-(1-6)]beta-D-galactopyranose-(1-4)-beta-D-glucopyranose"

### Modified residues

**Yes — the protein has mutations:**
- **R337T** — Arginine → Threonine
- **C338T** — Cysteine → Threonine
- **M340H** — Methionine → Histidine (as noted in the entry title)

These mutations are in the enzyme's active site region and affect its catalytic properties.

## Example answer

**Yes, 4EE3 contains both glycosylation and modified residues:**

1. **Glycosylation:** A **pentasaccharide** (5-sugar carbohydrate chain) is present with 15 copies. It contains glucose, N-acetylglucosamine, and galactose residues — this is a substrate/product analog for the galactosyltransferase enzyme.

2. **Modified residues:** The protein has three point mutations:
   - **R337T**
   - **C338T**
   - **M340H** (the entry names this variant "M340H-B4GAL-T1")

The carbohydrate is not N-linked glycosylation on the protein itself, but rather a bound oligosaccharide substrate. The mutations were introduced to study the enzyme's mechanism.

## Sources

- [PDBe entry 4EE3](https://www.ebi.ac.uk/pdbe/entry/pdb/4ee3)
