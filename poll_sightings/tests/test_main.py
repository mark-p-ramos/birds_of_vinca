import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from poll_sightings.main import fetch_sightings

# connect to database
# pass feed type with Sighting job
# TODO: confirm Bird Buddy datetime string format
# test respect last database fetch timestamp
# test update last database fetch timestamp
# test create a google cloud task for each sighting
# test name jobs so that same card id creates a duplicate that won't run again


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up mock environment variables."""
    monkeypatch.setenv("BIRD_BUDDY_USER", "test_user")
    monkeypatch.setenv("BIRD_BUDDY_PASSWORD", "test_password")


@pytest.fixture
def mock_postcard():
    """Create a mock postcard object."""
    card = MagicMock()
    card.get = MagicMock(
        side_effect=lambda key: {"__typename": "FeedItemNewPostcard", "id": "postcard_123"}.get(key)
    )
    card.data = {"id": "postcard_123"}
    card.created_at = "2024-02-14T12:00:00Z"
    return card


@pytest.fixture
def mock_sighting():
    """Create a mock sighting object with report and media."""
    mock_species_1 = MagicMock()
    mock_species_1.name = "Blue Jay"
    mock_species_2 = MagicMock()
    mock_species_2.name = "Cardinal"

    mock_report_sighting_1 = MagicMock()
    mock_report_sighting_1.species = mock_species_1
    mock_report_sighting_1.is_recognized = True

    mock_report_sighting_2 = MagicMock()
    mock_report_sighting_2.species = mock_species_2
    mock_report_sighting_2.is_recognized = True

    mock_report = MagicMock()
    mock_report.sightings = [mock_report_sighting_1, mock_report_sighting_2]

    mock_media_1 = MagicMock()
    mock_media_1.content_url = "https://example.com/image1.jpg"

    mock_media_2 = MagicMock()
    mock_media_2.content_url = "https://example.com/image2.jpg"

    mock_video = MagicMock()
    mock_video.content_url = "https://example.com/video1.mp4"

    sighting = MagicMock()
    sighting.report = mock_report
    sighting.medias = [mock_media_1, mock_media_2]
    sighting.video_media = [mock_video]

    return sighting


@pytest.mark.asyncio
async def test_fetch_sightings_success(mock_env_vars, mock_postcard, mock_sighting):
    """Test successful fetching of sightings with multiple species and media."""
    with patch("poll_sightings.main.BirdBuddy") as mock_bird_buddy_class:
        mock_bb_instance = AsyncMock()
        mock_bird_buddy_class.return_value = mock_bb_instance

        # Mock refresh_feed to return a list with one postcard
        mock_bb_instance.refresh_feed = AsyncMock(return_value=[mock_postcard])

        # Mock sighting_from_postcard to return the mock sighting
        mock_bb_instance.sighting_from_postcard = AsyncMock(return_value=mock_sighting)

        # Call the function
        result = await fetch_sightings()

        # Verify BirdBuddy was initialized with correct credentials
        mock_bird_buddy_class.assert_called_once_with("test_user", "test_password")

        # Verify refresh_feed was called with a datetime
        assert mock_bb_instance.refresh_feed.called
        call_args = mock_bb_instance.refresh_feed.call_args
        assert "since" in call_args.kwargs
        assert isinstance(call_args.kwargs["since"], datetime)

        # Verify sighting_from_postcard was called
        mock_bb_instance.sighting_from_postcard.assert_called_once_with("postcard_123")

        # Verify the result
        assert len(result) == 1
        sighting = result[0]
        assert sighting.card_id == "postcard_123"
        assert sighting.created_at == "2024-02-14T12:00:00Z"
        assert set(sighting.species) == {"Blue Jay", "Cardinal"}
        assert sighting.media.images == [
            "https://example.com/image1.jpg",
            "https://example.com/image2.jpg",
        ]
        assert sighting.media.videos == ["https://example.com/video1.mp4"]


@pytest.mark.asyncio
async def test_fetch_sightings_empty_feed(mock_env_vars):
    """Test fetching sightings when feed is empty."""
    with patch("poll_sightings.main.BirdBuddy") as mock_bird_buddy_class:
        mock_bb_instance = AsyncMock()
        mock_bird_buddy_class.return_value = mock_bb_instance

        # Mock refresh_feed to return empty list
        mock_bb_instance.refresh_feed = AsyncMock(return_value=[])

        # Call the function
        result = await fetch_sightings()

        # Verify result is empty
        assert len(result) == 0


@pytest.mark.asyncio
async def test_fetch_sightings_filters_non_postcards(mock_env_vars):
    """Test that non-postcard items are filtered out."""
    with patch("poll_sightings.main.BirdBuddy") as mock_bird_buddy_class:
        mock_bb_instance = AsyncMock()
        mock_bird_buddy_class.return_value = mock_bb_instance

        # Create mixed feed items
        postcard_item = MagicMock()
        postcard_item.get = MagicMock(
            side_effect=lambda key: {"__typename": "FeedItemNewPostcard", "id": "postcard_456"}.get(
                key
            )
        )
        postcard_item.data = {"id": "postcard_456"}
        postcard_item.created_at = "2024-02-14T12:00:00Z"

        non_postcard_item = MagicMock()
        non_postcard_item.get = MagicMock(
            side_effect=lambda key: {"__typename": "FeedItemOtherType", "id": "other_789"}.get(key)
        )

        mock_bb_instance.refresh_feed = AsyncMock(return_value=[non_postcard_item, postcard_item])

        # Create mock sighting for the postcard
        mock_sighting = MagicMock()
        mock_species = MagicMock()
        mock_species.name = "Sparrow"
        mock_report_sighting = MagicMock()
        mock_report_sighting.species = mock_species
        mock_report_sighting.is_recognized = True
        mock_report = MagicMock()
        mock_report.sightings = [mock_report_sighting]
        mock_sighting.report = mock_report
        mock_sighting.medias = []
        mock_sighting.video_media = []

        mock_bb_instance.sighting_from_postcard = AsyncMock(return_value=mock_sighting)

        # Call the function
        result = await fetch_sightings()

        # Verify only postcard was processed
        assert len(result) == 1
        assert result[0].card_id == "postcard_456"
        mock_bb_instance.sighting_from_postcard.assert_called_once_with("postcard_456")


@pytest.mark.asyncio
async def test_fetch_sightings_filters_unrecognized_species(mock_env_vars, mock_postcard):
    """Test that unrecognized species are filtered out."""
    with patch("poll_sightings.main.BirdBuddy") as mock_bird_buddy_class:
        mock_bb_instance = AsyncMock()
        mock_bird_buddy_class.return_value = mock_bb_instance

        mock_bb_instance.refresh_feed = AsyncMock(return_value=[mock_postcard])

        # Create sighting with recognized and unrecognized species
        mock_species_recognized = MagicMock()
        mock_species_recognized.name = "Robin"
        mock_species_unrecognized = MagicMock()
        mock_species_unrecognized.name = "Unknown Bird"

        mock_report_sighting_1 = MagicMock()
        mock_report_sighting_1.species = mock_species_recognized
        mock_report_sighting_1.is_recognized = True

        mock_report_sighting_2 = MagicMock()
        mock_report_sighting_2.species = mock_species_unrecognized
        mock_report_sighting_2.is_recognized = False

        mock_report = MagicMock()
        mock_report.sightings = [mock_report_sighting_1, mock_report_sighting_2]

        mock_sighting = MagicMock()
        mock_sighting.report = mock_report
        mock_sighting.medias = []
        mock_sighting.video_media = []

        mock_bb_instance.sighting_from_postcard = AsyncMock(return_value=mock_sighting)

        # Call the function
        result = await fetch_sightings()

        # Verify only recognized species are included
        assert len(result) == 1
        assert result[0].species == ["Robin"]


@pytest.mark.asyncio
async def test_fetch_sightings_deduplicates_species(mock_env_vars, mock_postcard):
    """Test that duplicate species names are deduplicated."""
    with patch("poll_sightings.main.BirdBuddy") as mock_bird_buddy_class:
        mock_bb_instance = AsyncMock()
        mock_bird_buddy_class.return_value = mock_bb_instance

        mock_bb_instance.refresh_feed = AsyncMock(return_value=[mock_postcard])

        # Create sighting with duplicate species
        mock_species_1 = MagicMock()
        mock_species_1.name = "Woodpecker"
        mock_species_2 = MagicMock()
        mock_species_2.name = "Woodpecker"

        mock_report_sighting_1 = MagicMock()
        mock_report_sighting_1.species = mock_species_1
        mock_report_sighting_1.is_recognized = True

        mock_report_sighting_2 = MagicMock()
        mock_report_sighting_2.species = mock_species_2
        mock_report_sighting_2.is_recognized = True

        mock_report = MagicMock()
        mock_report.sightings = [mock_report_sighting_1, mock_report_sighting_2]

        mock_sighting = MagicMock()
        mock_sighting.report = mock_report
        mock_sighting.medias = []
        mock_sighting.video_media = []

        mock_bb_instance.sighting_from_postcard = AsyncMock(return_value=mock_sighting)

        # Call the function
        result = await fetch_sightings()

        # Verify species are deduplicated
        assert len(result) == 1
        assert len(result[0].species) == 1
        assert result[0].species == ["Woodpecker"]


@pytest.mark.asyncio
async def test_fetch_sightings_no_media(mock_env_vars, mock_postcard):
    """Test sighting with no images or videos."""
    with patch("poll_sightings.main.BirdBuddy") as mock_bird_buddy_class:
        mock_bb_instance = AsyncMock()
        mock_bird_buddy_class.return_value = mock_bb_instance

        mock_bb_instance.refresh_feed = AsyncMock(return_value=[mock_postcard])

        # Create sighting with no media
        mock_species = MagicMock()
        mock_species.name = "Finch"
        mock_report_sighting = MagicMock()
        mock_report_sighting.species = mock_species
        mock_report_sighting.is_recognized = True
        mock_report = MagicMock()
        mock_report.sightings = [mock_report_sighting]

        mock_sighting = MagicMock()
        mock_sighting.report = mock_report
        mock_sighting.medias = []
        mock_sighting.video_media = []

        mock_bb_instance.sighting_from_postcard = AsyncMock(return_value=mock_sighting)

        # Call the function
        result = await fetch_sightings()

        # Verify media lists are empty
        assert len(result) == 1
        assert result[0].media.images == []
        assert result[0].media.videos == []


@pytest.mark.asyncio
async def test_fetch_sightings_multiple_postcards(mock_env_vars):
    """Test fetching multiple postcards."""
    with patch("poll_sightings.main.BirdBuddy") as mock_bird_buddy_class:
        mock_bb_instance = AsyncMock()
        mock_bird_buddy_class.return_value = mock_bb_instance

        # Create two postcards
        postcard_1 = MagicMock()
        postcard_1.get = MagicMock(
            side_effect=lambda key: {"__typename": "FeedItemNewPostcard", "id": "postcard_1"}.get(
                key
            )
        )
        postcard_1.data = {"id": "postcard_1"}
        postcard_1.created_at = "2024-02-14T10:00:00Z"

        postcard_2 = MagicMock()
        postcard_2.get = MagicMock(
            side_effect=lambda key: {"__typename": "FeedItemNewPostcard", "id": "postcard_2"}.get(
                key
            )
        )
        postcard_2.data = {"id": "postcard_2"}
        postcard_2.created_at = "2024-02-14T11:00:00Z"

        mock_bb_instance.refresh_feed = AsyncMock(return_value=[postcard_1, postcard_2])

        # Create mock sightings
        def create_mock_sighting(species_name):
            mock_species = MagicMock()
            mock_species.name = species_name
            mock_report_sighting = MagicMock()
            mock_report_sighting.species = mock_species
            mock_report_sighting.is_recognized = True
            mock_report = MagicMock()
            mock_report.sightings = [mock_report_sighting]
            mock_sighting = MagicMock()
            mock_sighting.report = mock_report
            mock_sighting.medias = []
            mock_sighting.video_media = []
            return mock_sighting

        mock_bb_instance.sighting_from_postcard = AsyncMock(
            side_effect=[create_mock_sighting("Crow"), create_mock_sighting("Hawk")]
        )

        # Call the function
        result = await fetch_sightings()

        # Verify both postcards were processed
        assert len(result) == 2
        assert result[0].card_id == "postcard_1"
        assert result[0].species == ["Crow"]
        assert result[1].card_id == "postcard_2"
        assert result[1].species == ["Hawk"]
