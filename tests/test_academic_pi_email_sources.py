from __future__ import annotations

import pytest

from Career_Job_Agent_Framework.deployments.academic_pi.email_ingestion import (
    parse_academic_alert_result,
    plan_gmail_labels,
)
from Career_Job_Agent_Framework.deployments.academic_pi.email_sources import (
    EmailMessageClass,
    classify_email,
)


REGISTRY = {
    "email_sources": [
        {
            "source_id": "nature_careers",
            "sender_domains": ["jobmail.naturecareers.com"],
        },
        {
            "source_id": "science_careers",
            "sender_domains": ["sciencecareers.org"],
        },
        {
            "source_id": "academic_positions",
            "sender_domains": ["academicpositions.com"],
        },
        {
            "source_id": "jobs_ac_uk",
            "sender_domains": ["jobs.ac.uk"],
        },
        {
            "source_id": "higher_ed_jobs",
            "sender_domains": ["higheredjobs.com"],
        },
        {
            "source_id": "jrec_in",
            "sender_addresses": ["auto-jrecin@jst.go.jp"],
        },
    ]
}


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            {
                "from": "noreply@jobmail.naturecareers.com",
                "subject": "Welcome - registration confirmation",
                "html": '<a href="https://nature.example/account/activate">Activate account</a>',
            },
            EmailMessageClass.ACCOUNT_ADMIN,
        ),
        (
            {
                "from": "reply@sciencecareers.org",
                "subject": "Reset your password",
                "body": "Create a new password",
            },
            EmailMessageClass.ACCOUNT_ADMIN,
        ),
        (
            {
                "from": "noreply@academicpositions.com",
                "subject": "Account activation",
            },
            EmailMessageClass.ACCOUNT_ADMIN,
        ),
        (
            {
                "from": "auto-jrecin@jst.go.jp",
                "subject": "ワンタイムパスワード",
                "body": "認証コード 123456",
            },
            EmailMessageClass.AUTH_OTP,
        ),
        (
            {
                "from": "account@higheredjobs.com",
                "subject": "Your Job Alert has been created",
                "body": "You will receive matching jobs later.",
            },
            EmailMessageClass.ALERT_CONFIRMATION,
        ),
        (
            {
                "from": "jobsacuk.noreply@jobs.ac.uk",
                "subject": "PhDs by Email",
                "body": "New PhD projects",
            },
            EmailMessageClass.IRRELEVANT,
        ),
    ],
)
def test_administrative_and_phd_messages_are_suppressed(message, expected) -> None:
    classification = classify_email(message, REGISTRY)
    assert classification.message_class == expected
    parsed = parse_academic_alert_result(message, email_source_registry=REGISTRY)
    assert parsed.candidates == []
    assert parsed.parse_failures == []
    plan = plan_gmail_labels(parsed)
    assert plan.processed
    assert "Error" not in " ".join(plan.add_labels)
    assert not plan.archive and not plan.delete


def test_valid_jobs_ac_uk_alert_is_classified_and_parsed() -> None:
    message = {
        "message_id": "jobs-ac-1",
        "from": "jobsacuk.noreply@jobs.ac.uk",
        "subject": "Jobs by Email",
        "body": "Assistant Professor of Biology\nhttps://www.jobs.ac.uk/job/ABC123",
    }
    parsed = parse_academic_alert_result(message, email_source_registry=REGISTRY)
    assert parsed.message_class == EmailMessageClass.JOB_ALERT
    assert parsed.source_id == "jobs_ac_uk"
    assert [(item.raw_title, item.source_id) for item in parsed.candidates] == [
        ("Assistant Professor of Biology", "jobs_ac_uk")
    ]


def test_valid_jobs_alert_survives_phds_by_email_footer_promotion() -> None:
    message = {
        "message_id": "jobs-ac-mixed-footer",
        "from": "jobsacuk.noreply@jobs.ac.uk",
        "subject": "Jobs by Email",
        "body": (
            "Assistant Professor of Immunology\n"
            "https://www.jobs.ac.uk/job/FAC123\n\n"
            "Looking for doctoral study? Try PhDs by Email."
        ),
    }

    parsed = parse_academic_alert_result(message, email_source_registry=REGISTRY)

    assert parsed.message_class == EmailMessageClass.JOB_ALERT
    assert [item.raw_title for item in parsed.candidates] == [
        "Assistant Professor of Immunology"
    ]


def test_html_parser_uses_adjacent_titles_rejects_navigation_and_unwraps_tracking() -> (
    None
):
    message = {
        "message_id": "html-many",
        "from": "alerts@jobs.ac.uk",
        "subject": "Jobs by Email",
        "html": """
          <div>Ａｓｓｉｓｔａｎｔ　Ｐｒｏｆｅｓｓｏｒ of Biology
            <a href="https://tracker.example/click?URL=https%253A%252F%252Fjobs.example.edu%252Fone">View job</a>
          </div>
          <div>Independent Group Leader
            <a href="https://jobs.example.edu/two">Details</a>
          </div>
          <a href="https://jobs.example.edu/account/preferences">Manage preferences</a>
          <a href="https://social.example/share">LinkedIn</a>
        """,
    }
    parsed = parse_academic_alert_result(message, email_source_registry=REGISTRY)
    assert len(parsed.candidates) == 2
    assert parsed.candidates[0].raw_title == "Assistant Professor of Biology"
    assert parsed.candidates[0].url == "https://jobs.example.edu/one"
    assert parsed.candidates[1].raw_title == "Independent Group Leader"


def test_plain_text_adjacent_lines_parse_all_jobs_even_with_malformed_html() -> None:
    parsed = parse_academic_alert_result(
        {
            "message_id": "adjacent",
            "body": (
                "Assistant Professor of Virology\nhttps://roles.example/one\n"
                "准教授（微生物学）\nhttps://roles.example/two"
            ),
            "html": "<div><a",
        }
    )
    assert [item.raw_title for item in parsed.candidates] == [
        "Assistant Professor of Virology",
        "准教授(微生物学)",
    ]


def test_unknown_plausible_source_is_processed_with_needs_review_after_handling() -> (
    None
):
    parsed = parse_academic_alert_result(
        {
            "message_id": "unknown-1",
            "body": "Assistant Professor of Biology https://roles.example/one",
        }
    )
    assert parsed.message_class == EmailMessageClass.UNKNOWN
    parsed.handled_candidate_ids.update(item.event_id for item in parsed.candidates)
    plan = plan_gmail_labels(parsed)
    assert plan.processed
    assert "Academic PI Job Agent/Needs Review" in plan.add_labels


def test_retry_and_partial_handling_remain_idempotent() -> None:
    message = {
        "message_id": "retry-1",
        "body": (
            "Assistant Professor of Biology https://roles.example/one\n"
            "Independent Group Leader https://roles.example/two"
        ),
    }
    parsed = parse_academic_alert_result(message)
    parsed.handled_candidate_ids.add(parsed.candidates[0].event_id)
    assert not plan_gmail_labels(parsed).processed
    parsed.handled_candidate_ids.add(parsed.candidates[1].event_id)
    assert plan_gmail_labels(parsed).processed
    repeated = parse_academic_alert_result(message, processed_message_ids={"retry-1"})
    assert repeated.already_processed
    assert repeated.candidates == []


def test_sender_domain_matching_does_not_accept_suffix_confusion() -> None:
    classification = classify_email(
        {
            "from": "noreply@jobmail.naturecareers.com.evil.example",
            "body": "Assistant Professor https://jobs.example/one",
        },
        REGISTRY,
    )
    assert classification.source_id == "email_alert"
