from parlot.core.ids import new_session_id


def test_new_session_id_is_32_hex() -> None:
    sid = new_session_id()
    assert len(sid) == 32
    assert sid == sid.lower()
    int(sid, 16)
