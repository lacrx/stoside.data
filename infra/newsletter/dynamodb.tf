resource "aws_dynamodb_table" "subscribers" {
  name         = "${var.project}-subscribers"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "list_id"
  range_key    = "email"

  attribute {
    name = "list_id"
    type = "S"
  }

  attribute {
    name = "email"
    type = "S"
  }

  attribute {
    name = "unsubscribe_token"
    type = "S"
  }

  global_secondary_index {
    name            = "token-index"
    hash_key        = "unsubscribe_token"
    projection_type = "ALL"
  }
}
