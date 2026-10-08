# Paper Extraction Prompt Packet

Use this packet to create one concise Markdown literature note from public abstract and metadata only. Do not invent facts. If information is missing, write "Not found in packet".

Target note path:

{note_path}

## Route Metadata

Apply this metadata to the final note frontmatter.

```yaml
{route_metadata_block}
```

## Source Metadata

```yaml
{metadata_block}
```

## Attachment References

These paths refer to read-only local Bookends attachments. Do not ask AI tools to modify, move, rename, delete, or copy them.

```yaml
{attachment_block}
```

## Citation

{citation}

## Abstract

{abstract}

## Output Template

Use this structure for the final paper note:

```markdown
{paper_note_template}
```

## Extraction Instructions

- Write in English.
- Keep the note explicitly abstract/metadata-only.
- Preserve uncertainty and limitations.
- Separate paper claims from interpretation and speculation.
- Do not imply full-text, figure-level, or supplementary-material review.
- Prioritize mechanism, experimental logic, limitations, and project relevance only when supported by the packet.
- Keep the final note concise enough to be useful in AI context exports.
- Do not include raw data or sensitive unpublished information unless supplied and intentionally reviewed.
