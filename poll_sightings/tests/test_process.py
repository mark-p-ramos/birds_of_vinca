from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from bov_data import BirdBuddy, BirdFeed, User

from poll_sightings.process import _fetch_bb_items, _poll_collections, _poll_feed

# test update last database fetch timestamp
# test create a google cloud task for each sighting
# test name jobs so that same card id creates a duplicate that won't run again


@pytest.fixture
def since_date():
    return datetime.now(UTC) - timedelta(hours=2)


@pytest.fixture
def mock_user(since_date):
    return User(
        email="test@example.com",
        _id="user_123",
        bird_buddy=BirdBuddy(
            user="test_user",
            password="test_password",
            location_zip="80027",
            feed=BirdFeed(brand="Test", product="Test Feed"),
            last_polled_at=since_date,
        ),
    )


@pytest.fixture
def mock_postcard(since_date):
    def _make(card_id="postcard_123", created_at=None):
        card = MagicMock()
        card.node_id = card_id
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


def _mock_feed(postcards):
    """Create a mock feed object whose .filter() returns the given postcards."""
    feed = MagicMock()
    feed.filter = MagicMock(return_value=postcards)
    return feed


@pytest.mark.asyncio
async def test_fetch_sightings_success(mock_postcard, mock_sighting, since_date):
    """Test successful fetching of sightings with multiple species and media."""
    mock_bb = AsyncMock()

    card = mock_postcard()
    sighting_obj = mock_sighting(
        images=["https://example.com/image1.jpg", "https://example.com/image2.jpg"],
        videos=["https://example.com/video1.mp4"],
    )
    mock_bb.feed = AsyncMock(return_value=_mock_feed([card]))
    mock_bb.sighting_from_postcard = AsyncMock(return_value=sighting_obj)

    result = await _poll_feed(mock_bb, since_date)

    assert mock_bb.feed.called
    mock_bb.sighting_from_postcard.assert_called_once_with("postcard_123")

    assert len(result) == 1
    sighting = result[0]
    assert sighting["bb_id"] == "postcard-postcard_123"
    assert sighting["created_at"] == card.created_at
    assert set(sighting["species"]) == {"Blue Jay", "Cardinal"}
    assert sighting["image_urls"] == [
        "https://example.com/image1.jpg",
        "https://example.com/image2.jpg",
    ]
    assert sighting["video_urls"] == ["https://example.com/video1.mp4"]


@pytest.mark.asyncio
async def test_fetch_sightings_empty_feed(since_date):
    """Test fetching sightings when feed is empty."""
    mock_bb = AsyncMock()
    mock_bb.feed = AsyncMock(return_value=_mock_feed([]))

    result = await _poll_feed(mock_bb, since_date)

    assert len(result) == 0


@pytest.mark.asyncio
async def test_fetch_sightings_filters_non_postcards(mock_postcard, mock_sighting, since_date):
    """Test that non-postcard items are filtered out (by bb_feed.filter)."""
    mock_bb = AsyncMock()

    card = mock_postcard()
    feed = _mock_feed([card])
    mock_bb.feed = AsyncMock(return_value=feed)
    mock_bb.sighting_from_postcard = AsyncMock(return_value=mock_sighting())

    result = await _poll_feed(mock_bb, since_date)

    feed.filter.assert_called_once()
    assert len(result) == 1
    assert result[0]["bb_id"] == "postcard-postcard_123"
    mock_bb.sighting_from_postcard.assert_called_once_with("postcard_123")


@pytest.mark.asyncio
async def test_fetch_sightings_filters_unrecognized_species(
    mock_postcard, mock_sighting, since_date
):
    """Test that unrecognized species are filtered out."""
    mock_bb = AsyncMock()

    sighting_obj = mock_sighting()
    unrecognized = MagicMock()
    unrecognized.species.name = "Unknown Bird"
    unrecognized.is_recognized = False
    sighting_obj.report.sightings.append(unrecognized)

    mock_bb.feed = AsyncMock(return_value=_mock_feed([mock_postcard()]))
    mock_bb.sighting_from_postcard = AsyncMock(return_value=sighting_obj)

    result = await _poll_feed(mock_bb, since_date)

    assert len(result) == 1
    assert "Unknown Bird" not in result[0]["species"]


@pytest.mark.asyncio
async def test_fetch_sightings_deduplicates_species(mock_postcard, mock_sighting, since_date):
    """Test that duplicate species names are deduplicated."""
    mock_bb = AsyncMock()

    sighting_obj = mock_sighting()
    duplicate = MagicMock()
    duplicate.species.name = sighting_obj.report.sightings[0].species.name
    duplicate.is_recognized = True
    sighting_obj.report.sightings.append(duplicate)

    mock_bb.feed = AsyncMock(return_value=_mock_feed([mock_postcard()]))
    mock_bb.sighting_from_postcard = AsyncMock(return_value=sighting_obj)

    result = await _poll_feed(mock_bb, since_date)

    assert len(result) == 1
    assert len(result[0]["species"]) == len(set(result[0]["species"]))


@pytest.mark.asyncio
async def test_fetch_sightings_no_media(mock_postcard, mock_sighting, since_date):
    """Test sighting with no images or videos."""
    mock_bb = AsyncMock()
    mock_bb.feed = AsyncMock(return_value=_mock_feed([mock_postcard()]))
    mock_bb.sighting_from_postcard = AsyncMock(return_value=mock_sighting())

    result = await _poll_feed(mock_bb, since_date)

    assert len(result) == 1
    assert result[0]["image_urls"] == []
    assert result[0]["video_urls"] == []


@pytest.mark.asyncio
async def test_fetch_sightings_multiple_postcards(mock_postcard, mock_sighting, since_date):
    """Test fetching multiple postcards."""
    mock_bb = AsyncMock()
    mock_bb.feed = AsyncMock(
        return_value=_mock_feed([mock_postcard("postcard_1"), mock_postcard("postcard_2")])
    )
    mock_bb.sighting_from_postcard = AsyncMock(
        side_effect=[mock_sighting(species=["Crow"]), mock_sighting(species=["Hawk"])]
    )

    result = await _poll_feed(mock_bb, since_date)

    assert len(result) == 2
    assert result[0]["bb_id"] == "postcard-postcard_1"
    assert result[0]["species"] == ["Crow"]
    assert result[1]["bb_id"] == "postcard-postcard_2"
    assert result[1]["species"] == ["Hawk"]


# --- _poll_collections tests ---


@pytest.fixture
def mock_collection(since_date):
    def _make(
        collection_id="col_123",
        bird_name="Blue Jay",
        visit_time=None,
    ):
        col = MagicMock()
        col.collection_id = collection_id
        col.bird_name = bird_name
        visit = visit_time or (since_date + timedelta(minutes=10))
        col.data = {"visitLastTime": visit.isoformat()}
        return col

    return _make


def _mock_media(images=None, videos=None):
    """Create a mock media dict as returned by bb.collection()."""
    media = {}
    for i, url in enumerate(images or []):
        m = MagicMock()
        m.content_url = url
        m.is_video = False
        media[f"img_{i}"] = m
    for i, url in enumerate(videos or []):
        m = MagicMock()
        m.content_url = url
        m.is_video = True
        media[f"vid_{i}"] = m
    return media


@pytest.mark.asyncio
async def test_poll_collections_success(mock_collection, since_date):
    """Test successful fetching of collections with images and videos."""
    mock_bb = AsyncMock()

    col = mock_collection()
    mock_bb.refresh_collections = AsyncMock(return_value={"col_123": col})
    mock_bb.collection = AsyncMock(
        return_value=_mock_media(
            images=["https://example.com/img1.jpg"],
            videos=["https://example.com/vid1.mp4"],
        )
    )

    result = await _poll_collections(mock_bb, since_date)

    mock_bb.refresh_collections.assert_called_once()
    mock_bb.collection.assert_called_once_with("col_123")

    assert len(result) == 1
    entry = result[0]
    assert entry["bb_id"] == "collection-col_123"
    assert entry["species"] == ["Blue Jay"]
    assert entry["image_urls"] == ["https://example.com/img1.jpg"]
    assert entry["video_urls"] == ["https://example.com/vid1.mp4"]


@pytest.mark.asyncio
async def test_poll_collections_empty(since_date):
    """Test with no collections returned."""
    mock_bb = AsyncMock()
    mock_bb.refresh_collections = AsyncMock(return_value={})

    result = await _poll_collections(mock_bb, since_date)

    assert len(result) == 0


@pytest.mark.asyncio
async def test_poll_collections_filters_old(mock_collection, since_date):
    """Test that collections older than since are filtered out."""
    mock_bb = AsyncMock()

    old_col = mock_collection(
        collection_id="old_col",
        visit_time=since_date - timedelta(hours=1),
    )
    new_col = mock_collection(collection_id="new_col")

    mock_bb.refresh_collections = AsyncMock(
        return_value={"old_col": old_col, "new_col": new_col}
    )
    mock_bb.collection = AsyncMock(return_value=_mock_media())

    result = await _poll_collections(mock_bb, since_date)

    assert len(result) == 1
    assert result[0]["bb_id"] == "collection-new_col"
    mock_bb.collection.assert_called_once_with("new_col")


@pytest.mark.asyncio
async def test_poll_collections_no_media(mock_collection, since_date):
    """Test collection with no images or videos."""
    mock_bb = AsyncMock()

    mock_bb.refresh_collections = AsyncMock(
        return_value={"col_123": mock_collection()}
    )
    mock_bb.collection = AsyncMock(return_value=_mock_media())

    result = await _poll_collections(mock_bb, since_date)

    assert len(result) == 1
    assert result[0]["image_urls"] == []
    assert result[0]["video_urls"] == []


@pytest.mark.asyncio
async def test_poll_collections_multiple(mock_collection, since_date):
    """Test fetching multiple collections."""
    mock_bb = AsyncMock()

    col1 = mock_collection(collection_id="col_1", bird_name="Robin")
    col2 = mock_collection(collection_id="col_2", bird_name="Finch")

    mock_bb.refresh_collections = AsyncMock(
        return_value={"col_1": col1, "col_2": col2}
    )
    mock_bb.collection = AsyncMock(
        side_effect=[
            _mock_media(images=["https://example.com/robin.jpg"]),
            _mock_media(images=["https://example.com/finch.jpg"]),
        ]
    )

    result = await _poll_collections(mock_bb, since_date)

    assert len(result) == 2
    assert result[0]["bb_id"] == "collection-col_1"
    assert result[0]["species"] == ["Robin"]
    assert result[0]["image_urls"] == ["https://example.com/robin.jpg"]
    assert result[1]["bb_id"] == "collection-col_2"
    assert result[1]["species"] == ["Finch"]
    assert result[1]["image_urls"] == ["https://example.com/finch.jpg"]


# --- _fetch_bb_items tests ---


@pytest.mark.asyncio
async def test_fetch_bb_items_sorted_by_created_at(
    mock_postcard, mock_sighting, mock_collection, since_date
):
    """Test that _fetch_bb_items returns items sorted by created_at ascending."""
    mock_bb = AsyncMock()

    oldest = since_date + timedelta(minutes=5)
    middle = since_date + timedelta(minutes=15)
    newest = since_date + timedelta(minutes=30)

    # Postcards return newest first
    card_newest = mock_postcard("postcard_new", created_at=newest)
    card_oldest = mock_postcard("postcard_old", created_at=oldest)
    mock_bb.feed = AsyncMock(return_value=_mock_feed([card_newest, card_oldest]))
    mock_bb.sighting_from_postcard = AsyncMock(return_value=mock_sighting())

    # Collection returns middle timestamp
    col = mock_collection(collection_id="col_mid", bird_name="Robin", visit_time=middle)
    mock_bb.refresh_collections = AsyncMock(return_value={"col_mid": col})
    mock_bb.collection = AsyncMock(return_value={})

    result = await _fetch_bb_items(mock_bb, since_date)

    assert len(result) == 3
    assert result[0]["created_at"] == oldest
    assert result[1]["created_at"] == middle
    assert result[2]["created_at"] == newest
