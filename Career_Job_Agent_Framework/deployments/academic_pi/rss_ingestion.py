"""Pure RSS parsing for Academic PI discovery sources."""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html import unescape
from typing import Any
from urllib.parse import urlparse

from ...core.urls import normalize_url


PARSER_VERSION = "academic_pi_rss_v1"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1].casefold()


def _clean(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = unicodedata.normalize("NFKC", unescape(str(value)))
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.split())
    return text or None


def _child_values(element: ET.Element) -> dict[str, str]:
    values: dict[str, str] = {}
    for child in list(element):
        text = _clean("".join(child.itertext()))
        if text is not None:
            values.setdefault(_local_name(child.tag), text)
    return values


def canonicalize_feed_link(value: str | None) -> str | None:
    return normalize_url(value)


@dataclass(frozen=True)
class FeedItem:
    source_id: str
    feed_url: str
    title: str
    link: str
    source_listing_id: str | None = None
    university: str | None = None
    department: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    disciplines: tuple[str, ...] = ()
    post_date: str | None = None
    deadline: str | None = None
    description: str | None = None

    @property
    def item_key(self) -> str:
        return self.source_listing_id or self.link

    def to_candidate_dict(self) -> dict[str, Any]:
        location = (
            ", ".join(value for value in (self.city, self.state, self.country) if value)
            or None
        )
        host = urlparse(self.link).hostname or "unverified source"
        return {
            "title": self.title,
            "institution": self.university,
            "organization": self.university or host.removeprefix("www."),
            "department": self.department,
            "location": location,
            "country": self.country,
            "discovery_urls": [self.link],
            "posted_date": self.post_date,
            "deadline": self.deadline,
            "description": self.description,
            # These additive fields are retained by JobRecord.extra until the
            # canonical model exposes first-class source-listing provenance.
            "source_listing_id": self.source_listing_id,
            "feed_url": self.feed_url,
            "disciplines": list(self.disciplines),
        }


@dataclass
class FeedParseResult:
    source_id: str
    feed_url: str
    items: list[FeedItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    parser_version: str = PARSER_VERSION

    @property
    def candidates(self) -> list[dict[str, Any]]:
        return [item.to_candidate_dict() for item in self.items]


def parse_feed(xml_text: str, source_id: str, feed_url: str) -> FeedParseResult:
    """Parse RSS/RDF text without network or state side effects."""

    result = FeedParseResult(source_id=source_id, feed_url=feed_url)
    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, TypeError, ValueError) as exc:
        result.errors.append(f"malformed_xml: {exc}")
        return result

    elements = [
        element for element in root.iter() if _local_name(element.tag) == "item"
    ]
    for index, element in enumerate(elements):
        values = _child_values(element)
        title = _clean(values.get("title"))
        link = canonicalize_feed_link(values.get("link"))
        if not title or not link:
            result.warnings.append(
                f"item_{index}_missing_{'title' if not title else 'link'}"
            )
            continue
        listing_id = _clean(
            values.get("id")
            or values.get("jobid")
            or values.get("listingid")
            or values.get("guid")
        )
        if not listing_id:
            result.warnings.append(f"missing_source_listing_id:{link}")
        disciplines_text = _clean(values.get("disciplines") or values.get("discipline"))
        disciplines = tuple(
            item.strip()
            for item in re.split(r"\s*[;,|]\s*", disciplines_text or "")
            if item.strip()
        )
        result.items.append(
            FeedItem(
                source_id=source_id,
                feed_url=feed_url,
                source_listing_id=listing_id,
                title=title,
                link=link,
                university=_clean(
                    values.get("university")
                    or values.get("institution")
                    or values.get("organization")
                ),
                department=_clean(values.get("department")),
                city=_clean(values.get("city")),
                state=_clean(values.get("state") or values.get("region")),
                country=_clean(values.get("country")),
                disciplines=disciplines,
                post_date=_clean(
                    values.get("postdate")
                    or values.get("posteddate")
                    or values.get("pubdate")
                    or values.get("date")
                ),
                deadline=_clean(
                    values.get("deadline")
                    or values.get("applicationdeadline")
                    or values.get("expirationdate")
                ),
                description=_clean(
                    values.get("description")
                    or values.get("summary")
                    or values.get("content")
                ),
            )
        )
    return result


__all__ = [
    "FeedItem",
    "FeedParseResult",
    "PARSER_VERSION",
    "canonicalize_feed_link",
    "parse_feed",
]
