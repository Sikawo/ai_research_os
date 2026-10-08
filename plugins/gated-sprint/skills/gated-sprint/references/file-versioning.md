# Working-file naming and archival

Load this reference whenever GatedSprint creates, exports, promotes, archives, or identifies current files in a user-designated working parent folder.

If the current user or project instructions designate `Working_File_Versioning_Convention.md`, read it from the designated location—normally the working parent, but sometimes a project root explicitly named by the instructions—and treat that complete file as the folder-level naming/archival authority. Mere file presence is a discovery cue, not permission to edit or move files. The tracked project authority is convention v1.1; this reference summarizes rather than replaces it. The portable convention currently uses these defaults:

- separate stable family stem and version token with `__`;
- automatic names: `<family>__YYYYMMDD-HHmmssZ.ext`;
- semantic names: `<family>__lower-kebab-version.ext`;
- semantic-name collisions: `<family>__lower-kebab-version-YYYYMMDD-HHmmssZ.ext` (one managed suffix, never stacked `__` tokens);
- same-content companion DOCX/PDF files share the same version token;
- parent root holds the current version group for each logical family;
- `previous/` holds superseded versions;
- never overwrite or delete a current/archived version;
- create and verify the new candidate before moving the predecessor to `previous/`;
- do not infer current status from modification time alone;
- resolve multiple plausible manual-edit successors before moving anything;
- do not apply this rule to read-only `sources/` or unrelated files.

Folder-current status and GatedSprint release status are independent. A newly implemented, checked candidate may become the working-current root version while remaining `UNVERIFIED` for submission until `RELEASE` passes. Never describe root placement alone as final verification.

Strip only a suffix known to have been created under the convention after `__`; never guess that a single-underscore suffix such as `_submitted` or `_draft21` is version metadata. If an unmanaged legacy name already contains `__`, require one explicit family-stem designation. Do not stack managed suffixes.

A pre-convention unversioned current file may remain a declared legacy baseline. After its verified successor is promoted, preserve that baseline unchanged under `previous/` with its original path/hash recorded; do not fabricate a historical timestamp or silently rename it. Newly created candidates always use a canonical token.

For manual revisions, create the new canonical name with Save As (or duplicate first) before substantial editing. Do not claim the prior checkpoint was preserved if an older-token file was edited in place.

Treat companion identity as a verified revision/release-bundle relationship, not a filename or extracted-text match. Text, figures, captions, or review-relevant layout differences require a new token. Enumerate outgoing companions/derivatives; archive stale old-token derivatives unless explicitly retained as independently current.

Immediately before promotion, rescan group membership and fingerprints. Stop on an archive-path collision, lock/partial/conflict file, unexpected candidate, or changed predecessor. After the move, verify both locations. On partial success, preserve and report the exact state; do not auto-retry, overwrite, rename history, or hide the inconsistency.

During `DIAGNOSE`, inspect/report file-family or current-version ambiguity but do not rename or move files. During `IMPLEMENT` or `RELEASE`, promote/archive only within the authorized working family. If the folder-level policy is absent, apply these defaults and report the chosen family stem/token. These rules never grant edit/move authority. If the policy conflicts with a current user instruction, the current instruction controls.

When a PDF and editable source differ in content, they are not the same version group even if their names imply otherwise. Resolve content authority before promotion.
