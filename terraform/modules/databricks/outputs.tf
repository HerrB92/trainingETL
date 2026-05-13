output "workspace_url" {
  value = "https://${azurerm_databricks_workspace.main.workspace_url}"
}
output "workspace_id" {
  value = azurerm_databricks_workspace.main.workspace_id
}
output "cluster_id" {
  value = databricks_cluster.dev.cluster_id
}
output "sql_warehouse_id" {
  value = databricks_sql_endpoint.main.id
}
output "secret_scope_name" {
  value = databricks_secret_scope.keyvault.name
}
