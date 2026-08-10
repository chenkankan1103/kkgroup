#!/usr/bin/env python3
"""
Complete VM fix script for KKGroup uibot service.
Run this on the VM to fix:
1. anime_votes missing video_sn column (database migration)
2. anime_name NOT NULL constraint failure (fixed in code)
3. Restart uibot service
"""

import subprocess
import sys
import os
import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PROJECT_DIR = Path("/home/e193752468/kkgroup")


def run_command(cmd, cwd=None, timeout=60, capture=True):
    """Run shell command and return (success, stdout, stderr)"""
    try:
        if capture:
            result = subprocess.run(
                cmd, shell=True, cwd=cwd or PROJECT_DIR,
                capture_output=True, text=True, timeout=timeout
            )
            return result.returncode == 0, result.stdout, result.stderr
        else:
            result = subprocess.run(cmd, shell=True, cwd=PROJECT_DIR, timeout=timeout)
            return True, "", ""
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)


def check_service_status(service_name):
    """Check if a service is active"""
    success, stdout, stderr = run_command(f"systemctl is-active {service_name}", timeout=10)
    return "active" in stdout.strip()


def main():
    logger.info("=" * 60)
    logger.info("🔧 KKGroup VM Fix Script Starting")
    logger.info("=" * 60)

    # Step 1: Check current status
    logger.info("📋 Step 1: Checking current service status...")
    success, stdout, stderr = run_command("systemctl status uibot.service --no-pager", timeout=10)
    logger.info(f"uibot status: {stdout[:500]}")
    if stderr:
        logger.warning(f"stderr: {stderr}")

    # Step 2: Run database migration
    logger.info("\n📋 Step 2: Running database migration...")
    migration_script = PROJECT_DIR / "scripts" / "migrate_anime_db.py"
    if migration_script.exists():
        success, stdout, stderr = run_command(f"python3 {migration_script}", timeout=120)
        if success:
            logger.info("✅ Database migration completed")
        else:
            logger.error(f"❌ Migration failed: {stderr}")
            return 1
    else:
        logger.error(f"Migration script not found at {migration_script}")
        return 1

    # Step 3: Pull latest code
    logger.info("\n📋 Step 3: Pulling latest code from GitHub...")
    success, stdout, stderr = run_command("git fetch && git reset --hard origin/main", timeout=60)
    if success:
        logger.info("✅ Code updated")
    else:
        logger.error(f"❌ Git pull failed: {stderr}")
        return 1

    # Step 4: Restart services
    logger.info("\n📋 Step 4: Restarting services...")
    services = ["bot.service", "shopbot.service", "uibot.service", "auto-self-heal.service"]

    # Daemon reload
    success, stdout, stderr = run_command("sudo systemctl daemon-reload", timeout=30)
    logger.info(f"Daemon reload: {'✅' if success else '❌'}")

    for service in services:
        logger.info(f"  Restarting {service}...")
        success, stdout, stderr = run_command(f"sudo systemctl restart {service}", timeout=60)
        if success:
            logger.info(f"  ✅ {service} restarted")
        else:
            logger.error(f"  ❌ {service} failed: {stderr}")

    # Step 5: Wait and verify
    logger.info("\n⏳ Waiting for services to stabilize...")
    time.sleep(10)

    # Step 6: Verify services
    logger.info("\n📋 Step 5: Verifying service status...")
    services = ["bot.service", "shopbot.service", "uibot.service", "auto-self-heal.service", "kkgroup-api.service"]
    all_ok = True
    for service in services:
        success, stdout, stderr = run_command(f"systemctl is-active {service}", timeout=10)
        status = "active" if "active" in stdout else "inactive"
        status_icon = "✅" if "active" in stdout else "❌"
        logger.info(f"  {status_icon} {service}: {stdout.strip()}")
        if "active" not in stdout:
            all_ok = False

    # Check logs for errors
    logger.info("\n📋 Step 6: Checking recent uibot logs for errors...")
    success, stdout, stderr = run_command("journalctl -u uibot.service -n 100 --no-pager --since '5 minutes ago'", timeout=15)
    if "ERROR" in stdout or "ERROR" in stderr or "error" in stdout.lower() or "error" in stderr.lower():
        logger.warning("⚠️ Errors found in recent logs:")
        for line in stdout.split('\n'):
            if "ERROR" in line or "error" in line.lower():
                logger.warning(f"  {line.strip()}")
        for line in stderr.split('\n'):
            if "ERROR" in line or "error" in line.lower():
                logger.warning(f"  {line.strip()}")
    else:
        logger.info("✅ No errors in recent uibot logs")

    logger.info("=" * 60)
    if all_ok:
        logger.info("✅ ALL SERVICES RUNNING SUCCESSFULLY!")
    else:
        logger.warning("⚠️ Some services may have issues - check logs")
    logger.info("=" * 60)

    return 0 if all_ok else 1


if __name__ == "__main__":
    exit(main())