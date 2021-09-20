# clamav-mirror for s3

A clamav mirror that leverages s3 static webhosting and is inspired by [cvdupdate](https://github.com/Cisco-Talos/cvdupdate/)

It is ready to run in cloudfoundry and requires an associated AWS s3 bucket with static web hosting enabled.

The web app is a single flask page that checks the version of the databases in s3 and compares them to the available versions.  If these are sufficiently out-of-date (by default > 1 version out-of-date) then the healthcheck will report a `FAIL` in pingdom xml monitoring format.

Then there is an update script `run-update.py` which can be run periodically, e.g every hour.

## Environment variables

S3_BUCKET: the name of the s3 bucket
AWS_ACCESS_KEY_ID: aws iam credentials with get/put/put acl perms for the bucket
AWS_SECRET_ACCESS_KEY: aws iam credentials with get/put/put acl perms for the bucket
