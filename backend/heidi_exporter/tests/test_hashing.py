from src.utils.hashing import sha256_text


def test_sha256_text_is_stable() -> None:
    assert sha256_text("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

