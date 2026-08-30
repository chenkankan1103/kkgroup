#!/usr/bin/env python3
"""
Script to synchronize anime_notified table videoSn values with current Bahamut API data.
This fixes the issue where Bahamut reassigns videoSn when schedules update, but the database retains old values.
"""

import json
import sqlite3
import asyncio
import sys
import os

# Add the project root to the path so we can import the scraper
# Need to go up two levels from worktree to reach project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from cogs.ui.bahamut_web_scraper import BahamutWebScraper

async def fetch_current_anime_data():
    """Fetch current anime data from Bahamut API"""
    print("Fetching current anime data from Bahamut API...")
    scraper = BahamutWebScraper()
    # Get weekly schedule which includes both anime_sn and video_sn
    current_data = await scraper.fetch_weekly_schedule_from_homepage()
    print(f"Fetched {len(current_data)} anime entries from API")

    # Check for duplicate videoSn in API data
    video_sn_counts = {}
    for anime in current_data:
        video_sn = anime['video_sn']
        video_sn_counts[video_sn] = video_sn_counts.get(video_sn, 0) + 1
    duplicate_video_sn = {vsn: count for vsn, count in video_sn_counts.items() if count > 1}
    if duplicate_video_sn:
        print(f"Warning: Duplicate videoSn in API data: {duplicate_video_sn}")
    else:
        print("No duplicate videoSn in API data.")

    # Create a mapping from animeSn to videoSn for easy lookup
    anime_sn_to_video_sn = {}
    for anime in current_data:
        anime_sn = anime['anime_sn']
        video_sn = anime['video_sn']
        anime_sn_to_video_sn[anime_sn] = video_sn

    return anime_sn_to_video_sn, current_data

def get_database_anime_data(db_path):
    """Get current anime data from the database"""
    print(f"Reading anime data from database: {db_path}")
    if not os.path.exists(db_path):
        print(f"ERROR: Database file does not exist at {db_path}")
        return {}
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all records from anime_notified table
    cursor.execute('SELECT videoSn, animeSn, anime_name, volume, cover_url, notified_at FROM anime_notified')
    rows = cursor.fetchall()

    # Create a mapping from animeSn to database record
    anime_sn_to_db_record = {}
    for row in rows:
        videoSn, animeSn, anime_name, volume, cover_url, notified_at = row
        anime_sn_to_db_record[animeSn] = {
            'videoSn': videoSn,
            'animeSn': animeSn,
            'anime_name': anime_name,
            'volume': volume,
            'cover_url': cover_url,
            'notified_at': notified_at
        }

    print(f"Found {len(anime_sn_to_db_record)} anime entries in database")
    conn.close()
    return anime_sn_to_db_record

def update_database_video_sn(db_path, anime_sn_to_video_sn, anime_sn_to_db_record, current_data):
    """Update videoSn values in the database to match current API data.
    We will deduplicate by animeSn, keeping the most recent record for each animeSn.
    """
    print("Updating videoSn values in database (deduplicating by animeSn)...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # First, let's get all rows with animeSn and notified_at to find the most recent per animeSn
    cursor.execute('''
        SELECT rowid, videoSn, animeSn, anime_name, volume, cover_url, notified_at
        FROM anime_notified
        ORDER BY animeSn, notified_at DESC
    ''')
    rows = cursor.fetchall()
    # Group by animeSn
    from collections import defaultdict
    groups = defaultdict(list)
    for row in rows:
        groups[row[2]].append(row)  # row[2] is animeSn

    # We'll keep the first row in each group (most recent notified_at) and delete the rest
    # Then update the videoSn of the kept row to the current videoSn from API (if available)
    # For animeSn in API but not in database, we will insert new rows.

    # Track changes
    updated_count = 0
    inserted_count = 0
    deleted_count = 0

    # Process each animeSn that is in the database
    for animeSn, group in groups.items():
        if animeSn in anime_sn_to_video_sn:
            # Keep the first row (most recent)
            kept_row = group[0]
            # Delete the rest
            for row in group[1:]:
                cursor.execute('DELETE FROM anime_notified WHERE rowid = ?', (row[0],))
                deleted_count += 1
                print(f"    Deleted duplicate row for animeSn {animeSn} (videoSn {row[1]}, notifiedAt {row[6]})")
            # Now update the kept row's videoSn if needed
            current_videoSn = anime_sn_to_video_sn[animeSn]
            if kept_row[1] != current_videoSn:  # kept_row[1] is videoSn
                cursor.execute('''
                    UPDATE anime_notified
                    SET videoSn = ?
                    WHERE rowid = ?
                ''', (current_videoSn, kept_row[0]))
                updated_count += 1
                print(f"    Updated animeSn {animeSn}: videoSn {kept_row[1]} -> {current_videoSn}")
            else:
                print(f"    No change needed for animeSn {animeSn}: videoSn {kept_row[1]}")
        else:
            # This animeSn is not in the current API data. We'll keep the most recent row but leave its videoSn unchanged.
            # Optionally, we could delete it? But we don't want to lose data. Let's keep it.
            kept_row = group[0]
            print(f"    animeSn {animeSn} not in API data; keeping most recent row (videoSn {kept_row[1]})")
            # Delete duplicates
            for row in group[1:]:
                cursor.execute('DELETE FROM anime_notified WHERE rowid = ?', (row[0],))
                deleted_count += 1
                print(f"    Deleted duplicate row for animeSn {animeSn} (videoSn {row[1]}, notifiedAt {row[6]})")

    # Now, for animeSn in API that are not in the database, insert new rows.
    # We need to get the anime_name, volume, cover_url from the API data.
    # We have the current_data list, which contains:
    #   anime_sn, video_sn, title, day_of_week, scheduled_time, episode, cover
    # We'll map:
    #   animeSn -> anime_sn
    #   videoSn -> video_sn
    #   anime_name -> title
    #   volume -> episode (e.g., '第8集')
    #   cover_url -> cover
    #   notified_at -> CURRENT_TIMESTAMP (default)
    # We'll create a dictionary from animeSn to the API data for easy lookup.
    api_data_by_animeSn = {anime['anime_sn']: anime for anime in current_data}

    for animeSn, api_anime in api_data_by_animeSn.items():
        if animeSn not in groups:  # not in database
            # Insert new row
            cursor.execute('''
                INSERT INTO anime_notified (videoSn, animeSn, anime_name, volume, cover_url)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                api_anime['video_sn'],
                animeSn,
                api_anime['title'],
                api_anime['episode'],
                api_anime['cover']
            ))
            inserted_count += 1
            print(f"    Inserted new row for animeSn {animeSn}: videoSn {api_anime['video_sn']}")

    conn.commit()
    conn.close()

    print(f"\nSummary:")
    print(f"  Updated: {updated_count} records")
    print(f"  Inserted: {inserted_count} records")
    print(f"  Deleted (duplicates): {deleted_count} records")

    return updated_count

def verify_update(db_path, anime_sn_to_video_sn):
    """Verify that the update was successful"""
    print("\nVerifying update...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('SELECT videoSn, animeSn, anime_name FROM anime_notified')
    rows = cursor.fetchall()

    mismatch_count = 0
    for videoSn, animeSn, anime_name in rows:
        if animeSn in anime_sn_to_video_sn:
            expected_video_sn = anime_sn_to_video_sn[animeSn]
            if videoSn != expected_video_sn:
                print(f"  Mismatch: animeSn {animeSn} ({anime_name}): DB videoSn={videoSn}, expected={expected_video_sn}")
                mismatch_count += 1
        else:
            print(f"  Warning: animeSn {animeSn} ({anime_name}) not found in API data")

    if mismatch_count == 0:
        print("  All videoSn values match API data!")
    else:
        print(f"  Found {mismatch_count} mismatches")

    conn.close()
    return mismatch_count == 0

async def main():
    """Main function to synchronize the database"""
    print("=== Anime Database VideoSn Synchronization ===")

    # Path to the database - need to go up three levels from worktree to reach project root
    db_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'user_data.db')

    if not os.path.exists(db_path):
        print(f"Error: Database file not found at {db_path}")
        return 1

    try:
        # Fetch current anime data from API
        anime_sn_to_video_sn, current_data = await fetch_current_anime_data()

        # Get current database data
        anime_sn_to_db_record = get_database_anime_data(db_path)

        # Update database videoSn values
        updated_count = update_database_video_sn(db_path, anime_sn_to_video_sn, anime_sn_to_db_record, current_data)

        # Verify the update
        success = verify_update(db_path, anime_sn_to_video_sn)

        if success and updated_count > 0:
            print("\n✅ Database synchronization completed successfully!")
            print("The anime push system should now work correctly.")
            return 0
        elif success and updated_count == 0:
            print("\n✅ Database is already up-to-date!")
            return 0
        else:
            print("\n❌ Database synchronization completed with errors!")
            return 1

    except Exception as e:
        print(f"Error during synchronization: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    result = asyncio.run(main())
    sys.exit(result)