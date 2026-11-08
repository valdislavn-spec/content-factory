"""Tests for Travelata integration (no network)."""

from content_factory.integrations.travelata import TravelataClient, encode_params, parse_feed

FEED = (
    "Страна\tКурорт\tНазвание отеля\tСредняя цена\tСреднее количество взрослых\tСреднее количество ночей\tСсылка на отель\n"
    "Турция\tАнталья\tClub Hotel Sera\t55496\t2\t7\thttps://travelata.ru/goto/hotel/47905\n"
    "Куба\tо. Кайо Коко\tMemories Caribe\t131898\t2\t10\thttps://travelata.ru/goto/hotel/10284\n"
).encode("utf-16")


def test_encode_params_arrays():
    encoded = encode_params({"countries[]": [92, 111], "departureCity": 2, "nightRange[from]": 5})
    assert "countries[]=92" in encoded
    assert "countries[]=111" in encoded
    assert "departureCity=2" in encoded
    assert "nightRange[from]=5" in encoded


def test_parse_feed():
    rows = parse_feed(FEED)
    assert len(rows) == 2
    assert rows[0]["Страна"] == "Турция"
    assert rows[0]["price"] == 55496
    assert rows[1]["Название отеля"].startswith("Memories")


def test_client_configuration():
    client = TravelataClient(login="", password="")
    assert not client.configured()
    client = TravelataClient(login="user", password="pass")
    assert client.configured()
    assert client._auth_header().startswith("Basic ")
