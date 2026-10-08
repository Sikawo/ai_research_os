import importlib.util
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_triage.py"
SPEC = importlib.util.spec_from_file_location("run_pubmed_ai_triage", SCRIPT)
triage = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(triage)


def write_synthetic_pubmed_fixture(tmp_path):
    fixture = tmp_path / "synthetic_pubmed_results.json"
    fixture.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "pmid": "88888888",
                        "title": "Synthetic public ChatGPT packet PMC article",
                        "authors": ["Ada Example"],
                        "year": "2026",
                        "journal": "Journal of Synthetic Public Packets",
                        "doi": "10.0000/synthetic.packet.1",
                        "pmcid": "PMC8888888",
                        "abstract": (
                            "This synthetic public abstract discusses vesicle-mediated "
                            "enterovirus transmission for packet generation testing."
                        ),
                    },
                    {
                        "pmid": "99999999",
                        "title": "Synthetic public abstract only packet article",
                        "authors": ["Ben Example"],
                        "year": "2024",
                        "journal": "Journal of Synthetic Abstracts",
                        "abstract": (
                            "This synthetic public abstract discusses collective "
                            "transmission using PubMed metadata only."
                        ),
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return fixture


def write_synthetic_pmc_fixture(tmp_path):
    fixture_dir = tmp_path / "synthetic_pmc_fixtures"
    fixture_dir.mkdir()
    (fixture_dir / "PMC8888888.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<article>
  <front>
    <article-meta>
      <title-group>
        <article-title>Synthetic public ChatGPT packet PMC article</article-title>
      </title-group>
      <abstract>
        <p>Public PMC abstract text describes vesicle-associated viral transmission.</p>
      </abstract>
    </article-meta>
  </front>
  <body>
    <sec>
      <title>Results</title>
      <p>Public PMC body text reports synthetic vesicle transmission evidence.</p>
    </sec>
    <fig>
      <caption>
        <p>Public PMC figure caption describes a synthetic vesicle panel.</p>
      </caption>
    </fig>
  </body>
</article>
""",
        encoding="utf-8",
    )
    return fixture_dir


def run_packet_triage(tmp_path, *extra_args):
    output_root = tmp_path / "exports" / "pubmed_ai_triage"
    args = [
        sys.executable,
        str(SCRIPT),
        "--goal",
        "Synthetic public packet goal for vesicle-mediated enterovirus transmission.",
        "--topic-slug",
        "synthetic_chatgpt_packet",
        "--input-pubmed-json",
        str(write_synthetic_pubmed_fixture(tmp_path)),
        "--input-pmc-fixtures",
        str(write_synthetic_pmc_fixture(tmp_path)),
        "--sort",
        "newest",
        "--check-pmc-full-text",
        "--generate-full-text-drafts",
        "--generate-chatgpt-note-packet",
        "--pmc-top-n",
        "2",
        "--abstract-top-n",
        "2",
        "--output-root",
        str(output_root),
        "--timestamp",
        "20260526_180000",
        *extra_args,
    ]
    result = subprocess.run(
        args,
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    run_folder = output_root / "20260526_180000_synthetic_chatgpt_packet"
    return result, run_folder


def assert_conditional_source_provenance_rules(text):
    abstract_match = re.search(
        r"For abstract-only notes generated from PubMed metadata and PubMed abstract only(?:,|:)"
        r".*?```yaml\n(?P<yaml>.*?)\n```",
        text,
        flags=re.S,
    )
    assert abstract_match is not None
    abstract_yaml = abstract_match.group("yaml")
    assert "source: pubmed_ai_triage_chatgpt_packet" in abstract_yaml
    assert "note_depth: abstract_metadata_only" in abstract_yaml
    assert "security_tier: public" in abstract_yaml
    assert "read_depth: pubmed_abstract_reviewed" in abstract_yaml
    assert "human_review_status: ai_draft_needs_human_review" in abstract_yaml
    assert "source_provenance:\n  - PubMed metadata\n  - PubMed abstract" in abstract_yaml
    assert "public PMC XML text" not in abstract_yaml

    public_pmc_match = re.search(
        r"For notes generated from included public PMC XML/text evidence(?:, use exactly)?:"
        r".*?```yaml\n(?P<yaml>.*?)\n```",
        text,
        flags=re.S,
    )
    assert public_pmc_match is not None
    public_pmc_yaml = public_pmc_match.group("yaml")
    assert "source: pubmed_ai_triage_chatgpt_packet" in public_pmc_yaml
    assert "note_depth: public_full_text_reviewed" in public_pmc_yaml
    assert "security_tier: public" in public_pmc_yaml
    assert "read_depth: public_full_text_reviewed" in public_pmc_yaml
    assert "human_review_status: ai_draft_needs_human_review" in public_pmc_yaml
    assert (
        "source_provenance:\n"
        "  - PubMed metadata\n"
        "  - PubMed abstract\n"
        "  - public PMC XML text"
    ) in public_pmc_yaml


def test_generate_chatgpt_note_packet_creates_canonical_files(tmp_path):
    result, run_folder = run_packet_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    packet_dir = run_folder / "chatgpt_note_packet"
    assert packet_dir.is_dir()
    assert (packet_dir / "README_START_HERE.md").is_file()
    assert (packet_dir / "CHATGPT_CREATE_NOTES_PACKET.md").is_file()
    assert (packet_dir / "expected_output_schema.md").is_file()
    assert (packet_dir / "selected_notes_template.yaml").read_text(encoding="utf-8") == "notes: []\n"
    assert (packet_dir / "public_sources" / "pubmed_records.json").is_file()
    assert (packet_dir / "public_sources" / "abstract_candidates.md").is_file()
    assert (packet_dir / "public_sources" / "pmc_full_text_candidates.md").is_file()
    assert (packet_dir / "generated_context" / "PUBMED_TRIAGE_SUMMARY.md").is_file()
    assert (packet_dir / "generated_context" / "DISCUSS_IMPORT_TO_PAPERS.md").is_file()
    assert (
        packet_dir / "CHATGPT_CREATE_NOTES_PACKET_synthetic_chatgpt_packet_20260526_180000.zip"
    ).is_file()


def test_packet_source_manifest_records_public_sources_and_sort_mode(tmp_path):
    result, run_folder = run_packet_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    manifest = json.loads(
        (run_folder / "chatgpt_note_packet" / "public_sources" / "source_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    main_manifest = json.loads((run_folder / "pubmed_triage_manifest.json").read_text(encoding="utf-8"))
    summary = (run_folder / "PUBMED_TRIAGE_SUMMARY.md").read_text(encoding="utf-8")

    assert manifest["pubmed_sort_mode"] == "newest"
    assert main_manifest["pubmed_sort_mode"] == "newest"
    assert "PubMed sort mode: `newest`" in summary
    assert manifest["pubmed_metadata_included"] is True
    assert manifest["pubmed_abstracts_included"] is True
    assert manifest["public_pmc_xml_text_included"] is True
    assert manifest["pdfs_included"] is False
    assert manifest["bookends_files_included"] is False
    assert manifest["existing_paper_notes_included"] is False
    assert manifest["private_notes_included"] is False


def test_zip_contains_expected_packet_files(tmp_path):
    result, run_folder = run_packet_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    zip_path = (
        run_folder
        / "chatgpt_note_packet"
        / "CHATGPT_CREATE_NOTES_PACKET_synthetic_chatgpt_packet_20260526_180000.zip"
    )
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())

    assert "README_START_HERE.md" in names
    assert "CHATGPT_CREATE_NOTES_PACKET.md" in names
    assert "expected_output_schema.md" in names
    assert "selected_notes_template.yaml" in names
    assert "public_sources/source_manifest.json" in names
    assert "generated_context/PUBMED_TRIAGE_SUMMARY.md" in names
    assert "generated_context/DISCUSS_IMPORT_TO_PAPERS.md" in names


def test_primary_packet_includes_required_review_rules_and_excludes_unsafe_markers(tmp_path):
    result, run_folder = run_packet_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    packet = (
        run_folder / "chatgpt_note_packet" / "CHATGPT_CREATE_NOTES_PACKET.md"
    ).read_text(encoding="utf-8")

    assert "human_review_status: ai_draft_needs_human_review" in packet
    assert "security_tier: public" in packet
    assert "restricted to public PubMed/PMC evidence" in packet
    assert "Do not mark anything `approved_for_import`" in packet
    assert "use prior memory, private notes" in packet
    assert "restricted evidence" in packet
    assert "unpublished evidence" in packet
    assert "repository-private evidence" in packet
    assert "Bookends files" in packet
    assert "Not available in packet" in packet
    assert "source_url" not in packet
    assert "file:" + "//" not in packet
    assert "/" + "Users/" not in packet
    assert str(tmp_path) not in packet
    assert "Bookends/Attachments" not in packet
    assert "OPENAI_API_KEY" not in packet
    assert "API key" not in packet
    assert "Papers/" not in packet
    assert "Indexes/PAPER_SOURCE_MAP.yaml" not in packet


def test_packet_instructions_use_conditional_source_provenance_by_depth(tmp_path):
    result, run_folder = run_packet_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    packet_dir = run_folder / "chatgpt_note_packet"
    packet = (packet_dir / "CHATGPT_CREATE_NOTES_PACKET.md").read_text(encoding="utf-8")
    schema = (packet_dir / "expected_output_schema.md").read_text(encoding="utf-8")

    assert_conditional_source_provenance_rules(packet)
    assert_conditional_source_provenance_rules(schema)
    assert "human_review_status: ai_draft_needs_human_review" in packet
    assert "human_review_status: ai_draft_needs_human_review" in schema
    assert "security_tier: public" in packet
    assert "security_tier: public" in schema
    assert "Do not mark anything `approved_for_import`" in packet
    assert "Do not mark anything `approved_for_import`" in schema
    assert "Use only the included public PubMed metadata" in packet
    assert '"external_ai_api_called": false' in packet


def test_generated_context_is_sanitized_for_upload_packet(tmp_path):
    result, run_folder = run_packet_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    packet_dir = run_folder / "chatgpt_note_packet"
    combined_context = (
        (packet_dir / "generated_context" / "PUBMED_TRIAGE_SUMMARY.md").read_text(encoding="utf-8")
        + "\n"
        + (packet_dir / "generated_context" / "DISCUSS_IMPORT_TO_PAPERS.md").read_text(
            encoding="utf-8"
        )
    )

    assert "Papers/" not in combined_context
    assert "source_url" not in combined_context
    assert "file:" + "//" not in combined_context
    assert "/" + "Users/" not in combined_context


def test_copy_packet_artifacts_to_fake_downloads_adds_safe_suffix(tmp_path):
    primary = tmp_path / "CHATGPT_CREATE_NOTES_PACKET_topic_20260526.md"
    archive = tmp_path / "CHATGPT_CREATE_NOTES_PACKET_topic_20260526.zip"
    primary.write_text("packet", encoding="utf-8")
    archive.write_text("zip", encoding="utf-8")
    fake_downloads = tmp_path / "Downloads"
    fake_downloads.mkdir()
    (fake_downloads / primary.name).write_text("existing", encoding="utf-8")

    copied = triage.copy_packet_artifacts_to_downloads(
        primary_packet_path=primary,
        zip_packet_path=archive,
        downloads_dir=fake_downloads,
    )

    assert copied["md"].name == "CHATGPT_CREATE_NOTES_PACKET_topic_20260526_1.md"
    assert copied["md"].read_text(encoding="utf-8") == "packet"
    assert copied["zip"].name == "CHATGPT_CREATE_NOTES_PACKET_topic_20260526.zip"
    assert copied["zip"].read_text(encoding="utf-8") == "zip"


def test_main_without_timestamp_copies_actual_generated_packet_paths(tmp_path, monkeypatch):
    fake_downloads = tmp_path / "Downloads"
    captured = {}
    original_copy = triage.copy_packet_artifacts_to_downloads

    def copy_to_fake_downloads(*, primary_packet_path, zip_packet_path, downloads_dir=None):
        copied = original_copy(
            primary_packet_path=primary_packet_path,
            zip_packet_path=zip_packet_path,
            downloads_dir=fake_downloads,
        )
        captured["primary_packet_path"] = primary_packet_path
        captured["zip_packet_path"] = zip_packet_path
        captured["copied"] = copied
        return copied

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(triage, "copy_packet_artifacts_to_downloads", copy_to_fake_downloads)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--goal",
            "Synthetic public packet goal for vesicle-mediated enterovirus transmission.",
            "--topic-slug",
            "synthetic_chatgpt_packet",
            "--input-pubmed-json",
            str(write_synthetic_pubmed_fixture(tmp_path)),
            "--input-pmc-fixtures",
            str(write_synthetic_pmc_fixture(tmp_path)),
            "--check-pmc-full-text",
            "--generate-chatgpt-note-packet",
            "--copy-packet-to-downloads",
            "--output-root",
            str(tmp_path / "exports" / "pubmed_ai_triage"),
        ],
    )

    assert triage.main() == 0

    run_folders = sorted((tmp_path / "exports" / "pubmed_ai_triage").glob("*_synthetic_chatgpt_packet"))
    assert len(run_folders) == 1
    actual_timestamp = run_folders[0].name.removesuffix("_synthetic_chatgpt_packet")
    assert re.fullmatch(r"\d{8}T\d{6}Z", actual_timestamp)
    expected_md_name = f"CHATGPT_CREATE_NOTES_PACKET_synthetic_chatgpt_packet_{actual_timestamp}.md"
    expected_zip_name = f"CHATGPT_CREATE_NOTES_PACKET_synthetic_chatgpt_packet_{actual_timestamp}.zip"

    assert captured["primary_packet_path"].name == expected_md_name
    assert captured["zip_packet_path"].name == expected_zip_name
    assert captured["copied"]["md"].is_file()
    assert captured["copied"]["zip"].is_file()
    assert captured["copied"]["md"].name == expected_md_name
    assert captured["copied"]["zip"].name == expected_zip_name


def test_reveal_packet_helper_is_skipped_off_macos(tmp_path):
    packet_zip = tmp_path / "packet.zip"
    packet_zip.write_text("zip", encoding="utf-8")

    assert triage.reveal_packet_in_finder(packet_zip, platform="linux") is False


def test_copy_and_reveal_flags_require_packet_generation(tmp_path):
    output_root = tmp_path / "exports" / "pubmed_ai_triage"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--goal",
            "Synthetic public packet goal.",
            "--topic-slug",
            "synthetic_chatgpt_packet",
            "--output-root",
            str(output_root),
            "--timestamp",
            "20260526_180001",
            "--copy-packet-to-downloads",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "--generate-chatgpt-note-packet" in result.stdout


def test_existing_prompt_packet_backend_unchanged_without_new_packet_flag(tmp_path):
    output_root = tmp_path / "exports" / "pubmed_ai_triage"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--goal",
            "Synthetic public packet goal.",
            "--topic-slug",
            "synthetic_prompt_packet",
            "--input-pubmed-json",
            str(write_synthetic_pubmed_fixture(tmp_path)),
            "--output-root",
            str(output_root),
            "--timestamp",
            "20260526_180002",
            "--ai-backend",
            "prompt_packet",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    run_folder = output_root / "20260526_180002_synthetic_prompt_packet"

    assert result.returncode == 0, result.stderr + result.stdout
    assert (run_folder / "ai_backend" / "AI_PROMPT_PACKET.md").is_file()
    assert not (run_folder / "chatgpt_note_packet").exists()
