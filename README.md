# clamav-mirror for s3

A clamav mirror that leverages s3 static webhosting and is inspired by [cvdupdate](https://github.com/Cisco-Talos/cvdupdate/)

It is ready to run in cloudfoundry and requires an associated AWS s3 bucket with static web hosting enabled.

The web app is a single flask page that checks the version of the databases in s3 and compares them to the available versions.  If these are sufficiently out-of-date (by default > 1 version out-of-date) then the healthcheck will report a `FAIL` in pingdom xml monitoring format.

Run `cvd.py` to check and download the latest database versions. This should be run periodically.

## Environment variables


| Variable name | Required | Description |
| ------------- | ------------- | ------------- |
| `S3_BUCKET ` | Yes | S3 bucket name |
| `AWS_ACCESS_KEY_ID` | Yes | aws iam credentials with get/put/put acl perms for the bucket |
| `AWS_SECRET_ACCESS_KEY` | Yes | aws iam credentials with get/put/put acl perms for the bucket |

