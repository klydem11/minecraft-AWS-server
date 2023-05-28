import boto3
import os
import shutil
import tempfile
import requests
import json
from python_terraform import Terraform
from git import Repo, Actor
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import logging

# Enable detailed boto3 logging
logging.basicConfig(level=logging.DEBUG)

######################################################################
#                           Functions                                #
######################################################################
# Fetch the SSH key from the Parameter Store
def get_ssm_param(param_name):
    ssm_client = boto3.client('ssm', region_name='eu-west-2')

    param = ssm_client.get_parameter(Name=param_name, WithDecryption=True)
    contents = param["Parameter"]["Value"]
        
    return contents

def write_to_tmp_file(content):
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
        temp_file.write(content)
        temp_file.flush() # Ensure any buffered data is written to the file
        dir = temp_file.name
    return dir

def create_private_key(file_name, directory):
    # Generate an RSA key pair
    # - public_exponent: The public exponent (e) is a value used in the RSA algorithm, usually set to 65537
    # - key_size: The size of the key in bits, here set to 2048 bits
    # - backend: The backend used for cryptographic operations, here we use the default_backend
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    # Serialize the private key in PEM format (Privacy-Enhanced Mail, a widely used format for storing and sending cryptographic keys)
    # - encoding: The format used to encode the key, here PEM
    # - format: The format used for the private key, here PKCS8 (Public-Key Cryptography Standards #8)
    # - encryption_algorithm: The algorithm used to encrypt the key, here no encryption is used
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Save the serialized private key to a file named "private_key.pem" with write binary mode
    file_path = os.path.join(directory, file_name)
    with open(file_path, "wb") as f:
        f.write(private_key_pem)

    os.chmod(file_path, 0o400)

    # Return t he directory of the priv key
    return os.path.abspath(file_path)

def get_command():
    ssm_client = boto3.client('ssm', region_name='eu-west-2')
    response = ssm_client.get_parameter(
        Name='BOT_COMMAND',
        WithDecryption=True
    )
    return response['Parameter']['Value']

################################
#         Git Functions        #
################################
def git_clone(repo_url, dir, branch, ssh_key):
    # Set the SSH key environment variable and disable host key checking
    custom_ssh_env = os.environ.copy()
    custom_ssh_env["GIT_SSH_COMMAND"] = f"ssh -v -i {ssh_key} -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"
    
    try:
        repo = Repo.clone_from(repo_url, dir, branch=branch, env=custom_ssh_env)
    except Exception as e:
        raise Exception(f"Git clone failed:\n{str(e)}")
    
    return repo

def git_commit(repo, commit_message, author_name, author_email):
    author = Actor(author_name, author_email)
    repo.git.add(update=True)  # Stage all changes
    repo.index.commit(commit_message, author=author)

def git_push(repo, ssh_key, remote_name="origin", branch="main"):
    # Set the SSH key environment variable and disable host key checking
    custom_ssh_env = os.environ.copy()
    custom_ssh_env["GIT_SSH_COMMAND"] = f"ssh -v -i {ssh_key} -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"
    
    remote = repo.remote(remote_name)

    try:
        with repo.git.custom_environment(GIT_SSH_COMMAND=custom_ssh_env["GIT_SSH_COMMAND"]):
            remote.push(branch)
    except Exception as e:
        raise Exception(f"Git push failed:\n{str(e)}")
    
################################
#     Terraform Functions      #
################################
def terraform_init(tf_obj):
    return_code, stdout, stderr = tf_obj.init(capture_output=True, reconfigure=False)

    if return_code != 0:
        raise Exception(f"Terraform init failed:\n{stderr}")

    return stdout

def terraform_apply(tf_obj):
    return_code, stdout, stderr = tf_obj.apply(skip_plan=True, capture_output=True, auto_approve=True)

    if return_code != 0:
        raise Exception(f"Terraform apply failed:\n{stderr}")

    return stdout

def terraform_destroy(tf_obj):
    return_code, stdout, stderr = tf_obj.destroy(capture_output=True, auto_approve=True)

    if return_code != 0:
        raise Exception(f"Terraform destroy failed:\n{stderr}")

    return stdout

######################################################################
#                       Server Handler                               #
######################################################################
def server_handler(command):
    ssm_client = boto3.client('ssm', region_name='eu-west-2')
    
    ssh_key = get_ssm_param("dark-mango-bot-private-key") # SSH Key name from system manager parameter store
    tf_api_key = get_ssm_param("terraform-cloud-user-api") # terraform cloud api keyget_ssm_param(ssh_key_name))

    # Repo containing terraform manifests and scripts
    tf_manifest_repo = { 
                        "name": "tf_manifests",
                        "url": "git@github.com:Klyde-Moradeyo/minecraft-AWS-server.git", 
                        "branch": "main",
                        "ssh_key": f"{write_to_tmp_file(ssh_key)}",
                        }
    
    tf_manifest_paths = {
                        "tf_mc_infra_manifests": os.path.join(tf_manifest_repo["name"], "terraform", "minecraft_infrastructure"),
                        "tf_private_key_folder": os.path.join(tf_manifest_repo["name"], "terraform", "minecraft_infrastructure", "private-key"),
                        "tf_mc_infra_scripts": os.path.join(tf_manifest_repo["name"], "scripts")
                        }
                          
    
    # Repo contains private key of minceraft ec2 instnace
    # Warn: This is not best practice but due to cost and time it is better to store it here
    #       Not to big of an issue in this case as the keys a short lived
    miscellaneous_repo = { 
                        "name": "miscellaneous",
                        "url": "git@github.com:Klyde-Moradeyo/miscellaneous.git", 
                        "branch": "main",
                        "ssh_key": f"{write_to_tmp_file(ssh_key)}"
                        }
    
    miscellaneous_paths = { 
                        "none": None,
                        }
    
    # print(tf_manifest_repo["ssh_key"])
    git_clone(tf_manifest_repo["url"], tf_manifest_repo["name"], tf_manifest_repo["branch"], tf_manifest_repo["ssh_key"])
    git_clone(miscellaneous_repo["url"], miscellaneous_repo["name"], miscellaneous_repo["branch"], miscellaneous_repo["ssh_key"])

    # Create a Terraform object in minecraft_infrastrucutre dir 
    tf = Terraform(working_dir=tf_manifest_paths["tf_mc_infra_manifests"])
    os.environ['TF_TOKEN_app_terraform_io'] = get_ssm_param(tf_api_key)
    
    if command == "start":
        create_private_key("terraform_key.pem", tf_manifest_paths["tf_private_key_folder"])
        terraform_init(tf)
        # terraform_apply(tf)
        print("x is positive")
    elif command == "stop":
        terraform_init(tf)
        # terraform_destroy(tf)
    else:
        print("error command not found")
        
if __name__ == "__main__":
    print(requests.get('http://169.254.170.2/v2/metadata').json())
    response = ssm_client.get_parameter(Name='/BOT_COMMAND', WithDecryption=True)
    print(f"response {response}")
    job = get_command()
    server_handler(job)
