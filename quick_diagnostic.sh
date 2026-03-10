#!/bin/bash

# Simple metrics diagnostic
cd /home/e193752468/kkgroup

echo "=== GCP Metrics Diagnostic ==="
echo ""
echo "[1] Service Status:"
sudo systemctl status bot.service --no-pager | head -5

echo ""
echo "[2] Recent Logs (DASHBOARD|METRICS|Error):"
sudo journalctl -u bot.service -n 100 | grep -E 'DASHBOARD|METRICS|Error|cannot import' | tail -20

echo ""
echo "[3] Python Import Test:"
/home/e193752468/kkgroup/venv/bin/python3 << 'EOF'
try:
    from status_dashboard import GCP_METRICS_ENABLED, metrics_cache
    print(f"✓ Got metrics_cache: {metrics_cache}")
    print(f"✓ GCP_METRICS_ENABLED: {GCP_METRICS_ENABLED}")
except Exception as e:
    print(f"✗ Import failed: {e}")
EOF

echo ""
echo "[4] GCP Monitor Test:"
/home/e193752468/kkgroup/venv/bin/python3 << 'EOF'
try:
    from gcp_metrics_monitor import GCPMetricsMonitor
    m = GCPMetricsMonitor(project_id="kkgroup")
    print(f"✓ GCPMetricsMonitor available: {m.available}")
except Exception as e:
    print(f"✗ GCPMetricsMonitor failed: {e}")
EOF

echo ""
echo "[5] Check env vars:"
grep -E 'DASHBOARD_|METRICS' /home/e193752468/kkgroup/.env | head -5

echo ""
echo "=== Done ==="
