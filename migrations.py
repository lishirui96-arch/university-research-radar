from __future__ import annotations


LATEST_SCHEMA_VERSION = 5


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
CREATE TABLE IF NOT EXISTS snapshot_batches (
    batch_id TEXT PRIMARY KEY,
    batch_type TEXT NOT NULL,
    logical_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN (
        'collecting', 'validating', 'validated', 'published', 'failed'
    )),
    source TEXT NOT NULL,
    code_version TEXT,
    schema_version INTEGER NOT NULL,
    algorithm_version TEXT,
    stats_json TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    published_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshot_batches_type_status
    ON snapshot_batches(batch_type, status, logical_date);

CREATE TABLE IF NOT EXISTS collection_jobs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    logical_date TEXT NOT NULL,
    shard_key TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK(status IN (
        'pending', 'leased', 'running', 'validating', 'succeeded',
        'retry_wait', 'failed'
    )),
    priority INTEGER NOT NULL DEFAULT 100,
    leased_by TEXT,
    lease_expires_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    next_retry_at TEXT,
    batch_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(job_type, logical_date, shard_key),
    FOREIGN KEY(batch_id) REFERENCES snapshot_batches(batch_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_collection_jobs_ready
    ON collection_jobs(status, next_retry_at, priority, created_at);
CREATE INDEX IF NOT EXISTS idx_collection_jobs_lease
    ON collection_jobs(lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_collection_jobs_batch
    ON collection_jobs(batch_id);

CREATE TABLE IF NOT EXISTS collection_job_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('running', 'succeeded', 'failed', 'interrupted')),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    request_count INTEGER NOT NULL DEFAULT 0,
    response_bytes INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    error_type TEXT,
    error_message TEXT,
    log_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(job_id, attempt_number),
    FOREIGN KEY(job_id) REFERENCES collection_jobs(job_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_collection_attempts_job
    ON collection_job_attempts(job_id, attempt_number);

CREATE TABLE IF NOT EXISTS collection_checkpoints (
    job_id TEXT NOT NULL,
    checkpoint_key TEXT NOT NULL,
    cursor_value TEXT,
    page_number INTEGER NOT NULL DEFAULT 0,
    records_processed INTEGER NOT NULL DEFAULT 0,
    state_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL,
    PRIMARY KEY(job_id, checkpoint_key),
    FOREIGN KEY(job_id) REFERENCES collection_jobs(job_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS source_query_audit (
    query_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    select_fields TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    completed_at TEXT,
    http_status INTEGER,
    total_count INTEGER,
    sampled_count INTEGER NOT NULL DEFAULT 0,
    coverage_rate REAL,
    is_truncated INTEGER NOT NULL DEFAULT 0,
    request_count INTEGER NOT NULL DEFAULT 0,
    response_bytes INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    rate_limit INTEGER,
    rate_remaining INTEGER,
    rate_reset_seconds INTEGER,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(batch_id) REFERENCES snapshot_batches(batch_id) ON DELETE CASCADE,
    FOREIGN KEY(job_id) REFERENCES collection_jobs(job_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_source_query_audit_hash
    ON source_query_audit(query_hash, requested_at);
CREATE INDEX IF NOT EXISTS idx_source_query_audit_batch
    ON source_query_audit(batch_id, endpoint);

CREATE TABLE IF NOT EXISTS published_snapshots (
    snapshot_type TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    published_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(batch_id) REFERENCES snapshot_batches(batch_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS data_quality_reports (
    report_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    check_name TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('info', 'warning', 'error')),
    status TEXT NOT NULL CHECK(status IN ('passed', 'warning', 'failed')),
    expected_json TEXT NOT NULL DEFAULT '{}',
    actual_json TEXT NOT NULL DEFAULT '{}',
    details TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(batch_id, check_name),
    FOREIGN KEY(batch_id) REFERENCES snapshot_batches(batch_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_quality_reports_batch_status
    ON data_quality_reports(batch_id, status, severity);

CREATE TABLE IF NOT EXISTS topic_catalog_metadata (
    topic_key TEXT PRIMARY KEY,
    subfield_id TEXT,
    subfield_name TEXT,
    field_id TEXT,
    field_name TEXT,
    domain_id TEXT,
    domain_name TEXT,
    works_count INTEGER,
    cited_by_count INTEGER,
    openalex_updated_date TEXT,
    metadata_hash TEXT NOT NULL,
    source TEXT NOT NULL,
    first_collected_at TEXT NOT NULL,
    last_collected_at TEXT NOT NULL,
    last_batch_id TEXT,
    FOREIGN KEY(topic_key) REFERENCES topics(topic_key) ON DELETE CASCADE,
    FOREIGN KEY(last_batch_id) REFERENCES snapshot_batches(batch_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_topic_catalog_domain
    ON topic_catalog_metadata(domain_id, field_id, subfield_id);

CREATE TABLE IF NOT EXISTS topic_catalog_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_key TEXT NOT NULL,
    metadata_hash TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source TEXT NOT NULL,
    batch_id TEXT,
    UNIQUE(topic_key, metadata_hash),
    FOREIGN KEY(topic_key) REFERENCES topics(topic_key) ON DELETE CASCADE,
    FOREIGN KEY(batch_id) REFERENCES snapshot_batches(batch_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS institution_catalog_metadata (
    institution_id TEXT PRIMARY KEY,
    homepage_url TEXT,
    image_url TEXT,
    works_count INTEGER,
    cited_by_count INTEGER,
    openalex_updated_date TEXT,
    geo_json TEXT NOT NULL DEFAULT '{}',
    ids_json TEXT NOT NULL DEFAULT '{}',
    metadata_hash TEXT NOT NULL,
    source TEXT NOT NULL,
    first_collected_at TEXT NOT NULL,
    last_collected_at TEXT NOT NULL,
    last_batch_id TEXT,
    FOREIGN KEY(institution_id) REFERENCES institutions(openalex_institution_id) ON DELETE CASCADE,
    FOREIGN KEY(last_batch_id) REFERENCES snapshot_batches(batch_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS institution_aliases (
    institution_id TEXT NOT NULL,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    alias_type TEXT NOT NULL,
    source TEXT NOT NULL,
    first_collected_at TEXT NOT NULL,
    last_collected_at TEXT NOT NULL,
    last_batch_id TEXT,
    PRIMARY KEY(institution_id, normalized_alias, source),
    FOREIGN KEY(institution_id) REFERENCES institutions(openalex_institution_id) ON DELETE CASCADE,
    FOREIGN KEY(last_batch_id) REFERENCES snapshot_batches(batch_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_institution_alias_normalized
    ON institution_aliases(normalized_alias);

CREATE TABLE IF NOT EXISTS institution_lineage (
    institution_id TEXT NOT NULL,
    ancestor_institution_id TEXT NOT NULL,
    lineage_order INTEGER NOT NULL,
    source TEXT NOT NULL,
    first_collected_at TEXT NOT NULL,
    last_collected_at TEXT NOT NULL,
    last_batch_id TEXT,
    PRIMARY KEY(institution_id, ancestor_institution_id),
    FOREIGN KEY(institution_id) REFERENCES institutions(openalex_institution_id) ON DELETE CASCADE,
    FOREIGN KEY(last_batch_id) REFERENCES snapshot_batches(batch_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS work_collection_metadata (
    work_id TEXT PRIMARY KEY,
    language TEXT,
    journal_name TEXT,
    landing_page_url TEXT,
    openalex_updated_date TEXT,
    openalex_created_date TEXT,
    primary_topic_id TEXT,
    countries_json TEXT NOT NULL DEFAULT '[]',
    last_batch_id TEXT,
    source TEXT NOT NULL,
    first_collected_at TEXT NOT NULL,
    last_collected_at TEXT NOT NULL,
    FOREIGN KEY(work_id) REFERENCES works(openalex_work_id) ON DELETE CASCADE,
    FOREIGN KEY(last_batch_id) REFERENCES snapshot_batches(batch_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS doi_conflicts (
    conflict_id TEXT PRIMARY KEY,
    normalized_doi TEXT NOT NULL,
    existing_work_id TEXT NOT NULL,
    incoming_work_id TEXT NOT NULL,
    batch_id TEXT,
    status TEXT NOT NULL DEFAULT 'candidate'
        CHECK(status IN ('candidate', 'resolved_same_work', 'resolved_distinct_works')),
    evidence_json TEXT NOT NULL DEFAULT '{}',
    first_detected_at TEXT NOT NULL,
    last_detected_at TEXT NOT NULL,
    UNIQUE(normalized_doi, existing_work_id, incoming_work_id),
    FOREIGN KEY(existing_work_id) REFERENCES works(openalex_work_id) ON DELETE CASCADE,
    FOREIGN KEY(batch_id) REFERENCES snapshot_batches(batch_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_doi_conflicts_status
    ON doi_conflicts(status, normalized_doi);
"""


MIGRATION_4_SQL = """
CREATE TABLE IF NOT EXISTS daily_collection_runs (
    run_id TEXT PRIMARY KEY,
    run_date TEXT NOT NULL,
    timezone_name TEXT NOT NULL,
    trigger_kind TEXT NOT NULL CHECK(trigger_kind IN (
        'scheduled', 'manual', 'missed_startup', 'test'
    )),
    scheduled_for TEXT,
    status TEXT NOT NULL CHECK(status IN (
        'pending', 'running', 'succeeded', 'partial', 'failed'
    )),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    window_count INTEGER NOT NULL DEFAULT 0,
    completed_windows INTEGER NOT NULL DEFAULT 0,
    failed_windows INTEGER NOT NULL DEFAULT 0,
    request_budget INTEGER NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    response_bytes INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    rate_remaining INTEGER,
    backup_path TEXT,
    report_path TEXT,
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_daily_collection_runs_date_status
    ON daily_collection_runs(run_date, status, started_at);

CREATE TABLE IF NOT EXISTS daily_collection_windows (
    run_id TEXT NOT NULL,
    publication_date TEXT NOT NULL,
    reasons_json TEXT NOT NULL DEFAULT '[]',
    priority INTEGER NOT NULL,
    preflight_meta_count INTEGER,
    estimated_requests INTEGER,
    status TEXT NOT NULL CHECK(status IN (
        'pending', 'running', 'succeeded', 'skipped', 'failed'
    )),
    job_id TEXT,
    batch_id TEXT,
    skip_reason TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(run_id, publication_date),
    FOREIGN KEY(run_id) REFERENCES daily_collection_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(job_id) REFERENCES collection_jobs(job_id) ON DELETE SET NULL,
    FOREIGN KEY(batch_id) REFERENCES snapshot_batches(batch_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_daily_windows_status_priority
    ON daily_collection_windows(run_id, status, priority);

CREATE TABLE IF NOT EXISTS work_date_observations (
    observation_id TEXT PRIMARY KEY,
    publication_date TEXT NOT NULL,
    batch_id TEXT NOT NULL UNIQUE,
    run_id TEXT,
    observed_at TEXT NOT NULL,
    meta_count INTEGER NOT NULL,
    previous_meta_count INTEGER,
    count_delta INTEGER,
    sampled_count INTEGER NOT NULL,
    coverage_rate REAL,
    is_truncated INTEGER NOT NULL DEFAULT 0,
    inserted_works INTEGER NOT NULL DEFAULT 0,
    updated_works INTEGER NOT NULL DEFAULT 0,
    unchanged_works INTEGER NOT NULL DEFAULT 0,
    authors_inserted INTEGER NOT NULL DEFAULT 0,
    authors_updated INTEGER NOT NULL DEFAULT 0,
    institution_relationship_changes INTEGER NOT NULL DEFAULT 0,
    topic_relationship_changes INTEGER NOT NULL DEFAULT 0,
    request_count INTEGER NOT NULL DEFAULT 0,
    response_bytes INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    rate_remaining INTEGER,
    quality_status TEXT NOT NULL CHECK(quality_status IN ('passed', 'warning', 'failed')),
    stability_status TEXT NOT NULL CHECK(stability_status IN (
        'provisional', 'rechecking', 'stabilizing', 'stable', 'failed'
    )),
    published INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(batch_id) REFERENCES snapshot_batches(batch_id) ON DELETE CASCADE,
    FOREIGN KEY(run_id) REFERENCES daily_collection_runs(run_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_work_date_observations_history
    ON work_date_observations(publication_date, observed_at);

CREATE TABLE IF NOT EXISTS work_date_status (
    publication_date TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK(status IN (
        'provisional', 'rechecking', 'stabilizing', 'stable', 'failed'
    )),
    first_observed_at TEXT,
    last_observed_at TEXT,
    last_meta_count INTEGER,
    successful_observations INTEGER NOT NULL DEFAULT 0,
    consecutive_unchanged INTEGER NOT NULL DEFAULT 0,
    last_batch_id TEXT,
    last_run_id TEXT,
    next_recheck_after TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(last_batch_id) REFERENCES snapshot_batches(batch_id) ON DELETE SET NULL,
    FOREIGN KEY(last_run_id) REFERENCES daily_collection_runs(run_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_work_date_status_state
    ON work_date_status(status, publication_date);

CREATE TABLE IF NOT EXISTS work_type_observations (
    batch_id TEXT NOT NULL,
    raw_type TEXT NOT NULL,
    normalized_group TEXT NOT NULL,
    work_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(batch_id, raw_type),
    FOREIGN KEY(batch_id) REFERENCES snapshot_batches(batch_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_work_type_observations_group
    ON work_type_observations(normalized_group, batch_id);

CREATE TABLE IF NOT EXISTS work_source_state (
    work_id TEXT PRIMARY KEY,
    source_hash TEXT NOT NULL,
    source_updated_date TEXT,
    first_seen_batch_id TEXT NOT NULL,
    last_seen_batch_id TEXT NOT NULL,
    last_changed_batch_id TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    FOREIGN KEY(work_id) REFERENCES works(openalex_work_id) ON DELETE CASCADE,
    FOREIGN KEY(first_seen_batch_id) REFERENCES snapshot_batches(batch_id) ON DELETE RESTRICT,
    FOREIGN KEY(last_seen_batch_id) REFERENCES snapshot_batches(batch_id) ON DELETE RESTRICT,
    FOREIGN KEY(last_changed_batch_id) REFERENCES snapshot_batches(batch_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_work_source_state_last_batch
    ON work_source_state(last_seen_batch_id);

CREATE TABLE IF NOT EXISTS collection_entity_changes (
    batch_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    change_type TEXT NOT NULL CHECK(change_type IN ('inserted', 'updated', 'deleted')),
    created_at TEXT NOT NULL,
    PRIMARY KEY(batch_id, entity_type, entity_key, change_type),
    FOREIGN KEY(batch_id) REFERENCES snapshot_batches(batch_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_collection_entity_changes_summary
    ON collection_entity_changes(batch_id, entity_type, change_type);
"""

MIGRATION_5_SQL = """
-- Preserve published V3 Works counts as the first V3.2 observation. Entity
-- change counts are unknown for legacy batches and therefore remain zero.
INSERT OR IGNORE INTO work_date_observations(
    observation_id, publication_date, batch_id, run_id, observed_at,
    meta_count, previous_meta_count, count_delta, sampled_count,
    coverage_rate, is_truncated, inserted_works, updated_works,
    unchanged_works, authors_inserted, authors_updated,
    institution_relationship_changes, topic_relationship_changes,
    request_count, response_bytes, retry_count, rate_remaining,
    quality_status, stability_status, published, source, created_at
)
SELECT
    'legacy:' || sb.batch_id,
    REPLACE(ps.snapshot_type, 'daily_ingest:', ''),
    sb.batch_id,
    NULL,
    COALESCE(sqa.completed_at, ps.published_at),
    sqa.total_count,
    NULL,
    NULL,
    sqa.sampled_count,
    sqa.coverage_rate,
    sqa.is_truncated,
    0, 0, 0, 0, 0, 0, 0,
    sqa.request_count,
    sqa.response_bytes,
    sqa.retry_count,
    sqa.rate_remaining,
    CASE WHEN sqa.is_truncated=0 AND sqa.sampled_count=sqa.total_count
         THEN 'passed' ELSE 'warning' END,
    'provisional',
    1,
    'OpenAlex',
    COALESCE(sqa.completed_at, ps.published_at)
FROM published_snapshots ps
JOIN snapshot_batches sb ON sb.batch_id=ps.batch_id
JOIN source_query_audit sqa ON sqa.batch_id=sb.batch_id
    AND sqa.endpoint='works'
    AND sqa.query_id=(
        SELECT inner_audit.query_id FROM source_query_audit inner_audit
        WHERE inner_audit.batch_id=sb.batch_id AND inner_audit.endpoint='works'
        ORDER BY inner_audit.created_at DESC LIMIT 1
    )
WHERE ps.snapshot_type LIKE 'daily_ingest:%'
  AND sqa.total_count IS NOT NULL;

INSERT OR IGNORE INTO work_date_status(
    publication_date, status, first_observed_at, last_observed_at,
    last_meta_count, successful_observations, consecutive_unchanged,
    last_batch_id, last_run_id, next_recheck_after, updated_at
)
SELECT
    observation.publication_date,
    'provisional',
    MIN(all_observations.observed_at),
    observation.observed_at,
    observation.meta_count,
    COUNT(all_observations.observation_id),
    0,
    observation.batch_id,
    NULL,
    NULL,
    observation.observed_at
FROM work_date_observations observation
JOIN work_date_observations all_observations
  ON all_observations.publication_date=observation.publication_date
WHERE observation.published=1
  AND NOT EXISTS (
      SELECT 1 FROM work_date_observations later
      WHERE later.publication_date=observation.publication_date
        AND later.published=1
        AND later.observed_at>observation.observed_at
  )
GROUP BY observation.publication_date;
"""
