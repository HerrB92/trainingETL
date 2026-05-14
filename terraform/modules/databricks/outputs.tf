output "workspace_url" {
  value = "https://${azurerm_databricks_workspace.main.workspace_url}"
}
output "workspace_id" {
  value = azurerm_databricks_workspace.main.workspace_id
}
output "cluster_id" {
  value = null
}
output "sql_warehouse_id" {
  value = var.phase2 ? databricks_sql_endpoint.main[0].id : null
}
output "secret_scope_name" {
  value = var.phase2 ? databricks_secret_scope.main[0].name : null
}
