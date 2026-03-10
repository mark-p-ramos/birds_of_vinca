import asyncio
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bov_data import BirdFeed, Media, Sighting

from curator.main import _is_too_many_squirrels, import_sighting


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


def _make_mock_db(**kwargs):
    mock_db = MagicMock(**kwargs)
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    return mock_db


@patch(
    "curator.main.post_sighting",
    new_callable=AsyncMock,
    return_value=("https://www.instagram.com/p/test/", None),
)
@patch("curator.main.curate_videos", return_value=None)
@patch("curator.main.curate_images", return_value=["curated.jpg"])
@patch(
    "curator.main.get_weather",
    return_value={
        "temperature_f": 72.0,
        "was_cloudy": False,
        "was_precipitating": False,
    },
)
def test_import_sighting_success(
    _mock_weather, mock_images, mock_videos, _mock_post, sample_sighting_json
):
    """Test successful import of a new sighting."""
    mock_db = _make_mock_db()
    mock_db.exists_sighting = AsyncMock(return_value=False)
    mock_db.create_sighting = AsyncMock(return_value="sighting_789")

    with patch("curator.main.MongoClient", return_value=mock_db):
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


@patch(
    "curator.main.post_sighting",
    new_callable=AsyncMock,
    return_value=(
        "https://www.instagram.com/p/images_post/",
        "https://www.instagram.com/reel/video_post/",
    ),
)
@patch("curator.main.curate_videos", return_value="videos/abc-123.mp4")
@patch("curator.main.curate_images", return_value=["images/def-456.jpg", "images/ghi-789.jpg"])
@patch(
    "curator.main.get_weather",
    return_value={
        "temperature_f": 55.0,
        "was_cloudy": True,
        "was_precipitating": False,
    },
)
def test_import_sighting_posts_to_instagram(
    _mock_weather, _mock_images, _mock_videos, _mock_post, sample_sighting_json
):
    """Test that the sighting written to db has Instagram post URLs set."""
    mock_db = _make_mock_db()
    mock_db.exists_sighting = AsyncMock(return_value=False)
    mock_db.create_sighting = AsyncMock(return_value="sighting_789")

    with patch("curator.main.MongoClient", return_value=mock_db):
        request = _make_request(sample_sighting_json)
        import_sighting(request)

    created_sighting = mock_db.create_sighting.call_args[0][0]

    assert created_sighting.bb_id == sample_sighting_json["bb_id"]
    assert created_sighting.user_id == sample_sighting_json["user_id"]
    assert created_sighting.bird_feed == BirdFeed(**sample_sighting_json["bird_feed"])
    assert created_sighting.location_zip == sample_sighting_json["location_zip"]
    assert created_sighting.species == sample_sighting_json["species"]

    assert (
        created_sighting.media.instagram_images_post_url
        == "https://www.instagram.com/p/images_post/"
    )
    assert (
        created_sighting.media.instagram_video_post_url
        == "https://www.instagram.com/reel/video_post/"
    )


def test_import_sighting_duplicate(sample_sighting_json):
    """Test that duplicate sightings are rejected."""
    mock_db = _make_mock_db()
    mock_db.exists_sighting = AsyncMock(return_value=True)

    with patch("curator.main.MongoClient", return_value=mock_db):
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


@patch(
    "curator.main.post_sighting",
    new_callable=AsyncMock,
    return_value=(None, None),
)
@patch("curator.main.curate_videos", return_value=None)
@patch("curator.main.curate_images", return_value=[])
@patch(
    "curator.main.get_weather",
    return_value={
        "temperature_f": 72.0,
        "was_cloudy": False,
        "was_precipitating": False,
    },
)
def test_import_sighting_writes_when_no_media(
    _mock_weather, _mock_images, _mock_videos, _mock_post, sample_sighting_json
):
    """Test that sighting is still written to db even if images and videos are both empty."""
    mock_db = _make_mock_db()
    mock_db.exists_sighting = AsyncMock(return_value=False)
    mock_db.create_sighting = AsyncMock(return_value="sighting_789")

    with patch("curator.main.MongoClient", return_value=mock_db):
        request = _make_request(sample_sighting_json)
        result = import_sighting(request)

    assert result == "created sighting id: sighting_789"
    mock_db.create_sighting.assert_called_once()


def test_import_sighting_too_many_squirrels(sample_sighting_json):
    """Test that a sighting is not imported when there are too many squirrels."""
    mock_db = _make_mock_db()
    mock_db.exists_sighting = AsyncMock(return_value=False)

    with patch("curator.main._is_too_many_squirrels", new=AsyncMock(return_value=True)):
        with patch("curator.main.MongoClient", return_value=mock_db):
            request = _make_request(sample_sighting_json)
            result = import_sighting(request)

    assert result == "sighting not imported: too many squirrels"
    mock_db.create_sighting.assert_not_called()


def test_is_too_many_squirrels_no_squirrel_in_species(sample_sighting):
    """Returns False immediately when sighting has no squirrel species."""
    mock_db = _make_mock_db()
    mock_db.has_squirrel_sighting_since = AsyncMock(return_value=True)

    result = asyncio.run(_is_too_many_squirrels(mock_db, sample_sighting))

    assert result is False
    mock_db.has_squirrel_sighting_since.assert_not_called()


def test_is_too_many_squirrels_recent_squirrel_exists(sample_sighting):
    """Returns True when incoming sighting has squirrel and a recent squirrel sighting exists."""
    sample_sighting.species = ["Eastern Gray Squirrel"]
    mock_db = _make_mock_db()
    mock_db.has_squirrel_sighting_since = AsyncMock(return_value=True)

    result = asyncio.run(_is_too_many_squirrels(mock_db, sample_sighting))

    assert result is True


def test_is_too_many_squirrels_no_recent_squirrel(sample_sighting):
    """Returns False when incoming sighting has squirrel but no recent squirrel sighting in DB."""
    sample_sighting.species = ["Eastern Gray Squirrel"]
    mock_db = _make_mock_db()
    mock_db.has_squirrel_sighting_since = AsyncMock(return_value=False)

    result = asyncio.run(_is_too_many_squirrels(mock_db, sample_sighting))

    assert result is False


def test_is_too_many_squirrels_case_insensitive(sample_sighting):
    """Squirrel check is case-insensitive (e.g. 'SQUIRREL', 'Squirrel')."""
    mock_db = _make_mock_db()
    mock_db.has_squirrel_sighting_since = AsyncMock(return_value=True)

    for name in ["SQUIRREL", "Squirrel", "Red Squirrel"]:
        sample_sighting.species = [name]
        result = asyncio.run(_is_too_many_squirrels(mock_db, sample_sighting))
        assert result is True, f"Expected True for species '{name}'"


def test_is_too_many_squirrels_passes_correct_since_date(sample_sighting):
    """Passes a datetime 6 hours before sighting.created_at to the DB query."""
    mock_db = _make_mock_db()
    mock_db.has_squirrel_sighting_since = AsyncMock(return_value=False)
    sample_sighting.species = ["Eastern Gray Squirrel"]

    asyncio.run(_is_too_many_squirrels(mock_db, sample_sighting))

    expected_since = sample_sighting.created_at - timedelta(hours=6)
    mock_db.has_squirrel_sighting_since.assert_called_once_with(expected_since)
