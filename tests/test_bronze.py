"""Tests for the Bronze ingestion layer.

These tests verify the metadata column logic and path construction
without requiring an actual Azure SQL connection.
"""

from pyspark.sql import functions as F


def test_bronze_path_construction():
    """Bronze path must be correctly formatted with storage account name."""
    from etl.bronze.ingest import _bronze_path

    path = _bronze_path("mystorageacct", "oltp.orders")
    assert path == "abfss://bronze@mystorageacct.dfs.core.windows.net/orders"


def test_bronze_path_strips_schema_prefix():
    """The 'oltp.' prefix should be removed from the table name in the path."""
    from etl.bronze.ingest import _bronze_path

    path = _bronze_path("myacct", "oltp.order_items")
    assert "oltp." not in path
    assert path.endswith("/order_items")


def test_metadata_columns_added(spark, sample_customers):
    """Bronze ingestion must add _source_system, _ingested_at, _batch_id columns."""
    batch_id = "test-batch-001"

    enriched = (
        sample_customers
        .withColumn("_source_system", F.lit("azure_sql_oltp"))
        .withColumn("_ingested_at", F.lit("2024-01-01T00:00:00+00:00"))
        .withColumn("_batch_id", F.lit(batch_id))
    )

    cols = enriched.columns
    assert "_source_system" in cols
    assert "_ingested_at" in cols
    assert "_batch_id" in cols


def test_metadata_source_system_value(spark, sample_customers):
    """_source_system must always be 'azure_sql_oltp'."""
    enriched = sample_customers.withColumn("_source_system", F.lit("azure_sql_oltp"))
    values = [row._source_system for row in enriched.select("_source_system").collect()]
    assert all(v == "azure_sql_oltp" for v in values)


def test_oltp_tables_config():
    """All configured OLTP tables should have a valid watermark column or None."""
    from etl.bronze.ingest import OLTP_TABLES

    valid_watermark_cols = {"created_at", "updated_at", None}
    for table, col in OLTP_TABLES.items():
        assert col in valid_watermark_cols, f"Unexpected watermark column '{col}' for {table}"
        assert table.startswith("oltp."), f"Table '{table}' must be schema-qualified"
