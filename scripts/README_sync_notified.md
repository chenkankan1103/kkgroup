# Run the sync script on startup (optional)
# This file documents how to run the one-off sync we added in the fix branch.

# To run manually on the VM (example):
#   ANIME_DB_PATH=/home/ubuntu/kkgroup/data/anime.db python3 scripts/sync_notified_to_schedule.py
# Or using the script directly if in project root and anime.db sits in cwd:
#   python3 scripts/sync_notified_to_schedule.py

# You can add a cron job or systemd oneshot if you want this to run automatically once after deployment.
