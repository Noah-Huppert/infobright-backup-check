#!/usr/bin/env python3

import sys
import logging
import argparse
import os
import os.path
import hashlib
import subprocess
import json
from typing import Dict, List

from git import Repo
import boto3
import inflection

# Path constants (All relative)
repo_dir = '../'  # Path to Git repository root
src_dir = repo_dir + 'ib_backup/'  # Path to source directory

pipfile_path = src_dir + 'Pipfile.lock'  # File which contains exact versions and hashes of all 3rd party dependencies

lib_dir = src_dir + 'lib'  # Directory containing common code between lambdas

cf_stack_path = 'stack.template'  # Path to CloudFormation stack template

DEV_PROD_SUBNET_ID = 'subnet-f16e3daa'  # Id of subnet in development & production with access to the development
# Salt master
DEV_PROD_SECURITY_GROUP_ID = 'sg-c9210cb6'  # Id of security group in development & product with access to the
# development Salt master

SAND_SUBNET_ID = 'subnet-dfc16bf1'  # Id of subnet in the sandbox with access to the salt master, this is just a
# dummy value because there is no functioning salt master in the sandbox
SAND_SECURITY_GROUP_ID = 'sg-b66e74fd'  # Id of security group in the sandbox with access to the salt master, this is
# just a dummy value because there is no functioning salt master in the sandbox

# Step constants
# Names of process steps
steps = ['step_create_volume', 'step_wait_volume_created', 'step_attach_volume', 'step_wait_volume_attached',
         'step_test_backup']


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
    env_dependant_placeholder = '<depends on --env>'

    parser = argparse.ArgumentParser(description="Deploy script")
    parser.add_argument('--stages',
                        help="Which deploy stages to run. The 'upload' stage builds and uploads lambda function " +
                             "deployment artifacts. The 'deploy' stage deploys a CloudFormation template for the " +
                             "lambda function",
                        choices=['upload', 'deploy'],
                        action='append')
    parser.add_argument('--artifact-s3-keys',
                        help="(Required if only stage is 'deploy') String representing JSON object which holds " +
                             "locations of step build artifacts in S3. Object keys are step " +
                             "names (Names: {}), all step names must be provided. Object ".format(", ".join(steps)) +
                             "values are AWS S3 keys to step build artifacts in the specified code bucket.")
    parser.add_argument('--save-artifact-s3-keys',
                        help="(Optional when stage is 'upload') File to save step artifact S3 locations. Saved in " +
                             "JSON format described by --artifact-s3-keys help")
    parser.add_argument('--aws-profile',
                        help="(Required by all stages) AWS credential profile")
    parser.add_argument('--env',
                        choices=['sand', 'dev', 'prod'],
                        default='dev',
                        help="(Required by all stages) Environment stack is being deployed to")
    parser.add_argument('--stack-name',
                        help="(Required by all stages) Base name of CloudFormation stack to deploy, " +
                        "will be prefixed with the environment",
                        default='ib-backup')
    parser.add_argument('--code-bucket',
                        help="(Required by all stages) S3 bucket to upload code into",
                        default=env_dependant_placeholder)
    parser.add_argument('--save-code-bucket',
                        help="(Optional when stage is 'upload') File to save the name of the S3 code bucket")
    parser.add_argument('--subnet-id',
                        help="(Required by 'deploy' stage) Id of subnet which has access to the development " +
                             "Salt master",
                        default=env_dependant_placeholder)
    parser.add_argument('--security-group-id',
                        help="(Required by 'deploy' stage) Id of security group which has access to the development " +
                             "Salt master",
                        default=env_dependant_placeholder)
    parser.add_argument('--salt-api-user',
                        help="(Required by 'deploy' stage) Salt API user")
    parser.add_argument('--salt-api-password',
                        help="(Required by 'deploy' state) Salt API password")
    args = parser.parse_args()

    # Set default --code-bucket depending on --env
    if args.code_bucket == env_dependant_placeholder:
        if args.env == 'sand':
            args.code_bucket = 'amino-sandbox-repo'
        else:
            args.code_bucket = 'repo.code418.net'

    # Set default --subnet-id depending on --env
    if args.subnet_id == env_dependant_placeholder:
        if args.env in 'sand':
            args.subnet_id = SAND_SUBNET_ID
        else:
            args.subnet_id = DEV_PROD_SUBNET_ID

    # Set default --security-group-id depending on --env
    if args.security_group_id == env_dependant_placeholder:
        if args.security_group_id in 'sand':
            args.security_group_id = SAND_SECURITY_GROUP_ID
        else:
            args.security_group_id = DEV_PROD_SECURITY_GROUP_ID

    # Set --stages argument to default if not provided
    if not args.stages:
        args.stages = ['upload', 'stages']

    # Check --artifact-s3-keys if --stages == ['deploy']
    artifact_s3_keys = None
    if args.stages == ['deploy']:
        # If empty
        if not args.artifact_s3_keys:
            raise ValueError("--artifact-s3-keys must be provided if 'deploy' is the only stage passed via the " +
                             "--stages argument")

        # Try deserializing
        try:
            artifact_s3_keys = json.loads(args.artifact_s3_keys)
        except Exception as e:
            logger.error("Error parsing --artifact-s3-keys argument as JSON")
            raise e

        # Check is dict
        if type(artifact_s3_keys) != dict:
            raise ValueError("--artifact-s3-keys must deserialize to type dict, was: {}".format(type(artifact_s3_keys)))

        # Check each step is present
        expected_steps = set(steps)
        actual_steps = set(artifact_s3_keys)

        if expected_steps != actual_steps:
            raise ValueError("--artifact-s3-keys must contain a key for each step, expected keys: {}, actual keys: {}"
                             .format(expected_steps, actual_steps))
    else:
        # If --stages != ['deploy'] notify user that argument will not do anything
        if args.artifact_s3_keys:
            raise ValueError("--artifact-s3-keys argument provided but --stages != ['deploy'], --artifact-s3-keys " +
                             "values will not be used")

    # Check if --save-artifact-s3-keys is provided and 'upload' not in --stages
    if 'upload' not in args.stages and args.save_artifact_s3_keys:
        raise ValueError("--save-artifact-s3-keys argument provided but 'upload' not in --stages, " +
                         "--save-artifact-s3-keys value will not be used")

    # Check --salt-api-{user,password} arguments provided id 'deploy' in --stages
    if 'deploy' in args.stages:
        if not args.salt_api_user:
            raise ValueError("--salt-api-user argument must be provided when 'deploy' in --stages")

        if not args.salt_api_password:
            raise ValueError("--salt-api-password argument must be provided when 'deploy' in --stages")

    # Print configuration
    printed_args = dict(args).copy()

    if args.salt_api_password:
        # Redact
        printed_args.salt_api_password = '[REDACTED]'

    logger.debug("Configuration: {}".format(printed_args))

    # AWS clients
    aws_profile_args = {}

    if args.aws_profile is not None:
        aws_profile_args['profile_name'] = args.aws_profile

    aws_profile = boto3.session.Session(**aws_profile_args)

    s3 = aws_profile.client('s3')

    # Stack name
    stack_name = "{}-{}".format(args.env, args.stack_name)

    if 'upload' in args.stages:
        logger.debug("Running upload stage")

        # Build artifacts
        artifact_names = build_artifacts(logger)

        logger.debug("Built artifacts, locations={}".format(artifact_names))

        # Upload artifacts
        artifact_s3_keys = upload_artifacts(logger=logger, s3=s3, artifact_names=artifact_names, stack_name=stack_name,
                                            code_bucket=args.code_bucket, env=args.env)

        logger.debug("Uploaded artifacts, locations={}".format(artifact_s3_keys))

        # Save code_bucket if --save-code-bucket is provided
        if args.save_code_bucket:
            with open(repo_dir + args.save_code_bucket, 'w') as f:
                f.write(args.code_bucket)

            logger.debug("Saved code bucket to \"{}\"".format(args.code_bucket))

        # Save artifact_s3_keys if --save-artifact-s3-keys is provided
        if args.save_artifact_s3_keys:
            with open(repo_dir + args.save_artifact_s3_keys, 'w') as f:
                json.dump(artifact_s3_keys, f)

            logger.debug("Saved artifact upload locations to \"{}\"".format(args.save_artifact_s3_keys))

    if 'deploy' in args.stages:
        logger.debug("Running deploy stage")

        # Deploy CloudFormation stack
        deploy_cloudformation_stack(logger=logger, artifact_s3_keys=artifact_s3_keys, env=args.env,
                                    stack_name=stack_name, code_bucket=args.code_bucket, subnet_id=args.subnet_id,
                                    security_group_id=args.security_group_id, salt_api_user=args.salt_api_user,
                                    salt_api_password=args.salt_api_password, aws_profile=args.aws_profile)

        logger.debug("Ran deploy")

    return 0


def deploy_cloudformation_stack(logger: logging.Logger, artifact_s3_keys: Dict[str, str], env: str,
                                stack_name: str, code_bucket: str, subnet_id: str, security_group_id: str,
                                salt_api_user: str, salt_api_password, aws_profile: str = None):
    """ Deploys a CloudFormation stack
    Args:
        - logger
        - artifact_s3_keys: Location of all lambda deployment artifacts in S3, output of upload_artifacts()
        - env: Name of environment stack is being deployed to
        - stack_name: Name of CloudFormation stack to deploy
        - code_bucket: Name of bucket Lambda deployment artifacts were stored in
        - subnet_id: Id of subnet which has access to the development Salt master
        - security_group_id: Id of security group which has access to the development Salt master
        - aws_profile: Name of aws credentials profile, None if default credentials should be used
    """
    # Assemble deploy command arguments
    args = ['cloudformation', 'deploy', '--stack-name', stack_name, '--template-file', cf_stack_path,
            '--capabilities', 'CAPABILITY_NAMED_IAM', '--parameter-overrides']

    # Define CloudFormation parameters values
    param_overrides = {
        'Environment': env,
        'StepLambdaCodeBucket': code_bucket,
        'SaltAPIUser': salt_api_user,
        'SaltAPIPassword': salt_api_password,
        'SaltDevSubnetId': subnet_id,
        'SaltDevSecurityGroupId': security_group_id
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
        logger.info("NOTE: Displaying Stack events below, these may not contain the problem, please look for any " +
                    "errors in the output above")

        args = ['cloudformation', 'describe-stack-events', '--stack-name', stack_name]

        exec_aws(args, aws_profile)
    else:
        logger.info("Deployed CloudFormation stack")


def exec_aws(cmd_args: List[str], aws_profile: str = None) -> subprocess.CompletedProcess:
    """ Executes an AWS CLI command
    Args:
        - cmd_args: AWS command arguments
        - aws_profile: AWS credentials profile to execute command with

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
                     code_bucket: str, env: str) -> Dict[str, str]:
    """ Uploads step artifacts to S3
    Args:
        - logger
        - s3: AWS S3 API client
        - artifact_names: Paths to artifacts on system, output of build_artifacts()
        - stack_name: Name of CloudFormation stack, used to determine where artifacts are uploaded in s3
        - code_bucket: Bucket to upload artifacts into
        - env: Name of deployment environment

    Returns:
        - S3 keys for step artifacts
            - Dict keys are step names
            - Dict valuess are S3 keys
    """
    s3_keys = {}

    logger.info("Uploading step artifacts")

    # Upload artifacts
    for step_name in artifact_names:
        # Compute S3 key name
        file_path = artifact_names[step_name]
        file_name = os.path.basename(file_path)

        upload_parent_dir = 'snapshot'
        if env == 'prod':
            upload_parent_dir = 'release'

        s3_key = "{}/lambdas/{}/{}".format(upload_parent_dir, stack_name, file_name)
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

    Returns:
        - Dict of step artifact locations on disk
            - Dict keys are step names
            - Dict values are zip file paths
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
