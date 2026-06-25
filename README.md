# Cisco CX: Portable CDC Pipeline

Platform-agnostic Change Data Capture for 10M+ device telemetry records.  
Same code runs on **Snowflake SPCS** (cloud) and **EC2/Docker** (on-prem).

## Architecture

```
Previous Snapshot (Snowflake)  +  Current Snapshot (S3 Parquet)
                │                              │
                └──────────── CDC Engine ───────┘
                              │
                    Hash → Full Outer Join → Classify (I/U/D)
                              │
                    43,952 changed rows → Snowflake / PostgreSQL
```

## Frameworks

| Framework | Engine | Cloud Backend | On-Prem Backend |
|-----------|--------|---------------|-----------------|
| **Polars** | Rust | Local (PyArrow) | Local (PyArrow) |
| **PySpark** | JVM | Local + S3A native | Local + S3A native |
| **Ibis/DuckDB** | C++ | DuckDB embedded | DuckDB embedded |
| **Ibis/Snowflake** | SQL | Snowflake Warehouse | DuckDB (portable) |

## Results

### Snowflake SPCS (HIGHMEM_X64_L, 28 cores, 128GB)

| Framework | Total |
|-----------|-------|
| Polars | 39.5s |
| PySpark | 41.9s |
| Ibis/DuckDB | 47.2s |

### EC2 On-Prem (r5.4xlarge, 16 cores, 124GB)

| Framework | Total |
|-----------|-------|
| Polars | 34.7s |
| Ibis/Snowflake | 45.4s |
| PySpark | 53.6s |
| Ibis/DuckDB | 70.6s |

All frameworks produce **identical results**: 25,000 inserts | 18,952 updates | 5,000 deletes = 43,952 rows.

## Repository Structure

```
├── notebooks/
│   ├── source/                  # Portable notebook code
│   │   ├── nb_polars_cdc.ipynb
│   │   ├── nb_spark_iceberg_cdc.ipynb
│   │   ├── nb_ibis_cdc.ipynb          # Ibis + DuckDB backend
│   │   └── nb_ibis_snowflake_cdc.ipynb # Ibis + Snowflake/DuckDB portable
│   ├── ec2-results/             # Executed on EC2 (on-prem)
│   └── spcs-results/            # Executed on Snowflake SPCS (cloud)
├── report/
│   └── cisco_cx_cdc_comparison.html   # Benchmark report
├── generate_s3_parquet.py       # Generate 10M test data
└── PILOT_PREREQUISITES.md       # Snowflake setup guide
```

## Quick Start

1. Review [PILOT_PREREQUISITES.md](PILOT_PREREQUISITES.md) for Snowflake setup
2. Generate test data: `python generate_s3_parquet.py`
3. Run any notebook on SPCS or EC2 — same code, same results
