import io
import logging
import re
import socket

from dns.resolver import Resolver
import environ
import backoff
import boto3
import requests

env = environ.Env()
environ.Env.read_env()

HOSTNAME = env("HOSTNAME", default=socket.gethostname())
MIRROR_BUCKET = env("S3_BUCKET")
CVDUPDATE_NAMESERVER = env("CVDUPDATE_NAMESERVER", default="current.cvd.clamav.net")

USER_AGENT = f"CVDUPDATE/1.0 ({HOSTNAME})"

s3 = boto3.client("s3")

logger = logging.getLogger(__name__)


DATABASES = {
    "main.cvd": {
        "url": "https://database.clamav.net/main.cvd",
        "dns_index": 1,
    },
    "daily.cvd": {
        "url": "https://database.clamav.net/daily.cvd",
        "dns_index": 2,
    },
    "bytecode.cvd": {
        "url": "https://database.clamav.net/bytecode.cvd",
        "dns_index": 7,
    },
}


def get_database_header_from_s3(object_name):
    """Retrieve the first 96 bytes from a file object"""

    resp = s3.get_object(Bucket=MIRROR_BUCKET, Key=object_name, Range="bytes=0-95")
    return resp["Body"].read()


class DownloadError(Exception):
    pass


def backoff_hdlr(details):
    print(
        "Backing off {wait:0.1f} seconds afters {tries} tries "
        "calling function {func} with args {args} and kwargs "
        "{kwargs}".format(**details)
    )


def fatal_code(e):
    return (
        isinstance(e, DownloadError)
        or e.response.status_code == 429
        or e.response.status_code >= 500
    )


@backoff.on_exception(
    backoff.expo,
    requests.exceptions.RequestException,
    max_time=300,
    giveup=fatal_code,
    on_backoff=backoff_hdlr,
)
def download_file_obj(url):
    """
    Download a file to a stream
    """

    response = requests.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
        },
    )

    response.raise_for_status()

    content_length = int(response.headers.get("content-length", "0"))

    if response.status_code in [200, 206] and content_length > len(response.content):
        raise DownloadError(
            f"Content length for {url} was {len(response.content)} but expected {content_length}"
        )

    return io.BytesIO(response.content)


def get_remote_version_string():
    """
    Get the current cvd string from the clamav DNS TXT entry
    """

    resolver = Resolver()
    resolver.timeout = 5
    nameserver = CVDUPDATE_NAMESERVER

    record = str(resolver.resolve(CVDUPDATE_NAMESERVER, "TXT").response.answer[0])

    versions = re.search('"(.*)"', record)[1]

    return versions.split(":")


def get_local_database_version(database):
    """
    Extract the local version number from the header of a local s3 database object
    """
    cvd_header = get_database_header_from_s3(database)

    header_fields = cvd_header.decode("utf-8", "ignore").strip().split(":")

    return int(header_fields[2])


def get_last_local_cdiff_number(database):
    """
    Check for the last local diff file for a database
    """
    # TODO: handle pagination. Not an urgent requirement as the default
    # wil return up to 1000 keys

    def extract_version_num(item_name):
        pattern = f"{prefix}(\d+).cdiff"

        matches = re.search(pattern, item_name)

        return int(matches[1]) if matches else None

    prefix = database.replace(".cvd", "-")

    search = f"{prefix}(\d+).cdiff"

    response = s3.list_objects_v2(
        Bucket=MIRROR_BUCKET,
        Prefix=prefix,
    )

    items = sorted(
        [extract_version_num(item["Key"]) for item in response.get("Contents", [])]
    )

    return items[-1] if len(items) else 0


def get_version_info(database, version_string):
    """Get the local, remote and last cdiff number for a specific database"""

    config = DATABASES[database]

    version = {
        "available": int(version_string[config["dns_index"]]),
        "local": get_local_database_version(database),
        "last_cdiff": 0,
    }

    version["last_cdiff"] = get_last_local_cdiff_number(database)

    return version


def healthcheck(max_allowed_database_versions=1, max_allowed_diff_versions=1):

    version_string = get_remote_version_string()

    status_text = []
    status_ok = True

    for database in DATABASES:
        db_ver = get_version_info(database, version_string)

        status_text.append(
            "{} available version: {}; local version: {}; last cdiff: {}".format(
                database,
                db_ver["available"],
                db_ver["local"],
                db_ver["last_cdiff"],
            )
        )

        if db_ver["local"] < db_ver["available"]:
            if db_ver["available"] - db_ver["local"] > max_allowed_database_versions:
                # database is too old
                status_ok = False

                status_text.append(
                    "{} is out date by {} version(s)".format(
                        database,
                        db_ver["available"] - db_ver["local"],
                    )
                )

            elif db_ver["available"] - db_ver["last_cdiff"] > max_allowed_diff_versions:
                # the diffs are too old
                status_ok = False

                status_text.append(
                    "{} cdiffs are out of date by {} version(s)".format(
                        database,
                        db_ver["available"] - db_ver["last_cdiff"],
                    )
                )

    return status_ok, "\n".join(status_text)


def update():
    """Get the latest updates from the clamav server and upload to s3"""

    version_string = get_remote_version_string()

    for database, config in DATABASES.items():
        db_ver = get_version_info(database, version_string)

        # are cdiffs up to date?
        if db_ver["last_cdiff"] < db_ver["available"]:
            if db_ver["available"] - db_ver["last_cdiff"] > 5:
                cdiff_start = db_ver["local"] + 1
            else:
                cdiff_start = db_ver["last_cdiff"] + 1

            if cdiff_start <= db_ver["available"]:
                for i in range(cdiff_start, db_ver["available"] + 1):
                    prefix = database.replace(".cvd", "")
                    cdiff = f"{prefix}-{i}.cdiff"
                    url = config["url"].replace(database, cdiff)
                    print(f"fetching {url}")

                    fd = download_file_obj(url)
                    s3.upload_fileobj(
                        fd, MIRROR_BUCKET, cdiff, ExtraArgs={"ACL": "public-read"}
                    )
        else:
            print(f"{database} cdiffs are up to date")

        # is the database up to date?
        if db_ver["local"] < db_ver["available"]:

            url = "{}?version={}".format(
                config["url"],
                db_ver["available"],
            )

            print(f"fetching {url}")

            fd = download_file_obj(url)
            s3.upload_fileobj(
                fd, MIRROR_BUCKET, database, ExtraArgs={"ACL": "public-read"}
            )
        else:
            print(f"{database} is up to date")


if __name__ == "__main__":
    # if the file is run directly, download updates
    update()
