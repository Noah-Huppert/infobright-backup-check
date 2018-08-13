# Infobright Backup Check Run Book
Details for running the Infobright Backup Check process.

# Table Of Contents
- [Infrastructure Overview](#infrastructure-overview)
- [Deploy](#deploy)
- [View Logs](#view-logs)
- [Debug Run Errors](#debug-run-errors)

# Infrastructure Overview
The Infobright Backup Check process is run by a series of AWS Lambda functions.  

Each Lambda function completes a part of the process and then invokes the next Lambda function. Sometimes functions will 
invoke themselves if they are waiting for an operation to complete (ex: An EC2 volume to create).

See the [readme](README.md) for detailed information about each Lambda function.  

At the end of this process the status of the Infobright backup is recorded in 2 ways:

- As the `infobright_backup_valid` Datadog metric
- As the `DBBackupValid` tag on the backup snapshot that was tested

# Deploy
CircleCI will create a GitHub release for every commit pushed to the `master` branch.  

Each release provides the exact command one should run to deploy that release to AWS.

# View Logs
Logs can be found in [AWS CloudWatch](https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logs:prefix=/aws/lambda/dev-ib).

# Debug Run Errors
Debug run errors by viewing the logs for each AWS Lambda function.  

Start at the Lambda function with `step-1` in its name.  

If a Lambda function completes successfully a log entry in the following format should be present towards the bottom of
the log stream:

```
Invoked lambda, name=<NEXT LAMBDA NAME>, event={ ... }
```

Look at the logs for the lambda name in that log statement. Continue following the log trail until you reach a Lambda 
which has errors in its logs.
