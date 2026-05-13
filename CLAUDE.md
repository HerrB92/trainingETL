# CLAUDE.md — B2B E-Commerce Analytics ETL Platform

## Architecture Overview

Medallion architecture on Azure + Databricks:

```
Azure SQL DB (3NF OLTP)
        │ JDBC
        ▼
  [Bronze Layer]  — raw Delta tables, append-only, metadata columns
        │ PySpark transforms
        ▼
  [Silver Layer]  — cleansed, validated, deduplicated Delta tables
        │ PySpark aggregations
        ▼
  [Gold Layer]    — Kimball star schema (fact_sales + dim_* tables)
        │
        ▼
  SQL Warehouse   — BI / ad-hoc queries
  GenAI Module    — embeddings, categorization, RAG stubs
```

All infrastructure is managed via Terraform. Secrets live exclusively in Azure Key Vault.

## Tech Stack

| Component | Version / SKU |
|-----------|--------------|
| Python | 3.11 |
| PySpark | 3.5 (Databricks Runtime 14.3 LTS) |
| Delta Lake | 3.x (bundled with DBR 14.3) |
| Terraform | >= 1.7 |
| Databricks CLI | >= 0.200 |
| Azure Provider | azurerm ~> 3.110 |
| Databricks Provider | databricks ~> 1.40 |
| OpenAI SDK | openai >= 1.0 (Azure endpoint) |

## Project Conventions

- **Formatter:** Black (line length 100)
- **Linter:** ruff (configured in `pyproject.toml`)
- **Type hints:** required on all function signatures
- **Tests:** pytest; local Spark runs in `local[1]` mode — no Azure credentials needed
- **No hardcoded credentials:** all secrets via Key Vault or environment variables
- **Commit style:** conventional commits (`feat:`, `fix:`, `docs:`, `chore:`)

## Repository Layout

```
etl/          Python ETL modules (bronze/, silver/, gold/, genai/, utils/)
terraform/    All Azure infrastructure as code
databricks/   Databricks Asset Bundle (jobs, cluster policies)
sql/          DDL scripts (OLTP 3NF + Star Schema reference)
tests/        pytest unit tests (PySpark local mode)
docs/         Architecture and beginner guides
.github/      GitHub Actions CI/CD workflows
```

## Environment Variables

When running locally outside Databricks, set these before running ETL scripts:

```bash
# Azure credentials (for Key Vault access)
AZURE_CLIENT_ID=<service-principal-app-id>
AZURE_CLIENT_SECRET=<service-principal-secret>
AZURE_TENANT_ID=<aad-tenant-id>

# Key Vault name (all other secrets are fetched at runtime)
KEY_VAULT_NAME=<your-key-vault-name>

# For local testing without Azure (skips Key Vault, uses local Spark)
SPARK_ENV=local
```

On Databricks, secrets are read from a Databricks Secret Scope backed by Azure Key Vault.

## Running Locally

```bash
# Install dependencies
pip install -r etl/requirements.txt

# Lint
ruff check etl/

# Tests (no Azure required)
pytest tests/ -v

# Format check
black --check etl/
```

## Infrastructure Bootstrap

See [docs/02_terraform_guide.md](docs/02_terraform_guide.md) for the one-time setup steps required before running `terraform apply`.

## Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `etl/utils/spark.py` | SparkSession factory (local vs. Databricks) |
| `etl/utils/keyvault.py` | Secret retrieval from Key Vault or env vars |
| `etl/utils/logging.py` | Structured JSON logging |
| `etl/bronze/ingest.py` | JDBC extraction from Azure SQL → raw Delta |
| `etl/silver/transform_*.py` | Cleanse, validate, upsert per domain entity |
| `etl/gold/star_schema.py` | Build dim + fact tables from Silver |
| `etl/genai/embeddings.py` | Azure OpenAI embeddings for products |
| `etl/genai/categorization.py` | LLM zero-shot product categorization |

## CI/CD Pipeline Summary

| Workflow | Trigger | Actions |
|----------|---------|---------|
| `ci.yml` | Every PR | ruff lint → pytest |
| `terraform.yml` | PR: plan only / main: apply | terraform validate → plan → apply |
| `deploy.yml` | After terraform on main | Databricks bundle deploy |

## Integration of New AI/GenAI Use Cases

The `etl/genai/` module is the entry point for new AI features. Stubs for RAG, Text-to-SQL, anomaly detection, and churn prediction are documented in [docs/05_genai_features.md](docs/05_genai_features.md).
