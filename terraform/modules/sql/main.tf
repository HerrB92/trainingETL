resource "random_string" "sql_suffix" {
  length  = 6
  special = false
  upper   = false
}

resource "azurerm_mssql_server" "main" {
  name                         = "sql-${var.prefix}-${random_string.sql_suffix.result}"
  resource_group_name          = var.resource_group_name
  location                     = var.location
  version                      = "12.0"
  administrator_login          = var.admin_username
  administrator_login_password = var.admin_password

  minimum_tls_version = "1.2"

  tags = var.tags
}

# Firewall rule: allow Azure services (incl. Databricks) to connect
resource "azurerm_mssql_firewall_rule" "azure_services" {
  name             = "AllowAzureServices"
  server_id        = azurerm_mssql_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# Serverless database — auto-pauses after 15 minutes of inactivity
# Cost: you only pay for vCore-seconds when the DB is actually running.
# On first connection after auto-pause, the DB resumes (takes ~1-2 minutes).
resource "azurerm_mssql_database" "oltp" {
  name      = "db-${var.prefix}-oltp"
  server_id = azurerm_mssql_server.main.id

  # Serverless compute tier (auto-pause capable)
  sku_name = "GP_S_Gen5_1"  # General Purpose, Serverless, Gen5, 1 vCore max

  # vCore range for the serverless auto-scaling
  min_capacity = 0.5  # minimum 0.5 vCores (lowest billable unit)

  # Auto-pause after 15 minutes of inactivity (minimum allowed value)
  auto_pause_delay_in_minutes = 15

  # Storage: 32 GB max (increase for production)
  max_size_gb = 32

  tags = var.tags
}
