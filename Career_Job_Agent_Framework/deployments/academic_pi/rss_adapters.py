"""Injected RSS discovery adapter using the existing connector protocol."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, MutableMapping

from ...core.connectors import DiscoveryBatch, DiscoveryRequest
from ...core.models import utc_now
from .rss_ingestion import PARSER_VERSION, FeedItem, parse_feed


FetchText = Callable[[str], str | Mapping[str, Any]]
BootstrapFetcher = Callable[[str], Iterable[Mapping[str, Any]] | DiscoveryBatch]


def _state_row(state: MutableMapping[str, Any], url: str) -> dict[str, Any]:
    current = state.get(url)
    if not isinstance(current, Mapping):
        current = {}
    row = copy.deepcopy(dict(current))
    state[url] = row
    return row


def _bounded(values: Iterable[str], *, limit: int = 5000) -> list[str]:
    unique = list(dict.fromkeys(str(value) for value in values if value))
    return unique[-limit:]


@dataclass
class RssDiscoveryAdapter:
    """Fetch configured feeds through a host callback and emit DiscoveryBatch.

    ``feed_state`` is an injected mutable mapping so the adapter stays agnostic
    about the durable storage implementation.  A production host should load it
    from private state before a run and persist it only after the run succeeds.
    """

    id: str
    feed_urls: tuple[str, ...]
    fetch_text: FetchText
    feed_state: MutableMapping[str, Any] = field(default_factory=dict)
    bootstrap_url: str | None = None
    bootstrap_fetcher: BootstrapFetcher | None = None
    bootstrap_enabled: bool = False
    parser_version: str = PARSER_VERSION
    supports_institution_scan: bool = field(default=False, init=False)

    @property
    def connector_id(self) -> str:
        return self.id

    def clone_for_dry_run(self) -> "RssDiscoveryAdapter":
        """Return an isolated adapter whose feed bookkeeping cannot leak live."""

        clone = copy.copy(self)
        clone.feed_state = copy.deepcopy(self.feed_state)
        return clone

    def _bootstrap(
        self,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
        if not self.bootstrap_enabled or not self.bootstrap_url:
            return [], [], False
        marker = _state_row(self.feed_state, "__bootstrap__")
        if marker.get("completed") is True:
            return [], [], False
        marker["enabled"] = True
        marker["listing_url"] = self.bootstrap_url
        marker["last_attempt_at"] = utc_now()
        if self.bootstrap_fetcher is None:
            return (
                [],
                [
                    {
                        "category": "source_unavailable",
                        "message": "RSS bootstrap is enabled but no bootstrap fetcher is configured",
                        "source_id": self.id,
                    }
                ],
                False,
            )
        try:
            value = self.bootstrap_fetcher(self.bootstrap_url)
            if isinstance(value, DiscoveryBatch):
                if value.errors:
                    raise RuntimeError("; ".join(str(item) for item in value.errors))
                candidates = list(value.candidates)
            else:
                candidates = [dict(item) for item in value]
        except Exception as exc:
            marker["last_error"] = str(exc)
            return (
                [],
                [
                    {
                        "category": "source_unavailable",
                        "message": f"RSS bootstrap failed: {exc}",
                        "source_id": self.id,
                    }
                ],
                False,
            )
        marker.update(
            {
                "completed": True,
                "completed_at": utc_now(),
                "items_seen": len(candidates),
                "last_error": None,
            }
        )
        return candidates, [], True

    @staticmethod
    def _fetch_payload(
        value: str | Mapping[str, Any],
    ) -> tuple[str | None, dict[str, Any]]:
        if isinstance(value, str):
            return value, {}
        metadata = dict(value)
        text = metadata.pop(
            "text", metadata.pop("xml_text", metadata.pop("body", None))
        )
        return str(text) if text is not None else None, metadata

    def discover(self, request: DiscoveryRequest) -> DiscoveryBatch:
        candidates, errors, bootstrap_succeeded = self._bootstrap()
        attempted_at = utc_now()
        health: list[dict[str, Any]] = []
        successful_feeds = 0

        for feed_url in self.feed_urls:
            row = _state_row(self.feed_state, feed_url)
            row["feed_url"] = feed_url
            row["last_attempt_at"] = utc_now()
            row["parser_version"] = self.parser_version
            try:
                fetched = self.fetch_text(feed_url)
                xml_text, response = self._fetch_payload(fetched)
                if response.get("not_modified") is True:
                    successful_feeds += 1
                    row["last_success_at"] = utc_now()
                    row["last_error"] = None
                    health.append(
                        {
                            "feed_url": feed_url,
                            "status": "not_modified",
                            "items_seen": 0,
                            "new_items": 0,
                        }
                    )
                    continue
                if xml_text is None:
                    raise ValueError("fetch callback returned no feed text")
                parsed = parse_feed(xml_text, self.id, feed_url)
                if parsed.errors:
                    raise ValueError("; ".join(parsed.errors))

                seen_ids = set(
                    str(item) for item in row.get("seen_source_item_ids", ()) or ()
                )
                seen_links = set(
                    str(item) for item in row.get("seen_canonicalized_links", ()) or ()
                )
                new_items: list[FeedItem] = []
                for item in parsed.items:
                    known = bool(
                        (item.source_listing_id and item.source_listing_id in seen_ids)
                        or item.link in seen_links
                    )
                    if not known:
                        new_items.append(item)
                    if item.source_listing_id:
                        seen_ids.add(item.source_listing_id)
                    seen_links.add(item.link)

                candidates.extend(item.to_candidate_dict() for item in new_items)
                row.update(
                    {
                        "last_success_at": utc_now(),
                        "etag": response.get("etag", row.get("etag")),
                        "last_modified": response.get(
                            "last_modified", row.get("last_modified")
                        ),
                        "last_item_seen_at": utc_now()
                        if parsed.items
                        else row.get("last_item_seen_at"),
                        "seen_source_item_ids": _bounded(seen_ids),
                        "seen_canonicalized_links": _bounded(seen_links),
                        "last_error": None,
                        "items_seen": len(parsed.items),
                        "new_items": len(new_items),
                        "parser_warnings": list(parsed.warnings),
                    }
                )
                successful_feeds += 1
                health.append(
                    {
                        "feed_url": feed_url,
                        "status": "success",
                        "items_seen": len(parsed.items),
                        "new_items": len(new_items),
                        "warnings": list(parsed.warnings),
                    }
                )
            except Exception as exc:
                row["last_error"] = str(exc)
                errors.append(
                    {
                        "category": "parser_error"
                        if "xml" in str(exc).casefold()
                        else "source_unavailable",
                        "message": str(exc),
                        "source_id": self.id,
                        "feed_url": feed_url,
                    }
                )
                health.append(
                    {"feed_url": feed_url, "status": "failed", "error": str(exc)}
                )

        deduplicated: list[dict[str, Any]] = []
        seen_candidates: set[tuple[str, ...]] = set()
        for candidate in candidates:
            urls = candidate.get("discovery_urls", ()) or ()
            link = str(urls[0]) if urls else ""
            listing_id = str(candidate.get("source_listing_id") or "")
            key = (
                ("source_listing_id", listing_id)
                if listing_id
                else ("canonical_link", link)
                if link
                else (
                    str(candidate.get("organization") or "").casefold(),
                    str(candidate.get("title") or "").casefold(),
                    str(candidate.get("department") or "").casefold(),
                )
            )
            if key in seen_candidates:
                continue
            seen_candidates.add(key)
            deduplicated.append(candidate)

        return DiscoveryBatch(
            source_id=self.id,
            candidates=deduplicated,
            attempted_at=attempted_at,
            completed_at=utc_now() if successful_feeds or bootstrap_succeeded else None,
            errors=errors,
            metadata={
                "retrieval_completed": bool(successful_feeds or bootstrap_succeeded),
                "bootstrap_completed_this_run": bootstrap_succeeded,
                "feed_health": health,
                "items_seen": sum(int(item.get("items_seen", 0)) for item in health),
                "new_items": sum(int(item.get("new_items", 0)) for item in health),
                "parser_version": self.parser_version,
            },
        )


__all__ = ["BootstrapFetcher", "FetchText", "RssDiscoveryAdapter"]
