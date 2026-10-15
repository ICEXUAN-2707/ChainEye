CREATE TABLE IF NOT EXISTS company_profiles(
    id TEXT NOT NULL,
    profile_version INTEGER NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY(id,profile_version)
);
CREATE TABLE IF NOT EXISTS identity_candidates(
    dataset_id TEXT NOT NULL,
    dataset_version INTEGER NOT NULL,
    source_id TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY(dataset_id,dataset_version,source_id),
    FOREIGN KEY(dataset_id,dataset_version) REFERENCES dataset_snapshots(dataset_id,version),
    FOREIGN KEY(source_id) REFERENCES sources(id)
);
CREATE TABLE IF NOT EXISTS identity_confirmations(
    id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    from_version INTEGER NOT NULL,
    to_version INTEGER NOT NULL,
    body TEXT NOT NULL,
    UNIQUE(dataset_id,to_version),
    FOREIGN KEY(dataset_id,to_version) REFERENCES dataset_snapshots(dataset_id,version)
);
