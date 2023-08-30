########################
#   Instance Profile   #
########################
# Used to pass the role information to an EC2 instance
resource "aws_iam_instance_profile" "mc" {
  name = "${var.label_id}-instance-profile"
  role = aws_iam_role.allow_ec2.name
}

########################
#    IAM Role for      #
#     Ec2 Instance     #
########################
resource "aws_iam_role" "allow_ec2" {
  name   = "${var.label_id}-allow-ec2"
  assume_role_policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Action": "sts:AssumeRole",
        "Principal": {
          "Service": "ec2.amazonaws.com"
        },
        "Effect": "Allow",
        "Sid": ""
      }
    ]
  })
}

########################
#    IAM Role for      #
#   Ec2 to S3 acces    #
########################
# The policy grants permissions to list the specified S3 bucket and 
# to perform put, get, and delete actions on objects within the bucket.
resource "aws_iam_role_policy" "mc_allow_ec2_to_s3" {
  name   = "${var.label_id}-allow-ec2-to-s3"
  role   = aws_iam_role.allow_ec2.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = ["${var.mc_s3_bucket_arn}"]
      },
      {
        Effect   = "Allow"
        Action   = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
        ]
        Resource = ["${var.mc_s3_bucket_arn}/*"]
      },
    ]
  })
}

########################
#       IAM Role       #
#      for Ec2 to      #
#    Systems Manager   #
########################
resource "aws_iam_role_policy" "mc_allow_ec2_to_asm" {
  name   = "${var.label_id}-allow-ec2-to-asm"
  role   = aws_iam_role.allow_ec2.id
  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid" = "",
            "Effect" = "Allow",
            "Action" = [ 
              "ssm:GetParameter",
            ]
            "Resource"=  [ 
              "arn:aws:ssm:*:847399026905:parameter/${var.git_private_key_name}",
            ]
        }
    ]
  })
}