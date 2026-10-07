# Target-institution monitoring

Target priorities belong in private configuration. Copy the synthetic
`templates/target_institutions.example.yaml` into the private overlay and
replace it with approved institutions and public starting URLs.

Targets support IDs, aliases, country/region, `priority_tier`, numeric
priority, domains, career/department URLs, expected role terms, and an
optional interval. Without an override, S-tier is due daily and A-tier weekly.

Trusted host discovery visits official URLs first. For a broken URL, it uses a
bounded domain-restricted fallback plan and records old/new evidence without
silently rewriting or deleting the target. A successful zero-result scan is
successful coverage. Only institution-owned pages or allowlisted official ATS
hosts can authoritatively verify lifecycle.
