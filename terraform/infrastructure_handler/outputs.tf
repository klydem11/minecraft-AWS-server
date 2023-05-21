########################
#         EIP          #
########################
output "eip" {
  value = aws_eip.mc_server_eip.public_ip
}

output "aws_account_id" {
  description = "The AWS Account ID"
  value       = data.aws_caller_identity.aws.account_id
}

output "vpc_id" {
  description = "The VPC ID"
  value       = local.vpc_id
}

output "subnet_id" {
  description = "The Subnet ID"
  value       = local.subnet_id
}

output "mc_server_eip_allocation_id" {
  description = "The EIP Allocation ID for the Minecraft server"
  value       = aws_eip.mc_server_eip.id
}

########################
#        Lambda        #
########################
output "lambda_function_arn" {
  description = "The ARN of the Lambda function"
  value       = aws_lambda_function.lambda_function.arn
}

output "iam_role_arn" {
  description = "The ARN of the IAM role for Lambda"
  value       = aws_iam_role.iam_for_lambda.arn
}

output "iam_policy_arn" {
  description = "The ARN of the IAM policy for Lambda to access SSM Parameter Store"
  value       = aws_iam_policy.ssm_access.arn
}

########################
#     API Gateway      #
########################
output "api_gateway_url" {
  value = aws_apigatewayv2_api.minecraft_http_api.api_endpoint
}
########################
#         ECR          #
########################
output "ecr_repository_url" {
  value = aws_ecr_repository.mc_repository.repository_url
}

output "ecr_repository_name" {
  value = aws_ecr_repository.mc_repository.name
}