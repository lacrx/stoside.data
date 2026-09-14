variable "region" {
  default = "us-east-1"
}

variable "project" {
  default = "newsletter"
}

variable "allowed_lists" {
  description = "Comma-separated list IDs that the API accepts"
  default     = "stoside,ncyimby"
}

variable "from_email" {
  description = "Verified SES sender address"
  default     = "newsletter@strongtownsoside.org"
}

variable "allowed_origins" {
  description = "CORS allowed origins"
  default     = "https://strongtownsoside.org,https://ncyimby.org,http://localhost:8000,http://localhost:9000"
}
