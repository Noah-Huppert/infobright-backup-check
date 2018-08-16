# Infobright Backup Check Run Book
Details for running the Infobright Backup Check process.

# Table Of Contents
- [Infrastructure Overview](#infrastructure-overview)
- [Deploy](#deploy)
- [DataDog Dashboard](#datadog-dashboard)
- [View Logs](#view-logs)
- [Debug Run Errors](#debug-run-errors)
- [Debug Database Backup Test](#debug-database-backup-test)

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

[GitHub releases page](https://github.com/aminopay/infobright-backup-check/releases).

# DataDog Dashboard
Metrics like error count and run duration are graphed in the [Infobright Backup Check DataDog Dashboard](https://app.datadoghq.com/dash/889950/infobright-backup-check?live=true&page=0&is_auto=false&from_ts=1534258488237&to_ts=1534431288237&tile_size=m).  

Use the error count graph to see exactly which function failed to run due to an error.  

Use the run duration graph to see if any Lambda functions are taking less or more time to finish than they usually do.

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

# Debug Database Backup Test
If:

- The `infobright_backup_valid` metric in Datadog equals `0`
- The `DBBackupValid` tag equals `False`

This means that the Infobright Backup Check process ran, and found an error with the Infobright backup.  

To see what is wrong with the Infobright backup check [the logs for the step 6 Lambda](https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logs:prefix=/aws/lambda/dev-ib-backup-step-6).  

This Lambda function waits for the database backup integrity script to finish running. It checks to see if the script
has finished running. If it hasn't finished running it will wait 1 minute, then invoke itself again.  

Because the script invokes itself multiple times there will be a lot of log lines. The issue with the Infobright backup 
will be located all the way at the bottom.  

Look for a log item in the format:

```
test cmd job status resp=[{'ib02.dev.code418.net': ... }]
```

This log item will contain the output of the database backup integrity test script.
