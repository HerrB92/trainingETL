output "server_fqdn" {
  value = azurerm_mssql_server.main.fully_qualified_domain_name
}
output "server_name" {
  value = azurerm_mssql_server.main.name
}
output "database_name" {
  value = azurerm_mssql_database.oltp.name
}
output "jdbc_url" {
  description = "JDBC connection URL for PySpark"
  value       = "jdbc:sqlserver://${azurerm_mssql_server.main.fully_qualified_domain_name}:1433;database=${azurerm_mssql_database.oltp.name};encrypt=true;trustServerCertificate=false"
}
