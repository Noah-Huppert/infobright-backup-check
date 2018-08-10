import os
from typing import Dict
import time

import lib.job
import lib.steps
import lib.salt

import boto3

BACKUP_TEST_STATUS_TAG_NAME = 'DBBackupValid'


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

        # Check status of test backup Salt job
        backup_tested_successfully = True

        try:
            lib.salt.check_job_result(job_status_resp)
        except lib.salt.NoMinionResultsException as e:
            self.logger.debug("No results for test backup Salt job yet, still running")

            return lib.job.NextAction.REPEAT
        except lib.salt.JobFailedException as e:
            self.logger.error("Failed to verify integrity of database backup: {}".format(e))

            backup_tested_successfully = False

        # Label backup snapshot based on results of test
        backup_test_status_tag_value = 'True'
        if not backup_tested_successfully:
            backup_test_status_tag_value = 'False'

        volume_resp = ec2.describe_volumes(VolumeIds=[volume_id])

        if len(volume_resp['Volumes']) == 0:
            raise ValueError("Could not find test backup volume which we just tested")

        volume = volume_resp['Volumes'][0]

        snapshot_id = volume['SnapshotId']

        self.logger.debug("Adding db backup test command result tag to \"{}={}\" to snapshot_id={}"
                          .format(BACKUP_TEST_STATUS_TAG_NAME, backup_test_status_tag_value, snapshot_id))

        ec2.create_tags(Resources=[snapshot_id], Tags=[{
            'Key': BACKUP_TEST_STATUS_TAG_NAME,
            'Value': backup_test_status_tag_value
        }])

        # Publish datadog statistic
        unix_time = int(time.time())
        datadog_metric_value = 1
        if not backup_test_status_tag_value:
            datadog_metric_value = 0

        self.logger.info("MONITORING|{}|{}|gauge|infobright_backup_valid|#snapshot_id:{}"
                         .format(unix_time, datadog_metric_value, snapshot_id))

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


def main(event, ctx):
    """ Lambda function handler
    Args:
        - event: AWS event which triggered Lambda function
        - ctx: Invocation information

    Raises: Any exception
    """
    step_job = WaitTestCompletedJob(lambda_name=lib.steps.STEP_WAIT_TEST_COMPLETED)
    step_job.run(event, ctx)
