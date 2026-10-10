from core.config import get_app_name, get_environment


def test_app_name():
    assert get_app_name() == "Blue Moon Apartments"


def test_environment():
    assert isinstance(get_environment(), str)
    assert len(get_environment()) > 0