
########################
#       Labels         #
########################
module "label" {
  source   = "cloudposse/label/null"
  version = "0.25.0"

  namespace   = var.namespace
  stage       = var.environment
  name        = var.name
  delimiter   = "-"
  label_order = ["environment", "stage", "name", "attributes"]
  tags        = merge(var.tags, local.tf_tags)
}

########################
#     EC2 Instance     #
########################
// Get latest Ubuntu 22.04AMI
data "aws_ami" "ubuntu" {
  most_recent      = true
  owners           = ["099720109477"]

  filter {
    name   = "name"
    values = [ var.ami ]
  }

  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
      name   = "architecture"
      values = ["x86_64"]
  }
}

module "ec2_instance" {
  source  = "terraform-aws-modules/ec2-instance/aws"
  version = "~> 3.0"

  name = "${var.name}-public"

  # Spot Instance
  # create_spot_instance = true
  # spot_price           = "0.60"
  # spot_type            = "persistent"

  # Instance
  ami                    = data.aws_ami.ubuntu.image_id
  instance_type          = var.instance_type
  key_name               = var.instance_keypair

  # Instance Profile
  iam_instance_profile = aws_iam_instance_profile.mc.name

  # Network
  vpc_security_group_ids = [ aws_security_group.minecraft_SG.id ]
  subnet_id              = local.subnet_id
  
  # Monitoring
  monitoring             = true

  // Pre-req install Script
  # user_data = file("scripts/ec2_install.sh")

  tags = module.label.tags
}

// Set-up Ec2 Pre-reqs
resource "null_resource" "setup_ec2" {
  depends_on = [ module.ec2_instance ]

  provisioner "file" {
    source      = "./scripts/ec2_install.sh"
    destination = "/home/ubuntu/ec2_install.sh"

    connection {
      type        = "ssh"
      user        = "ubuntu"
      private_key = "${file("./private-key/terraform-key.pem")}"
      host        = module.ec2_instance.public_dns
    }
  }

  provisioner "file" {
    source      = "./scripts/prepare_ec2_env.sh"
    destination = "/home/ubuntu/prepare_ec2_env.sh"

    connection {
      type        = "ssh"
      user        = "ubuntu"
      private_key = "${file("./private-key/terraform-key.pem")}"
      host        = module.ec2_instance.public_dns
    }
  }

  provisioner "remote-exec" {
    inline = [
      "#!/bin/bash",
      "mkdir -p /home/ubuntu/setup/scripts /home/ubuntu/setup/logs",
      "mv /home/ubuntu/ec2_install.sh /home/ubuntu/setup/scripts",
      "mv /home/ubuntu/prepare_ec2_env.sh /home/ubuntu/setup/scripts",
      "chmod +x /home/ubuntu/setup/scripts/ec2_install.sh",
      "sudo /home/ubuntu/setup/scripts/ec2_install.sh > /home/ubuntu/setup/logs/install.log",
      "aws ssm get-parameter --name \"${var.git_private_key_name}\" --with-decryption --region \"${var.aws_region}\" --query \"Parameter.Value\" --output text > ~/.ssh/id_rsa",
      "chmod 600 ~/.ssh/id_rsa",
      "ssh-keyscan github.com >> ~/.ssh/known_hosts",
      "chmod +x /home/ubuntu/setup/scripts/prepare_ec2_env.sh",
      "sudo /home/ubuntu/setup/scripts/prepare_ec2_env.sh > /home/ubuntu/setup/logs/prepare_ec2_env.log"
    ]

    connection {
      type        = "ssh"
      user        = "ubuntu"
      private_key = "${file("./private-key/terraform-key.pem")}"
      host        = module.ec2_instance.public_dns
    }
  }
}

// Ec2 before destroy 
resource "null_resource" "post_mc_server_close" {
  depends_on = [ module.ec2_instance ]

  triggers = {
    # Every time you run terraform apply or terraform destroy, 
    # the timestamp will be different, causing the null_resource to be recreated
    before_destroy_timestamp = timestamp()
  }

  provisioner "local-exec" {
    when    = destroy # Only execute on destruction of resource
    command = <<-EOT
      ssh -i ./private-key/terraform-key.pem -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ubuntu@$(terraform output -raw public_ip) \
      sudo chmod +x /home/ubuntu/minecraft-tf-AWS-server/terraform-manifests/scripts/post_mc_server_shutdown.sh \
      cp /home/ubuntu/setup/logs/* /home/ubuntu/minecraft-tf-AWS-server/minecraft-data/minecraft-world/logs \
      sudo /home/ubuntu/minecraft-tf-AWS-server/terraform-manifests/scripts/post_mc_server_shutdown.sh > /home/ubuntu/minecraft-tf-AWS-server/minecraft-data/minecraft-world/logs/post_mc_server_shutdown.log
    EOT
  }
}

########################
#   Security Groups    #
########################
resource "aws_security_group" "minecraft_SG" {
  name        = "${var.name}-sg"
  description = "Minecraft Security Group Allow SSH and TCP"
  vpc_id      = local.vpc_id // default VPC

  # Ingress rule for SSH
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    description = "SSH"
    cidr_blocks = [ var.allowed_cidrs ]
  }

  # Ingress rule for Minecraft server
  ingress {
    description      = "Minecraft Server"
    from_port        = var.mc_port
    to_port          = var.mc_port
    protocol         = "tcp"
    cidr_blocks      = [ var.allowed_cidrs ]
  }

  // Allow all outgoing traffic without any restrictions
  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = module.label.tags
}

########################
#       S3 Bucket      #
########################
resource "random_string" "unique_bucket_suffix" {
  length  = 8
  special = false
  upper   = false
  numeric  = false
}

locals {
  bucket_name = "${var.name}-s3-${random_string.unique_bucket_suffix.result}"
}

resource "aws_s3_bucket" "mc_s3" {
  bucket = local.bucket_name
  # acl    = "private"

  force_destroy = var.bucket_force_destroy
  
  # versioning = {
  #   enabled = false
  # }

  tags = module.label.tags
}

resource "aws_s3_bucket_public_access_block" "mc_s3_public_access_block" {
  bucket = aws_s3_bucket.mc_s3.id

  # S3 bucket-level Public Access Block configuration
  block_public_acls       = true # blocks the creation or modification of any new public ACLs on the bucket
  block_public_policy     = true # blocks the creation or modification of any new public bucket policies
  ignore_public_acls      = true # instructs Amazon S3 to ignore all public ACLs associated with the bucket and its objects
  restrict_public_buckets = true # restricts access to the bucket and its objects to only AWS services and authorized users
}

resource "aws_s3_bucket_ownership_controls" "mc_s3_ownership_control" {
  bucket = aws_s3_bucket.mc_s3.id
  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_acl" "mc_s3_acl" {
  depends_on = [aws_s3_bucket_ownership_controls.mc_s3_ownership_control]

  bucket = aws_s3_bucket.mc_s3.id
  acl    = "private"
}