import asyncio
from gcp_metrics_monitor import GCPMetricsMonitor

async def main():
    m = GCPMetricsMonitor()
    print("testing system metrics")
    for mt in [
        'agent.googleapis.com/cpu/utilization',
        'agent.googleapis.com/memory/percent_used',
        'agent.googleapis.com/disk/percent_used',
    ]:
        v = await m.get_system_metric(mt, hours=1)
        print(mt, '->', v)

if __name__ == '__main__':
    asyncio.run(main())
