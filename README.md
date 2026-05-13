# B2B E-Commerce Analytics ETL Platform

A production-grade data engineering platform for B2B e-commerce analytics, built on **Azure Databricks** with a **Medallion architecture** (Bronze → Silver → Gold), **Kimball-style star schema**, and integrated **GenAI features** for semantic product search and automated categorization.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Azure Cloud                          │
│                                                         │
│  ┌──────────────┐    ┌────────────────────────────────┐ │
│  │ Azure SQL DB │    │  Azure Data Lake Storage Gen2  │ │
│  │  (3NF OLTP)  │───▶│  Bronze │ Silver │ Gold        │ │
│  └──────────────┘    └────────────────────────────────┘ │
│         JDBC                      Delta Lake            │
│                      ┌────────────────────────────────┐ │
│                      │    Azure Databricks            │ │
│                      │  ┌──────────┐ ┌─────────────┐  │ │
│                      │  │  ETL     │ │  SQL        │  │ │
│                      │  │  Jobs    │ │  Warehouse  │  │ │
│                      │  └──────────┘ └─────────────┘  │ │
│                      │  ┌─────────────────────────┐   │ │
│                      │  │   GenAI Module          │   │ │
│                      │  │  (Embeddings + LLM)     │   │ │
│                      │  └─────────────────────────┘   │ │
│                      └────────────────────────────────┘ │
│  ┌──────────────┐    ┌──────────────────────────────┐  │
│  │  Key Vault   │    │  AI Services (multi-service) │  │
│  │  (secrets)   │    │  text-embedding-ada-002      │  │
│  └──────────────┘    │  GPT-4o                      │  │
│                      └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Azure CLI (`az login`)
- Terraform >= 1.7
- Python 3.11
- Databricks CLI >= 0.200

### 1. Bootstrap Infrastructure

```bash
cd terraform/
# See docs/02_terraform_guide.md for the one-time backend setup
terraform init
terraform plan -var-file="environments/dev.tfvars"
terraform apply -var-file="environments/dev.tfvars"
```

### 2. Run ETL Locally (Tests Only — No Azure Required)

```bash
pip install -r etl/requirements.txt
pytest tests/ -v
```

### 3. Deploy to Databricks

```bash
databricks configure  # set host + token from Key Vault outputs
databricks bundle deploy --target dev
databricks bundle run etl_bronze_ingest
```

## Documentation

| Guide | Description |
|-------|-------------|
| [Architecture](docs/01_architecture.md) | System overview, data flow, Mermaid diagrams |
| [Terraform Guide](docs/02_terraform_guide.md) | Beginner-friendly IaC guide, bootstrap steps |
| [ETL Pipeline](docs/03_etl_pipeline.md) | Medallion architecture, Bronze/Silver/Gold explained |
| [Data Modeling](docs/04_data_modeling.md) | 3NF vs Star Schema, SCD2, Kimball concepts |
| [GenAI Features](docs/05_genai_features.md) | Embeddings, RAG, Text-to-SQL, future use cases |

## Project Structure

```
trainingETL/
├── etl/            Python ETL modules (bronze/silver/gold/genai/utils)
├── terraform/      Azure infrastructure as code
├── databricks/     Databricks Asset Bundle
├── sql/            DDL scripts
├── tests/          Unit tests (local PySpark)
├── docs/           Guides and architecture docs
└── .github/        CI/CD workflows
```

## Tech Stack

- **Orchestration:** Databricks Workflows (via Asset Bundles)
- **Processing:** PySpark 3.5 on Databricks Runtime 14.3 LTS
- **Storage:** Azure Data Lake Storage Gen2 with Delta Lake
- **Source DB:** Azure SQL Database (Serverless, auto-pause)
- **IaC:** Terraform (azurerm + databricks providers)
- **CI/CD:** GitHub Actions
- **GenAI:** Azure AI Services (OpenAI embeddings + GPT-4o)
- **Secrets:** Azure Key Vault

## Cost Estimate (Dev Environment)

| Component | Auto-stop | ~Monthly Cost |
|-----------|-----------|---------------|
| ADLS Gen2 (LRS) | — | €2–5 |
| Azure SQL Serverless | 15 min pause | €5–15 |
| Databricks Cluster | 15 min terminate | €0 when idle |
| Databricks SQL Warehouse | 10 min stop | €0 when idle |
| Key Vault | — | <€1 |
| **Total (light use)** | | **~€10–25/month** |
