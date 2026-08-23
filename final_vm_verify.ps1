# Final verification script for anime push on VM
# Run this on the GCP VM to verify everything works

Write-Host "=== VM Anime Push Verification ===" -ForegroundColor Green

# 1. Check uibot service status
Write-Host "`n1. Checking uibot service status..." -ForegroundColor Yellow
sudo systemctl status uibot.service --no-pager -l

# 2. Check recent logs for scheduler initialization
Write-Host "`n2. Checking recent logs for scheduler/push jobs..." -ForegroundColor Yellow
sudo journalctl -u uibot.service -n 200 --no-pager | grep -iE "(scheduler|push_|_reschedule|_init_scheduler|set_dependencies|anime_sn|video_sn|排程|推送任務)" | head -30

# 3. Check database for schedule data
Write-Host "`n3. Checking anime_weekly_schedule table..." -ForegroundColor Yellow
sqlite3 user_data.db "SELECT COUNT(*) as total, COUNT(DISTINCT anime_sn) as unique_anime, COUNT(CASE WHEN anime_sn IS NOT NULL AND anime_sn != 0 THEN 1 END) as with_anime_sn FROM anime_weekly_schedule;"

# 4. Check today's schedule
Write-Host "`n4. Checking today's schedule (Taiwan time)..." -ForegroundColor Yellow
TZ=Asia/Taipei date
sqlite3 user_data.db "SELECT video_sn, anime_sn, scheduled_time, day_of_week, name FROM anime_weekly_schedule WHERE day_of_week = (CAST(strftime('%w', 'now', 'localtime') AS INTEGER) + 6) % 7 ORDER BY scheduled_time LIMIT 20;"

# 5. Test anime push command
Write-Host "`n5. Testing /anime_status command logic locally..." -ForegroundColor Yellow
cd /home/e193752468/kkgroup
source .venv/bin/activate
python3 -c "
import sys
sys.path.insert(0, '.')
from cogs.ui.schedule_tracker import AnimeScheduleTracker
tracker = AnimeScheduleTracker('./user_data.db')
today = tracker.get_today_schedule()
print(f'Today schedule count: {len(today)}')
for item in today[:5]:
    print(f'  video_sn={item.get(\"video_sn\")} anime_sn={item.get(\"anime_sn\")} time={item.get(\"scheduled_time\")} day={item.get(\"day_of_week\")}')
print(f'... and {len(today) - 5} more' if len(today) > 5 else '')
"

# 6. Check scheduler jobs count
Write-Host "`n6. Checking APScheduler jobs..." -ForegroundColor Yellow
python3 -c "
import sys
sys.path.insert(0, '.')
from cogs.ui.anime_tracker import AnimeTracker

class MockBot:
    def __init__(self):
        self.cogs = {}
    def get_cog(self, name):
        return self.cogs.get(name)
    def add_cog(self, cog):
        self.cogs[cog.__class__.__name__] = cog

import asyncio
async def test():
    bot = MockBot()
    tracker = AnimeTracker(bot)
    await tracker.set_dependencies('./user_data.db')
    print('Scheduler running:', tracker.scheduler.running if tracker.scheduler else 'None')
    if tracker.scheduler:
        jobs = tracker.scheduler.get_jobs()
        push_jobs = [j for j in jobs if j.id.startswith('push_')]
        print(f'Total jobs: {len(jobs)}')
        print(f'Push jobs: {len(push_jobs)}')
        for j in push_jobs:
            print(f'  {j.id} -> next_run: {j.next_run_time}')
    else:
        print('No scheduler!')

asyncio.run(test())
"

Write-Host "`n=== Verification Complete ===" -ForegroundColor Green