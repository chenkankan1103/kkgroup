import sqlite3
import os
from pathlib import Path

# Get the database path
db_path = Path(__file__).parent / "user_data.db"
print(f"Checking database at: {db_path}")

if not db_path.exists():
    print("Database not found!")
    exit(1)

# Connect to database
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get distinct weekStartDate values
cursor.execute("SELECT DISTINCT weekStartDate FROM anime_weekly_schedule ORDER BY weekStartDate DESC LIMIT 10")
weeks = cursor.fetchall()
print("\nRecent weekStartDate values in DB:")
for week in weeks:
    print(f"  {week[0]}")

# Check today's schedule
from datetime import datetime
from zoneinfo import ZoneInfo
TW_TZ = ZoneInfo("Asia/Taipei")
now = datetime.now(TW_TZ)
today_weekday_num = now.weekday() + 1  # Convert to 1=Monday,...,7=Sunday
print(f"\nCurrent time in Taiwan: {now}")
print(f"Today's weekday number (1=Mon, 7=Sun): {today_weekday_num}")

# Calculate week start date (Monday of current week)
today_weekday = now.weekday()  # Monday=0, Sunday=6
days_since_monday = today_weekday
monday = now - timedelta(days=days_since_monday)
week_start_date = monday.strftime("%Y-%m-%d")
print(f"Calculated week start date (Monday): {week_start_date}")

# Query today's schedule
query = """
    SELECT videoSn, dayOfWeek, scheduledTime, pushed, weekStartDate, animeData
    FROM anime_weekly_schedule
    WHERE weekStartDate = ?
"""
cursor.execute(query, (week_start_date,))
rows = cursor.fetchall()
print(f"\nFound {len(rows)} entries for week starting {week_start_date}")

if rows:
    print("\nToday's schedule (matching dayOfWeek):")
    for row in rows:
        video_sn, day_of_week, scheduled_time, pushed, week_start_date, anime_data = row
        if day_of_week == today_weekday_num:
            # Parse scheduled time
            try:
                scheduled_dt = datetime.strptime(scheduled_time, "%H:%M").time()
                scheduled_datetime = datetime.combine(now.date(), scheduled_dt, tzinfo=TW_TZ)
                time_diff = now - scheduled_datetime
                print(f"  VideoSn: {video_sn}, DayOfWeek: {day_of_week}, Scheduled: {scheduled_time}, Pushed: {pushed}, Time diff: {time_diff}")
                if pushed == 0:
                    if time_diff.total_seconds() > 0:
                        print(f"    -> PUSH SHOULD HAVE HAPPENED {abs(time_diff.total_seconds())} seconds ago")
                    else:
                        print(f"    -> Scheduled for future (in {abs(time_diff.total_seconds())} seconds)")
                else:
                    print(f"    -> Already pushed")
            except Exception as e:
                print(f"  Error parsing time: {e}")
else:
    print("No entries for this week start date.")

conn.close()