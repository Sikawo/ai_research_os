# AI Safety Boundary

## Public-only rule

Assume every tracked byte and every Git object can be read by anyone. Content
must be safe to publish before it is staged.

## Allowed public content

- public repository guidance;
- the Apache-2.0 license;
- deny-by-default safety configuration;
- synthetic safety tests; and
- an exact deny-by-default transfer manifest;
- reviewed reusable framework and governance source;
- public schemas, templates, and synthetic fixtures; and
- tests that contain no private instances or bindings.

## Never allowed by default

- secrets, credentials, tokens, keys, cookies, or authentication material;
- personal or private configuration values;
- private resource identifiers or URLs;
- local absolute filesystem paths;
- research data, raw data, PDFs, images, notebooks, reports, logs, or caches;
- candidate, application, or personally identifying records;
- protected scientific content or private research instances; and
- prior Git objects, histories, archives, branches, tags, or reflogs.

## Stop conditions

Stop before staging if a transferred file is not explicitly allowlisted, its sharing status
is uncertain, a value appears environment-specific, or validation reports a
potential secret, private path, unsupported file type, or history anomaly.

When uncertain, leave the content out and request human review.
