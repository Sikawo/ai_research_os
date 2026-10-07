"""Academic PI Career Job Agent deployment.

The deployment is import-safe and performs no network, credential, state, or
application-submission action until a caller invokes a service with explicit
adapters.
"""

from .adapters import (
    CallableDiscoveryAdapter,
    CallableVerificationAdapter,
    CallableWebAdapter,
    MemoryReportAdapter,
    NoOpReportAdapter,
    NoOpVerificationAdapter,
    StaticDiscoveryAdapter,
    StaticEmailAdapter,
    StaticWebAdapter,
)
from .cli import build_parser, load_academic_config, main
from .email_ingestion import (
    DEFAULT_GMAIL_LABELS,
    EmailParseResult,
    parse_academic_alert,
    parse_academic_alert_result,
    plan_gmail_labels,
)
from .email_sources import EmailMessageClass, classify_email
from .handoff import (
    build_academic_gatedsprint_handoff,
    build_gatedsprint_handoff,
    render_gatedsprint_handoff,
)
from .models import (
    AcademicJob,
    AcademicQuery,
    AcademicRoleClass,
    AcademicTier,
    DiscoveryCandidate,
    FitEvaluation,
    GmailLabelPlan,
    IndependenceAssessment,
    IndependenceClass,
    TitleNormalization,
    WorkflowResult,
)
from .institution_monitor import plan_target_scan, target_cadence_days
from .qol import build_qol_assessment, requires_full_qol
from .queries import AcademicQueryGenerator, QueryGenerator, generate_academic_queries
from .reports import render_daily_report, render_weekly_report
from .rss_adapters import RssDiscoveryAdapter
from .rss_ingestion import FeedParseResult, parse_feed
from .scoring import AcademicScorer, apply_broad_search_rule, is_broad_search, score_academic_fit
from .service import AcademicPIService, AcademicPiService
from .titles import infer_independence, normalize_academic_title, normalize_titles


__all__ = [
    "AcademicJob",
    "AcademicPiService",
    "AcademicPIService",
    "AcademicQuery",
    "AcademicQueryGenerator",
    "AcademicRoleClass",
    "AcademicScorer",
    "AcademicTier",
    "CallableDiscoveryAdapter",
    "CallableVerificationAdapter",
    "CallableWebAdapter",
    "DEFAULT_GMAIL_LABELS",
    "DiscoveryCandidate",
    "EmailParseResult",
    "EmailMessageClass",
    "FeedParseResult",
    "FitEvaluation",
    "GmailLabelPlan",
    "IndependenceAssessment",
    "IndependenceClass",
    "MemoryReportAdapter",
    "NoOpReportAdapter",
    "NoOpVerificationAdapter",
    "QueryGenerator",
    "RssDiscoveryAdapter",
    "StaticDiscoveryAdapter",
    "StaticEmailAdapter",
    "StaticWebAdapter",
    "TitleNormalization",
    "WorkflowResult",
    "apply_broad_search_rule",
    "build_academic_gatedsprint_handoff",
    "build_gatedsprint_handoff",
    "build_parser",
    "build_qol_assessment",
    "classify_email",
    "generate_academic_queries",
    "infer_independence",
    "is_broad_search",
    "load_academic_config",
    "main",
    "normalize_academic_title",
    "normalize_titles",
    "parse_academic_alert",
    "parse_academic_alert_result",
    "parse_feed",
    "plan_target_scan",
    "plan_gmail_labels",
    "render_daily_report",
    "render_gatedsprint_handoff",
    "render_weekly_report",
    "requires_full_qol",
    "score_academic_fit",
    "target_cadence_days",
]
