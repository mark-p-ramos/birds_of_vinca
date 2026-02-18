from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from poll_sightings.process import _poll_sightings

# test update last database fetch timestamp
# test create a google cloud task for each sighting
# test name jobs so that same card id creates a duplicate that won't run again


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up mock environment variables."""
    monkeypatch.setenv("BIRD_BUDDY_USER", "test_user")
    monkeypatch.setenv("BIRD_BUDDY_PASSWORD", "test_password")


@pytest.fixture
def since_date():
    return datetime.now(UTC) - timedelta(hours=2)


@pytest.fixture
def mock_postcard(since_date):
    def _make(card_id="postcard_123", created_at=None):
        card = MagicMock()
        card.get = MagicMock(
            side_effect=lambda key: {"__typename": "FeedItemNewPostcard", "id": card_id}.get(key)
        )
        card.data = {"id": card_id}
        card.created_at = created_at or since_date + timedelta(minutes=10)
        return card

    return _make


@pytest.fixture
def mock_sighting():
    def _make(species=None, images=None, videos=None):
        report_sightings = []
        for name in species or ["Blue Jay", "Cardinal"]:
            mock_species = MagicMock()
            mock_species.name = name
            mock_report_sighting = MagicMock()
            mock_report_sighting.species = mock_species
            mock_report_sighting.is_recognized = True
            report_sightings.append(mock_report_sighting)

        mock_report = MagicMock()
        mock_report.sightings = report_sightings

        sighting = MagicMock()
        sighting.report = mock_report
        sighting.medias = [m for url in (images or []) for m in [MagicMock(content_url=url)]]
        sighting.video_media = [m for url in (videos or []) for m in [MagicMock(content_url=url)]]
        return sighting

    return _make


@pytest.mark.asyncio
async def test_fetch_sightings_success(mock_env_vars, mock_postcard, mock_sighting, since_date):
    """Test successful fetching of sightings with multiple species and media."""
    with patch("poll_sightings.process.BirdBuddy") as mock_bird_buddy_class:
        mock_bb_instance = AsyncMock()
        mock_bird_buddy_class.return_value = mock_bb_instance

        card = mock_postcard()
        sighting_obj = mock_sighting(
            images=["https://example.com/image1.jpg", "https://example.com/image2.jpg"],
            videos=["https://example.com/video1.mp4"],
        )
        mock_bb_instance.refresh_feed = AsyncMock(return_value=[card])
        mock_bb_instance.sighting_from_postcard = AsyncMock(return_value=sighting_obj)

        result = await _poll_sightings("user_123", "BIRD_BUDDY", since_date)

        mock_bird_buddy_class.assert_called_once_with("test_user", "test_password")

        assert mock_bb_instance.refresh_feed.called
        call_args = mock_bb_instance.refresh_feed.call_args
        assert "since" in call_args.kwargs
        assert isinstance(call_args.kwargs["since"], datetime)

        mock_bb_instance.sighting_from_postcard.assert_called_once_with("postcard_123")

        assert len(result) == 1
        sighting = result[0]
        assert sighting.card_id == "postcard_123"
        assert sighting.created_at == card.created_at
        assert set(sighting.species) == {"Blue Jay", "Cardinal"}
        assert sighting.media.images == [
            "https://example.com/image1.jpg",
            "https://example.com/image2.jpg",
        ]
        assert sighting.media.videos == ["https://example.com/video1.mp4"]


@pytest.mark.asyncio
async def test_fetch_sightings_empty_feed(mock_env_vars, since_date):
    """Test fetching sightings when feed is empty."""
    with patch("poll_sightings.process.BirdBuddy") as mock_bird_buddy_class:
        mock_bb_instance = AsyncMock()
        mock_bird_buddy_class.return_value = mock_bb_instance

        mock_bb_instance.refresh_feed = AsyncMock(return_value=[])

        result = await _poll_sightings("user_123", "BIRD_BUDDY", since_date)

        assert len(result) == 0


@pytest.mark.asyncio
async def test_fetch_sightings_filters_non_postcards(
    mock_env_vars, mock_postcard, mock_sighting, since_date
):
    """Test that non-postcard items are filtered out."""
    with patch("poll_sightings.process.BirdBuddy") as mock_bird_buddy_class:
        mock_bb_instance = AsyncMock()
        mock_bird_buddy_class.return_value = mock_bb_instance

        non_postcard_item = MagicMock()
        non_postcard_item.get = MagicMock(
            side_effect=lambda key: {"__typename": "FeedItemOtherType", "id": "other_789"}.get(key)
        )

        mock_bb_instance.refresh_feed = AsyncMock(return_value=[non_postcard_item, mock_postcard()])
        mock_bb_instance.sighting_from_postcard = AsyncMock(return_value=mock_sighting())

        result = await _poll_sightings("user_123", "BIRD_BUDDY", since_date)

        assert len(result) == 1
        assert result[0].card_id == "postcard_123"
        mock_bb_instance.sighting_from_postcard.assert_called_once_with("postcard_123")


@pytest.mark.asyncio
async def test_fetch_sightings_filters_unrecognized_species(
    mock_env_vars, mock_postcard, mock_sighting, since_date
):
    """Test that unrecognized species are filtered out."""
    with patch("poll_sightings.process.BirdBuddy") as mock_bird_buddy_class:
        mock_bb_instance = AsyncMock()
        mock_bird_buddy_class.return_value = mock_bb_instance

        sighting_obj = mock_sighting()
        unrecognized = MagicMock()
        unrecognized.species.name = "Unknown Bird"
        unrecognized.is_recognized = False
        sighting_obj.report.sightings.append(unrecognized)

        mock_bb_instance.refresh_feed = AsyncMock(return_value=[mock_postcard()])
        mock_bb_instance.sighting_from_postcard = AsyncMock(return_value=sighting_obj)

        result = await _poll_sightings("user_123", "BIRD_BUDDY", since_date)

        assert len(result) == 1
        assert "Unknown Bird" not in result[0].species


@pytest.mark.asyncio
async def test_fetch_sightings_deduplicates_species(
    mock_env_vars, mock_postcard, mock_sighting, since_date
):
    """Test that duplicate species names are deduplicated."""
    with patch("poll_sightings.process.BirdBuddy") as mock_bird_buddy_class:
        mock_bb_instance = AsyncMock()
        mock_bird_buddy_class.return_value = mock_bb_instance

        sighting_obj = mock_sighting()
        duplicate = MagicMock()
        duplicate.species.name = sighting_obj.report.sightings[0].species.name
        duplicate.is_recognized = True
        sighting_obj.report.sightings.append(duplicate)

        mock_bb_instance.refresh_feed = AsyncMock(return_value=[mock_postcard()])
        mock_bb_instance.sighting_from_postcard = AsyncMock(return_value=sighting_obj)

        result = await _poll_sightings("user_123", "BIRD_BUDDY", since_date)

        assert len(result) == 1
        assert len(result[0].species) == len(set(result[0].species))


@pytest.mark.asyncio
async def test_fetch_sightings_no_media(mock_env_vars, mock_postcard, mock_sighting, since_date):
    """Test sighting with no images or videos."""
    with patch("poll_sightings.process.BirdBuddy") as mock_bird_buddy_class:
        mock_bb_instance = AsyncMock()
        mock_bird_buddy_class.return_value = mock_bb_instance

        mock_bb_instance.refresh_feed = AsyncMock(return_value=[mock_postcard()])
        mock_bb_instance.sighting_from_postcard = AsyncMock(return_value=mock_sighting())

        result = await _poll_sightings("user_123", "BIRD_BUDDY", since_date)

        assert len(result) == 1
        assert result[0].media.images == []
        assert result[0].media.videos == []


@pytest.mark.asyncio
async def test_fetch_sightings_feed_type_propagated(
    mock_env_vars, mock_postcard, mock_sighting, since_date
):
    """All returned sightings should have feed_type matching the value passed to poll_sightings."""
    with patch("poll_sightings.process.BirdBuddy") as mock_bird_buddy_class:
        mock_bb_instance = AsyncMock()
        mock_bird_buddy_class.return_value = mock_bb_instance

        mock_bb_instance.refresh_feed = AsyncMock(
            return_value=[mock_postcard("postcard_1"), mock_postcard("postcard_2")]
        )
        mock_bb_instance.sighting_from_postcard = AsyncMock(
            side_effect=[mock_sighting(species=["Robin"]), mock_sighting(species=["Finch"])]
        )

        result = await _poll_sightings("user_123", "BIRD_BUDDY", since_date)

        assert len(result) == 2
        assert all(s.feed_type == "BIRD_BUDDY" for s in result)


@pytest.mark.asyncio
async def test_fetch_sightings_multiple_postcards(
    mock_env_vars, mock_postcard, mock_sighting, since_date
):
    """Test fetching multiple postcards."""
    with patch("poll_sightings.process.BirdBuddy") as mock_bird_buddy_class:
        mock_bb_instance = AsyncMock()
        mock_bird_buddy_class.return_value = mock_bb_instance

        mock_bb_instance.refresh_feed = AsyncMock(
            return_value=[mock_postcard("postcard_1"), mock_postcard("postcard_2")]
        )
        mock_bb_instance.sighting_from_postcard = AsyncMock(
            side_effect=[mock_sighting(species=["Crow"]), mock_sighting(species=["Hawk"])]
        )

        result = await _poll_sightings("user_123", "BIRD_BUDDY", since_date)

        assert len(result) == 2
        assert result[0].card_id == "postcard_1"
        assert result[0].species == ["Crow"]
        assert result[1].card_id == "postcard_2"
        assert result[1].species == ["Hawk"]
