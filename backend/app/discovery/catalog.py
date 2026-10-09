"""Surface B: cloud & code evidence descriptors.

Deliberately **not** a scanner. This is a static catalog of the read-only calls that
evidence each control family — the existing `aws` collector and the `github` collector
do the pulling, and discovery only has to say which call answers which control. That
is the whole of "Surface B discovery": matching control text to a known API call.

Descriptors are plain asset dicts, the same shape `document_scanner` returns, so one
matchmaker scores documents and API calls identically. They are pre-wired with their
collector_type + config (unlike a discovered file, which the matchmaker pairs with
`local_file`).

ponytail: only parameter-free calls are listed, so a bound descriptor can always be
run without extra config. Bucket/repo-scoped calls that need an argument
(s3 get_bucket_encryption, per-repo advisories) are the next rung — they need a params
convention before they can ship.
"""
import os

DESCRIPTORS = [
    # ---- AWS: configuration APIs that return a control's parameters verbatim ----
    {"surface": "cloud", "source_name": "AWS IAM account password policy",
     "collector_type": "aws",
     "config": {"service": "iam", "operation": "get_account_password_policy"},
     "text": "password complexity minimum length reuse prevention expiry credential authentication "
             "logical access control"},
    {"surface": "cloud", "source_name": "AWS IAM users and MFA enrolment",
     "collector_type": "aws",
     "config": {"service": "iam", "operation": "list_users"},
     "text": "multi factor authentication mfa enrolment user identity credential access deprovisioning"},
    {"surface": "cloud", "source_name": "AWS IAM account summary",
     "collector_type": "aws",
     "config": {"service": "iam", "operation": "get_account_summary"},
     "text": "identity inventory account entity policy count access keys"},
    {"surface": "cloud", "source_name": "AWS CloudTrail trail configuration",
     "collector_type": "aws",
     "config": {"service": "cloudtrail", "operation": "describe_trails"},
     "text": "logging audit trail monitoring event record retention multi region log file validation "
             "system operations incident"},
    {"surface": "cloud", "source_name": "AWS KMS key inventory",
     "collector_type": "aws",
     "config": {"service": "kms", "operation": "list_keys"},
     "text": "encryption key management rotation kms cryptographic confidential data at rest"},
    {"surface": "cloud", "source_name": "AWS GuardDuty detectors",
     "collector_type": "aws",
     "config": {"service": "guardduty", "operation": "list_detectors"},
     "text": "threat detection monitoring intrusion anomaly security incident response"},
    {"surface": "cloud", "source_name": "AWS Config rule evaluations",
     "collector_type": "aws",
     "config": {"service": "config", "operation": "describe_config_rules"},
     "text": "configuration compliance monitoring baseline rule continuous assessment change"},
    {"surface": "cloud", "source_name": "AWS S3 bucket inventory",
     "collector_type": "aws",
     "config": {"service": "s3", "operation": "list_buckets"},
     "text": "storage bucket inventory asset data classification confidential availability"},

    # Added after the discovery eval: availability, capacity and backup controls had no
    # descriptor to match against — the thesaurus had the words, the catalogue had no
    # check. These three groupings closed the largest recall gap (see eval_discovery.py).
    {"surface": "cloud", "source_name": "AWS CloudWatch alarm configuration",
     "collector_type": "aws",
     "config": {"service": "cloudwatch", "operation": "describe_alarms"},
     "text": "monitoring alerting threshold capacity performance utilisation dashboard notification operational"},
    {"surface": "cloud", "source_name": "AWS Auto Scaling group configuration",
     "collector_type": "aws",
     "config": {"service": "autoscaling", "operation": "describe_auto_scaling_groups"},
     "text": "capacity scaling elasticity instance count load performance resilience availability"},
    {"surface": "cloud", "source_name": "AWS Backup vault inventory",
     "collector_type": "aws",
     "config": {"service": "backup", "operation": "list_backup_vaults"},
     "text": "backup vault retention recovery restore continuity disaster protection schedule"},
    {"surface": "cloud", "source_name": "AWS RDS instance configuration",
     "collector_type": "aws",
     "config": {"service": "rds", "operation": "describe_db_instances"},
     "text": "database backup retention automated snapshot multi availability failover recovery storage"},
    {"surface": "cloud", "source_name": "AWS Elastic Load Balancer configuration",
     "collector_type": "aws",
     "config": {"service": "elbv2", "operation": "describe_load_balancers"},
     "text": "load balancing availability failover health check resilience redundancy traffic"},
    {"surface": "cloud", "source_name": "AWS Route 53 health checks",
     "collector_type": "aws",
     "config": {"service": "route53", "operation": "list_health_checks"},
     "text": "health check failover dns availability disaster recovery redundancy monitoring"},

    # ---- GitHub: version-control governance and CI/CD change control ----
    {"surface": "code", "source_name": "GitHub branch protection rules",
     "collector_type": "github",
     "config": {"endpoint": "repos/{owner}/{repo}/branches/{branch}/protection"},
     "text": "branch protection required pull request review approval status check signed commit "
             "code review change management access control"},
    {"surface": "code", "source_name": "GitHub organization two-factor requirement",
     "collector_type": "github",
     "config": {"endpoint": "orgs/{org}"},
     "text": "two factor authentication mfa enforcement organization member access identity"},
    {"surface": "code", "source_name": "GitHub Actions workflow inventory",
     "collector_type": "github",
     "config": {"endpoint": "repos/{owner}/{repo}/actions/workflows"},
     "text": "continuous integration automated testing pipeline build deploy change management "
             "release approval"},
    {"surface": "code", "source_name": "GitHub secret scanning alerts",
     "collector_type": "github",
     "config": {"endpoint": "repos/{owner}/{repo}/secret-scanning/alerts"},
     "text": "secret scanning credential leak exposure vulnerability detection remediation"},
    {"surface": "code", "source_name": "GitHub Dependabot alerts",
     "collector_type": "github",
     "config": {"endpoint": "repos/{owner}/{repo}/dependabot/alerts"},
     "text": "dependency vulnerability advisory patch third party component risk supply chain"},
]


def discover():
    """Asset dicts for the matchmaker. Descriptors are static, so there is no crawl —
    reaching the API happens later, when a candidate is bound and collected."""
    return list(DESCRIPTORS)


def credentials_present():
    """Whether a bound descriptor will collect real evidence or a labeled sample.
    The catalog is scanned either way — the collectors degrade to samples without
    credentials, exactly as the aws collector already does.

    'code' needs the placeholder vars too: a token alone can't resolve
    repos/{owner}/{repo}/..., so the github collector would still emit a sample."""
    cloud = bool(os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("AWS_PROFILE"))
    code = all(os.getenv(v) for v in ("GITHUB_TOKEN", "GITHUB_OWNER", "GITHUB_REPO"))
    return {"cloud": cloud, "code": bool(code)}
