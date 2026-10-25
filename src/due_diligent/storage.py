"""Load inputs and save outputs, locally or on S3. The only module that touches files."""
from __future__ import annotations

import io
import logging
from pathlib import Path

import boto3
import pandas as pd
from botocore.exceptions import BotoCoreError, ClientError

from due_diligent import config

logger = logging.getLogger(__name__)


# --- public: what cli.py calls -----------------------------------------------------

def load_tickers() -> pd.DataFrame:
    """Read the ticker list (Symbol, Sector, Industry, ...) from local disk or S3."""
    if config.STORAGE_MODE == "s3":
        key = f"{config.INPUT_PREFIX}/{config.TICKERS_FILENAME}"
        logger.info("Reading tickers from s3://%s/%s", config.S3_BUCKET, key)
        df = _read_s3_csv(config.S3_BUCKET, key)
        logger.info("Loaded %d tickers", len(df))
    elif config.STORAGE_MODE == "local" :
        path = Path(config.LOCAL_INPUT_DIR) / config.TICKERS_FILENAME
        logger.info("Reading tickers from %s", path)
        df = pd.read_csv(path)
        logger.info("Loaded %d tickers", len(df))
    else:
        logger.error("Invalid storage mode: %s", config.STORAGE_MODE)
        raise ValueError(f"Unknown STORAGE_MODE: {config.STORAGE_MODE!r}")
    return df

def save_results(df: pd.DataFrame, run_date: str) -> str:
    """Save the ranked results and return where they were written (path or s3:// URL)."""
    if config.STORAGE_MODE == "s3":
        key = f"{config.OUTPUT_PREFIX}/sp500/{run_date}/{config.TICKERS_FILENAME}"
        logger.info("Saving results to s3://%s/%s", config.S3_BUCKET, key)
        _write_s3_csv(df.round(3), config.S3_BUCKET, key)
        return f"s3://{config.S3_BUCKET}/{key}"
    elif config.STORAGE_MODE == "local":
        path = Path(config.LOCAL_OUTPUT_DIR) / "sp500" / run_date / config.TICKERS_FILENAME
        logger.info("Saving results to %s", path)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.round(3).to_csv(path, index=False)
        return str(path)
    else:
        logger.error("Invalid storage mode: %s", config.STORAGE_MODE)
        raise ValueError(f"Unknown STORAGE_MODE: {config.STORAGE_MODE!r}")

# --- private: one helper per backend -------------------------------------------------

def _read_s3_csv(bucket: str, key: str) -> pd.DataFrame:
    """Replaces old util.get_file."""
    s3_client = boto3.client("s3")
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        text = response['Body'].read().decode('utf-8')
    except (ClientError, BotoCoreError) as e:
        logger.error("Error reading from s3://%s/%s: %s", bucket, key, e)
        raise
    df = pd.read_csv(io.StringIO(text))
    return df

def _write_s3_csv(df: pd.DataFrame, bucket: str, key: str) -> None:
    """Replaces old upload.upload_s3."""
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    s3_client = boto3.client("s3")
    try:
        s3_client.put_object(Bucket=bucket, Key=key, Body=buffer.getvalue())
    except (ClientError, BotoCoreError) as e:
        logger.error("Error writing to s3://%s/%s: %s", bucket, key, e)
        raise
    logger.info("Wrote %d rows to s3://%s/%s", len(df), bucket, key)