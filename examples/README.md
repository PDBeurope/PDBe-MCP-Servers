# Worked PDBe MCP examples

These examples show how an LLM can answer real structural-biology questions by combining PDBe API and PDBe Search MCP tools. They were generated with **Moonshot AI Kimi K2.5** (`moonshotai.kimi-k2.5`), and the tool calls and results were captured on **2026-10-11**. Search results and entry content can change as PDBe is updated.

## Examples

| Benchmark question | Worked example |
| --- | --- |
| Q001 — 1CBS function, organism, and ligands | [Q001: 1CBS summary](Q001-1cbs-function-organism-ligands.md) |
| Q002 — 7K00 method, resolution, and method limitations | [Q002: 7K00 cryo-EM](Q002-7k00-method-resolution.md) |
| Q003 — Haemoglobin and oxygen binding | [Q003: Haemoglobin](Q003-hemoglobin-oxygen-binding.md) |
| Q006 — Human sialyltransferases and sugar-containing ligands | [Q006: Sialyltransferase search](Q006-sialyltransferases-search.md) |
| Q008 — Find an EMDB map linked to a PDB entry | [Q008: PDB-to-EMDB link](Q008-find-linked-emdb-map.md) |
| Q010 — Search for uncomplexed SARS-CoV-2 spike entries | [Q010: SARS-CoV-2 spike](Q010-unbound-sars-cov-2-spike.md) |
| Q011 — Cryo-EM ribosomes better than 3 Å | [Q011: Ribosome search](Q011-cryo-em-ribosome-under-3a.md) |
| Q015 — 6QVT ligands and NCC interactions | [Q015: Ligand interactions](Q015-6qvt-ligand-interactions.md) |
| Q016 — 4EE3 glycosylation and modified residues | [Q016: Glycosylation and modifications](Q016-4ee3-glycosylation-modifications.md) |

Both the PDBe API and Search servers should be enabled in the MCP client. An individual answer uses whichever tool calls are relevant; examples do not make unrelated calls just to demonstrate a server.

## Model and reproducibility

These are worked examples, not guaranteed deterministic transcripts. Other models—or the same model with different prompts, conversation context, or tool availability—may choose different tool calls, emphasize different evidence, or phrase and interpret an answer differently. PDBe's live data and server behavior can also change. For reproducible comparisons, record the model/version, prompt, tool/server version, and retrieval date.

## Reading the tool traces

- Search queries are shown as passed to `run_pdbe_search_query`; the relevant fields and filters are included where useful.
- API tool names and inputs are recorded so readers can repeat the lookup.
- Tool results are summarized rather than copied wholesale. The linked PDBe entry pages provide the full, current context.
- Criteria such as "best" or "unbound" are stated explicitly because they can have more than one interpretation.
