from __future__ import annotations


LATEST_SCHEMA_VERSION = 7


MIGRATION_2_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS works (
    openalex_work_id TEXT PRIMARY KEY,
    doi TEXT UNIQUE,
    title TEXT NOT NULL,
    publication_date TEXT,
    work_type TEXT,
    source_type TEXT,
    venue TEXT,
    cited_by_count INTEGER,
    is_open_access INTEGER,
    source TEXT NOT NULL,
    first_created_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    last_seen_run_id TEXT,
    FOREIGN KEY(last_seen_run_id) REFERENCES scan_runs(run_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_works_publication_date ON works(publication_date);
CREATE INDEX IF NOT EXISTS idx_works_doi ON works(doi);

CREATE TABLE IF NOT EXISTS authors (
    openalex_author_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    orcid TEXT,
    source TEXT NOT NULL,
    first_created_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_authors_display_name ON authors(display_name);

CREATE TABLE IF NOT EXISTS institutions (
    openalex_institution_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    country_code TEXT,
    institution_type TEXT,
    ror TEXT,
    source TEXT NOT NULL,
    first_created_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_institutions_country ON institutions(country_code);
CREATE INDEX IF NOT EXISTS idx_institutions_name ON institutions(display_name);

CREATE TABLE IF NOT EXISTS topics (
    topic_key TEXT PRIMARY KEY,
    openalex_topic_id TEXT UNIQUE,
    label TEXT NOT NULL,
    topic_kind TEXT NOT NULL CHECK(topic_kind IN ('controlled', 'openalex')),
    description TEXT,
    source TEXT NOT NULL,
    first_created_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_topics_label ON topics(label);

CREATE TABLE IF NOT EXISTS work_authorships (
    authorship_id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id TEXT NOT NULL,
    author_id TEXT NOT NULL,
    author_position TEXT,
    is_corresponding INTEGER NOT NULL DEFAULT 0,
    authorship_order INTEGER,
    source TEXT NOT NULL,
    first_created_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    UNIQUE(work_id, author_id),
    FOREIGN KEY(work_id) REFERENCES works(openalex_work_id) ON DELETE CASCADE,
    FOREIGN KEY(author_id) REFERENCES authors(openalex_author_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_work_authorships_author ON work_authorships(author_id);

CREATE TABLE IF NOT EXISTS work_authorship_institutions (
    authorship_id INTEGER NOT NULL,
    institution_id TEXT NOT NULL,
    source TEXT NOT NULL,
    first_created_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    PRIMARY KEY(authorship_id, institution_id),
    FOREIGN KEY(authorship_id) REFERENCES work_authorships(authorship_id) ON DELETE CASCADE,
    FOREIGN KEY(institution_id) REFERENCES institutions(openalex_institution_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_authorship_institutions_institution
    ON work_authorship_institutions(institution_id);

CREATE TABLE IF NOT EXISTS work_topics (
    work_id TEXT NOT NULL,
    topic_key TEXT NOT NULL,
    score REAL,
    is_primary INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL,
    first_created_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    PRIMARY KEY(work_id, topic_key),
    FOREIGN KEY(work_id) REFERENCES works(openalex_work_id) ON DELETE CASCADE,
    FOREIGN KEY(topic_key) REFERENCES topics(topic_key) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_work_topics_topic ON work_topics(topic_key);

CREATE TABLE IF NOT EXISTS research_groups (
    group_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    institution_id TEXT,
    status TEXT NOT NULL DEFAULT 'candidate'
        CHECK(status IN ('candidate', 'verified', 'rejected')),
    confidence TEXT NOT NULL CHECK(confidence IN ('high', 'medium_high', 'medium', 'low')),
    source TEXT NOT NULL,
    first_created_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    FOREIGN KEY(institution_id) REFERENCES institutions(openalex_institution_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_research_groups_institution ON research_groups(institution_id);
CREATE INDEX IF NOT EXISTS idx_research_groups_status ON research_groups(status, confidence);

CREATE TABLE IF NOT EXISTS research_group_evidence (
    evidence_id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL,
    work_id TEXT,
    author_id TEXT,
    evidence_type TEXT NOT NULL,
    evidence_url TEXT,
    evidence_text TEXT NOT NULL,
    confidence TEXT NOT NULL CHECK(confidence IN ('high', 'medium_high', 'medium', 'low')),
    verification_status TEXT NOT NULL DEFAULT 'candidate'
        CHECK(verification_status IN ('candidate', 'verified', 'rejected')),
    observed_at TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    source TEXT NOT NULL,
    first_created_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    FOREIGN KEY(group_id) REFERENCES research_groups(group_id) ON DELETE CASCADE,
    FOREIGN KEY(work_id) REFERENCES works(openalex_work_id) ON DELETE SET NULL,
    FOREIGN KEY(author_id) REFERENCES authors(openalex_author_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_group_evidence_group ON research_group_evidence(group_id);
CREATE INDEX IF NOT EXISTS idx_group_evidence_status
    ON research_group_evidence(verification_status, confidence);

CREATE TABLE IF NOT EXISTS topic_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    topic_key TEXT NOT NULL,
    region TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    window_start TEXT,
    window_end TEXT,
    total_count INTEGER,
    sampled_count INTEGER,
    coverage_rate REAL,
    sample_truncated INTEGER NOT NULL DEFAULT 0,
    growth_rate REAL,
    adjusted_growth_rate REAL,
    acceleration REAL,
    institution_count INTEGER,
    institution_count_is_complete INTEGER NOT NULL DEFAULT 0,
    author_count INTEGER,
    data_confidence REAL,
    heat_score REAL,
    score_coverage REAL,
    algorithm_version TEXT NOT NULL,
    query_string TEXT,
    coverage_comparability TEXT,
    source TEXT NOT NULL,
    first_created_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    UNIQUE(run_id, topic_key, region),
    FOREIGN KEY(run_id) REFERENCES scan_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(topic_key) REFERENCES topics(topic_key) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_topic_snapshots_history
    ON topic_snapshots(topic_key, region, snapshot_date);

CREATE TABLE IF NOT EXISTS institution_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    institution_id TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    sampled_work_count INTEGER NOT NULL,
    topic_count INTEGER NOT NULL,
    count_scope TEXT NOT NULL DEFAULT 'sample',
    data_confidence REAL,
    source TEXT NOT NULL,
    first_created_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    UNIQUE(run_id, institution_id),
    FOREIGN KEY(run_id) REFERENCES scan_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(institution_id) REFERENCES institutions(openalex_institution_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_institution_snapshots_history
    ON institution_snapshots(institution_id, snapshot_date);

CREATE TABLE IF NOT EXISTS author_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    author_id TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    sampled_work_count INTEGER NOT NULL,
    topic_count INTEGER NOT NULL,
    count_scope TEXT NOT NULL DEFAULT 'sample',
    data_confidence REAL,
    source TEXT NOT NULL,
    first_created_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    UNIQUE(run_id, author_id),
    FOREIGN KEY(run_id) REFERENCES scan_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(author_id) REFERENCES authors(openalex_author_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_author_snapshots_history
    ON author_snapshots(author_id, snapshot_date);
"""


MIGRATION_3_SQL = """
CREATE TABLE IF NOT EXISTS trend_backfill_runs (
    run_id TEXT PRIMARY KEY,
    run_type TEXT NOT NULL CHECK(run_type IN ('backfill', 'revision')),
    start_snapshot_date TEXT NOT NULL,
    end_snapshot_date TEXT NOT NULL,
    snapshot_dates TEXT NOT NULL,
    expected_query_count INTEGER NOT NULL CHECK(expected_query_count > 0),
    completed_query_count INTEGER NOT NULL DEFAULT 0 CHECK(completed_query_count >= 0),
    successful_query_count INTEGER NOT NULL DEFAULT 0 CHECK(successful_query_count >= 0),
    failed_query_count INTEGER NOT NULL DEFAULT 0 CHECK(failed_query_count >= 0),
    status TEXT NOT NULL CHECK(status IN ('running', 'paused', 'partial', 'success', 'failed')),
    topic_mapping_version TEXT NOT NULL,
    query_version TEXT NOT NULL,
    calculation_version TEXT NOT NULL,
    revision_reason TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trend_runs_status_dates
    ON trend_backfill_runs(status, start_snapshot_date, end_snapshot_date);

CREATE TABLE IF NOT EXISTS trend_query_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    category_id TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    topic_ids TEXT NOT NULL,
    query_filter TEXT NOT NULL,
    request_status TEXT NOT NULL CHECK(request_status IN ('success', 'failed')),
    http_status INTEGER,
    works_count INTEGER CHECK(works_count IS NULL OR works_count >= 0),
    query_as_of TEXT NOT NULL,
    duration_ms REAL NOT NULL CHECK(duration_ms >= 0),
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK(retry_count >= 0),
    error_message TEXT,
    query_version TEXT NOT NULL,
    rate_limit_limit INTEGER,
    rate_limit_remaining INTEGER,
    rate_limit_reset TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES trend_backfill_runs(run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_trend_query_logs_run_status
    ON trend_query_logs(run_id, request_status, category_id, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_trend_query_logs_category_date
    ON trend_query_logs(category_id, snapshot_date, created_at);

CREATE TABLE IF NOT EXISTS trend_30d_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    category_id TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    works_count INTEGER NOT NULL CHECK(works_count >= 0),
    query_as_of TEXT NOT NULL,
    data_status TEXT NOT NULL CHECK(data_status IN ('success')),
    topic_mapping_version TEXT NOT NULL,
    query_version TEXT NOT NULL,
    calculation_version TEXT NOT NULL,
    revision_no INTEGER NOT NULL DEFAULT 1 CHECK(revision_no > 0),
    is_current INTEGER NOT NULL DEFAULT 1 CHECK(is_current IN (0, 1)),
    supersedes_id INTEGER,
    revision_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(category_id, snapshot_date, revision_no),
    FOREIGN KEY(run_id) REFERENCES trend_backfill_runs(run_id) ON DELETE RESTRICT,
    FOREIGN KEY(supersedes_id) REFERENCES trend_30d_snapshots(id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trend_snapshots_one_current
    ON trend_30d_snapshots(category_id, snapshot_date) WHERE is_current=1;
CREATE INDEX IF NOT EXISTS idx_trend_snapshots_current_date
    ON trend_30d_snapshots(snapshot_date, category_id, is_current);
"""


MIGRATION_4_SQL = """
ALTER TABLE trend_backfill_runs
    ADD COLUMN data_origin TEXT NOT NULL DEFAULT 'historical_backfill'
    CHECK(data_origin IN ('historical_backfill', 'daily_live', 'historical_revision'));
ALTER TABLE trend_query_logs
    ADD COLUMN data_origin TEXT NOT NULL DEFAULT 'historical_backfill'
    CHECK(data_origin IN ('historical_backfill', 'daily_live', 'historical_revision'));
ALTER TABLE trend_30d_snapshots
    ADD COLUMN data_origin TEXT NOT NULL DEFAULT 'historical_backfill'
    CHECK(data_origin IN ('historical_backfill', 'daily_live', 'historical_revision'));

UPDATE trend_backfill_runs
SET data_origin=CASE
    WHEN run_type='revision' THEN 'historical_revision'
    ELSE 'historical_backfill'
END;
UPDATE trend_query_logs
SET data_origin=(
    SELECT r.data_origin FROM trend_backfill_runs r
    WHERE r.run_id=trend_query_logs.run_id
);
UPDATE trend_30d_snapshots
SET data_origin=(
    SELECT r.data_origin FROM trend_backfill_runs r
    WHERE r.run_id=trend_30d_snapshots.run_id
);
"""


MIGRATION_5_SQL = """
CREATE TABLE IF NOT EXISTS topic_update_runs (
    run_id TEXT PRIMARY KEY,
    ranking_date TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK(source_type IN ('audit_import', 'daily_update')),
    status TEXT NOT NULL CHECK(status IN ('running', 'validated', 'published', 'failed')),
    query_as_of TEXT NOT NULL,
    calculation_version TEXT NOT NULL,
    error_message TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_topic_update_runs_status_date
    ON topic_update_runs(status, ranking_date);

CREATE TABLE IF NOT EXISTS openalex_topics (
    topic_id TEXT PRIMARY KEY,
    topic_name TEXT NOT NULL,
    topic_name_zh TEXT,
    subfield_id TEXT NOT NULL,
    subfield_name TEXT NOT NULL,
    field_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    domain_id TEXT NOT NULL,
    domain_name TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_openalex_topics_hierarchy
    ON openalex_topics(domain_id, field_id, subfield_id);

CREATE TABLE IF NOT EXISTS topic_daily_counts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    daily_works_count INTEGER NOT NULL CHECK(daily_works_count >= 0),
    query_as_of TEXT NOT NULL,
    query_status TEXT NOT NULL CHECK(query_status IN ('success')),
    revision_no INTEGER NOT NULL CHECK(revision_no > 0),
    is_current INTEGER NOT NULL DEFAULT 1 CHECK(is_current IN (0, 1)),
    query_version TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    revision_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(date, topic_id, revision_no),
    FOREIGN KEY(topic_id) REFERENCES openalex_topics(topic_id) ON DELETE RESTRICT,
    FOREIGN KEY(source_run_id) REFERENCES topic_update_runs(run_id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_topic_daily_one_current
    ON topic_daily_counts(date, topic_id) WHERE is_current=1;
CREATE INDEX IF NOT EXISTS idx_topic_daily_current_topic_date
    ON topic_daily_counts(topic_id, date, is_current);

CREATE TABLE IF NOT EXISTS topic_ranking_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ranking_date TEXT NOT NULL,
    period_days INTEGER NOT NULL CHECK(period_days IN (90, 360)),
    topic_id TEXT NOT NULL,
    rank INTEGER NOT NULL CHECK(rank > 0),
    period_works_count INTEGER NOT NULL CHECK(period_works_count >= 0),
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    query_as_of TEXT NOT NULL,
    calculation_version TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    is_current INTEGER NOT NULL DEFAULT 1 CHECK(is_current IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(ranking_date, period_days, topic_id, calculation_version),
    UNIQUE(ranking_date, period_days, rank, calculation_version),
    FOREIGN KEY(topic_id) REFERENCES openalex_topics(topic_id) ON DELETE RESTRICT,
    FOREIGN KEY(source_run_id) REFERENCES topic_update_runs(run_id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_topic_rank_one_current_topic
    ON topic_ranking_snapshots(ranking_date, period_days, topic_id) WHERE is_current=1;
CREATE UNIQUE INDEX IF NOT EXISTS idx_topic_rank_one_current_rank
    ON topic_ranking_snapshots(ranking_date, period_days, rank) WHERE is_current=1;
CREATE INDEX IF NOT EXISTS idx_topic_rank_current_period
    ON topic_ranking_snapshots(period_days, ranking_date, rank, is_current);
"""


ROLLBACK_MIGRATION_5_SQL = """
DROP TABLE IF EXISTS topic_ranking_snapshots;
DROP TABLE IF EXISTS topic_daily_counts;
DROP TABLE IF EXISTS openalex_topics;
DROP TABLE IF EXISTS topic_update_runs;
"""


MIGRATION_6_SQL = """
CREATE TABLE IF NOT EXISTS taxonomy_versions (
    taxonomy_version TEXT PRIMARY KEY,
    effective_date TEXT NOT NULL,
    source TEXT NOT NULL,
    topic_count INTEGER NOT NULL CHECK(topic_count >= 0),
    field_count INTEGER NOT NULL CHECK(field_count >= 0),
    is_current INTEGER NOT NULL DEFAULT 0 CHECK(is_current IN (0, 1)),
    imported_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_taxonomy_versions_one_current
    ON taxonomy_versions(is_current) WHERE is_current=1;

CREATE TABLE IF NOT EXISTS field_scope_versions (
    taxonomy_version TEXT NOT NULL,
    field_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    field_name_zh TEXT,
    topic_count INTEGER NOT NULL CHECK(topic_count >= 0),
    PRIMARY KEY(taxonomy_version, field_id),
    FOREIGN KEY(taxonomy_version) REFERENCES taxonomy_versions(taxonomy_version)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS topic_taxonomy_versions (
    taxonomy_version TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    topic_name TEXT NOT NULL,
    topic_name_zh TEXT,
    subfield_id TEXT NOT NULL,
    subfield_name TEXT NOT NULL,
    field_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    domain_id TEXT NOT NULL,
    domain_name TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    PRIMARY KEY(taxonomy_version, topic_id),
    FOREIGN KEY(taxonomy_version) REFERENCES taxonomy_versions(taxonomy_version)
        ON DELETE RESTRICT,
    FOREIGN KEY(taxonomy_version, field_id)
        REFERENCES field_scope_versions(taxonomy_version, field_id)
        ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_topic_taxonomy_version_field
    ON topic_taxonomy_versions(taxonomy_version, field_id, topic_id);
"""


ROLLBACK_MIGRATION_6_SQL = """
DROP TABLE IF EXISTS topic_taxonomy_versions;
DROP TABLE IF EXISTS field_scope_versions;
DROP TABLE IF EXISTS taxonomy_versions;
"""


MIGRATION_7_SQL = """
CREATE TABLE IF NOT EXISTS regional_snapshot_batches (
    batch_id TEXT PRIMARY KEY,
    ranking_date TEXT NOT NULL,
    daily_start TEXT NOT NULL,
    daily_end TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    query_version TEXT NOT NULL,
    calculation_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN (
        'running', 'partial', 'validated', 'published', 'failed'
    )),
    expected_region_count INTEGER NOT NULL DEFAULT 2
        CHECK(expected_region_count = 2),
    completed_region_count INTEGER NOT NULL DEFAULT 0
        CHECK(completed_region_count BETWEEN 0 AND 2),
    api_request_count INTEGER NOT NULL DEFAULT 0 CHECK(api_request_count >= 0),
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK(retry_count >= 0),
    error_message TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(taxonomy_version) REFERENCES taxonomy_versions(taxonomy_version)
        ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_regional_batches_status_date
    ON regional_snapshot_batches(status, ranking_date, completed_at);

CREATE TABLE IF NOT EXISTS regional_topic_runs (
    run_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    region_code TEXT NOT NULL CHECK(region_code IN ('CN', 'US')),
    status TEXT NOT NULL CHECK(status IN (
        'running', 'partial', 'validated', 'published', 'failed'
    )),
    query_as_of TEXT,
    completed_daily_dates INTEGER NOT NULL DEFAULT 0
        CHECK(completed_daily_dates >= 0),
    api_request_count INTEGER NOT NULL DEFAULT 0 CHECK(api_request_count >= 0),
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK(retry_count >= 0),
    error_message TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(batch_id, region_code),
    FOREIGN KEY(batch_id) REFERENCES regional_snapshot_batches(batch_id)
        ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_regional_runs_batch_status
    ON regional_topic_runs(batch_id, status, region_code);

CREATE TABLE IF NOT EXISTS regional_topic_period_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    region_code TEXT NOT NULL CHECK(region_code IN ('CN', 'US')),
    ranking_date TEXT NOT NULL,
    period_days INTEGER NOT NULL CHECK(period_days IN (90, 360)),
    topic_id TEXT NOT NULL,
    field_id TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    works_count INTEGER NOT NULL CHECK(works_count >= 0),
    previous_window_start TEXT NOT NULL,
    previous_window_end TEXT NOT NULL,
    previous_works_count INTEGER NOT NULL CHECK(previous_works_count >= 0),
    growth_amount INTEGER NOT NULL,
    growth_rate REAL,
    growth_status TEXT NOT NULL CHECK(growth_status IN ('success', 'zero_baseline')),
    works_rank INTEGER NOT NULL CHECK(works_rank > 0),
    growth_amount_rank INTEGER NOT NULL CHECK(growth_amount_rank > 0),
    growth_rate_rank INTEGER CHECK(growth_rate_rank IS NULL OR growth_rate_rank > 0),
    query_as_of TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    query_version TEXT NOT NULL,
    calculation_version TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    data_status TEXT NOT NULL CHECK(data_status = 'success'),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(batch_id, region_code, period_days, topic_id),
    UNIQUE(batch_id, region_code, period_days, works_rank),
    UNIQUE(batch_id, region_code, period_days, growth_amount_rank),
    FOREIGN KEY(batch_id) REFERENCES regional_snapshot_batches(batch_id)
        ON DELETE RESTRICT,
    FOREIGN KEY(source_run_id) REFERENCES regional_topic_runs(run_id)
        ON DELETE RESTRICT,
    FOREIGN KEY(taxonomy_version, topic_id)
        REFERENCES topic_taxonomy_versions(taxonomy_version, topic_id)
        ON DELETE RESTRICT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_regional_period_growth_rate_rank
    ON regional_topic_period_snapshots(
        batch_id, region_code, period_days, growth_rate_rank
    ) WHERE growth_rate_rank IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_regional_period_lookup
    ON regional_topic_period_snapshots(
        batch_id, region_code, period_days, field_id, topic_id
    );

CREATE TABLE IF NOT EXISTS regional_topic_daily_counts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    region_code TEXT NOT NULL CHECK(region_code IN ('CN', 'US')),
    publication_date TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    field_id TEXT NOT NULL,
    daily_works_count INTEGER NOT NULL CHECK(daily_works_count >= 0),
    query_as_of TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    query_version TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    data_status TEXT NOT NULL CHECK(data_status = 'success'),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(batch_id, region_code, publication_date, topic_id),
    FOREIGN KEY(batch_id) REFERENCES regional_snapshot_batches(batch_id)
        ON DELETE RESTRICT,
    FOREIGN KEY(source_run_id) REFERENCES regional_topic_runs(run_id)
        ON DELETE RESTRICT,
    FOREIGN KEY(taxonomy_version, topic_id)
        REFERENCES topic_taxonomy_versions(taxonomy_version, topic_id)
        ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_regional_daily_lookup
    ON regional_topic_daily_counts(
        batch_id, region_code, topic_id, publication_date
    );
CREATE INDEX IF NOT EXISTS idx_regional_daily_field_date
    ON regional_topic_daily_counts(
        batch_id, region_code, field_id, publication_date
    );

CREATE TABLE IF NOT EXISTS regional_query_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    region_code TEXT NOT NULL CHECK(region_code IN ('CN', 'US')),
    query_kind TEXT NOT NULL CHECK(query_kind IN ('period', 'daily')),
    period_days INTEGER CHECK(period_days IS NULL OR period_days IN (90, 360)),
    window_role TEXT CHECK(window_role IS NULL OR window_role IN ('current', 'previous')),
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    query_filter TEXT NOT NULL,
    request_status TEXT NOT NULL CHECK(request_status IN ('success', 'failed')),
    response_group_count INTEGER,
    page_count INTEGER NOT NULL DEFAULT 0 CHECK(page_count >= 0),
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK(retry_count >= 0),
    query_as_of TEXT NOT NULL,
    error_message TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(batch_id) REFERENCES regional_snapshot_batches(batch_id)
        ON DELETE RESTRICT,
    FOREIGN KEY(source_run_id) REFERENCES regional_topic_runs(run_id)
        ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_regional_query_logs_run_status
    ON regional_query_logs(source_run_id, request_status, query_kind, window_start);
"""
