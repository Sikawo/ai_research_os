# PubMed AI Chat Search Prompt

Use this prompt with ChatGPT or Claude before running the local PubMed metadata script.

```text
You are helping plan a PubMed-only literature search.

Research question:
[PASTE QUESTION]

Constraints:
- Use PubMed/NCBI as the search source.
- Do not claim full-text review unless full text is actually provided and read.
- Treat PubMed Best Match top-N as a candidate list, not as a claim of scientific importance.
- Prefer precise Boolean queries, MeSH terms when useful, and clear inclusion/exclusion criteria.
- Keep human scientific judgment primary.

Please provide:
1. A refined PubMed search question.
2. Two to four PubMed query candidates, from broad to narrow.
3. Key synonyms, organism/cell-type terms, disease/process terms, and method terms.
4. Suggested screening criteria for relevance and evidence strength.
5. A recommended `retmax` and `deep-read` value for the local script.
6. A short note about what would require full-text review.
```

After running `scripts/run_search.py`, paste or upload `SEARCH_PACKET.md` and ask:

```text
Screen this PubMed metadata packet.

Use only the provided PubMed metadata unless I provide additional public abstract or full-text content.
For each top candidate, classify relevance as high, medium, low, or unclear.
Then choose the requested number of papers for deeper reading and explain exactly what should be checked in the full text.
Do not use `Full text reviewed` unless full text was actually read.
```

If the script was run with `--include-abstracts`, paste or upload `ABSTRACT_SCREENING_PACKET.md` instead:

```text
Screen this PubMed abstract packet.

Use only the provided PubMed/NCBI metadata and abstracts.
For each top candidate, classify relevance as high, medium, low, or unclear.
Then choose the requested number of deep-reading candidates and explain exactly what should be checked in the full text.
Use `PubMed verified; abstract reviewed` only for abstract-level screening.
Use `Abstract reviewed; full text not available in this workflow` when full text was not supplied.
Do not use `Full text reviewed` unless full text was actually read.
Do not treat PMCID or PMC URLs as evidence that PMC full text was read.
```
