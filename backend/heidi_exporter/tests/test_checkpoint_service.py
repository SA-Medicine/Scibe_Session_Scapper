from src.services.checkpoint_service import CheckpointService


def test_checkpoint_defaults_and_updates(tmp_path) -> None:
    checkpoint = CheckpointService(tmp_path)
    assert checkpoint.load() == {
        "last_processed_ordinal": 0,
        "last_session_id": None,
        "last_session_url": None,
        "total_processed": 0,
        "last_updated": None,
        "run_started": None,
    }
    assert not checkpoint.should_skip(1)

    checkpoint.update_session_pointer("session-3", "https://scribe.heidihealth.com/en/scribe/session/session-3", 3)

    assert checkpoint.load() == {
        "last_processed_ordinal": 3,
        "last_session_id": "session-3",
        "last_session_url": "https://scribe.heidihealth.com/en/scribe/session/session-3",
        "total_processed": 3,
        "last_updated": checkpoint.load()["last_updated"],
        "run_started": checkpoint.load()["run_started"],
    }
    assert checkpoint.should_skip(2)
    assert not checkpoint.should_skip(4)


def test_checkpoint_loads_legacy_schema(tmp_path) -> None:
    checkpoint = CheckpointService(tmp_path)
    checkpoint.path.write_text('{"last_processed_session": 7}', encoding="utf-8")

    loaded = checkpoint.load()

    assert loaded["last_processed_ordinal"] == 7
    assert loaded["last_session_id"] is None
    assert loaded["total_processed"] == 0

