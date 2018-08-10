import os
from typing import Dict

import lib.job
import lib.steps
import lib.salt


class TestBackupJob(lib.job.Job):
    """ Performs the test backup step
    """

    def handle(self, event: Dict[str, object], ctx) -> lib.job.NextAction:
        # Get Salt API configuration
        missing_env_vars = []

        salt_api_url = os.environ.get('SALT_API_URL', None)
        if not salt_api_url:
            missing_env_vars.append('SALT_API_URL')

        salt_api_user = os.environ.get('SALT_API_USER', None)
        if not salt_api_user:
            missing_env_vars.append('SALT_API_USER')

        salt_api_password = os.environ.get('SALT_API_PASSWORD', None)
        if not salt_api_password:
            missing_env_vars.append('SALT_API_PASSWORD')

        if len(missing_env_vars) > 0:
            raise KeyError("Missing environment variables: {}".format(missing_env_vars))

        # Get volume id from event
        if 'volume_id' not in event:
            raise KeyError("event must contain \"volume_id\" field")

        volume_id = event['volume_id']

        # Get instance id from event
        if 'dev_ib_backup_instance_id' not in event:
            raise KeyError("event must contain \"dev_ib_backup_instance_id\" field")

        dev_ib_backup_instance_id = event['dev_ib_backup_instance_id']

        # Get mount point from event
        if 'mount_point' not in event:
            raise KeyError("\"mount_point\" expected to be in event")

        mount_point = event['mount_point']

        # Authenticate with Salt API
        salt_api_token = lib.salt.get_auth_token(host=salt_api_url, username=salt_api_user, password=salt_api_password)

        self.logger.debug("Authenticated with Salt API")

        # Setup ib02.dev for snapshot test
        ib_backup_salt_target = "ec2:instance_id:{}".format(dev_ib_backup_instance_id)

        setup_result = lib.salt.exec(host=salt_api_url, auth_token=salt_api_token, minion=ib_backup_salt_target,
                                     cmd='state.apply', args=['infobright-backup-check.setup-ib-restore-test'],
                                     tgt_type='grain')

        lib.salt.check_job_result(setup_result)

        self.logger.debug("Setup Infobright development instance for test, result={}".format(setup_result))

        # Test snapshot integrity
        test_result = lib.salt.exec(host=salt_api_url, auth_token=salt_api_token, minion=ib_backup_salt_target,
                                    cmd='state.apply', args=['infobright-backup-check.test-restored-backup'],
                                    salt_client='local_async', tgt_type='grain')

        self.logger.debug("Test result={}".format(test_result))

        if len(test_result) != 1:
            raise ValueError("Test backup command Salt invocation response did not contain exactly 1 result")

        test_cmd_salt_job_id = test_result[0]['jid']

        # Run next lambda
        self.next_lambda_event = {
            'volume_id': volume_id,
            'dev_ib_backup_instance_id': dev_ib_backup_instance_id,
            'mount_point': mount_point,
            'test_cmd_salt_job_id': test_cmd_salt_job_id
        }
        return lib.job.NextAction.NEXT


def main(event, ctx):
    """ Lambda function handler
    Args:
        - event: AWS event which triggered Lambda function
        - ctx: Invocation information

    Raises: Any exception
    """
    step_job = TestBackupJob(lambda_name=lib.steps.STEP_TEST_BACKUP)
    step_job.run(event, ctx)
