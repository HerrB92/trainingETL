"""SparkSession factory — returns a local or Databricks session."""

import os

from pyspark.sql import SparkSession


def get_spark(app_name: str = "b2b-etl") -> SparkSession:
    """Return an active SparkSession.

    On Databricks the session already exists; locally it creates one
    in 'local[*]' mode so tests and dev runs work without a cluster.
    """
    env = os.getenv("SPARK_ENV", "databricks")

    if env == "local":
        return (
            SparkSession.builder.appName(app_name)
            .master("local[*]")
            .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
            .config(
                "spark.sql.catalog.spark_catalog",
                "org.apache.spark.sql.delta.catalog.DeltaCatalog",
            )
            .config("spark.sql.warehouse.dir", "/tmp/spark-warehouse")
            .config("spark.driver.memory", "2g")
            .getOrCreate()
        )

    # On Databricks: the session is already initialised by the runtime.
    # SparkSession.builder.getOrCreate() returns the existing one.
    return SparkSession.builder.appName(app_name).getOrCreate()
