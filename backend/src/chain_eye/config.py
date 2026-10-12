"""Shared local runtime paths and explicit environment overrides."""
import os
from pathlib import Path


PROJECT_ROOT=Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH=PROJECT_ROOT/'.runtime/chain_eye.sqlite'
DEFAULT_UPLOAD_ROOT=PROJECT_ROOT/'.runtime/sources'
DEFAULT_LOG_PATH=PROJECT_ROOT/'.runtime/logs/chain-eye.jsonl'


def database_path(override=None):
    return Path(override or os.getenv('CHAIN_EYE_DB') or DEFAULT_DB_PATH)


def upload_root(override=None):
    return Path(override or os.getenv('CHAIN_EYE_UPLOAD_DIR') or DEFAULT_UPLOAD_ROOT)


def log_path(override=None):
    return Path(override or os.getenv('CHAIN_EYE_LOG_PATH') or DEFAULT_LOG_PATH)
