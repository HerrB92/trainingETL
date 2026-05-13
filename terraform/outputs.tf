output "resource_group_name" {
  description = "Name of the created resource group"
  value       = azurerm_resource_group.main.name
}

output "storage_account_name" {
  description = "ADLS Gen2 storage account name"
  value       = module.storage.account_name
}

output "databricks_workspace_url" {
  description = "Databricks workspace URL (use for CLI configuration)"
  value       = module.databricks.workspace_url
}

output "sql_server_fqdn" {
  description = "Fully qualified domain name of the Azure SQL Server"
  value       = module.sql.server_fqdn
}

output "key_vault_uri" {
  description = "Azure Key Vault URI"
  value       = module.keyvault.key_vault_uri
}

output "next_steps" {
  description = "Manual steps required after terraform apply"
  value       = <<-EOT
    ╔══════════════════════════════════════════════════════════╗
    ║  NEXT STEPS after terraform apply                       ║
    ╠══════════════════════════════════════════════════════════╣
    ║ 1. Log into Databricks: ${module.databricks.workspace_url}
    ║ 2. Create a Personal Access Token (User Settings → Access Tokens)
    ║ 3. Store it: az keyvault secret set \
    ║      --vault-name <kv-name> \
    ║      --name databricks-token \
    ║      --value <your-pat>
    ║ 4. Configure Databricks CLI:
    ║      databricks configure --host ${module.databricks.workspace_url}
    ║ 5. Deploy ETL bundle:
    ║      databricks bundle deploy --target dev
    ║ 6. Run OLTP seed SQL against: ${module.sql.server_fqdn}
    ╚══════════════════════════════════════════════════════════╝
  EOT
}
