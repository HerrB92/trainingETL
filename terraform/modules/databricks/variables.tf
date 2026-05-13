variable "prefix" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "storage_account_name" { type = string }
variable "storage_account_key" {
  type      = string
  sensitive = true
}
variable "key_vault_id" { type = string }
variable "key_vault_uri" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}
