"""Pluggable evidence collectors. Each collector takes a config dict and returns
a list of artifacts: {filename, bytes, meta}. Deterministic and auditable — the
config says exactly what will be collected. Add a new vector = add a class + register it.
"""
import json
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


# ponytail: 3 HTTP collectors + 1 SDK collector (aws) prove both plug-in shapes.
# More cloud collectors (okta, github) are the same pattern — add when a control needs them.
REGISTRY = {
    "http_api": http_api,
    "document": document,
    "screenshot": screenshot,
    "aws": aws,
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
