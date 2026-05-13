# Architecture Overview

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Azure Cloud                                 │
│                                                                     │
│  ┌──────────────────┐                                               │
│  │  Azure SQL DB    │  Serverless, auto-pause 15 min               │
│  │  (OLTP / 3NF)    │  7 tables, ~500+ rows seed data              │
│  └────────┬─────────┘                                               │
│           │ JDBC (read-only)                                         │
│           ▼                                                          │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              Azure Databricks Workspace                      │   │
│  │                                                              │   │
│  │  ┌─────────────────────────────────────────────────────┐     │   │
│  │  │             Databricks Workflows (Jobs)             │     │   │
│  │  │                                                     │     │   │
│  │  │  Bronze Ingest ──► Silver Transform ──► Gold Build  │     │   │
│  │  │                                          │           │     │   │
│  │  │                              GenAI Enrich ◄──────────┘     │   │
│  │  └─────────────────────────────────────────────────────┘     │   │
│  │                                                              │   │
│  │  All-Purpose Cluster   │   SQL Warehouse                    │   │
│  │  (auto-terminate 15m)  │   (auto-stop 10m)                  │   │
│  └──────────────────────────────────────────────────────────────┘   │
│           │  read/write                   │ SQL queries              │
│           ▼                               ▼                          │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │        Azure Data Lake Storage Gen2 (ADLS)                   │   │
│  │                                                              │   │
│  │  bronze/   silver/   gold/   quarantine/                     │   │
│  │  (raw)     (clean)   (star   (invalid)                       │   │
│  │                       schema)                                │   │
│  │              Delta Lake (ACID, time-travel, versioning)       │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────┐   ┌──────────────────────────────────────┐   │
│  │  Azure Key Vault │   │  Azure AI Services (existing)        │   │
│  │  (all secrets)   │   │  train-bb-ai-services                │   │
│  │                  │   │  • text-embedding-ada-002            │   │
│  └──────────────────┘   │  • GPT-4o (chat completions)         │   │
│                          └──────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
Azure SQL (3NF OLTP)
    │
    │  Full load (first run) / Watermark-based incremental (subsequent runs)
    │
    ▼
Bronze Layer  ─── Raw Delta tables, append/overwrite, metadata columns added
    │
    │  Cleanse, validate, deduplicate (MERGE INTO / upsert)
    │
    ▼
Silver Layer  ─── Validated Delta tables, quarantine for bad rows
    │
    │  Aggregate, join, apply surrogate keys
    │
    ▼
Gold Layer    ─── Kimball star schema (fact_sales + dim_*)
    │
    │  Semantic embeddings via Azure OpenAI
    │
    ▼
GenAI Layer   ─── Embedding vectors in dim_product, LLM auto-categorization
```

## Layer Responsibilities

| Layer | Path | Format | Purpose |
|-------|------|--------|---------|
| Bronze | `abfss://bronze@<acct>/` | Delta | Exact copy of source, immutable history |
| Silver | `abfss://silver@<acct>/` | Delta | Validated, normalised, upserted |
| Gold | `abfss://gold@<acct>/` | Delta | Analytics-ready star schema |
| Quarantine | `abfss://quarantine@<acct>/` | Delta | Rejected rows with failure reason |

## Key Design Decisions

**Why Delta Lake?**
Delta adds ACID transactions, schema enforcement, and `MERGE INTO` (upsert) to Parquet files. Without it, overwriting partial data could corrupt tables. Time-travel (versioning) lets you query yesterday's data: `SELECT * FROM delta.\`path\` VERSION AS OF 5`.

**Why Medallion Architecture (Bronze/Silver/Gold)?**
Each layer has one job. Bronze never modifies raw data — you can always re-derive Silver from it. Silver never shapes data for a specific report — Gold does. This separation makes debugging simple: bad data in Gold? Check Silver. Bad Silver? Check Bronze. Bad Bronze? Check the source.

**Why Kimball Star Schema?**
Relational 3NF databases are good for writing data (few joins, no redundancy). Star schemas are good for *reading* data: one central fact table, short join paths, fast aggregations. BI tools (Power BI, Tableau) query star schemas significantly faster than 3NF.

**Why SCD Type 2 for dim_customer?**
If a customer moves company, we want historical orders to still show the *old* company (the company at order time), not the new one. SCD2 inserts a new row instead of overwriting, preserving history.

## Infrastructure Overview

All Azure resources are managed by Terraform (see [02_terraform_guide.md](02_terraform_guide.md)):

| Resource | Purpose | Auto-stop |
|----------|---------|-----------|
| Resource Group | Container for all ETL resources | — |
| ADLS Gen2 | Delta Lake storage (Bronze/Silver/Gold) | Lifecycle policy |
| Key Vault | All secrets — never hardcoded | — |
| Azure SQL Serverless | OLTP source database | 15 min auto-pause |
| Databricks Workspace | ETL compute + SQL Warehouse | — |
| Databricks Cluster | Job runs and interactive dev | 15 min auto-terminate |
| Databricks SQL Warehouse | BI queries against Gold | 10 min auto-stop |
| Azure AI Services | Embeddings + chat completions | — (existing resource) |

## Component Interaction via Secret Scope

Databricks jobs never receive credentials directly. Instead:

```
Terraform ──► writes secrets to ──► Azure Key Vault
Terraform ──► creates ──► Databricks Secret Scope (backed by Key Vault)
Databricks job ──► reads ──► dbutils.secrets.get("kv-scope", "secret-name")
```

This means: no credentials in code, no credentials in logs, no credentials in Git.
