from typing import Dict

import lib.job
import lib.steps
import lib.salt
from step_attach_volume import DEV_IB_BACKUP_NAME


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

        # Authenticate with Salt API
        salt_api_token = lib.salt.get_auth_token(host=salt_api_url, username=salt_api_user, password=salt_api_password)

        # Setup ib02.dev for snapshot test
        lib.salt.exec(host=salt_api_url, auth_token=salt_api_token, minion=DEV_IB_BACKUP_NAME, cmd='state.apply',
                      args=['infobright.setup-ib-restore-test'])

        # TODO: Run db-cli integrity test

        # Tear down ib02.dev for snapshot test
        lib.salt.exec(host=salt_api_url, auth_token=salt_api_token, minion=DEV_IB_BACKUP_NAME, cmd='state.apply',
                      args=['infobright.teardown-ib-restore-test'])

        return lib.job.NextAction.TERMINATE


def main(event, ctx):
    """ Lambda function handler
    Args:
        - event: AWS event which triggered Lambda function
        - ctx: Invocation information

    Raises: Any exception
    """
    step_job = TestBackupJob(lambda_name=lib.steps.STEP_TEST_BACKUP)
    step_job.run(event, ctx)
