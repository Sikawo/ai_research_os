---
name: buycheck
description: Compare public laboratory-product information and visible prices without logging in, purchasing, or using institutional pricing. Use when the user requests reagent or lab-supply comparison.
---

# BuyCheck

Use this workflow when the user says:

buycheck: [item] / [category] / [requirements]

Purpose:
Compare publicly visible web prices for laboratory purchasing and produce a reproducible procurement comparison table.

This workflow is research-only. Never place an order, add an item to a cart,
sign in, contact a vendor, or initiate payment.

Default assumptions:
- United States delivery
- Public web prices only
- No hidden login prices
- No institutional contract prices
- No punchout prices
- No shipping, tax, cold-chain fees, or special fees unless publicly shown
- Do not guess missing prices
- Use official manufacturer pages or reputable scientific distributors
- Avoid Amazon, eBay, marketplace listings, and unknown resellers unless explicitly requested

Valid categories:
- chemical
- plastic
- sirna
- molbio
- antibody

## Vendor groups

### chemical
Thermo Fisher / Fisher Scientific; Sigma-Aldrich / MilliporeSigma / Merck; Cayman Chemical; Bio-Rad; RPI; GoldBio; Tocris; Selleck; MedChemExpress; Roche; Quality Biological; Crystalgen; K•D Medical; Qiagen; Wako / Fujifilm.

### plastic
Thermo Fisher / Fisher Scientific; Sigma-Aldrich / MilliporeSigma / Merck; VWR / Avantor; Thomas Scientific; Genesee Scientific; USA Scientific; Corning; Eppendorf; Greiner Bio-One; Bio-Rad.

### sirna
Horizon Discovery; Thermo Fisher / Fisher Scientific.

### molbio
Thermo Fisher / Fisher Scientific; TOYOBO; Zymo Research; Takara / Clontech; NEB; Qiagen.

### antibody
Thermo Fisher / Fisher Scientific; Sigma-Aldrich / MilliporeSigma / Merck; Abcam; Cell Signaling Technology; Proteintech; BD; BioLegend; Wako / Fujifilm.

## Search rules

1. Search the vendor group matching the category first.
2. If too few comparable options are found, add reputable scientific distributors or manufacturer pages.
3. Include the information retrieval date.
4. For each candidate, collect:
   - public product page
   - catalog number
   - package size
   - public price
   - normalized unit price
   - stock status
   - manufacturer/vendor contact email
   - phone number
   - SDS link
   - TDS/product datasheet/product information link
   - alternative or equivalent product notes
5. If price is not publicly shown, write "price not publicly shown."
6. If stock is not publicly shown, write "stock not publicly shown."
7. If SDS or TDS is not found, write "not found."
8. Do not infer hidden values.
9. Sort known prices by normalized unit price from lowest to highest.
10. Put unknown-price entries below known-price entries.

## Unit normalization

Use one normalized unit across all comparable products.

- Liquid reagent: USD/mL
- Solid or powder reagent: USD/g, or USD/mg if more appropriate
- Plastic consumable: USD/piece
- Dish or plate: USD/dish or USD/plate
- Antibody: USD/µg if total mass is available; otherwise USD/vial
- siRNA: USD/nmol if amount is available; otherwise USD/tube
- Kit: USD/reaction, USD/prep, or USD/sample when possible

## Output table

Use this exact table format:

| Rank | Product name | Vendor / manufacturer | Catalog # | Package size | Public price | Normalized unit | Unit price | Stock status | Product page | SDS | TDS/datasheet | Email | Phone | Alternative / notes |
|---:|---|---|---|---:|---:|---|---:|---|---|---|---|---|---|---|

After the table, include:

## Recommendation

- Best public price:
- Best known-brand / low-risk option:
- Need quote or login price check:
- Main caveats:

## RFQ email template

Subject: Request for Quote – [Product name / Catalog number]

Dear [Vendor Name],

I am interested in purchasing the following product for our laboratory:

Product: [Product name]
Catalog number: [Catalog number]
Package size: [Package size]
Quantity requested: [Quantity]

Could you please provide a formal quote including current availability, estimated shipping time, and any academic or institutional pricing if available?

Best regards,
the researcher
