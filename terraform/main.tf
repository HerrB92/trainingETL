locals {
  prefix = "${var.project_name}-${var.environment}"
  tags = {
    Project     = "b2b-etl-platform"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# Resource Group for all ETL project resources
resource "azurerm_resource_group" "main" {
  name     = "rg-${local.prefix}"
  location = var.location
  tags     = local.tags
}

# Reference the existing AI Services account (not managed by this Terraform)
data "azurerm_cognitive_account" "ai_services" {
  name                = var.ai_services_account_name
  resource_group_name = var.ai_services_resource_group
}

# ── Modules ─────────────────────────────────────────────────

module "storage" {
  source              = "./modules/storage"
  prefix              = local.prefix
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags
}

module "keyvault" {
  source              = "./modules/keyvault"
  prefix              = local.prefix
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  tenant_id           = var.tenant_id
  admin_object_id     = var.key_vault_admin_object_id
  tags                = local.tags

  secrets = {
    "sql-admin-username"    = var.sql_admin_username
    "sql-admin-password"    = var.sql_admin_password
    "storage-account-key"   = module.storage.primary_access_key
    "ai-services-endpoint"  = data.azurerm_cognitive_account.ai_services.endpoint
    "ai-services-api-key"   = data.azurerm_cognitive_account.ai_services.primary_access_key
  }
}

module "sql" {
  source              = "./modules/sql"
  prefix              = local.prefix
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  admin_username      = var.sql_admin_username
  admin_password      = var.sql_admin_password
  tags                = local.tags
}

module "databricks" {
  source               = "./modules/databricks"
  prefix               = local.prefix
  location             = var.location
  resource_group_name  = azurerm_resource_group.main.name
  storage_account_name = module.storage.account_name
  storage_account_key  = module.storage.primary_access_key
  phase2               = var.databricks_host != ""
  tags                 = local.tags
}

# ── Budget Alert ─────────────────────────────────────────────

resource "azurerm_monitor_action_group" "budget_alert" {
  name                = "ag-${local.prefix}-budget"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "budget"

  email_receiver {
    name          = "admin"
    email_address = var.budget_alert_email
  }
}

resource "azurerm_consumption_budget_resource_group" "main" {
  name              = "budget-${local.prefix}"
  resource_group_id = azurerm_resource_group.main.id

  amount     = var.monthly_budget_eur
  time_grain = "Monthly"

  time_period {
    # Static start date: first day of the project month.
    # Avoid timestamp() here — it is non-deterministic and causes a plan diff on every run.
    start_date = "2026-05-01T00:00:00Z"
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_groups = [azurerm_monitor_action_group.budget_alert.id]
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThan"
    threshold_type = "Forecasted"
    contact_groups = [azurerm_monitor_action_group.budget_alert.id]
  }
}
