from __future__ import annotations


LATEST_SCHEMA_VERSION = 2


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
