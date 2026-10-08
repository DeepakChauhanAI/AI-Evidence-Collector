"""Starter SOC 2 evidence checklist. Modeled on the Trust Services Criteria and the
way GRC platforms (Drata, Vanta) phrase their evidence requests: each item names the
control and the specific artifact an auditor expects. Seeded on demand so a new
install has something real to work with before a GRC export is imported."""

SOC2_STARTER = [
    ("CC1.1", "Board oversight of security",
     "Provide the most recent board or security-committee meeting minutes showing oversight of the information security program."),
    ("CC1.4", "Code of conduct acknowledgement",
     "Provide the current code of conduct and evidence that personnel have acknowledged it."),
    ("CC2.1", "Security policies published",
     "Provide the current information security policy set and evidence it is communicated to all personnel."),
    ("CC2.2", "Security awareness training",
     "Provide completion records for annual security awareness training covering all employees."),
    ("CC5.2", "Access control policy",
     "Provide the logical access control policy governing provisioning, review, and revocation."),
    ("CC6.1", "Logical access provisioning",
     "Provide a user access listing for production systems showing role-based entitlements."),
    ("CC6.2", "Access deprovisioning on termination",
     "Provide evidence that terminated users had access revoked within the defined SLA."),
    ("CC6.3", "Periodic access reviews",
     "Provide the most recent quarterly user access review with reviewer sign-off."),
    ("CC6.6", "Multi-factor authentication",
     "Provide a configuration export showing MFA is enforced for all remote and administrative access."),
    ("CC6.7", "Encryption in transit",
     "Provide TLS configuration or scan results confirming data in transit is encrypted."),
    ("CC6.8", "Encryption at rest",
     "Provide configuration evidence that production datastores encrypt data at rest."),
    ("CC7.1", "Vulnerability scanning",
     "Provide the most recent vulnerability scan report for production infrastructure."),
    ("CC7.2", "Security monitoring and alerting",
     "Provide a sample of security monitoring alerts and the logging configuration that generates them."),
    ("CC7.3", "Incident response",
     "Provide the incident response plan and evidence of the last incident response test or real incident handling."),
    ("CC7.5", "Backup and recovery",
     "Provide backup job configuration and evidence of a successful recovery test."),
    ("CC8.1", "Change management",
     "Provide a sample of change tickets showing approval, testing, and deployment for production changes."),
    ("CC9.2", "Vendor risk management",
     "Provide the vendor inventory and the most recent risk reviews for critical third parties."),
    ("A1.1", "Capacity monitoring",
     "Provide dashboards or reports showing production capacity and performance are monitored against thresholds."),
    ("A1.2", "Availability / disaster recovery",
     "Provide the disaster recovery plan and evidence of the last DR test."),
    ("C1.1", "Data classification",
     "Provide the data classification policy and evidence confidential data is identified and protected accordingly."),
]


def seed_controls(db, Control):
    """Insert the starter set, skipping SOC2 codes that already exist. Returns inserted controls."""
    existing = {c.code for c in db.query(Control).filter(Control.framework == "SOC2").all()}
    created = []
    for code, name, description in SOC2_STARTER:
        if code in existing:
            continue
        ctrl = Control(framework="SOC2", code=code, name=name, description=description)
        db.add(ctrl)
        created.append(ctrl)
    db.commit()
    return created
