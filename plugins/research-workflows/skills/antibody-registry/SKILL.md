---
name: antibody-registry
description: Extract public antibody product metadata into a proposed standalone record without accessing or modifying a real inventory. Use for schema-guided antibody record preparation; do not use for inventory mutation or purchasing.
---

# Antibody Record Preparation

Prepare one proposed antibody record from a public vendor page, datasheet,
label, screenshot, or other source deliberately supplied by the user. A PDF is
eligible only when the user explicitly supplies a public PDF for the current
run; never discover, copy, or upload PDFs automatically.

## Boundary

- Use `assets/antibody_extraction_schema.yaml`.
- Return YAML or JSON for human review.
- Do not open, search, infer, create, or modify a real inventory.
- Do not merge with an existing record or claim an inventory update occurred.
- Do not purchase, add to a cart, sign in, or contact a vendor.
- Separate vendor claims from user-supplied comments or observations.
- Preserve uncertainty and conflicting source statements.

## Extraction rules

1. Classify the proposed record as primary or secondary antibody.
2. Extract only explicitly supported information.
3. Never invent RRIDs, clone names, validation claims, concentrations,
   wavelengths, species reactivity, or recommended dilutions.
4. Record source URLs and retrieval dates when available.
5. Flag missing identifiers, possible duplicates, and source conflicts.
6. Keep experimental observations distinct from vendor documentation.

Return the proposed record, a short confidence summary, missing or uncertain
fields, and any questions needed before the user decides whether to save it.
