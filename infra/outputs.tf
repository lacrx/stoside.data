output "cloudfront_domain" {
  value = aws_cloudfront_distribution.data.domain_name
}

output "cloudfront_url" {
  value = "https://${aws_cloudfront_distribution.data.domain_name}"
}

output "api_gateway_url" {
  value = aws_apigatewayv2_api.query.api_endpoint
}

output "s3_bucket" {
  value = aws_s3_bucket.data.bucket
}
