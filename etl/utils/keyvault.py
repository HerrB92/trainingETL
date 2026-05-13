"""Secret retrieval from Azure Key Vault or environment variables.

On Databricks: uses dbutils.secrets (backed by Key Vault secret scope).
Locally: reads from environment variables (useful for testing).
"""

import os
from functools import lru_cache


def get_secret(secret_name: str, scope: str = "kv-scope") -> str:
    """Retrieve a secret by name.

    Tries Databricks dbutils first (available on Databricks clusters),
    then falls back to environment variables for local runs.
    """
    # Databricks path: dbutils is injected into the global namespace
    try:
        dbutils = _get_dbutils()
        if dbutils is not None:
            return dbutils.secrets.get(scope=scope, key=secret_name)
    except Exception:
        pass

    # Local fallback: environment variable (dashes → underscores, upper)
    env_key = secret_name.replace("-", "_").upper()
    value = os.getenv(env_key)
    if value:
        return value

    raise RuntimeError(
        f"Secret '{secret_name}' not found in Databricks secrets scope '{scope}' "
        f"or environment variable '{env_key}'."
    )


def get_sql_connection_string() -> str:
    """Build a JDBC connection string from Key Vault secrets."""
    server = get_secret("sql-server-fqdn")
    database = get_secret("sql-database-name")
    username = get_secret("sql-admin-username")
    password = get_secret("sql-admin-password")
    return (
        f"jdbc:sqlserver://{server}:1433;"
        f"database={database};"
        f"user={username};"
        f"password={password};"
        f"encrypt=true;trustServerCertificate=false"
    )


def get_storage_account_name() -> str:
    return get_secret("storage-account-name")


def get_ai_services_config() -> dict[str, str]:
    return {
        "endpoint": get_secret("ai-services-endpoint"),
        "api_key": get_secret("ai-services-api-key"),
    }


@lru_cache(maxsize=1)
def _get_dbutils():
    """Return dbutils if running on Databricks, else None."""
    try:
        from pyspark.sql import SparkSession

        spark = SparkSession.builder.getOrCreate()
        # IPython-style globals trick used by Databricks utilities
        sc = spark.sparkContext
        _ = sc  # noqa: used to avoid 'unused' warnings
        import IPython

        return IPython.get_ipython().user_ns.get("dbutils")
    except Exception:
        return None
