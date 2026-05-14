"""Bronze layer: raw ingestion from Azure SQL (OLTP) → Delta Lake.

Strategy:
- Full load on first run (no watermark file exists)
- Watermark-based incremental on subsequent runs (uses updated_at / created_at)
- Adds metadata columns: _source_system, _ingested_at, _batch_id
- All OLTP tables are written as-is (no transformations here)
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from etl.utils.keyvault import get_secret, get_sql_connection_string
from etl.utils.logging import get_logger
from etl.utils.spark import get_spark

logger = get_logger(__name__)

# Tables and their watermark column (None = full load only)
OLTP_TABLES: dict[str, Optional[str]] = {
    "oltp.addresses": None,  # rarely changes, always full load
    "oltp.categories": None,
    "oltp.suppliers": "created_at",
    "oltp.customers": "created_at",
    "oltp.products": "updated_at",
    "oltp.orders": "created_at",
    "oltp.order_items": None,  # no updated_at; use order watermark
}


def _bronze_path(storage_account: str, table: str) -> str:
    """Construct the abfss path for a Bronze Delta table."""
    table_name = table.replace(".", "_").replace("oltp_", "")
    return f"abfss://bronze@{storage_account}.dfs.core.windows.net/{table_name}"


def _read_watermark(spark: SparkSession, path: str) -> Optional[datetime]:
    """Read the last successful watermark from a Delta table property."""
    try:
        props = spark.sql(f"DESCRIBE DETAIL delta.`{path}`").collect()
        wm = dict(props[0].asDict()).get("properties", {}).get("etl_watermark")
        return datetime.fromisoformat(wm) if wm else None
    except Exception:
        return None


def _write_watermark(spark: SparkSession, path: str, watermark: datetime) -> None:
    spark.sql(
        f"ALTER TABLE delta.`{path}` "
        f"SET TBLPROPERTIES ('etl_watermark' = '{watermark.isoformat()}')"
    )


def ingest_table(
    spark: SparkSession,
    table: str,
    watermark_col: Optional[str],
    jdbc_url: str,
    batch_id: str,
    storage_account: str,
) -> int:
    """Ingest a single OLTP table to Bronze Delta. Returns row count written."""
    bronze_path = _bronze_path(storage_account, table)
    ingested_at = datetime.now(timezone.utc)

    watermark_value = _read_watermark(spark, bronze_path) if watermark_col else None

    # Build the JDBC query with optional watermark filter
    if watermark_col and watermark_value:
        query = (
            f"(SELECT * FROM {table} "
            f"WHERE {watermark_col} > '{watermark_value.isoformat()}') AS t"
        )
        load_type = "incremental"
    else:
        query = f"(SELECT * FROM {table}) AS t"
        load_type = "full"

    logger.info("Reading", extra={"table": table, "load_type": load_type})

    username = get_secret("sql-admin-username")
    password = get_secret("sql-admin-password")

    df: DataFrame = (
        spark.read.format("jdbc")
        .option("url", jdbc_url)
        .option("dbtable", query)
        .option("user", username)
        .option("password", password)
        .option("driver", "com.microsoft.sqlserver.jdbc.SQLServerDriver")
        .option("fetchsize", "10000")
        .load()
    )

    # Add ETL metadata columns
    df = df.withColumn("_source_system", F.lit("azure_sql_oltp"))
    df = df.withColumn("_ingested_at", F.lit(ingested_at.isoformat()))
    df = df.withColumn("_batch_id", F.lit(batch_id))

    count = df.count()
    if count == 0:
        logger.info("No new rows", extra={"table": table})
        return 0

    # Write mode: overwrite for full load, append for incremental
    write_mode = "overwrite" if load_type == "full" else "append"
    (df.write.format("delta").mode(write_mode).option("mergeSchema", "true").save(bronze_path))

    # Update watermark
    if watermark_col:
        _write_watermark(spark, bronze_path, ingested_at)

    logger.info("Ingested", extra={"table": table, "rows": count, "mode": write_mode})
    return count


def run_bronze_ingestion(storage_account: Optional[str] = None) -> dict[str, int]:
    """Ingest all OLTP tables to Bronze. Entry point for Databricks job."""
    spark = get_spark("bronze-ingestion")
    batch_id = str(uuid.uuid4())
    jdbc_url = get_sql_connection_string()

    if storage_account is None:
        storage_account = get_secret("storage-account-name")

    results = {}
    for table, watermark_col in OLTP_TABLES.items():
        try:
            count = ingest_table(spark, table, watermark_col, jdbc_url, batch_id, storage_account)
            results[table] = count
        except Exception as exc:
            logger.error("Ingestion failed", extra={"table": table, "error": str(exc)})
            raise

    logger.info("Bronze ingestion complete", extra={"batch_id": batch_id, "results": results})
    return results


if __name__ == "__main__":
    run_bronze_ingestion()
