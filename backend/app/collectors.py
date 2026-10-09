"""Pluggable evidence collectors. Each collector takes a config dict and returns
a list of artifacts: {filename, bytes, meta}. Deterministic and auditable — the
config says exactly what will be collected. Add a new vector = add a class + register it.
"""
import json
import os
import requests


class CollectorError(Exception):
    pass


def _artifact(filename, data, meta):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return {"filename": filename, "bytes": data, "meta": meta}


def http_api(config):
    """Pull evidence from any HTTP/JSON API (cloud, SaaS, internal endpoint).
    config: {url, method?, headers?, body?}
    """
    url = config.get("url")
    if not url:
        raise CollectorError("http_api: config.url required")
    method = config.get("method", "GET").upper()
    resp = requests.request(
        method, url,
        headers=config.get("headers") or {},
        json=config.get("body"),
        timeout=30,
    )
    resp.raise_for_status()
    try:
        body = json.dumps(resp.json(), indent=2, sort_keys=True)
        ext = "json"
    except ValueError:
        body = resp.text
        ext = "txt"
    return [_artifact(f"response.{ext}", body, {"url": url, "status": resp.status_code})]


def document(config):
    """Capture a document fetched over HTTP (policy PDF, exported report, drive link).
    config: {url, filename?, headers?}
    """
    url = config.get("url")
    if not url:
        raise CollectorError("document: config.url required")
    resp = requests.get(url, headers=config.get("headers") or {}, timeout=60)
    resp.raise_for_status()
    name = config.get("filename") or url.rsplit("/", 1)[-1] or "document"
    return [_artifact(name, resp.content, {"url": url, "content_type": resp.headers.get("content-type")})]


def screenshot(config):
    """Capture a full-page screenshot of a web console/dashboard that has no API.
    config: {url, full_page?, wait_ms?, headers?}
    Lazy-imports playwright so the rest of the app runs without it installed.
    """
    url = config.get("url")
    if not url:
        raise CollectorError("screenshot: config.url required")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise CollectorError("screenshot: playwright not installed (pip install playwright && playwright install chromium)")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            if config.get("headers"):
                page.set_extra_http_headers(config["headers"])
            page.goto(url, wait_until="networkidle", timeout=60000)
            if config.get("wait_ms"):
                page.wait_for_timeout(int(config["wait_ms"]))
            png = page.screenshot(full_page=config.get("full_page", True))
        finally:
            browser.close()
    return [_artifact("screenshot.png", png, {"url": url})]


def local_file(config):
    """Re-read a local document discovered by Surface A. config: {path}
    Guarded to the discovery root so a bound candidate can't be pointed at an
    arbitrary file after the scan (input validation at the trust boundary).
    """
    path = config.get("path")
    if not path:
        raise CollectorError("local_file: config.path required")
    root = os.path.abspath(os.getenv("DISCOVERY_DOCS_DIR", "./compliance_docs"))
    full = os.path.abspath(path)
    try:
        inside = os.path.commonpath([full, root]) == root
    except ValueError:  # different drive on Windows -> not inside
        inside = False
    if not inside:
        raise CollectorError(f"local_file: path outside discovery root ({root})")
    if not os.path.isfile(full):
        raise CollectorError(f"local_file: not a file: {path}")
    with open(full, "rb") as f:
        data = f.read()
    return [_artifact(os.path.basename(full), data, {"path": full, "bytes": len(data)})]


# Representative shapes for the sample fallback — enough to demo the audit loop and
# to show the operator exactly what a real call would return.
_AWS_SAMPLES = {
    ("iam", "get_account_password_policy"): {
        "PasswordPolicy": {"MinimumPasswordLength": 14, "RequireSymbols": True,
                           "RequireNumbers": True, "RequireUppercaseCharacters": True,
                           "RequireLowercaseCharacters": True, "MaxPasswordAge": 90,
                           "PasswordReusePrevention": 24}},
    ("iam", "list_users"): {"Users": [{"UserName": "sample-admin", "MFADevices": 1}]},
    ("cloudtrail", "describe_trails"): {
        "trailList": [{"Name": "org-trail", "IsMultiRegionTrail": True,
                       "LogFileValidationEnabled": True}]},
    ("s3", "get_bucket_encryption"): {
        "ServerSideEncryptionConfiguration": {"Rules": [
            {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "aws:kms"}}]}},
    ("cloudwatch", "describe_alarms"): {
        "MetricAlarms": [{"AlarmName": "prod-cpu-high", "MetricName": "CPUUtilization",
                          "Namespace": "AWS/EC2", "Threshold": 80.0,
                          "ComparisonOperator": "GreaterThanThreshold", "StateValue": "OK"}]},
    ("autoscaling", "describe_auto_scaling_groups"): {
        "AutoScalingGroups": [{"AutoScalingGroupName": "prod-app", "MinSize": 2, "MaxSize": 10,
                               "DesiredCapacity": 3, "HealthCheckType": "ELB"}]},
    ("backup", "list_backup_vaults"): {
        "BackupVaultList": [{"BackupVaultName": "prod-vault",
                             "EncryptionKeyArn": "arn:aws:kms:...:key/sample"}]},
    ("rds", "describe_db_instances"): {
        "DBInstances": [{"DBInstanceIdentifier": "prod-db", "Engine": "postgres",
                         "BackupRetentionPeriod": 35, "MultiAZ": True,
                         "StorageEncrypted": True, "PubliclyAccessible": False}]},
    ("elbv2", "describe_load_balancers"): {
        "LoadBalancers": [{"LoadBalancerName": "prod-alb", "Scheme": "internet-facing",
                           "State": {"Code": "active"}, "AvailabilityZones": [
                               {"ZoneName": "us-east-1a"}, {"ZoneName": "us-east-1b"}]}]},
    ("route53", "list_health_checks"): {
        "HealthChecks": [{"Id": "abc123", "HealthCheckConfig": {
            "Type": "HTTPS", "FullyQualifiedDomainName": "app.example.com",
            "FailureThreshold": 3}}]},
}


def aws(config):
    """Collect AWS configuration evidence via boto3 (read-only describe/list/get calls).
    config: {service, operation, params?, region?}

    Makes a real call when boto3 + credentials are present. When they're absent it
    emits a clearly-labeled SAMPLE artifact (meta.sample=true) so the loop is demoable
    now and becomes real audit evidence the moment credentials exist — nothing else changes.
    Real call errors (bad op, access denied) propagate as audit failures, not samples.
    """
    service, operation = config.get("service"), config.get("operation")
    if not service or not operation:
        raise CollectorError("aws: config.service and config.operation required")

    def _sample(reason):
        payload = _AWS_SAMPLES.get((service, operation),
                                   {"note": "no sample fixture for this operation"})
        body = json.dumps(payload, indent=2, sort_keys=True)
        return [_artifact(f"aws-{service}-{operation}.json", body,
                          {"service": service, "operation": operation, "sample": True, "reason": reason})]

    try:
        import boto3
        from botocore.exceptions import NoCredentialsError, BotoCoreError
    except ImportError:
        return _sample("boto3 not installed")

    try:
        client = boto3.client(service, region_name=config.get("region"))
        result = getattr(client, operation)(**(config.get("params") or {}))
    except NoCredentialsError:
        return _sample("no AWS credentials configured")
    except (BotoCoreError,) as e:
        if "credential" in str(e).lower():  # endpoint/metadata credential lookups vary by botocore version
            return _sample(str(e))
        raise CollectorError(f"aws: {e}")
    except AttributeError:
        raise CollectorError(f"aws: unknown operation {service}.{operation}")

    result.pop("ResponseMetadata", None)
    body = json.dumps(result, indent=2, sort_keys=True, default=str)
    return [_artifact(f"aws-{service}-{operation}.json", body,
                      {"service": service, "operation": operation, "sample": False})]


def s3_file(config):
    """Collect one S3 object as evidence. config: {bucket, key, region?}
    Separate from `aws` because that collector JSON-encodes responses, and an S3
    object body is a binary stream — stringifying it yields a useless artifact.
    Same contract as the others: labeled SAMPLE without boto3/credentials.
    """
    bucket, key = config.get("bucket"), config.get("key")
    if not bucket or not key:
        raise CollectorError("s3_file: config.bucket and config.key required")
    name = key.rsplit("/", 1)[-1] or "s3-object"

    def _sample(reason):
        body = json.dumps({"Bucket": bucket, "Key": key, "note": "sample object body — no real content fetched"},
                          indent=2, sort_keys=True)
        return [_artifact(f"s3-{name}.json", body,
                          {"bucket": bucket, "key": key, "sample": True, "reason": reason})]

    try:
        import boto3
        from botocore.exceptions import NoCredentialsError, BotoCoreError
    except ImportError:
        return _sample("boto3 not installed")

    try:
        client = boto3.client("s3", region_name=config.get("region"))
        obj = client.get_object(Bucket=bucket, Key=key)
        data = obj["Body"].read()
    except NoCredentialsError:
        return _sample("no AWS credentials configured")
    except (BotoCoreError,) as e:
        if "credential" in str(e).lower():
            return _sample(str(e))
        raise CollectorError(f"s3_file: {e}")

    return [_artifact(name, data, {"bucket": bucket, "key": key,
                                   "etag": obj.get("ETag"), "bytes": len(data), "sample": False})]


# Placeholders in a GitHub endpoint, and the env var that fills each.
_GITHUB_VARS = {"owner": "GITHUB_OWNER", "repo": "GITHUB_REPO", "branch": "GITHUB_BRANCH", "org": "GITHUB_ORG"}
# Representative shapes, so a token-less demo shows what a real call returns.
_GITHUB_SAMPLES = [
    ("/protection", {"required_pull_request_reviews": {"required_approving_review_count": 1,
                                                       "dismiss_stale_reviews": True},
                     "required_status_checks": {"strict": True, "contexts": ["ci"]},
                     "enforce_admins": {"enabled": True},
                     "required_signatures": {"enabled": True}}),
    ("/workflows", {"total_count": 2, "workflows": [
        {"name": "ci", "path": ".github/workflows/ci.yml", "state": "active"},
        {"name": "codeql", "path": ".github/workflows/codeql.yml", "state": "active"}]}),
    ("/secret-scanning", {"state": "open", "secret_type": "github_pat", "resolution": None}),
    ("/dependabot", {"state": "open", "dependency": {"package": {"name": "lodash"}},
                     "security_advisory": {"severity": "high", "ghsa_id": "GHSA-xxxx"}}),
    ("/orgs/", {"two_factor_requirement_enabled": True, "members_can_create_repositories": False}),
]


def _github_sample(endpoint, reason):
    payload = next((body for key, body in _GITHUB_SAMPLES if key in endpoint),
                   {"endpoint": endpoint, "note": "no sample fixture for this endpoint"})
    return [_artifact(f"github-{endpoint.replace('/', '-')[:80]}.json",
                      json.dumps(payload, indent=2, sort_keys=True),
                      {"endpoint": endpoint, "sample": True, "reason": reason})]


def github(config):
    """Collect GitHub org/repo configuration evidence via the REST API (read-only).
    config: {endpoint} — e.g. "repos/{owner}/{repo}/branches/{branch}/protection".
    {owner}/{repo}/{branch}/{org} are filled from GITHUB_OWNER / GITHUB_REPO /
    GITHUB_BRANCH / GITHUB_ORG, authenticated with GITHUB_TOKEN.

    Without a token (or with an unfilled placeholder) it emits a clearly-labeled SAMPLE
    (meta.sample=true) — same contract as the aws collector, so a scan is demoable now
    and becomes real evidence the moment the credentials and variables exist.
    """
    endpoint = (config.get("endpoint") or "").strip("/")
    if not endpoint:
        raise CollectorError("github: config.endpoint required")

    token = os.getenv("GITHUB_TOKEN")
    unfilled = [env for k, env in _GITHUB_VARS.items() if f"{{{k}}}" in endpoint and not os.getenv(env)]
    if not token or unfilled:
        reason = ("no GITHUB_TOKEN configured" if not token
                  else f"set {', '.join(unfilled)}")
        return _github_sample(endpoint, reason)

    for k, env in _GITHUB_VARS.items():
        endpoint = endpoint.replace(f"{{{k}}}", os.getenv(env))
    resp = requests.get(
        "https://api.github.com/" + endpoint,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"},
        timeout=30,
    )
    resp.raise_for_status()
    body = json.dumps(resp.json(), indent=2, sort_keys=True)
    return [_artifact(f"github-{endpoint.replace('/', '-')[:80]}.json", body,
                      {"endpoint": endpoint, "sample": False})]


# ponytail: 3 HTTP collectors + 2 API collectors (aws, github) prove both plug-in
# shapes. More cloud collectors (okta, gcp) are the same pattern — add when a control needs them.
REGISTRY = {
    "http_api": http_api,
    "document": document,
    "local_file": local_file,
    "s3_file": s3_file,
    "screenshot": screenshot,
    "aws": aws,
    "github": github,
}


def agent(config):
    """Autonomous collector: given a natural-language goal, an LLM plans which real
    collector + config to use, then this delegates to it. The plan is recorded in
    the artifact meta so the run stays auditable."""
    goal = config.get("goal")
    if not goal:
        raise CollectorError("agent: config.goal required (describe the evidence to collect)")
    from .agent import plan_collection  # local import avoids circular import at module load
    plannable = [c for c in REGISTRY if c != "agent"]
    try:
        collector_type, planned_cfg = plan_collection(goal, plannable)
    except Exception as e:
        raise CollectorError(f"agent planning failed: {e}")
    artifacts = REGISTRY[collector_type](planned_cfg)
    for art in artifacts:  # stamp the plan onto every artifact for the audit trail
        art["meta"] = {**(art.get("meta") or {}), "agent_plan": {"collector_type": collector_type, "config": planned_cfg, "goal": goal}}
    return artifacts


REGISTRY["agent"] = agent


def get_collector(collector_type):
    fn = REGISTRY.get(collector_type)
    if not fn:
        raise CollectorError(f"unknown collector_type: {collector_type} (have {list(REGISTRY)})")
    return fn
