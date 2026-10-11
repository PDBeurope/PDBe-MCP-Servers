# Q013 — How do I download coordinates for 1CBS?

**Question:** How do I download coordinates for 1cbs?

- **Retrieved:** 2026-10-11
- **LLM:** Moonshot AI Kimi K2.5 (`moonshotai.kimi-k2.5`)

## MCP calls

`run_pdbe_search_query({"query":"pdb_id:1cbs","fl":["pdb_id","title","experimental_method","resolution"],"rows":1})`

## What the tool returned

- **PDB ID:** 1CBS
- **Title:** Crystal structure of cellular retinoic-acid-binding proteins I and II in complex with all-trans-retinoic acid and a synthetic retinoid
- **Method:** X-ray diffraction
- **Resolution:** 1.8 Å

## Example answer

To download coordinates for **1CBS**, use the following PDBe URLs:

### Coordinate files

| Format | URL |
|--------|-----|
| **PDB format** | `https://www.ebi.ac.uk/pdbe/entry-files/download/pdb1cbs.ent` |
| **mmCIF format** | `https://www.ebi.ac.uk/pdbe/entry-files/download/1cbs.cif` |
| **Binary mmCIF (.bcif)** | `https://www.ebi.ac.uk/pdbe/entry-files/download/1cbs.bcif` |

### Command-line download (Unix/Linux/Mac)

```bash
# Download in PDB format
curl -o 1cbs.pdb https://www.ebi.ac.uk/pdbe/entry-files/download/pdb1cbs.ent

# Download in mmCIF format
curl -o 1cbs.cif https://www.ebi.ac.uk/pdbe/entry-files/download/1cbs.cif
```

### Python example

```python
import urllib.request

# Download mmCIF file
url = "https://www.ebi.ac.uk/pdbe/entry-files/download/1cbs.cif"
urllib.request.urlretrieve(url, "1cbs.cif")
```

## Entry details

- **1CBS** — Cellular retinoic acid-binding protein 2 (CRABP2) from human
- **Method:** X-ray diffraction at 1.8 Å resolution
- **Ligand:** Retinoic acid (REA)

## Sources

- [PDBe entry 1CBS](https://www.ebi.ac.uk/pdbe/entry/pdb/1cbs)
- [PDBe File Download](https://www.ebi.ac.uk/pdbe/entry/pdb/1cbs#downloads)
