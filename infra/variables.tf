variable "region" {
  default = "us-east-1"
}

variable "project" {
  default = "civic-data"
}

variable "data_bucket_name" {
  default = "stoside-data"
}

variable "domain_name" {
  description = "Custom domain for CloudFront (leave empty to use CloudFront default domain)"
  default     = ""
}
