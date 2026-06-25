import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import boto3
import os
import time
import io

S3_BUCKET = "cisco-cx-cdc-pilot"
S3_PREFIX_PREV = "cdc_data/prev_snapshot"
S3_PREFIX_CURR = "cdc_data/curr_snapshot"

TOTAL_ROWS = 10_000_000
N_INSERTS = 25_000
N_UPDATES = 20_000
N_DELETES = 5_000

COMPARE_COLS = ['software_version', 'cpu_utilization', 'memory_utilization',
                'critical_bugs_count', 'contract_status', 'ip_address']

print(f"Generating {TOTAL_ROWS:,} row previous snapshot...")
np.random.seed(42)
t0 = time.time()

prev_data = {
    'device_id': np.arange(TOTAL_ROWS).astype(str),
    'customer_id': np.random.randint(1, 10001, TOTAL_ROWS).astype(str),
    'software_version': np.random.choice(['17.6.4', '17.6.3', '17.3.5', '16.12.8', '16.9.9'], TOTAL_ROWS),
    'cpu_utilization': np.round(np.random.uniform(5, 95, TOTAL_ROWS), 2),
    'memory_utilization': np.round(np.random.uniform(10, 90, TOTAL_ROWS), 2),
    'critical_bugs_count': np.random.randint(0, 10, TOTAL_ROWS),
    'contract_status': np.random.choice(['ACTIVE', 'EXPIRED', 'EXPIRING_SOON'], TOTAL_ROWS),
    'ip_address': np.array([f'10.{a}.{b}.{c}' for a, b, c in zip(
        np.random.randint(1, 255, TOTAL_ROWS),
        np.random.randint(1, 255, TOTAL_ROWS),
        np.random.randint(1, 255, TOTAL_ROWS))]),
    'product_family': np.random.choice(['Catalyst 9000', 'Nexus 9000', 'ISR 4000', 'ASR 9000', 'Firepower 4100'], TOTAL_ROWS),
}
print(f"Previous snapshot generated: {time.time()-t0:.1f}s")

t0 = time.time()
curr_data = {k: v.copy() for k, v in prev_data.items()}
update_idx = np.random.choice(TOTAL_ROWS, N_UPDATES, replace=False)
curr_data['cpu_utilization'][update_idx[:7_000]] = np.round(np.random.uniform(5, 95, 7_000), 2)
curr_data['memory_utilization'][update_idx[7_000:14_000]] = np.round(np.random.uniform(10, 90, 7_000), 2)
curr_data['software_version'][update_idx[14_000:18_000]] = np.random.choice(['17.6.4', '17.6.3'], 4_000)
curr_data['critical_bugs_count'][update_idx[18_000:]] = np.random.randint(0, 10, 2_000)

delete_idx = np.random.choice(np.setdiff1d(np.arange(TOTAL_ROWS), update_idx), N_DELETES, replace=False)
keep_mask = np.ones(TOTAL_ROWS, dtype=bool)
keep_mask[delete_idx] = False
for k in curr_data:
    curr_data[k] = curr_data[k][keep_mask]

new_data = {
    'device_id': np.arange(TOTAL_ROWS, TOTAL_ROWS + N_INSERTS).astype(str),
    'customer_id': np.random.randint(1, 10001, N_INSERTS).astype(str),
    'software_version': np.random.choice(['17.6.4', '17.6.3', '17.3.5'], N_INSERTS),
    'cpu_utilization': np.round(np.random.uniform(5, 95, N_INSERTS), 2),
    'memory_utilization': np.round(np.random.uniform(10, 90, N_INSERTS), 2),
    'critical_bugs_count': np.random.randint(0, 10, N_INSERTS),
    'contract_status': np.random.choice(['ACTIVE', 'EXPIRED', 'EXPIRING_SOON'], N_INSERTS),
    'ip_address': np.array([f'10.{a}.{b}.{c}' for a, b, c in zip(
        np.random.randint(1, 255, N_INSERTS), np.random.randint(1, 255, N_INSERTS), np.random.randint(1, 255, N_INSERTS))]),
    'product_family': np.random.choice(['Catalyst 9000', 'Nexus 9000', 'ISR 4000', 'ASR 9000', 'Firepower 4100'], N_INSERTS),
}
for k in curr_data:
    curr_data[k] = np.concatenate([curr_data[k], new_data[k]])
print(f"Current snapshot generated: {time.time()-t0:.1f}s")
print(f"Previous: {TOTAL_ROWS:,} | Current: {len(curr_data['device_id']):,}")
print(f"Changes: {N_INSERTS:,} inserts + {N_UPDATES:,} updates + {N_DELETES:,} deletes = {N_INSERTS+N_UPDATES+N_DELETES:,} total")

s3 = boto3.client('s3')

def upload_parquet_to_s3(data_dict, bucket, prefix, chunk_size=1_000_000):
    table = pa.table(data_dict)
    total = len(table)
    n_files = 0
    t0 = time.time()
    for i in range(0, total, chunk_size):
        chunk = table.slice(i, min(chunk_size, total - i))
        buf = io.BytesIO()
        pq.write_table(chunk, buf)
        buf.seek(0)
        key = f"{prefix}/part-{n_files:05d}.parquet"
        s3.upload_fileobj(buf, bucket, key)
        n_files += 1
    elapsed = time.time() - t0
    print(f"  Uploaded {n_files} files ({total:,} rows) to s3://{bucket}/{prefix}/ in {elapsed:.1f}s")
    return n_files

print("\nUploading to S3...")
upload_parquet_to_s3(prev_data, S3_BUCKET, S3_PREFIX_PREV)
upload_parquet_to_s3(curr_data, S3_BUCKET, S3_PREFIX_CURR)
print("\nDone! Data available at:")
print(f"  s3://{S3_BUCKET}/{S3_PREFIX_PREV}/")
print(f"  s3://{S3_BUCKET}/{S3_PREFIX_CURR}/")
