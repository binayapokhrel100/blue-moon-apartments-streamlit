
# Blue Moon Apartments
## Administrator Security Handover

**Project:** Blue Moon Apartments
**Phase:** Sprint 11B — Administrator Security
**Final Sprint:** 11B.8D
**Date:** October 2026

**Development status:** Completed and regression-tested
**Production status:** Deployment approval pending

---

## 1. Technology Stack

- Python 3.12
- Streamlit
- SQLAlchemy 2.x
- SQLite
- bcrypt password hashing
- pytest 9.0.3
- pip-audit

---

## 2. Administrator Security Architecture

### Authentication

The application provides separate administrator and
resident authentication workflows.

Security controls include:

- Password verification using stored password hashes
- Active account and employee verification
- Authentication failure throttling
- Temporary login lockouts
- Database-backed credential version checks
- Session invalidation following credential changes
- Mandatory initial administrator password changes

### Role-Based Access Control

Administrator authorization is enforced through
backend service permissions.

The supported administrative roles include:

- Super Admin
- Property Manager
- Finance Manager
- Maintenance Manager
- Leasing Agent
- Auditor

Permission checks are implemented in backend services,
not solely in the Streamlit interface.

### Administrator Account Management

Authorized Super Admins can:

- Create administrator accounts
- Assign and change administrator roles
- Activate and deactivate administrator accounts
- Review role-assignment history
- Perform authorized account recovery

Administrative changes are recorded in audit events.

### Password Recovery

Password recovery requires authorized identity
verification and an approved delivery method.

Reset codes are:

- Cryptographically generated
- Stored as hashes
- Time-limited
- Single-use
- Protected by authentication throttling

Successful recovery invalidates outdated credential
sessions.

### Emergency Super Admin Recovery

Offline emergency recovery is provided for the
existing, sole active Super Admin.

The procedure requires a separately provisioned
emergency recovery key.

Emergency recovery:

- Cannot assign new administrator roles
- Cannot create new administrators
- Does not directly modify the account password
- Consumes the emergency key
- Creates dedicated recovery audit records
- Issues a short-lived code for standard redemption

The emergency recovery service must never be exposed
through a public Streamlit page or HTTP endpoint.

### Security Monitoring

The Super Admin Security Monitoring dashboard displays:

- Failed administrator authentication events
- Blocked authentication events
- Current administrator lockouts
- Password reset requests
- Completed password recoveries
- Manual administrator unlocks
- Emergency recovery activity
- Chronological security audit records

The monitoring service is read-only.

### Audit Retention

Security event retention is managed using controlled,
explicitly confirmed cleanup procedures.

Permanent administrator role-audit and emergency
recovery records must be preserved according to
the application's retention policy.

---

## 3. Testing Evidence

Final reported automated regression suite:

339 tests passed
0 failures

Additional completed checks:

- Python syntax validation
- Git whitespace validation
- SQLite foreign-key integrity check
- Dependency compatibility verification
- Dependency vulnerability scan
- Authentication and RBAC regression tests
- Password recovery and concurrency tests
- Emergency recovery tests
- Database backup and disposable restore tests

These results establish automated regression-test
evidence, not an independent security certification.

---

## 4. Database Backup

Configured SQLite database:

blue_moon.db

A verified application database backup was created
on October 15, 2026 (UTC).

Tables verified: 24
Backup size: 270,336 bytes

The backup was stored outside the Git repository.

Backup preview:

    python -m scripts.database_backup

Create a verified backup:

    python -m scripts.database_backup --backup

Verify an existing backup:

    python -m scripts.database_backup --verify PATH_TO_BACKUP

Restoration verification uses a disposable SQLite
database and does not overwrite the live database.

Backup files contain sensitive application data and
must be stored with encryption and restricted access.

---

## 5. Configuration Security

Development configuration and production configuration
must remain separate.

Production requires explicitly configured:

- APP_ENV
- DATABASE_URL
- SECRET_KEY

Production must not use default development secrets.

The repository excludes environment secrets, local
databases, and backup files through .gitignore.

Actual secrets must never be committed to Git.

---

## 6. Administrator Provisioning

Initial administrator account seeding is restricted
to an explicitly authorized development setup.

The initial Super Admin bootstrap requires a trusted
terminal, explicit authorization, and an existing
active administrator.

Bootstrap history is checked to prevent repeating
the initial Super Admin assignment.

These provisioning scripts are not ordinary account
recovery tools and must not be exposed through the
application UI.

---

## 7. Operational Security Procedures

Daily operations:

- Review authentication failures and blocked attempts
- Investigate unusual administrator account activity
- Monitor administrator access changes

Periodic operations:

- Verify backup creation and restore capability
- Review administrator role assignments
- Review dependency vulnerability findings
- Confirm recovery keys remain securely stored
- Test disaster recovery in a non-production environment

After an emergency recovery:

- Redeem the reset code promptly
- Confirm existing sessions have been invalidated
- Provision a replacement emergency key
- Review the recovery audit event
- Document the incident and authorization

---

## 8. Production Release Requirements

Before production deployment, confirm:

- HTTPS and secure network configuration
- Protected production environment variables
- Restricted database-file access
- Encrypted backups with defined retention
- Scheduled backup automation
- Restore drills using a staging environment
- Host and operating-system patch management
- Dependency vulnerability scanning in CI
- Secrets scanning before Git commits
- Reviewed source-code changes
- Administrator access review
- Monitoring and incident-response procedures
- Production session and authentication behavior
- Secure deployment and rollback procedures

Do not interpret local automated test success
as final production deployment approval.

---

## 9. Handover Status

Administrator security development:
COMPLETE

Automated regression testing:
PASSED

Database backup and disposable restoration:
VERIFIED

Dependency vulnerability review:
PASSED AT TIME OF REVIEW

Repository accidental-file cleanup:
COMPLETE

Source control release commit:
PENDING

Production infrastructure verification:
PENDING

Final production approval:
PENDING
