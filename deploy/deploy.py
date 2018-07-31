#!/usr/bin/env python3

import sys
import logging
import argparse
import os
import os.path
import hashlib
import zipfile
import subprocess
from typing import Dict, List

from git import Repo
import boto3
import inflection

# Path constants (All relative)
repo_dir = '../../'  # Path to Git repository root
src_dir = repo_dir + 'ib-backup/ib_backup/'  # Path to source directory

pipfile_path = src_dir + 'Pipfile.lock'  # File which contains exact versions and hashes of all 3rd party dependencies

lib_dir = src_dir + 'lib'  # Directory containing common code between lambdas

cf_stack_path = 'stack.template'  # Path to CloudFormation stack template

# Step constants
steps = [ 'step_create_volume', 'step_wait_volume_created' ]  # Names of process steps


def main() -> int:
    """ Entry point
    Return: Exit code
    """
    # Setup logger
    logger = logging.getLogger('deploy')

    logger.setLevel(logging.DEBUG)

    hndlr = logging.StreamHandler(sys.stdout)
    hndlr.setFormatter(logging.Formatter("%(name)s [%(levelname)s] %(message)s"))

    logger.addHandler(hndlr)

    # Parse arguments
    parser = argparse.ArgumentParser(description="Deploy script")
    parser.add_argument('--aws-profile',
                        help="AWS credential profile")
    parser.add_argument('--env',
                        choices=['sand', 'dev', 'prod'],
                        default='dev',
                        help="Environment stack is being deployed to")
    parser.add_argument('--stack-name',
                        help="Name of CloudFormation stack to deploy",
                        default='ib-backup')
    parser.add_argument('--code-bucket',
                        help="S3 bucket to upload code into",
                        default='amino-sandbox-repo')
    args = parser.parse_args()

    # AWS clients
    aws_profile_args = {}

    if args.aws_profile is not None:
        aws_profile_args['profile_name'] = args.aws_profile

    aws_profile = boto3.session.Session(**aws_profile_args)

    s3 = aws_profile.client('s3')


    # Build artifacts
    artifact_names = build_artifacts(logger)

    # Upload artifacts
    artifact_s3_keys = upload_artifacts(logger=logger, s3=s3, artifact_names=artifact_names, stack_name=args.stack_name,
                                         code_bucket=args.code_bucket)

    # Deploy CloudFormation stack
    deploy_cloudformation_stack(logger=logger, artifact_s3_keys=artifact_s3_keys, env=args.env,
                                stack_name=args.stack_name, code_bucket=args.code_bucket, aws_profile=args.aws_profile)

    return 0


def deploy_cloudformation_stack(logger: logging.Logger, artifact_s3_keys: Dict[str, str], env: str,
                                stack_name: str, code_bucket: str, aws_profile: str = None):
    """ Deploys a CloudFormation stack
    Args:
        - logger
        - artifact_s3_keys: Location of all lambda deployment artifacts in S3, output of upload_artifacts()
        - env: Name of environment stack is being deployed to
        - stack_name: Name of CloudFormation stack to deploy
        - code_bucket: Name of bucket Lambda deployment artifacts were stored in
        - aws_profile: Name of aws credentials profile, None if default credentials should be used
    """
    # Assemble deploy command arguments
    args = ['cloudformation', 'deploy', '--stack-name', stack_name, '--template-file', cf_stack_path,
                 '--capabilities', 'CAPABILITY_NAMED_IAM', '--parameter-overrides']

    # Define CloudFormation parameters values
    param_overrides = {
        'Environment': env,
        'ProcessName': stack_name,
        'StepLambdaCodeBucket': code_bucket
    }

    # ... For each step find the key the lambda deployment artifact was uploaded to S3 under
    #     Set the appropriate CloudFormation parameter to this key so the stack knows where to get the Lambda's code
    for step_name in artifact_s3_keys:
        s3_key = artifact_s3_keys[step_name]
        camel_step_name = inflection.camelize(step_name)

        param_overrides["{}CodeKey".format(camel_step_name)] = s3_key

    # ... If Salt API user information is present in the environment provide these parameters as well
    salt_api_user = os.environ.get('SALT_API_USER')
    salt_api_password = os.environ.get('SALT_API_PASSWORD')

    if salt_api_user is not None:
        param_overrides['SaltAPIUser'] = salt_api_user

    if salt_api_password is not None:
        param_overrides['SaltAPIPassword'] = salt_api_password

    # Assemble param_overrides dict into command line arguments to be passed to the CloudFormation deploy command
    for param_key in param_overrides:
        args.append("{}={}".format(param_key, param_overrides[param_key]))

    # Run deploy command
    logger.info("Deploying CloudFormation stack")

    run_res = exec_aws(args, aws_profile)

    # Check if deploy successful
    if run_res.returncode != 0:
        # If not successful display events
        logger.info("Failed to deploy CloudFormation stack")

        args = ['cloudformation', 'describe-stack-events', '--stack-name', stack_name]

        exec_aws(args, aws_profile)
    else:
        logger.info("Deployed CloudFormation stack")


def exec_aws(cmd_args: List[str], aws_profile: str = None) -> subprocess.CompletedProcess:
    """ Executes an AWS CLI command
    Args:
        - cmd_args: AWS command arguments

    Returns: Command result
    """
    args = ['aws']

    # If custom aws profile specified
    if aws_profile is not None:
        args.extend(['--profile', aws_profile])

    # Execute
    args.extend(cmd_args)
    return subprocess.run(args)


def upload_artifacts(logger: logging.Logger, s3, artifact_names: Dict[str, str], stack_name: str,
                     code_bucket: str) -> Dict[str, str]:
    """ Uploads step artifacts to S3
    Args:
        - logger
        - s3: AWS S3 API client
        - artifact_names: Paths to artifacts on system, output of build_artifacts()

    Returns:
        - S3 keys step artifacts are uploaded under
    """
    s3_keys = {}

    logger.info("Uploading step artifacts")

    # Upload artifacts
    for step_name in artifact_names:
        # Compute S3 key name
        file_path = artifact_names[step_name]
        file_name = os.path.basename(file_path)

        s3_key = "release/lambdas/{}/{}".format(stack_name, file_name)
        s3_uri = "s3://{}/{}".format(code_bucket, s3_key)

        s3_keys[step_name] = s3_key

        # Check if already uploaded
        ls_resp = s3.list_objects_v2(Bucket=code_bucket, Prefix=s3_key)

        if 'Contents' in ls_resp and len(ls_resp['Contents']) > 0:
            logger.info("    {}: Already uploaded to {}".format(step_name, s3_uri))
            continue

        # Upload if not already
        s3.upload_file(file_path, code_bucket, s3_key)
        logger.info("    {}: Uploaded to {}".format(step_name, s3_uri))

    return s3_keys


def build_artifacts(logger: logging.Logger) -> Dict[str, str]:
    """ Builds all lambda deployment artifacts
    Args:
        - logger

    Returns: Dict of step artifact locations
    """
    git_head_sha = get_git_head_sha()[0:7]

    logger.info("Installing dependencies")
    subprocess.run(['pipenv', 'install'], cwd=src_dir, stdout=subprocess.PIPE)

    logger.info("Building step artifacts")

    artifact_names = {}

    for step_name in steps:
        # Assemble step artifact name
        checksum = compute_checksum(step_name)

        artifact_out = "/tmp/{}-git-{}-checksum-{}.zip".format(step_name, git_head_sha, checksum)

        artifact_names[step_name] = artifact_out

        # Check if artifact already exists
        if os.path.isfile(artifact_out):
            logger.info("    {}: Already exists at {}".format(step_name, artifact_out))
            continue

        # Create zip file
        subprocess.run(['zip', '-r', artifact_out, 'lib', "{}.py".format(step_name)],
                       cwd=src_dir, stdout=subprocess.PIPE)
        subprocess.run(['zip', '-r', artifact_out, '.'], cwd=get_venv_lib_dir(), stdout=subprocess.PIPE)

        logger.info("    {}: Built to {}".format(step_name, artifact_out))

    return artifact_names


def compute_checksum(step_name: str) -> str:
    """ Computes the checksum of the following source files: step src file, lib directory, Pipfile.lock
    Args:
        - step_name: Name of step

    Returns: Checksum of step source files
    """
    # Get file paths to hash
    hash_files = [pipfile_path]

    hash_files.append(os.path.abspath(os.path.join(src_dir, "{}.py".format(step_name))))

    for root, dirs, files in os.walk(lib_dir):
        for file in files:
            hash_files.append(os.path.join(root, file))

    # Hash
    hash_md5 = hashlib.md5()

    for file_path in hash_files:
        with open(file_path, 'rb') as file:
            hash_md5.update(file.read())

    return hash_md5.hexdigest()


def get_venv_lib_dir() -> str:
    venv_find_call = subprocess.run(['pipenv', '--venv'], cwd=src_dir, stdout=subprocess.PIPE)
    venv_dir = venv_find_call.stdout.strip().decode()

    return os.path.abspath(os.path.join(venv_dir, 'lib/python3.6/site-packages'))

def get_git_head_sha() -> str:
    """ Get Git repo HEAD sha
    Returns: Git repo HEAD sha
    """
    repo = Repo(repo_dir)
    return repo.head.commit.hexsha

if __name__ == '__main__':
    sys.exit(main())
