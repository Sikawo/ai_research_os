# Public Metadata Packet Workflow

Use this workflow for bibliographic metadata and abstracts that are public and
explicitly supplied by the user. `scripts/build_bibliographic_note_packet.py`
creates review packets; it does not fetch or inspect PDFs.

Required boundaries:

1. Use an explicit input file and output directory.
2. Treat the resulting note as `abstract_metadata_only` unless public full text
   was separately supplied and reviewed.
3. Do not encode source-machine paths in the packet.
4. Do not update a paper vault, index, or Git repository automatically.
5. Review generated Markdown before any separate import action.

The helper may parse the user-selected metadata file and generate Markdown
instructions. It must not scan reference-manager folders, attachment stores,
or other local directories.
