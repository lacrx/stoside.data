terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket  = "stoside-terraform-state"
    key     = "data/terraform.tfstate"
    region  = "us-east-1"
    profile = "civic"
  }
}

provider "aws" {
  region  = var.region
  profile = "civic"
}

# For CloudFront ACM cert (must be us-east-1)
provider "aws" {
  alias   = "us_east_1"
  region  = "us-east-1"
  profile = "civic"
}
