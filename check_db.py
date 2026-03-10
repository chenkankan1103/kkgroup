from metrics_database import MetricsDatabase

db = MetricsDatabase()
print(f"Egress points: {db.get_data_count('egress_timeseries')}")
print(f"System stats: {db.get_data_count('system_stats')}")
print(f"Billing: {db.get_data_count('billing_data')}")
print(f"Monthly egress: {db.get_data_count('monthly_egress')}")

# 查看最新的出站流量數據
egress_data = db.get_egress_data(hours=6)
if egress_data:
    print(f"\nLatest egress data (6h):")
    for point in egress_data[-5:]:
        print(f"  {point['timestamp']}: {point['mb']:.2f} MB")
