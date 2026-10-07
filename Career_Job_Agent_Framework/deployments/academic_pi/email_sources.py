"""Pure, configurable classification for academic job-alert email.

The module intentionally knows nothing about Gmail or credentials.  Trusted
host connectors provide message metadata and an optional private source
registry; this module only classifies that data before candidate parsing.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from email.message import Message
from email.utils import parseaddr
from enum import Enum
from typing import Any, Iterable, Mapping


class EmailMessageClass(str, Enum):
    JOB_ALERT = "JOB_ALERT"
    ACCOUNT_ADMIN = "ACCOUNT_ADMIN"
    AUTH_OTP = "AUTH_OTP"
    ALERT_CONFIRMATION = "ALERT_CONFIRMATION"
    IRRELEVANT = "IRRELEVANT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class EmailSourceRule:
    source_id: str
    sender_domains: tuple[str, ...] = ()
    sender_addresses: tuple[str, ...] = ()
    subject_positive: tuple[str, ...] = ()
    subject_negative: tuple[str, ...] = ()
    enabled: bool = True
    status: str | None = None
    expected_behavior: str | None = None
    parser: str = "generic_job_alert"

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EmailSourceRule":
        def values(name: str) -> tuple[str, ...]:
            raw = value.get(name, ())
            if isinstance(raw, str):
                raw = (raw,)
            return tuple(
                str(item).strip().casefold() for item in raw or () if str(item).strip()
            )

        return cls(
            source_id=str(value.get("source_id") or "email_alert"),
            sender_domains=values("sender_domains"),
            sender_addresses=values("sender_addresses"),
            subject_positive=values("subject_positive"),
            subject_negative=values("subject_negative"),
            enabled=value.get("enabled", True) is True,
            status=str(value["status"]) if value.get("status") is not None else None,
            expected_behavior=(
                str(value["expected_behavior"])
                if value.get("expected_behavior") is not None
                else None
            ),
            parser=str(value.get("parser") or "generic_job_alert"),
        )


@dataclass(frozen=True)
class EmailClassification:
    message_class: EmailMessageClass
    source_id: str = "email_alert"
    reason: str = ""
    matched_rule: EmailSourceRule | None = None
    plausible_job_content: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def suppressed(self) -> bool:
        return self.message_class in {
            EmailMessageClass.ACCOUNT_ADMIN,
            EmailMessageClass.AUTH_OTP,
            EmailMessageClass.ALERT_CONFIRMATION,
            EmailMessageClass.IRRELEVANT,
        }


_ROLE_RE = re.compile(
    r"(?:assistant|associate|full|open[\s-]?rank|tenure[\s-]?track|research)?\s*"
    r"(?:professor(?:ship)?|faculty|investigator|group\s+leader|lecturer|reader|"
    r"principal\s+investigator|w[123]\s+professor)|教授|准教授|講師|助教|研究主幹",
    re.I,
)
_URL_RE = re.compile(r"https?://[^\s<>\]\[()\"']+", re.I)
_OTP_RE = re.compile(
    r"\b(?:otp|one[\s-]?time (?:password|passcode)|verification code|security code)\b|"
    r"ワンタイムパスワード|認証コード",
    re.I,
)
_PHD_ALERT_RE = re.compile(r"\bphd(?:s)?\s+by\s+email\b|博士課程(?:向け)?", re.I)
_ALERT_CONFIRMATION_RE = re.compile(
    r"(?:job|search) alert (?:has been )?(?:created|confirmed|activated)|"
    r"confirm(?:ation)? of (?:your )?(?:job|search) alert|アラート.{0,12}(?:作成|登録|確認)",
    re.I,
)
_ACCOUNT_ADMIN_RE = re.compile(
    r"(?:registration confirmation|account activation|activate your account|"
    r"create (?:a |your )?password|reset (?:your )?password|password reset|"
    r"email address (?:was )?changed|welcome(?: to)?|unsubscribe confirmation|"
    r"confirm your email|verify your email)|"
    r"(?:登録確認|アカウント(?:有効化|認証)|パスワード(?:作成|再設定|リセット)|"
    r"メールアドレス.{0,8}変更|ようこそ|配信停止)",
    re.I,
)


def normalize_email_text(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split())


def _message_value(message: Any, *names: str) -> str:
    if isinstance(message, Mapping):
        headers = message.get("headers")
        metadata = message.get("metadata")
        for name in names:
            for key in (name, name.casefold(), name.replace("-", "_")):
                if message.get(key) not in (None, ""):
                    return str(message[key])
                if isinstance(headers, Mapping) and headers.get(key) not in (None, ""):
                    return str(headers[key])
                if isinstance(metadata, Mapping) and metadata.get(key) not in (
                    None,
                    "",
                ):
                    return str(metadata[key])
    if isinstance(message, Message):
        for name in names:
            value = message.get(name)
            if value:
                return str(value)
    for name in names:
        value = getattr(message, name.replace("-", "_"), None)
        if value not in (None, ""):
            return str(value)
    return ""


def message_sender(message: Any) -> str:
    raw = _message_value(message, "from", "sender", "from_address")
    return parseaddr(raw)[1].strip().casefold() or raw.strip().casefold()


def message_subject(message: Any) -> str:
    return normalize_email_text(_message_value(message, "subject"))


def message_search_text(message: Any) -> str:
    parts = [message_subject(message)]
    if isinstance(message, Mapping):
        payload = message.get("payload")
        parts.extend(
            str(message.get(key) or "") for key in ("text", "body", "plain", "html")
        )
        if isinstance(payload, Mapping):
            parts.extend(
                str(payload.get(key) or "") for key in ("text", "body", "html")
            )
        links = message.get("links", ())
        if isinstance(links, str):
            links = (links,)
        parts.extend(str(item) for item in links or ())
    elif isinstance(message, Message):
        parts.append(str(message))
    else:
        parts.append(str(getattr(message, "body", "") or ""))
        parts.append(str(getattr(message, "html", "") or ""))
        parts.extend(str(item) for item in getattr(message, "links", ()) or ())
    return normalize_email_text("\n".join(parts))


def _registry_rows(registry: Any) -> list[EmailSourceRule]:
    if isinstance(registry, Mapping):
        registry = registry.get("email_sources", registry.get("sources", ()))
    if registry is None:
        return []
    if isinstance(registry, Mapping):
        registry = [
            {"source_id": source_id, **dict(value)}
            for source_id, value in registry.items()
            if isinstance(value, Mapping)
        ]
    return [
        item
        if isinstance(item, EmailSourceRule)
        else EmailSourceRule.from_mapping(item)
        for item in registry
        if isinstance(item, (EmailSourceRule, Mapping))
    ]


def _matches_sender(rule: EmailSourceRule, sender: str) -> bool:
    if not sender:
        return False
    if sender in rule.sender_addresses:
        return True
    domain = sender.rsplit("@", 1)[-1].rstrip(".")
    return any(
        domain == item or domain.endswith("." + item) for item in rule.sender_domains
    )


def _subject_matches(subject: str, patterns: Iterable[str]) -> bool:
    folded = subject.casefold()
    return any(pattern in folded for pattern in patterns)


def classify_email(message: Any, registry: Any = None) -> EmailClassification:
    """Classify one message without parsing candidates or performing I/O."""

    subject = message_subject(message)
    text = message_search_text(message)
    sender = message_sender(message)
    rule = next(
        (
            item
            for item in _registry_rows(registry)
            if item.enabled and _matches_sender(item, sender)
        ),
        None,
    )
    source_id = (
        rule.source_id
        if rule is not None
        else str(_message_value(message, "source_id") or "email_alert")
    )
    plausible = bool(_ROLE_RE.search(text) and _URL_RE.search(text))
    metadata = {"sender_domain": sender.rsplit("@", 1)[-1] if "@" in sender else ""}

    # jobs.ac.uk and similar providers may promote a separate "PhDs by Email"
    # product in the footer of an otherwise valid faculty-job alert.  Treat the
    # phrase as suppressible when it identifies the message subject, or when
    # the message contains no plausible academic-role listing.  This keeps
    # genuinely PhD-only mail out without discarding mixed marketing footers.
    if _PHD_ALERT_RE.search(subject) or (
        _PHD_ALERT_RE.search(text) and not plausible
    ):
        return EmailClassification(
            EmailMessageClass.IRRELEVANT,
            source_id,
            "PhD/student-only alert",
            rule,
            plausible,
            metadata,
        )
    if _OTP_RE.search(text):
        return EmailClassification(
            EmailMessageClass.AUTH_OTP,
            source_id,
            "authentication or one-time code",
            rule,
            plausible,
            metadata,
        )
    if _ALERT_CONFIRMATION_RE.search(text) and not plausible:
        return EmailClassification(
            EmailMessageClass.ALERT_CONFIRMATION,
            source_id,
            "alert confirmation contains no listings",
            rule,
            plausible,
            metadata,
        )
    if _ACCOUNT_ADMIN_RE.search(text) and not plausible:
        return EmailClassification(
            EmailMessageClass.ACCOUNT_ADMIN,
            source_id,
            "account administration",
            rule,
            plausible,
            metadata,
        )
    if rule is not None and _subject_matches(subject, rule.subject_negative):
        return EmailClassification(
            EmailMessageClass.IRRELEVANT,
            source_id,
            "source-specific negative subject",
            rule,
            plausible,
            metadata,
        )
    if plausible and (
        rule is not None
        or _message_value(message, "source_id") not in ("", "email_alert")
        or "job" in text.casefold()
    ):
        return EmailClassification(
            EmailMessageClass.JOB_ALERT,
            source_id,
            "plausible job listings",
            rule,
            True,
            metadata,
        )
    if rule is not None and _subject_matches(subject, rule.subject_positive):
        return EmailClassification(
            EmailMessageClass.JOB_ALERT,
            source_id,
            "source-specific positive subject",
            rule,
            plausible,
            metadata,
        )
    return EmailClassification(
        EmailMessageClass.UNKNOWN,
        source_id,
        "unrecognized message with plausible job content"
        if plausible
        else "unrecognized message",
        rule,
        plausible,
        metadata,
    )


__all__ = [
    "EmailClassification",
    "EmailMessageClass",
    "EmailSourceRule",
    "classify_email",
    "message_search_text",
    "message_sender",
    "message_subject",
    "normalize_email_text",
]
