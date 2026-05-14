variable "prefix" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "tenant_id" { type = string }
variable "admin_object_id" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}
variable "secrets" {
  description = "Map of secret name → value to store in Key Vault"
  type        = map(string)
  # NOT marked sensitive at the variable level: Terraform can't use a fully-sensitive
  # map as for_each keys (keys would be exposed in state anyway as resource addresses).
  # Individual values that are sensitive (e.g. storage key) remain marked sensitive
  # by their source output; they are still redacted in plan/apply output.
  default = {}
}
