# IB Backup
Infobright backup.

# Table Of Contents
- [Overview](#overview)
- [Process](#process)
    - [Existing Functionality](#existing-functionality)
    - [New Functionality](#new-functionality)
- [Infrastructure](#infrastructure)
- [Development](#development)

# Overview
Creates and tests an Infobright disk snapshot.

# Process
This section details the steps taken to create and test an Infobright backup.  

The process is completed by a series of AWS Lambda functions which create a 
pipeline. After one AWS Lambda function has completed the next AWS Lambda 
function is invoked.  

## Trigger
The process is started by an AWS CloudWatch event which runs every day at 
00:00 UTC.  

## Existing Functionality
The following steps work is currently completed by a cron job which runs on the Util box. In the future it would be 
ideal if these steps were run via a Lambdas.  

The process of how this work would be run on Lambdas is documented below. For the future when we decide to port this
work from a Cron job to Lambda functions.

### Snapshot
Creates an Infobright data volume snapshot.  

Actions:

- SSH into the production Infobright replica
    - Stop the `mysqld-ib` service
    - Unmount the `/ibdata` directory
- Create a disk snapshot for the Infobright data volume
- Invoke the [Wait Snapshot Created step](#wait-snapshot-created) with `wait=creation`

### Wait Snapshot Created
Waits until the Infobright data volume snapshot has been completed.  

Accepts a `wait` context parameter which tells the Lambda what to wait for. Valid values:

- `creation`: Wait for snapshot creation to be started
- `completed`: Wait for the snapshot to be fully created

Actions:

- If `wait=creation`
    - Check if snapshot creation has been started
        - If started:
            - Invoke the [Resume Production IB Replica step](#resume-production-ib-replica-step)
            - Invoke the [Wait Snapshot Created step](#wait-snapshot-created) `wait=completed`
- If `wait=completed`
    - Check if snapshot has completed
        - If completed: Invoke the 
            [Resume Production IB Replica step](#resume-production-ib-replica)
        - If not completed: Send a message to the wait SQS queue which will invoke 
            this step again and the `wait=completed`

### Resume Production IB Replica
Resume the production Infobright replica.  

Actions:

- SSH into the production Infobright replica
    - Mount the `/ibdata` directory
    - Start the `mysqld-ib` service
- Invoke the [Start Development IB Replica step](#start-development-ib-replica)

## New Functionality
The following steps are not being executed anywhere on the infrastructure. AWS Lambda functions will be created to 
execute these steps.

### Create Test Volume
Creates a test volume from the Infobright data snapshot.  

File: `ib_backup/step_create_volume.py`  

Environment variables:

- `NEXT_LAMBDA_NAME`: Name of the [Wait Test Volume Created lambda](#wait-test-volume-created)

Expected event: None

Actions:

- Create a volume from the Infobright data snapshot
- Invoke the [Wait Test Volume Created step](#wait-test-volume-created)

### Wait Test Volume Created
Waits until the test volume has been created.  

File: `ib_backup/step_wait_volume_created.py`  

Environment variables:

- `NEXT_LAMBDA_NAME`: Name of the [Attach Test Volume lambda](#attach-test-volume)

Expected event: 

- `volume_id`: Id of volume to wait for

Actions:

- Check if the test volume has been created
    - If created: Invoke the [Attach Test Volume lambda](#attach-test-volume)
    - If not created: Invoke this step again in 15 seconds

### Attach Test Volume
Attaches the test volume to the development Infobright replica.

Environment variables:

- `NEXT_LAMBDA_NAME`: Name of the [Wait Test Volume Attached lambda](#wait-test-volume-attached)

Expected event:

- `volume_id`: Id of volume to attach

Actions:

- Attach the test volume to the `ib02.dev` instance
- Invoke the [Wait Test Volume Attached step](#wait-test-volume-attached)

### Wait Test Volume Attached
Waits for the test volume to be attached to the development Infobright replica.  

Environment variables:

- `NEXT_LAMBDA_NAME`: Name of the [Test Infobright Backup lambda](#test-infobright-backup)

Expected event:

- `volume_id`: Id of the volume to wait for
- `instance_id`: If of instance volume is attached to
- `mount_point`: Path in file system device was attached

Actions:

- Check if the test volume is attached to the `ib02.dev` instance
    - If attached: Invoke the [Test Infobright Backup step](#test-infobright-backup)
    - If not attached: Invoke this step again in 15 seconds

### Test Infobright Backup
Tests the integrity of the Infobright backup.  

Environment variables:

- `NEXT_LAMBDA_NAME`: Name of the [Wait Test Volume Detached lambda](#wait-test-volume-detached)
- `SALT_API_USER`: User to authenticate with Salt API
- `SALT_API_PASSWORD`: Password to authenticate with Salt API

Expected event:

- `volume_id`: Id of snapshot test volume
- `instance_id`: If of instance volume is attached to
- `mount_point`: Path in file system device was attached

Actions:

- SSH into the development Infobright replica:
    - Mount the test volume at `/ibdata-backup`
    - Start the `mysqld-ib` service
    - Run a test query and ensure the actual results match the expected results
        - Save the results of this test as the `Integrity` flag on the
            snapshot, with the value `good` or `bad`
    - Stop the `mysqld-ib` service
    - Unmount the `/ibdata-backup` directory
- Detach the test volume from the `ib02.dev` instance
- Invoke the [Wait Test Volume Detached step](#wait-test-volume-detached)

### Wait Test Volume Detached
Waits until the test volume is detached from the development Infobright replica.  

Environment variables:

- `NEXT_LAMBDA_NAME`: Name of the [Cleanup lambda](#cleanup)

Expected event:

- `volume_id`: Id of test volume to detach
- `instance_id`: If of instance volume is attached to

Actions:

- Check if the test volume is detached from the `ib02.dev` instance
    - If detached: Invoke the [Cleanup step](#cleanup)
    - If not detached: Invoke this step again in 15 seconds

### Cleanup
Deletes the test volume and stops the development Infobright replica.  

Environment variables: None

Expected event:

- `volume_id`: Id of test volume to delete

Actions:

- Delete the test volume

# Infrastructure
The infrastructure to run this process is created by an AWS CloudFormation 
stack in the `deploy/` directory.  

Components:

- Trigger CloudWatch rule
    - Triggers at 00:00 UTC
    - Triggers [Snapshot step](#snapshot) lambda
- Step lambdas
    - Python 3.6
    - For all steps

# Development
A deploy script it provided packages all step lambda code, uploads it, and then deploys a CloudFormation stack which 
creates all the Lambdas.  

Run by executing:

```
./deploy/deploy.sh
```

Lint code by running the `lint` make target:

```
make lint
```
