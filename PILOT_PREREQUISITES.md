# Cisco CX CDC Pilot — Snowflake Prerequisites Guide

## Overview

This document lists all Snowflake objects, permissions, and configurations required to execute the portable CDC pipeline (Ibis/Snowflake backend) at a customer environment.

---

## 1. Snowflake Account Requirements

| Requirement | Details |
|-------------|---------|
| **Edition** | Enterprise or Business Critical (for compute pools / SPCS) |
| **Cloud Region** | Same region as S3 bucket for lowest latency |
| **Warehouse Size** | X-Large recommended for 10M+ rows |

---

## 2. Database & Schema Setup

```sql
-- Create database and schemas
CREATE DATABASE IF NOT EXISTS CISCO_CX_PILOT;

CREATE SCHEMA IF NOT EXISTS CISCO_CX_PILOT.LANDING_ZONE;
CREATE SCHEMA IF NOT EXISTS CISCO_CX_PILOT.PROCESSED;
CREATE SCHEMA IF NOT EXISTS CISCO_CX_PILOT.PUBLIC;
```

---

## 3. Warehouse

```sql
CREATE WAREHOUSE IF NOT EXISTS CDC_WAREHOUSE
  WAREHOUSE_SIZE = 'X-LARGE'
  AUTO_SUSPEND = 300
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE;
```

---

## 4. Storage Integration (S3 Access)

```sql
CREATE STORAGE INTEGRATION CISCO_S3_INTEGRATION
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'S3'
  ENABLED = TRUE
  STORAGE_AWS_ROLE_ARN = 'arn:aws:iam::<CUSTOMER_AWS_ACCOUNT>:role/<ROLE_NAME>'
  STORAGE_ALLOWED_LOCATIONS = ('s3://<CUSTOMER_BUCKET>/');

-- After creation, retrieve the Snowflake IAM user and external ID:
DESCRIBE INTEGRATION CISCO_S3_INTEGRATION;
-- Note: STORAGE_AWS_IAM_USER_ARN and STORAGE_AWS_EXTERNAL_ID
-- Customer must update their IAM role trust policy with these values
```

### AWS IAM Trust Policy (Customer Action)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "<STORAGE_AWS_IAM_USER_ARN from DESCRIBE above>"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "<STORAGE_AWS_EXTERNAL_ID from DESCRIBE above>"
        }
      }
    }
  ]
}
```

The IAM role must have `AmazonS3ReadOnlyAccess` (or scoped to the bucket prefix).

---

## 5. External Stage

```sql
CREATE STAGE IF NOT EXISTS CISCO_CX_PILOT.LANDING_ZONE.CDC_S3_STAGE
  STORAGE_INTEGRATION = CISCO_S3_INTEGRATION
  URL = 's3://<CUSTOMER_BUCKET>/<PREFIX>/'
  FILE_FORMAT = (TYPE = 'PARQUET');
```

Verify access:
```sql
LIST @CISCO_CX_PILOT.LANDING_ZONE.CDC_S3_STAGE;
```

---

## 6. Tables

```sql
-- Previous snapshot table (represents yesterday's device state)
CREATE TABLE IF NOT EXISTS CISCO_CX_PILOT.PROCESSED.PREV_SNAPSHOT_STAGING (
    DEVICE_ID VARCHAR,
    CUSTOMER_ID VARCHAR,
    HOSTNAME VARCHAR,
    SOFTWARE_VERSION VARCHAR,
    CPU_UTILIZATION FLOAT,
    MEMORY_UTILIZATION FLOAT,
    CRITICAL_BUGS_COUNT NUMBER,
    CONTRACT_STATUS VARCHAR,
    IP_ADDRESS VARCHAR,
    LAST_SEEN TIMESTAMP_NTZ
);

-- CDC result table
CREATE TABLE IF NOT EXISTS CISCO_CX_PILOT.PROCESSED.IBIS_SF_CDC_RESULT (
    DEVICE_ID VARCHAR,
    CUSTOMER_ID VARCHAR,
    HOSTNAME VARCHAR,
    SOFTWARE_VERSION VARCHAR,
    CPU_UTILIZATION FLOAT,
    MEMORY_UTILIZATION FLOAT,
    CRITICAL_BUGS_COUNT NUMBER,
    CONTRACT_STATUS VARCHAR,
    IP_ADDRESS VARCHAR,
    LAST_SEEN TIMESTAMP_NTZ,
    CDC_ACTION VARCHAR
);
```

---

## 7. Initial Data Load (One-Time)

Load the previous snapshot from S3 into Snowflake:

```sql
COPY INTO CISCO_CX_PILOT.PROCESSED.PREV_SNAPSHOT_STAGING
FROM @CISCO_CX_PILOT.LANDING_ZONE.CDC_S3_STAGE/prev_snapshot/
FILE_FORMAT = (TYPE = 'PARQUET')
MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
FORCE = TRUE;
```

---

## 8. Compute Pool (for SPCS Notebook Execution)

```sql
CREATE COMPUTE POOL IF NOT EXISTS CISCO_CDC_POOL
  MIN_NODES = 1
  MAX_NODES = 3
  INSTANCE_FAMILY = HIGHMEM_X64_L
  AUTO_SUSPEND_SECS = 300
  AUTO_RESUME = TRUE;
```

---

## 9. External Access Integrations (for pip install in SPCS)

```sql
CREATE OR REPLACE NETWORK RULE PYPI_NETWORK_RULE
  MODE = EGRESS
  TYPE = HOST_PORT
  VALUE_LIST = ('pypi.org', 'files.pythonhosted.org');

CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION PYPI_ACCESS_INTEGRATION
  ALLOWED_NETWORK_RULES = (PYPI_NETWORK_RULE)
  ENABLED = TRUE;

-- For general external access (S3, etc.)
CREATE OR REPLACE NETWORK RULE ALLOW_ALL_RULE
  MODE = EGRESS
  TYPE = HOST_PORT
  VALUE_LIST = ('0.0.0.0:443', '0.0.0.0:80');

CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION ALLOW_ALL_EAI
  ALLOWED_NETWORK_RULES = (ALLOW_ALL_RULE)
  ENABLED = TRUE;
```

---

## 10. Notebook Deployment

```sql
-- Create internal stage for notebook files
CREATE STAGE IF NOT EXISTS CISCO_CX_PILOT.PUBLIC.NOTEBOOK_STAGE;

-- Upload notebook (via snow CLI or PUT)
-- PUT file:///path/to/nb_ibis_snowflake_cdc.ipynb @CISCO_CX_PILOT.PUBLIC.NOTEBOOK_STAGE;

-- Create workspace notebook
CREATE OR REPLACE NOTEBOOK CISCO_CX_PILOT.PUBLIC.NB_IBIS_SNOWFLAKE_CDC
  FROM '@CISCO_CX_PILOT.PUBLIC.NOTEBOOK_STAGE'
  MAIN_FILE = 'nb_ibis_snowflake_cdc.ipynb'
  QUERY_WAREHOUSE = 'CDC_WAREHOUSE'
  COMPUTE_POOL = 'CISCO_CDC_POOL'
  RUNTIME_NAME = 'SYSTEM$BASIC_RUNTIME'
  EXTERNAL_ACCESS_INTEGRATIONS = ('ALLOW_ALL_EAI', 'PYPI_ACCESS_INTEGRATION');

-- Activate live version
ALTER NOTEBOOK CISCO_CX_PILOT.PUBLIC.NB_IBIS_SNOWFLAKE_CDC ADD LIVE VERSION FROM LAST;
```

---

## 11. Network Policy (if applicable)

If the customer has a network policy restricting IPs, ensure the EC2/on-prem IPs are whitelisted for the connector to reach Snowflake:

```sql
-- Check existing policy
SHOW NETWORK POLICIES;

-- Add on-prem IPs
ALTER NETWORK POLICY <POLICY_NAME> SET ALLOWED_IP_LIST = (
  '<EXISTING_IPS>',
  '<ON_PREM_IP_1>/32',
  '<ON_PREM_IP_2>/32'
);
```

---

## 12. Role & Grants (Least Privilege)

```sql
CREATE ROLE IF NOT EXISTS CISCO_CDC_ROLE;

-- Database access
GRANT USAGE ON DATABASE CISCO_CX_PILOT TO ROLE CISCO_CDC_ROLE;
GRANT USAGE ON SCHEMA CISCO_CX_PILOT.LANDING_ZONE TO ROLE CISCO_CDC_ROLE;
GRANT USAGE ON SCHEMA CISCO_CX_PILOT.PROCESSED TO ROLE CISCO_CDC_ROLE;
GRANT USAGE ON SCHEMA CISCO_CX_PILOT.PUBLIC TO ROLE CISCO_CDC_ROLE;

-- Stage access
GRANT USAGE ON STAGE CISCO_CX_PILOT.LANDING_ZONE.CDC_S3_STAGE TO ROLE CISCO_CDC_ROLE;
GRANT USAGE ON STAGE CISCO_CX_PILOT.PUBLIC.NOTEBOOK_STAGE TO ROLE CISCO_CDC_ROLE;

-- Table access
GRANT SELECT, INSERT, TRUNCATE, DELETE ON ALL TABLES IN SCHEMA CISCO_CX_PILOT.PROCESSED TO ROLE CISCO_CDC_ROLE;
GRANT CREATE TABLE ON SCHEMA CISCO_CX_PILOT.PROCESSED TO ROLE CISCO_CDC_ROLE;

-- Warehouse access
GRANT USAGE ON WAREHOUSE CDC_WAREHOUSE TO ROLE CISCO_CDC_ROLE;

-- Compute pool
GRANT USAGE ON COMPUTE POOL CISCO_CDC_POOL TO ROLE CISCO_CDC_ROLE;

-- Integration access
GRANT USAGE ON INTEGRATION CISCO_S3_INTEGRATION TO ROLE CISCO_CDC_ROLE;
GRANT USAGE ON INTEGRATION PYPI_ACCESS_INTEGRATION TO ROLE CISCO_CDC_ROLE;
GRANT USAGE ON INTEGRATION ALLOW_ALL_EAI TO ROLE CISCO_CDC_ROLE;

-- Assign to user
GRANT ROLE CISCO_CDC_ROLE TO USER <CDC_SERVICE_USER>;
```

---

## 13. Service User (for EC2/On-Prem Connector)

```sql
CREATE USER IF NOT EXISTS CDC_SERVICE_USER
  PASSWORD = '<STRONG_PASSWORD>'
  DEFAULT_ROLE = 'CISCO_CDC_ROLE'
  DEFAULT_WAREHOUSE = 'CDC_WAREHOUSE'
  MUST_CHANGE_PASSWORD = FALSE;

GRANT ROLE CISCO_CDC_ROLE TO USER CDC_SERVICE_USER;
```

For key-pair auth (recommended for automation):
```sql
ALTER USER CDC_SERVICE_USER SET RSA_PUBLIC_KEY = '<PUBLIC_KEY>';
```

---

## 14. On-Prem / EC2 Requirements

| Component | Details |
|-----------|---------|
| **Python** | 3.10+ |
| **Packages** | `pip install ibis-framework[snowflake] pyarrow snowflake-connector-python[pandas]` |
| **Snowflake Connection** | `~/.snowflake/connections.toml` with account, user, key-pair or password |
| **Network** | Outbound HTTPS (443) to `<account>.snowflakecomputing.com` |

### connections.toml (on-prem)

```toml
[default]
account = "<ORG>-<ACCOUNT>"
user = "CDC_SERVICE_USER"
authenticator = "snowflake"
private_key_path = "/path/to/rsa_key.p8"
database = "CISCO_CX_PILOT"
schema = "PROCESSED"
warehouse = "CDC_WAREHOUSE"
role = "CISCO_CDC_ROLE"
```

---

## 15. S3 Data Layout (Expected by Pipeline)

```
s3://<BUCKET>/<PREFIX>/
├── prev_snapshot/
│   ├── part-00000.parquet
│   ├── part-00001.parquet
│   └── ...
└── curr_snapshot/
    ├── part-00000.parquet
    ├── part-00001.parquet
    └── ...
```

Each parquet file must contain columns:
`device_id, customer_id, hostname, software_version, cpu_utilization, memory_utilization, critical_bugs_count, contract_status, ip_address, last_seen`

---

## 16. Execution Checklist

- [ ] Snowflake account provisioned (Enterprise edition)
- [ ] Database, schemas, tables created
- [ ] Storage integration created + IAM trust policy updated
- [ ] External stage created and `LIST` returns files
- [ ] Warehouse created and sized appropriately
- [ ] Compute pool created (for SPCS)
- [ ] External access integrations created
- [ ] Network policy allows on-prem IPs
- [ ] Role and grants configured
- [ ] Service user created (key-pair auth for automation)
- [ ] Previous snapshot loaded via COPY INTO
- [ ] Notebook uploaded and deployed to Workspace
- [ ] `connections.toml` configured on on-prem machines
- [ ] Python packages installed on on-prem machines
- [ ] End-to-end test: Run notebook, verify 43,952 changed rows detected

---

## 17. Estimated Timeline

| Phase | Duration | Actions |
|-------|----------|---------|
| Snowflake Setup | 1 hour | Create all objects (DB, schemas, WH, integrations, stage) |
| AWS IAM Config | 30 min | Update trust policy, verify S3 access |
| Data Upload | 30 min | Upload parquet files to S3, COPY INTO prev_snapshot |
| Notebook Deploy | 15 min | Upload to Workspace, configure compute pool |
| E2E Validation | 15 min | Run notebook, verify CDC counts |
| **Total** | **~2.5 hours** | |
