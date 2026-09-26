import pytest
import pytest_asyncio
import asyncio
import tempfile
import os
from unittest.mock import MagicMock

from cogs.ui.push_core import AnimeDatabase, AnimeDBImpl


def create_test_db_path():
    """Create a temporary database file path for testing"""
    fd, path = tempfile.mkstemp(suffix='.db', prefix='test_is_notified_')
    os.close(fd)
    return path


class TestIsNotifiedFunction:
    """Tests for the is_notified function to verify episode-specific notifications"""

    @pytest_asyncio.fixture
    async def anime_db(self):
        """Create an AnimeDatabase instance with a temporary database"""
        db_path = create_test_db_path()
        db_impl = AnimeDBImpl(db_path)
        db = AnimeDatabase(db_impl)

        yield db

        # Clean up temp file after test
        if os.path.exists(db_path):
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_is_notified_false_when_only_other_volume_notified(self, anime_db):
        """Test that is_notified(video_sn, volume1) returns False when only volume2 has been notified"""
        video_sn = 51015
        volume1 = '第21集'
        volume2 = '第22集'

        # Notify only volume2
        anime_db.db.add_notified(video_sn, 12345, 'Test Anime', volume2, '')

        # Check that volume1 is not notified (should return False)
        result = anime_db.is_notified(video_sn, volume1)
        assert result is False, f"Expected is_notified({video_sn}, '{volume1}') to be False when only '{volume2}' is notified"

    @pytest.mark.asyncio
    async def test_is_notified_true_after_volume_notified(self, anime_db):
        """Test that is_notified(video_sn, volume2) returns True after volume2 has been notified"""
        video_sn = 51015
        volume2 = '第22集'

        # Notify volume2
        anime_db.db.add_notified(video_sn, 12345, 'Test Anime', volume2, '')

        # Check that volume2 is notified (should return True)
        result = anime_db.is_notified(video_sn, volume2)
        assert result is True, f"Expected is_notified({video_sn}, '{volume2}') to be True after '{volume2}' is notified"

    @pytest.mark.asyncio
    async def test_is_notified_backward_compatibility(self, anime_db):
        """Test that is_notified(video_sn) returns True when any episode of videoSn has been notified"""
        video_sn = 51015
        volume = '第22集'

        # Notify the volume
        anime_db.db.add_notified(video_sn, 12345, 'Test Anime', volume, '')

        # Check without volume parameter (backward compatibility) - should return True
        result = anime_db.is_notified(video_sn)
        assert result is True, f"Expected is_notified({video_sn}) to be True when any episode is notified (backward compatibility)"

    @pytest.mark.asyncio
    async def test_is_notified_false_when_no_notifications(self, anime_db):
        """Test that is_notified returns False when no notifications exist for the video_sn"""
        video_sn = 51015
        volume = '第21集'

        # No notifications added
        result_with_volume = anime_db.is_notified(video_sn, volume)
        result_without_volume = anime_db.is_notified(video_sn)

        assert result_with_volume is False, f"Expected is_notified({video_sn}, '{volume}') to be False when no notifications exist"
        assert result_without_volume is False, f"Expected is_notified({video_sn}) to be False when no notifications exist (backward compatibility)"

    @pytest.mark.asyncio
    async def test_is_notified_true_for_specific_volume_after_adding(self, anime_db):
        """Test that is_notified returns True for a specific volume after adding that volume"""
        video_sn = 51015
        volume1 = '第21集'
        volume2 = '第22集'

        # Notify volume1 only
        anime_db.db.add_notified(video_sn, 12345, 'Test Anime', volume1, '')

        # Check volume1 is notified (True)
        assert anime_db.is_notified(video_sn, volume1) is True
        # Check volume2 is not notified (False)
        assert anime_db.is_notified(video_sn, volume2) is False
        # Backward compatibility: any episode notified should return True
        assert anime_db.is_notified(video_sn) is True

        # Now notify volume2 as well
        anime_db.db.add_notified(video_sn, 12345, 'Test Anime', volume2, '')

        # Both volumes should now be notified
        assert anime_db.is_notified(video_sn, volume1) is True
        assert anime_db.is_notified(video_sn, volume2) is True
        # Backward compatibility still holds
        assert anime_db.is_notified(video_sn) is True