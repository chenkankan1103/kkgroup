import asyncio
from gcp_metrics_monitor import GCPMetricsMonitor
from google.cloud import monitoring_v3

async def main():
    m = GCPMetricsMonitor()
    print("testing system metrics")
    # try the three expected metrics
    for mt in [
        'agent.googleapis.com/cpu/utilization',
        'agent.googleapis.com/memory/percent_used',
        'agent.googleapis.com/disk/percent_used',
    ]:
        v = await m.get_system_metric(mt, hours=1)
        print(mt, '->', v)
    print("\nlisting some agent time series types:")
    # list time series to see what's available
    now = __import__('datetime').datetime.utcnow()
    start = now - __import__('datetime').timedelta(hours=6)
    from google.protobuf.timestamp_pb2 import Timestamp
    start_ts = Timestamp(); start_ts.FromDatetime(start)
    end_ts = Timestamp(); end_ts.FromDatetime(now)
    interval = monitoring_v3.TimeInterval({"start_time": start_ts, "end_time": end_ts})
    req = m.monitoring_v3.ListTimeSeriesRequest(
        name=f"projects/{m.project_id}",
        filter='metric.type="agent.googleapis.com"',
        interval=interval,
        page_size=10
    )
    results = list(m.metric_client.list_time_series(request=req))
    for series in results:
        print('series:', series.metric.type, 'points:', len(series.points))

if __name__ == '__main__':
    asyncio.run(main())
