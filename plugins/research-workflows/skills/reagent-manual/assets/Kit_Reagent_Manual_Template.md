# {{product_or_manual_name}}

```yaml
record_type: kit_reagent_manual
manual_id: MANUAL_YYYYMMDD_short-name
status: draft
last_reviewed: YYYY-MM-DD
source_type: pdf | url | webpage | vendor_page | pasted_text | other
source_reference: "URL, filename, DOI, vendor catalog page, or local file pointer"
source_date_accessed: YYYY-MM-DD
vendor: ""
manufacturer: ""
product_name: ""
catalog_number: ""
lot_specific: false
lot_number: ""
version_or_revision: ""
manual_date: ""
security_tier: external_standard
ai_extraction_status: extracted | partial | needs_human_review | source_not_accessible
manual_cautions_exhaustively_extracted: false
external_reagents_exhaustively_extracted: false
human_verified: false
related_protocols: []
related_experiments: []
tags: []
```

## 1. One-line purpose

Briefly state what this kit/reagent/manual is for.

## 2. When to use

- Suitable applications:
- Sample types / organisms / cell types:
- Input requirements:
- Output / readout:

## 3. Do not use / limitations

- Not suitable for:
- Known incompatibilities:
- Important assumptions:
- Vendor-stated limitations:

## 4. Protocol-critical cautions, notes, and gotchas from the manual

Extract this section exhaustively. Include every manual statement labeled or phrased as `Note`, `Important`, `Caution`, `Warning`, `Before you begin`, `Critical`, `Do not`, `Avoid`, `Prepare fresh`, `Use immediately`, `Protect from light`, `Keep on ice`, `Do not freeze`, `Do not vortex`, `Do not centrifuge`, or equivalent.

| Manual section / page | Exact topic | Practical meaning | Action required before experiment | Consequence if ignored | Human verified? |
|---|---|---|---|---|---|
|  |  |  |  |  | no |

## 5. Critical parameters

| Parameter | Recommended value | Acceptable range | Notes |
|---|---:|---:|---|
|  |  |  |  |

## 6. Required materials

### Included in kit

| Item | Amount / format | Storage | Notes |
|---|---:|---|---|
|  |  |  |  |

### Not included / user supplied: reagents, buffers, consumables, and equipment

Extract this section exhaustively. Include every reagent, buffer, consumable, apparatus, column, tube, plate, solvent, water type, carrier, enzyme, antibody, standard, control, or accessory that the manual says must be separately prepared, separately purchased, user-supplied, optional-but-recommended, or not included in the kit.

| Item | Type | Required / optional | Prepare or purchase? | Specification from manual | Suggested source/catalog if stated | Storage / handling | Used in step | Notes |
|---|---|---|---|---|---|---|---|---|
|  | reagent/buffer/consumable/equipment/control/other | required/optional | prepare/purchase/either/not stated |  |  |  |  |  |

### Reagents or buffers that must be freshly prepared

| Item | Composition / dilution | When to prepare | Stability after preparation | Notes |
|---|---|---|---|---|
|  |  |  |  |  |

## 7. Storage and stability

| Component | Storage | Stability / expiration | Freeze-thaw notes |
|---|---|---|---|
|  |  |  |  |

## 8. Safety and handling

- Hazard summary:
- PPE:
- Waste disposal:
- SDS/TDS status: not checked | checked | not found
- SDS/TDS link or reference:

## 9. Protocol summary for AI retrieval

Write a concise, non-verbatim operational summary. Do not copy the manual word-for-word. The procedure may be summarized, but cautions/notes and separately required reagents must not be summarized away; they must appear in Sections 4 and 6.

1. Step group 1:
2. Step group 2:
3. Step group 3:

## 10. Timing

| Stage | Approximate time | Hands-on? | Notes |
|---|---:|---|---|
|  |  |  |  |

## 11. Controls and QC

- Positive control:
- Negative control:
- Internal control:
- Pass/fail criteria:
- Expected result:

## 12. Troubleshooting

| Problem | Likely cause | Suggested action | Source confidence |
|---|---|---|---|
|  |  |  |  |

## 13. Calculations / scaling

- Reaction size:
- Number of reactions / preps / samples:
- Unit convention:
  - antibodies: USD/µg when mass is known; otherwise USD/vial
  - kits: USD/reaction, USD/prep, or USD/sample when possible
- Notes:

## 14. Ordering information

| Field | Value |
|---|---|
| Vendor |  |
| Catalog number |  |
| Pack size |  |
| Price |  |
| Normalized price |  |
| Stock status |  |
| Quote / RFQ needed |  |

## 15. User comments

Use this section for the user's empirical notes, lab-specific deviations, or comments after actual use.

- YYYY-MM-DD:

## 16. Extraction notes

- Extracted by:
- Extraction date:
- Source sections/pages used:
- Caution/note extraction status: complete | partial | needs human review
- External reagent/material extraction status: complete | partial | needs human review
- Fields requiring human verification:
- Ambiguities / missing information:

## 17. Minimal AI context block

Use this compact block when asking AI about this kit/reagent later.

```text
Manual: {{product_or_manual_name}}
Vendor/catalog: {{vendor}} / {{catalog_number}}
Purpose: {{one_line_purpose}}
Critical constraints: {{critical_constraints}}
Storage: {{storage_summary}}
Separately required reagents/materials: {{external_reagents_summary}}
Key protocol parameters: {{key_parameters}}
Controls/QC: {{controls_qc}}
Open questions: {{open_questions}}
```
