import os
from typing import Dict

import lib.job
import lib.steps
import lib.salt

import boto3


class WaitTestCompletedJob(lib.job.Job):
    """ Performs the wait test completed step
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

        # Get test cmd salt job id from event
        if 'test_cmd_salt_job_id' not in event:
            raise KeyError("event must contain \"test_cmd_salt_job_id\" field")

        test_cmd_salt_job_id = event['test_cmd_salt_job_id']

        # AWS clients
        ec2 = boto3.client('ec2')

        # Authenticate with Salt API
        salt_api_token = lib.salt.get_auth_token(host=salt_api_url, username=salt_api_user, password=salt_api_password)

        self.logger.debug("Authenticated with Salt API")

        # Get status of test backup Salt job
        job_status_resp = lib.salt.get_job(host=salt_api_url, auth_token=salt_api_token, job_id=test_cmd_salt_job_id)

        self.logger.debug("test cmd job status resp={}".format(job_status_resp))

        # ... Check there is exactly 1 job result returned by Salt API
        if len(job_status_resp) != 1:
            raise ValueError("Salt API did not return exactly 1 result for test backup command Salt job")

        minion_job_statuses = job_status_resp[0]

        # ... Check the job ran on exactly 1 minion
        job_minions = list(minion_job_statuses)
        if len(job_minions) != 1:
            raise ValueError("Test backup command Salt job must run on exactly 1 minion, ran on: " +
                             "{}".format(job_minions))

        job_minion = job_minions[0]
        job_status = minion_job_statuses[job_minion]

        # ... Check the job ran exactly 1 command
        job_cmds = list(job_status)
        if len(job_cmds) != 1:
            raise ValueError("Test backup command Salt job must run exactly 1 command, ran: {}".format(job_cmds))

        job_cmd = job_cmds[0]
        cmd_status = job_status[job_cmd]

        # ... Check if command completed
        if 'result' in cmd_status:
            # Test backup command completed successfully
            if not cmd_status['result']:
                self.logger.error("Test backup command failed to verify backup integrity")

            self.logger.debug("Check backup command completed")

            # Detach volume
            ec2.detach_volume(Device=mount_point, InstanceId=dev_ib_backup_instance_id, VolumeId=volume_id)

            self.logger.debug("Detached volume from dev Infobright instance, volume_id={}, dev_ib_backup_instance_id={}"
                              .format(volume_id, dev_ib_backup_instance_id))

            # Tear down ib02.dev for snapshot test
            ib_backup_salt_target = "ec2:instance_id:{}".format(dev_ib_backup_instance_id)

            teardown_result = lib.salt.exec(host=salt_api_url, auth_token=salt_api_token, minion=ib_backup_salt_target,
                                            cmd='state.apply',
                                            args=['infobright-backup-check.teardown-ib-restore-test'],
                                            tgt_type='grain')

            lib.salt.check_job_result(teardown_result)

            self.logger.debug("Teared down Infobright development instance for test, result={}".format(teardown_result))

            # Invoke next lambda
            self.next_lambda_event = {
                'volume_id': volume_id,
                'dev_ib_backup_instance_id': dev_ib_backup_instance_id
            }
            return lib.job.NextAction.NEXT
        else:
            # Still running test backup command
            self.logger.debug("Check backup command still running")
            return lib.job.NextAction.REPEAT


def main(event, ctx):
    """ Lambda function handler
    Args:
        - event: AWS event which triggered Lambda function
        - ctx: Invocation information

    Raises: Any exception
    """
    step_job = WaitTestCompletedJob(lambda_name=lib.steps.STEP_TEST_BACKUP)
    step_job.run(event, ctx)
