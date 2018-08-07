#!/usr/bin/env python3
"""
Environment Variables:
    - GITHUB_TOKEN : Personal access token w/ write perms
    - CIRCLE_PROJECT_USERNAME: Name of user who owns repo
    - CIRCLE_PROJECT_REPONAME: Name of repository
"""
import argparse
import json
import os
import sys
import time

from datetime import datetime
from urllib.request import urlopen, Request

DATE = time.strftime("%Y-%m-%d")
GITHUB_TOKEN = os.environ['GITHUB_TOKEN']
GITHUB_URL = "https://api.github.com/repos/" \
             + os.environ['CIRCLE_PROJECT_USERNAME'] + "/" \
             + os.environ['CIRCLE_PROJECT_REPONAME']
RELEASES_URL = GITHUB_URL + "/releases"
PULLS_URL = GITHUB_URL + "/pulls"
TREE_URL = GITHUB_URL + "/tree"
COMPARE_URL = GITHUB_URL + "/compare"


def get_releases():
    # gets all releases via GH API
    get_releases_req = Request(RELEASES_URL)
    get_releases_req.add_header('Authorization', 'token %s' % GITHUB_TOKEN)
    get_releases_resp = urlopen(get_releases_req)
    releases = json.loads(get_releases_resp.read().decode('utf-8'))
    return releases


def get_pulls(releases):
    url_pulls = PULLS_URL + "?state=closed"

    # get all commits since the last release
    get_pulls_since_req = Request(url_pulls)
    get_pulls_since_req.add_header('Authorization', 'token %s' % GITHUB_TOKEN)
    get_pulls_since_resp = urlopen(get_pulls_since_req)
    pulls = json.loads(get_pulls_since_resp.read().decode('utf-8'))
    good_pulls = []
    if len(releases) > 0:
        last_release_date = datetime.strptime(releases[0]['published_at'], "%Y-%m-%dT%H:%M:%Sz")
    else:
        last_release_date = datetime(1970, 1, 1, 0, 0)
    for pull in pulls:
        closed_date = datetime.strptime(pull['closed_at'], "%Y-%m-%dT%H:%M:%Sz")
        if closed_date > last_release_date:
            good_pulls.append(pull)
    return good_pulls


RELEASE_BODY = """
### [Full Change Log]({comparison_url})

### Merged Pull Requests
{pr_list}

### Artifacts
{artifacts_body}
"""


def generate_body(pulls, releases, tag, code_bucket_file, artifact_locations_file):
    """ Create GitHub release body
    Args:
        - pulls: List of pull requests
        - releases: GitHub release for repo
        - tag: GitHub release tag
        - code_bucket_file: File containing the name of the S3 bucket which artifacts will be uploaded to
        - artifact_locations_file: File containing the locations in S3 of the lambda deployment artifacts
    """
    # Get compare url
    tree_url = TREE_URL + '/{}'.format(tag)
    comparison_url = generate_diff_link(releases[0]['tag_name'], tag) if releases else tree_url

    # Make PR list
    pr_list = ''

    for pull in pulls:
        pr_list += "{} [#{}]({}) ([{}]({}))\n".format(pull['title'], pull['number'], pull['html_url'],
                                                      pull['user']['login'], pull['user']['html_url'])

    # Make artifacts body
    artifacts_body = ""
    artifacts_lists = []

    code_bucket = None
    with open(code_bucket_file, 'r') as f:
        code_bucket = f.read().strip()

    artifact_locations = None
    with open(artifact_locations_file, 'r') as f:
        artifact_locations = json.load(f)

    for step_name in list(artifact_locations):
        artifacts_lists.append("- `{}`: `{}`".format(step_name, artifact_locations[step_name]))

    artifact_body += "Artifact S3 Bucket: {}\n".format(code_bucket)

    artifacts_body += '\n'.join(artifacts_lists)

    artifacts_locations_str = json.dumps(artifact_locations)
    artifacts_body += "\n\nPass the following argument to the deploy script:\n```\n--artifact-s3-keys '{}'\n```"\
                      .format(artifacts_locations_str)

    artifacts_body += "\n\nPass the following pillar argument to the Salt state:\n```\npillar='{}'\n```"\
                      .format("{{\"artifact_s3_keys\": \"{}\"}}".format(artifacts_locations_str.replace("\"", "\\\"")))

    return RELEASE_BODY.format(comparison_url=comparison_url, pr_list=pr_list, artifacts_body=artifacts_body)


def generate_diff_link(prev_release_tag, new_release_tag):
    return COMPARE_URL + "/{}...{}".format(prev_release_tag, new_release_tag)


def generate_tag(releases):
    release_tags = [release['tag_name'] for release in releases]
    # want to make sure not to repeat a tag, so we start w/ version one for the day & increment until uniqueness
    v = 1
    tag = "{}-{}".format(DATE, v)
    while tag in release_tags:
        v += 1
        tag = "{}-{}".format(DATE, v)
    return tag


def create_release(tag, release_body_str, dry_run):  # create a new release

    new_release_data = json.dumps({
        'tag_name': tag,
        'name': tag,
        'body': release_body_str
    }).encode('utf-8')

    if dry_run:
        print(new_release_data)
        sys.exit()

    create_new_release_req = Request(RELEASES_URL, new_release_data, {'Content-Type': 'application/json'})
    create_new_release_req.add_header('Authorization', 'token %s' % GITHUB_TOKEN)
    with urlopen(create_new_release_req) as response:
        if 200 > response.status > 300:
            print('Exiting due to Github API response {} - {}'.format(response.status, response.reason))
            sys.exit(-1)
        else:
            print('Success of {}: {}'.format(response.status, json.loads(response.read().decode('utf-8'))))


def get_parser():
    parser = argparse.ArgumentParser(
        description="Release script for generating Github releases from within a CircleCI build")
    parser.add_argument('--get-new-tag',
                        help="Generate a new git release tag",
                        action='store_true')
    parser.add_argument('--release',
                        action='store_true',
                        help="Given a release tag, create a Github release with all of the PRs since the last release")
    parser.add_argument('--tag',
                        nargs=1,
                        help="Used in conjunction with --release")
    parser.add_argument('--code-bucket-file',
                        help="(Required with --release argument) File which contains the name of the S3 bucket code " +
                             "artifacts were uploaded to")
    parser.add_argument('--artifact-locations-file',
                        help="(Required with --release argument) File which contains locations of artifacts in S3")
    parser.add_argument('--dry-run',
                        action='store_true',
                        help="Dry run the release")
    return parser


if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    releases_result = get_releases()

    # Get or create a new release tag to be used in conjunction with CircleCI
    if args.get_new_tag or (args.release and not args.tag):
        tag = generate_tag(releases_result)
    else:
        tag = args.tag[0] if args.tag else ''

    # Perform a full release with either a generated or user provided tag
    if args.release:
        # Check --code-bucket-file and --artifact-locations-file arguments provided with --release argument
        if not args.code_bucket_file:
            raise ValueError("--code-bucket-file argument must be provided if --release argument is given")

        if not args.artifact_locations_file:
            raise ValueError("--artifact-locations-file argument must be provided if --release argument is given")

        # Get pull requests since last release
        pulls_result = get_pulls(releases_result)
        body = generate_body(pulls_result, releases_result, tag, args.code_bucket_file, args.artifact_locations_file)
        create_release(tag, body, args.dry_run)
    elif tag:
        # Used for exporting the value to be used in CircleCI
        print(tag)
    else:
        parser.print_help()
