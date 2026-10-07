from __future__ import annotations

from Career_Job_Agent_Framework.core.connectors import (
    DiscoveryConnector,
    DiscoveryRequest,
)
from Career_Job_Agent_Framework.core.state import InMemoryStateStore
from Career_Job_Agent_Framework.deployments.academic_pi.rss_adapters import (
    RssDiscoveryAdapter,
)
from Career_Job_Agent_Framework.deployments.academic_pi.rss_ingestion import parse_feed
from Career_Job_Agent_Framework.deployments.academic_pi.service import AcademicPiService


FEED_ONE = """<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://purl.org/rss/1.0/"
         xmlns:ads="https://academicjobsonline.org/ads#">
  <channel rdf:about="https://academicjobsonline.org/feed"><title>AJO</title></channel>
  <item rdf:about="https://academicjobsonline.org/ajo/jobs/30001">
    <title>Assistant Professor of Virology</title>
    <link>https://academicjobsonline.org/ajo/jobs/30001?utm_source=rss</link>
    <description>Tenure-track faculty opening</description>
    <ads:ID>30001</ads:ID>
    <ads:university>Synthetic University</ads:university>
    <ads:department>Microbiology</ads:department>
    <ads:city>Example City</ads:city>
    <ads:state>MA</ads:state>
    <ads:country>US</ads:country>
    <ads:disciplines>Virology; Immunology</ads:disciplines>
    <ads:postdate>2026-10-01</ads:postdate>
    <ads:deadline>2026-12-01</ads:deadline>
  </item>
</rdf:RDF>
"""

FEED_TWO = """<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://purl.org/rss/1.0/" xmlns:ads="https://academicjobsonline.org/ads#">
  <item rdf:about="https://academicjobsonline.org/ajo/jobs/30002">
    <title>Open Rank Professor of Biology</title>
    <link>https://academicjobsonline.org/ajo/jobs/30002</link>
    <ads:ID>30002</ads:ID>
    <ads:university>Example Institute</ads:university>
  </item>
</rdf:RDF>
"""


def test_parse_ajo_rdf_ads_fields() -> None:
    result = parse_feed(FEED_ONE, "academic_jobs_online", "https://feed.example/tt")
    assert result.errors == []
    assert len(result.items) == 1
    item = result.items[0]
    assert item.source_listing_id == "30001"
    assert item.title == "Assistant Professor of Virology"
    assert item.link == "https://academicjobsonline.org/ajo/jobs/30001"
    assert item.university == "Synthetic University"
    assert item.department == "Microbiology"
    assert (item.city, item.state, item.country) == ("Example City", "MA", "US")
    assert item.disciplines == ("Virology", "Immunology")
    assert item.post_date == "2026-10-01"
    assert item.deadline == "2026-12-01"
    candidate = result.candidates[0]
    assert "official_job_id" not in candidate
    assert candidate["source_listing_id"] == "30001"


def test_missing_ads_id_is_retained_by_canonical_link() -> None:
    xml = FEED_TWO.replace("<ads:ID>30002</ads:ID>", "")
    result = parse_feed(xml, "academic_jobs_online", "https://feed.example/open")
    assert len(result.items) == 1
    assert result.items[0].source_listing_id is None
    assert result.items[0].item_key.endswith("/30002")
    assert result.warnings == [
        "missing_source_listing_id:https://academicjobsonline.org/ajo/jobs/30002"
    ]


def test_malformed_xml_is_reported_without_raising() -> None:
    result = parse_feed(
        "<rss><item>", "academic_jobs_online", "https://feed.example/bad"
    )
    assert result.items == []
    assert result.errors and result.errors[0].startswith("malformed_xml:")


def test_adapter_satisfies_protocol_scans_both_feeds_and_dedupes_restarts() -> None:
    urls = ("https://feed.example/tt", "https://feed.example/open")
    payloads = {urls[0]: FEED_ONE, urls[1]: FEED_TWO}
    state: dict[str, object] = {}
    adapter = RssDiscoveryAdapter(
        "academic_jobs_online", urls, payloads.__getitem__, feed_state=state
    )
    assert isinstance(adapter, DiscoveryConnector)
    request = DiscoveryRequest(run_id="run-1", source_id="academic_jobs_online")
    first = adapter.discover(request)
    second = adapter.discover(request)
    assert {item["source_listing_id"] for item in first.candidates} == {
        "30001",
        "30002",
    }
    assert second.candidates == []
    assert first.metadata["items_seen"] == 2
    assert first.metadata["new_items"] == 2
    assert state[urls[0]]["seen_source_item_ids"] == ["30001"]


def test_duplicate_item_across_two_feeds_is_emitted_once() -> None:
    adapter = RssDiscoveryAdapter(
        "academic_jobs_online",
        ("https://feed.example/a", "https://feed.example/b"),
        lambda _url: FEED_ONE,
    )
    batch = adapter.discover(DiscoveryRequest(run_id="run-duplicate"))
    assert len(batch.candidates) == 1


def test_feed_failure_preserves_seen_state_and_reports_coverage_error() -> None:
    url = "https://feed.example/tt"
    state = {
        url: {
            "seen_source_item_ids": ["older"],
            "seen_canonicalized_links": ["https://example.org/older"],
            "last_success_at": "2026-10-01T00:00:00Z",
        }
    }
    adapter = RssDiscoveryAdapter(
        "academic_jobs_online", (url,), lambda _url: "<rss>", feed_state=state
    )
    batch = adapter.discover(DiscoveryRequest(run_id="run-failure"))
    assert batch.candidates == []
    assert batch.errors
    assert state[url]["seen_source_item_ids"] == ["older"]
    assert state[url]["seen_canonicalized_links"] == ["https://example.org/older"]
    assert state[url]["last_success_at"] == "2026-10-01T00:00:00Z"


def test_response_metadata_and_not_modified_update_feed_state() -> None:
    url = "https://feed.example/tt"
    calls = 0

    def fetch(_url: str):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"text": FEED_ONE, "etag": "v1", "last_modified": "Mon"}
        return {"not_modified": True, "etag": "v1"}

    state: dict[str, object] = {}
    adapter = RssDiscoveryAdapter(
        "academic_jobs_online", (url,), fetch, feed_state=state
    )
    adapter.discover(DiscoveryRequest(run_id="first"))
    second = adapter.discover(DiscoveryRequest(run_id="second"))
    assert second.candidates == []
    assert state[url]["etag"] == "v1"
    assert state[url]["last_modified"] == "Mon"
    assert second.metadata["feed_health"][0]["status"] == "not_modified"


def test_bootstrap_runs_once_and_only_marks_successful_completion() -> None:
    bootstrap_calls = 0

    def bootstrap(_url: str):
        nonlocal bootstrap_calls
        bootstrap_calls += 1
        return [
            {
                "title": "Assistant Professor of Biology",
                "organization": "Bootstrap University",
                "discovery_urls": ["https://example.edu/bootstrap-job"],
            }
        ]

    state: dict[str, object] = {}
    adapter = RssDiscoveryAdapter(
        "academic_jobs_online",
        (),
        lambda _url: "",
        feed_state=state,
        bootstrap_url="https://academicjobsonline.org/ajo/jobs/job",
        bootstrap_fetcher=bootstrap,
        bootstrap_enabled=True,
    )
    first = adapter.discover(DiscoveryRequest(run_id="bootstrap-1"))
    second = adapter.discover(DiscoveryRequest(run_id="bootstrap-2"))
    assert len(first.candidates) == 1
    assert second.candidates == []
    assert bootstrap_calls == 1
    assert state["__bootstrap__"]["completed"] is True


def test_rss_connector_cannot_claim_direct_target_institution_coverage() -> None:
    adapter = RssDiscoveryAdapter(
        "academic_jobs_online",
        ("https://feed.example/tt",),
        lambda _url: FEED_ONE,
    )
    state = InMemoryStateStore()
    service = AcademicPiService(
        config={
            "academic_pi": {"automation": {"auto_apply": False}},
            "target_institutions": {
                "institutions": [
                    {
                        "name": "Synthetic University",
                        "enabled": True,
                        "domains": ["synthetic.example.edu"],
                        "career_urls": ["https://synthetic.example.edu/careers"],
                    }
                ]
            },
        },
        state_store=state,
        discovery_connectors=[adapter],
    )

    result = service.daily()

    coverage = state.list_institution_coverage()[0]
    assert result.metrics["institutions_checked"] == 0
    assert coverage.status == "not_attempted"
    assert coverage.official_pages_checked == []


def test_service_dry_run_does_not_mutate_live_rss_feed_state() -> None:
    feed_state: dict[str, object] = {}
    adapter = RssDiscoveryAdapter(
        "academic_jobs_online",
        ("https://feed.example/tt",),
        lambda _url: FEED_ONE,
        feed_state=feed_state,
    )
    service = AcademicPiService(
        config={"academic_pi": {"automation": {"auto_apply": False}}},
        state_store=InMemoryStateStore(),
        discovery_connectors=[adapter],
    )

    result = service.dry_run()

    assert result.metrics["raw_candidates"] == 1
    assert feed_state == {}
