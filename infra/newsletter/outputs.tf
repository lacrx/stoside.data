output "api_url" {
  description = "API Gateway endpoint for the newsletter service"
  value       = aws_apigatewayv2_api.newsletter.api_endpoint
}

output "table_name" {
  value = aws_dynamodb_table.subscribers.name
}

output "ses_verification_token" {
  description = "Add this as a TXT record to verify the domain with SES"
  value       = aws_ses_domain_identity.main.verification_token
}

output "ses_dkim_tokens" {
  description = "Add these as CNAME records for DKIM signing"
  value       = aws_ses_domain_dkim.main.dkim_tokens
}
