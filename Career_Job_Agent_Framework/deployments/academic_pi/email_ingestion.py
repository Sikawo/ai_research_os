"""Credential-free parsing and label planning for academic Gmail alerts."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from email.message import Message
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qs, unquote, urlparse

from .email_sources import EmailMessageClass, classify_email
from .models import DiscoveryCandidate, GmailLabelPlan


DEFAULT_GMAIL_LABELS = {
    "alerts": "Academic PI Job Agent/Alerts",
    "processed": "Academic PI Job Agent/Processed",
    "needs_review": "Academic PI Job Agent/Needs Review",
    "error": "Academic PI Job Agent/Error",
}

_URL_RE = re.compile(r"https?://[^\s<>\]\[()\"']+", re.I)
_TITLE_RE = re.compile(
    r"\b(?:assistant|associate|full|open[- ]rank|tenure[- ]track|research)?\s*"
    r"(?:professor(?:ship)?|faculty|investigator|group leader|lecturer|reader|"
    r"principal investigator|w[123] professor)\b|教授|准教授|講師|助教|研究主幹",
    re.I,
)
_GENERIC_LINK_RE = re.compile(
    r"^(?:view|see|read|learn more|details?|apply|open)(?:\s+(?:job|position|role|posting))?$",
    re.I,
)
_REJECTED_LINK_TEXT_RE = re.compile(
    r"(?:unsubscribe|manage (?:account|alerts?|preferences)|sign[ -]?in|log[ -]?in|"
    r"reset password|activate account|verify email|privacy|terms|facebook|linkedin|"
    r"instagram|twitter|x\.com|配信停止|ログイン|パスワード|アカウント)",
    re.I,
)
_REJECTED_PATH_RE = re.compile(
    r"/(?:unsubscribe|optout|account|login|signin|password|preferences?|social|share|"
    r"privacy|terms|activate|verify)(?:/|$)",
    re.I,
)


@dataclass
class EmailParseResult:
    message_id: str
    candidates: list[DiscoveryCandidate] = field(default_factory=list)
    parse_failures: list[str] = field(default_factory=list)
    handled_candidate_ids: set[str] = field(default_factory=set)
    failures_recorded: bool = False
    already_processed: bool = False
    message_class: EmailMessageClass = EmailMessageClass.UNKNOWN
    source_id: str = "email_alert"
    suppressed_reason: str | None = None
    needs_review: bool = False

    @property
    def all_candidates_handled(self) -> bool:
        return bool(self.candidates) and all(
            candidate.event_id in self.handled_candidate_ids
            for candidate in self.candidates
        )

    @property
    def processing_complete(self) -> bool:
        if self.already_processed:
            return True
        if self.suppressed_reason:
            return True
        candidates_complete = not self.candidates or self.all_candidates_handled
        failures_complete = not self.parse_failures or self.failures_recorded
        return (
            candidates_complete
            and failures_complete
            and bool(self.candidates or self.parse_failures)
        )


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._href: str | None = None
        self._text: list[str] = []
        self._recent: list[str] = []
        self._context: str = ""
        self.links: list[tuple[str, str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        values = {key.casefold(): value for key, value in attrs}
        href = values.get("href")
        if href:
            self._href = href
            self._text = []
            self._context = "\n".join(self._recent[-3:])

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)
        else:
            value = _clean_title(data)
            if value:
                self._recent.append(value)
                self._recent = self._recent[-6:]

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "a" and self._href is not None:
            anchor = " ".join(self._text).strip()
            self.links.append((self._href, anchor, self._context))
            if anchor:
                self._recent.append(_clean_title(anchor))
                self._recent = self._recent[-6:]
            self._href = None
            self._text = []
            self._context = ""


def _message_id(message: Any) -> str:
    if isinstance(message, Mapping):
        value = message.get("message_id") or message.get("id")
        headers = message.get("headers")
        if not value and isinstance(headers, Mapping):
            value = headers.get("Message-ID") or headers.get("message-id")
        if value:
            return str(value)
    if isinstance(message, Message):
        value = message.get("Message-ID") or message.get("X-GM-MSGID")
        if value:
            return str(value)

    # Some adapters cannot expose provider IDs.  A stable content fingerprint
    # keeps retries idempotent without collapsing every such message into the
    # old shared ``unknown-message`` bucket.
    plain, html = _parts(message)
    if isinstance(message, Mapping):
        context = "\x1f".join(
            str(message.get(key) or "")
            for key in ("subject", "from", "sender", "date", "received_at")
        )
    elif isinstance(message, Message):
        context = "\x1f".join(
            str(message.get(key) or "") for key in ("Subject", "From", "Date")
        )
    else:
        context = ""
    digest = sha256(f"{context}\x1f{plain}\x1f{html}".encode("utf-8")).hexdigest()
    return f"synthetic:{digest}"


def _parts(message: Any) -> tuple[str, str]:
    if isinstance(message, str):
        return message, ""
    if isinstance(message, Mapping):
        text = message.get("text") or message.get("body") or message.get("plain") or ""
        html = message.get("html") or ""
        payload = message.get("payload")
        if isinstance(payload, Mapping):
            text = text or payload.get("text") or payload.get("body") or ""
            html = html or payload.get("html") or ""
        links = message.get("links", ())
        if isinstance(links, str):
            links = (links,)
        text = "\n".join(
            part
            for part in (
                str(message.get("subject") or ""),
                str(text),
                *(str(item) for item in links or ()),
            )
            if part
        )
        return str(text), str(html)
    if isinstance(message, Message):
        plain_parts: list[str] = []
        html_parts: list[str] = []
        parts: Iterable[Message] = (
            message.walk() if message.is_multipart() else (message,)
        )
        for part in parts:
            if part.get_content_maintype() == "multipart":
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                raw = part.get_payload()
                value = raw if isinstance(raw, str) else ""
            else:
                charset = part.get_content_charset() or "utf-8"
                value = payload.decode(charset, errors="replace")
            if part.get_content_type() == "text/html":
                html_parts.append(value)
            elif part.get_content_type() == "text/plain":
                plain_parts.append(value)
        return "\n".join(plain_parts), "\n".join(html_parts)
    return str(message or ""), ""


def _unwrap_redirect(url: str) -> str:
    value = unescape(url).strip()
    redirect_keys = {
        "url",
        "u",
        "q",
        "target",
        "redirect",
        "redirect_url",
        "dest",
        "destination",
    }
    for _ in range(4):
        parsed = urlparse(value)
        query = {key.casefold(): items for key, items in parse_qs(parsed.query).items()}
        nested = next(
            (
                unquote(items[0])
                for key, items in query.items()
                if key in redirect_keys
                and items
                and unquote(items[0]).startswith(("http://", "https://"))
            ),
            None,
        )
        if not nested or nested == value:
            break
        value = unescape(nested)
    return value


def _clean_title(text: str) -> str:
    value = unicodedata.normalize("NFKC", unescape(text or ""))
    value = re.sub(r"\s+", " ", value).strip(" -|:\t\r\n")
    if len(value) > 180:
        value = value[:177].rstrip() + "..."
    return value


def _candidate_title(anchor: str, context: str) -> str | None:
    anchor = _clean_title(anchor)
    if anchor and _TITLE_RE.search(anchor):
        return anchor
    for line in reversed(context.splitlines()):
        line = _clean_title(line)
        if _TITLE_RE.search(line) and len(line) <= 220:
            return line
    return None


def _reject_link(url: str, anchor: str, *, has_title_context: bool) -> bool:
    parsed = urlparse(url)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        return True
    text = _clean_title(anchor)
    if _REJECTED_PATH_RE.search(parsed.path) or _REJECTED_LINK_TEXT_RE.search(text):
        return True
    return bool(text and _GENERIC_LINK_RE.fullmatch(text) and not has_title_context)


def parse_academic_alert_result(
    message: Any,
    *,
    source_id: str = "email_alert",
    processed_message_ids: Iterable[str] = (),
    email_source_registry: Any = None,
) -> EmailParseResult:
    """Parse every plausible job link from one alert without making network calls."""

    message_id = _message_id(message)
    processed = set(str(value) for value in processed_message_ids)
    classification = classify_email(message, email_source_registry)
    effective_source = (
        source_id
        if source_id != "email_alert"
        else classification.source_id or source_id
    )
    result = EmailParseResult(
        message_id=message_id,
        already_processed=message_id in processed,
        message_class=classification.message_class,
        source_id=effective_source,
        suppressed_reason=classification.reason if classification.suppressed else None,
        needs_review=classification.message_class == EmailMessageClass.UNKNOWN,
    )
    if result.already_processed:
        return result
    if result.suppressed_reason:
        return result

    plain, html = _parts(message)
    parser = _LinkParser()
    if html:
        try:
            parser.feed(html)
        except (ValueError, AssertionError) as exc:
            result.parse_failures.append(f"html_parser_error: {exc}")

    link_rows: list[tuple[str, str, str]] = [
        (_unwrap_redirect(url), anchor, "\n".join((context, anchor)))
        for url, anchor, context in parser.links
    ]
    plain_lines = [line.strip() for line in plain.splitlines()]
    for index, line in enumerate(plain_lines):
        for match in _URL_RE.finditer(line):
            nearby = "\n".join(
                item for item in plain_lines[max(0, index - 2) : index + 1] if item
            )
            link_rows.append(
                (
                    _unwrap_redirect(match.group(0).rstrip(".,;")),
                    line[: match.start()],
                    nearby,
                )
            )

    seen: set[tuple[str, str]] = set()
    for url, anchor, context in link_rows:
        if not url.lower().startswith(("http://", "https://")):
            continue
        title = _candidate_title(anchor, context)
        if not title or _reject_link(url, anchor, has_title_context=True):
            continue
        key = (url.casefold().rstrip("/"), title.casefold())
        if key in seen:
            continue
        seen.add(key)
        result.candidates.append(
            DiscoveryCandidate(
                raw_title=title,
                url=url,
                source_id=effective_source,
                message_id=message_id,
                snippet=_clean_title(context) or None,
            )
        )

    if not result.candidates and not result.parse_failures:
        result.parse_failures.append("no_plausible_job_candidates")
    return result


def parse_academic_alert(
    message: Any,
    *,
    source_id: str = "email_alert",
    processed_message_ids: Iterable[str] = (),
    email_source_registry: Any = None,
) -> list[DiscoveryCandidate]:
    return parse_academic_alert_result(
        message,
        source_id=source_id,
        processed_message_ids=processed_message_ids,
        email_source_registry=email_source_registry,
    ).candidates


def plan_gmail_labels(
    result: EmailParseResult,
    labels: Mapping[str, str] | None = None,
) -> GmailLabelPlan:
    """Return a non-destructive label plan; callers apply it after state writes."""

    configured = {**DEFAULT_GMAIL_LABELS, **dict(labels or {})}
    if result.already_processed:
        return GmailLabelPlan(
            result.message_id, (), processed=True, reason="already_processed"
        )
    if result.suppressed_reason:
        return GmailLabelPlan(
            result.message_id,
            (configured["processed"],),
            (configured["needs_review"], configured["error"]),
            processed=True,
            reason=f"suppressed: {result.suppressed_reason}",
        )
    if result.processing_complete:
        review_labels: tuple[str, ...] = ()
        if result.parse_failures:
            review_labels = (
                configured["needs_review"]
                if result.candidates or result.needs_review
                else configured["error"],
            )
        elif result.needs_review:
            review_labels = (configured["needs_review"],)
        return GmailLabelPlan(
            result.message_id,
            (configured["processed"], *review_labels),
            () if review_labels else (configured["needs_review"], configured["error"]),
            processed=True,
            reason="all candidates handled and parse failures recorded",
        )
    if result.parse_failures:
        label = (
            configured["error"] if not result.candidates else configured["needs_review"]
        )
        return GmailLabelPlan(
            result.message_id,
            (label,),
            (),
            processed=False,
            reason="parsing or candidate handling incomplete",
        )
    return GmailLabelPlan(
        result.message_id,
        (configured["needs_review"],),
        (),
        processed=False,
        reason="candidate handling incomplete",
    )
