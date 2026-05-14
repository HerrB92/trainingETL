variable "prefix" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "storage_account_name" { type = string }
variable "storage_account_key" {
  type      = string
  sensitive = true
}
variable "tags" {
  type    = map(string)
  default = {}
}
variable "phase2" {
  description = "Set to true once databricks_host and databricks_pat_token are filled in"
  type        = bool
  default     = false
}

