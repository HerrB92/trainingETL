output "account_name" {
  value = azurerm_storage_account.adls.name
}
output "primary_access_key" {
  value     = azurerm_storage_account.adls.primary_access_key
  sensitive = true
}
output "account_id" {
  value = azurerm_storage_account.adls.id
}
output "dfs_endpoint" {
  description = "DFS endpoint for abfss:// URLs"
  value       = azurerm_storage_account.adls.primary_dfs_endpoint
}
