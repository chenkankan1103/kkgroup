import json
# Local test data we know works (63 entries from our local test)
# We'll use the same structure but with the actual data we verified locally
# Since we can't fetch from Bahamut on VM, we'll populate from a known-good JSON
# First, let's get the local test data
import sys

sys.path.insert(0, ".")
import asyncio

from cogs.ui.bahamut_web_scraper import BahamutWebScraper


async def get_local_data():
    scraper = BahamutWebScraper()
    return await scraper.fetch_weekly_schedule_from_homepage()


# Run locally to get data
local_data = asyncio.run(get_local_data())
print(f"Got {len(local_data)} entries locally")
for d in local_data[:5]:
    print(f"  {d}")

# Save to JSON for transfer
with open("local_schedule_data.json", "w", encoding="utf-8") as f:
    json.dump(local_data, f, ensure_ascii=False, indent=2)
print("Saved to local_schedule_data.json")
