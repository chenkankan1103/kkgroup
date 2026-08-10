#!/usr/bin/env python3
"""
Database migration script for anime tracking system.
Fixes missing columns in anime_votes, anime_messages, anime_rewards tables.
Run this on the VM after pulling latest code.
"""

import sqlite3
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = Path("/home/e193752468/kkgroup/user_data.db")

# Table names
ANIME_VOTES_TABLE = "anime_votes"
ANIME_MESSAGES_TABLE = "anime_messages"
ANIME_REWARDS_TABLE = "anime_rewards"
ANIME_DETAILS_TABLE = "anime_details"
EPISODE_STATS_TABLE = "episode_stats"
NOTIFIED_TABLE = "notified"


def get_connection():
    """Create database connection with WAL mode and busy timeout"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def get_table_columns(cursor, table_name):
    """Get list of column names for a table"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


def table_exists(cursor, table_name):
    """Check if a table exists"""
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
    return cursor.fetchone() is not None


def add_column_if_missing(cursor, table_name, column_name, column_def):
    """Add column if it doesn't exist. SQLite ALTER TABLE doesn't support non-constant defaults."""
    if not table_exists(cursor, table_name):
        logger.info(f"[Migration] Table {table_name} does not exist, skipping")
        return False

    columns = get_table_columns(cursor, table_name)
    if column_name not in columns:
        # Remove DEFAULT clause for ALTER TABLE - SQLite doesn't support non-constant defaults
        # Default will be handled by application INSERT statements
        if " DEFAULT " in column_def:
            base_def = column_def.split(" DEFAULT ")[0]
            logger.info(f"[Migration] Adding column {column_name} to {table_name} ({base_def}) - default handled by application")
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {base_def}")
        else:
            logger.info(f"[Migration] Adding column {column_name} to {table_name} ({column_def})")
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
        return True
    else:
        logger.info(f"[Migration] Column {column_name} already exists in {table_name}")
        return False


def fix_anime_votes_table(cursor):
    """Fix anime_votes table - ensure all required columns exist"""
    migrations = [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("videoSn", "INTEGER"),
        ("animeSn", "INTEGER"),
        ("video_sn", "INTEGER"),
        ("anime_sn", "INTEGER"),
        ("anime_name", "TEXT"),
        ("voteType", "TEXT"),
        ("vote_type", "TEXT"),
        ("userId", "TEXT"),
        ("user_hash", "TEXT"),
        ("messageId", "INTEGER"),
        ("message_id", "INTEGER"),
        ("comment", "TEXT"),
        ("votedAt", "TEXT DEFAULT (datetime('now'))"),
        ("voted_at", "TEXT DEFAULT (datetime('now'))"),
    ]

    added_count = 0
    for column_name, column_def in migrations:
        if add_column_if_missing(cursor, ANIME_VOTES_TABLE, column_name, column_def):
            added_count += 1

    # Create indexes for better performance
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{ANIME_VOTES_TABLE}_video_sn ON {ANIME_VOTES_TABLE}(video_sn)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{ANIME_VOTES_TABLE}_anime_sn ON {ANIME_VOTES_TABLE}(anime_sn)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{ANIME_VOTES_TABLE}_message_id ON {ANIME_VOTES_TABLE}(message_id)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{ANIME_VOTES_TABLE}_videoSn ON {ANIME_VOTES_TABLE}(videoSn)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{ANIME_VOTES_TABLE}_messageId ON {ANIME_VOTES_TABLE}(messageId)")

    logger.info(f"✅ Fixed {ANIME_VOTES_TABLE}: added {added_count} columns")
    return added_count


def fix_anime_messages_table(cursor):
    """Fix anime_messages table - ensure all required columns exist"""
    migrations = [
        ("messageId", "INTEGER PRIMARY KEY"),
        ("videoSn", "INTEGER"),
        ("animeSn", "INTEGER"),
        ("anime_name", "TEXT"),
        ("channelId", "INTEGER"),
        ("createdAt", "TEXT DEFAULT (datetime('now'))"),
        # snake_case compatibility
        ("video_sn", "INTEGER"),
        ("anime_sn", "INTEGER"),
        ("message_id", "INTEGER"),
        ("channel_id", "INTEGER"),
        ("created_at", "TEXT DEFAULT (datetime('now'))"),
    ]

    added_count = 0
    for column_name, column_def in migrations:
        if add_column_if_missing(cursor, ANIME_MESSAGES_TABLE, column_name, column_def):
            added_count += 1

    # Create indexes
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{ANIME_MESSAGES_TABLE}_videoSn ON {ANIME_MESSAGES_TABLE}(videoSn)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{ANIME_MESSAGES_TABLE}_animeSn ON {ANIME_MESSAGES_TABLE}(animeSn)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{ANIME_MESSAGES_TABLE}_video_sn ON {ANIME_MESSAGES_TABLE}(video_sn)")

    logger.info(f"✅ Fixed {ANIME_MESSAGES_TABLE}: added {added_count} columns")
    return added_count


def fix_anime_rewards_table(cursor):
    """Fix anime_rewards table - ensure all required columns exist"""
    migrations = [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("messageId", "INTEGER"),
        ("rewardType", "TEXT"),
        ("amount", "INTEGER"),
        ("userId", "TEXT"),
        ("rewardedAt", "TEXT DEFAULT (datetime('now'))"),
        # snake_case compatibility
        ("message_id", "INTEGER"),
        ("reward_type", "TEXT"),
        ("user_id", "TEXT"),
        ("reward_amount", "INTEGER"),
        ("awarded_at", "TEXT DEFAULT (datetime('now'))"),
    ]

    added_count = 0
    for column_name, column_def in migrations:
        if add_column_if_missing(cursor, ANIME_REWARDS_TABLE, column_name, column_def):
            added_count += 1

    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{ANIME_REWARDS_TABLE}_message_id ON {ANIME_REWARDS_TABLE}(message_id)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{ANIME_REWARDS_TABLE}_user_id ON {ANIME_REWARDS_TABLE}(user_id)")

    logger.info(f"✅ Fixed {ANIME_REWARDS_TABLE}: added {added_count} columns")
    return added_count


def fix_anime_details_table(cursor):
    """Fix anime_details table - ensure all required columns exist"""
    migrations = [
        ("animeSn", "INTEGER PRIMARY KEY"),
        ("title", "TEXT"),
        ("cover_url", "TEXT"),
        ("description", "TEXT"),
        ("score", "REAL"),
        ("tags", "TEXT"),
        ("createdAt", "TEXT DEFAULT (datetime('now'))"),
        # snake_case
        ("anime_sn", "INTEGER PRIMARY KEY"),
        ("cover", "TEXT"),
        ("created_at", "TEXT DEFAULT (datetime('now'))"),
    ]

    # Special handling for primary key - SQLite doesn't allow adding PK column easily
    columns = get_table_columns(cursor, ANIME_DETAILS_TABLE)
    if "animeSn" not in columns and "anime_sn" not in columns:
        logger.info(f"[Migration] Adding animeSn as PRIMARY KEY to {ANIME_DETAILS_TABLE}")
        cursor.execute(f"ALTER TABLE {ANIME_DETAILS_TABLE} ADD COLUMN animeSn INTEGER PRIMARY KEY")
        added = 1
    else:
        added = 0

    added_count = added
    for column_name, column_def in migrations:
        if column_name in ["animeSn", "anime_sn"]:
            continue  # Already handled
        if add_column_if_missing(cursor, ANIME_DETAILS_TABLE, column_name, column_def):
            added_count += 1

    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{ANIME_DETAILS_TABLE}_animeSn ON {ANIME_DETAILS_TABLE}(animeSn)")

    logger.info(f"✅ Fixed {ANIME_DETAILS_TABLE}: added {added_count} columns")
    return added_count


def fix_episode_stats_table(cursor):
    """Fix episode_stats table - ensure all required columns exist"""
    if not table_exists(cursor, EPISODE_STATS_TABLE):
        logger.info(f"[Migration] Table {EPISODE_STATS_TABLE} does not exist, skipping")
        return 0

    migrations = [
        ("videoSn", "INTEGER PRIMARY KEY"),
        ("animeSn", "INTEGER"),
        ("episodeNum", "TEXT"),
        ("views", "INTEGER"),
        ("score", "REAL DEFAULT 0"),
        ("recordedAt", "TEXT DEFAULT (datetime('now'))"),
        # snake_case
        ("video_sn", "INTEGER"),
        ("anime_sn", "INTEGER"),
        ("episode_num", "TEXT"),
        ("recorded_at", "TEXT DEFAULT (datetime('now'))"),
    ]

    added_count = 0
    for column_name, column_def in migrations:
        if add_column_if_missing(cursor, EPISODE_STATS_TABLE, column_name, column_def):
            added_count += 1

    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{EPISODE_STATS_TABLE}_videoSn ON {EPISODE_STATS_TABLE}(videoSn)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{EPISODE_STATS_TABLE}_video_sn ON {EPISODE_STATS_TABLE}(video_sn)")

    logger.info(f"✅ Fixed {EPISODE_STATS_TABLE}: added {added_count} columns")
    return added_count


def fix_notified_table(cursor):
    """Fix notified table - ensure all required columns exist"""
    if not table_exists(cursor, NOTIFIED_TABLE):
        logger.info(f"[Migration] Table {NOTIFIED_TABLE} does not exist, skipping")
        return 0

    migrations = [
        ("videoSn", "INTEGER PRIMARY KEY"),
        ("animeSn", "INTEGER"),
        ("anime_name", "TEXT"),
        ("volume", "TEXT"),
        ("cover_url", "TEXT"),
        ("notifiedAt", "TEXT DEFAULT (datetime('now'))"),
        # snake_case
        ("video_sn", "INTEGER"),
        ("anime_sn", "INTEGER"),
        ("anime_name", "TEXT"),  # duplicate name, skip
        ("volume", "TEXT"),
        ("cover", "TEXT"),
        ("notified_at", "TEXT DEFAULT (datetime('now'))"),
    ]

    added_count = 0
    for column_name, column_def in migrations:
        if add_column_if_missing(cursor, NOTIFIED_TABLE, column_name, column_def):
            added_count += 1

    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{NOTIFIED_TABLE}_videoSn ON {NOTIFIED_TABLE}(videoSn)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{NOTIFIED_TABLE}_video_sn ON {NOTIFIED_TABLE}(video_sn)")

    logger.info(f"✅ Fixed {NOTIFIED_TABLE}: added {added_count} columns")
    return added_count


def verify_fixes(cursor):
    """Verify all tables have required columns"""
    tables_to_check = {
        ANIME_VOTES_TABLE: ["video_sn", "anime_sn", "anime_name", "vote_type", "message_id", "voted_at"],
        ANIME_MESSAGES_TABLE: ["video_sn", "anime_sn", "anime_name", "channel_id"],
        ANIME_REWARDS_TABLE: ["message_id", "reward_type", "reward_amount", "user_id", "awarded_at"],
    }

    all_ok = True
    for table_name, required_columns in tables_to_check.items():
        columns = get_table_columns(cursor, table_name)
        logger.info(f"\n📋 {table_name} columns: {columns}")
        for col in required_columns:
            if col not in columns:
                logger.error(f"❌ MISSING: {table_name}.{col}")
                all_ok = False
            else:
                logger.info(f"✅ OK: {table_name}.{col}")

    return all_ok


def main():
    logger.info("=" * 60)
    logger.info("🔧 Starting Anime Database Migration")
    logger.info("=" * 60)

    if not DB_PATH.exists():
        logger.error(f"❌ Database not found at {DB_PATH}")
        return 1

    conn = get_connection()
    cursor = conn.cursor()

    try:
        total_added = 0

        # Fix all anime-related tables
        total_added += fix_anime_votes_table(cursor)
        total_added += fix_anime_messages_table(cursor)
        total_added += fix_anime_rewards_table(cursor)
        total_added += fix_anime_details_table(cursor)
        total_added += fix_episode_stats_table(cursor)
        total_added += fix_notified_table(cursor)

        conn.commit()
        logger.info(f"\n✅ Migration complete! Added {total_added} columns total")

        # Verify
        logger.info("\n" + "=" * 60)
        logger.info("🔍 Verifying migration...")
        logger.info("=" * 60)

        if verify_fixes(cursor):
            logger.info("\n✅ All required columns present!")
        else:
            logger.error("\n❌ Some columns still missing!")
            return 1

    except Exception as e:
        logger.error(f"\n❌ Migration failed: {e}", exc_info=True)
        conn.rollback()
        return 1
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    exit(main())