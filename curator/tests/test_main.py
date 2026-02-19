from dataclasses import asdict
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bov_data import BirdFeed, Media, Sighting

from curator.main import import_sighting


@pytest.fixture
def sample_sighting():
    return Sighting(
        bb_id="postcard-123",
        user_id="user_456",
        bird_feed=BirdFeed(brand="Test Brand", product="Test Product"),
        location_zip="80027",
        species=["Blue Jay", "Cardinal"],
        media=Media(images=["https://example.com/img.jpg"], videos=[]),
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_sighting_json(sample_sighting):
    d = asdict(sample_sighting)
    d["created_at"] = sample_sighting.created_at.isoformat()
    return d


def _make_request(json_body=None):
    request = MagicMock()
    request.get_json = MagicMock(return_value=json_body)
    return request


@patch("curator.main.curate_videos", return_value=[])
@patch("curator.main.curate_images", return_value=["curated.jpg"])
@patch("curator.main.get_historical_weather", return_value={
    "temperature_f": 72.0, "was_cloudy": False, "was_precipitating": False,
})
@patch("curator.main._get_db")
def test_import_sighting_success(
    mock_get_db, _mock_weather, mock_images, mock_videos, sample_sighting_json
):
    """Test successful import of a new sighting."""
    mock_db = MagicMock()
    mock_db.exists_sighting = AsyncMock(return_value=False)
    mock_db.create_sighting.return_value = "sighting_789"
    mock_get_db.return_value = mock_db

    request = _make_request(sample_sighting_json)
    result = import_sighting(request)

    assert result == "created sighting id: sighting_789"
    mock_db.exists_sighting.assert_called_once_with("postcard-123")
    mock_db.create_sighting.assert_called_once()
    created_sighting = mock_db.create_sighting.call_args[0][0]
    assert created_sighting.weather.temperature_f == 72.0
    assert created_sighting.weather.was_cloudy is False
    assert created_sighting.weather.was_precipitating is False
    mock_images.assert_called_once()
    mock_videos.assert_called_once()


@patch("curator.main._get_db")
def test_import_sighting_duplicate(mock_get_db, sample_sighting_json):
    """Test that duplicate sightings are rejected."""
    mock_db = MagicMock()
    mock_db.exists_sighting = AsyncMock(return_value=True)
    mock_get_db.return_value = mock_db

    request = _make_request(sample_sighting_json)
    result = import_sighting(request)

    assert "already imported" in result
    assert "postcard-123" in result


def test_import_sighting_missing_json():
    """Test request with no JSON body."""
    request = _make_request(None)
    result = import_sighting(request)

    assert result == "request missing json body"


def test_import_sighting_empty_json():
    """Test request with empty JSON body."""
    request = _make_request({})
    result = import_sighting(request)

    assert result == "request missing json body"
