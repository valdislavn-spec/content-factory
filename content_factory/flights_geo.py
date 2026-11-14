"""Справочник направлений для страниц и подборок дешёвых билетов.

Авиасейлс отдаёт только IATA-коды, поэтому на витрине появлялись строки вида
«CIT (CIT)» и «SCO». Здесь код превращается в человеческое название, страну и
набор тегов, по которым строятся подборки («тёплые», «Средняя Азия», «Турция»).

Теги:
    kz          — Казахстан
    cis         — СНГ (без Кавказа)
    caucasus    — Кавказ
    turkey      — Турция
    asia        — Азия дальше СНГ
    europe      — Европа
    middle_east — Ближний Восток
    warm        — зимой тепло (море или +20)
    beach       — курорт у моря
    long_haul   — дальний перелёт (7+ часов)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, Tuple


@dataclass(frozen=True)
class City:
    ru: str
    en: str
    country: str  # ISO-3166 alpha-2, пусто для неизвестных
    tags: FrozenSet[str] = frozenset()


COUNTRIES: Dict[str, Tuple[str, str]] = {
    "KZ": ("Казахстан", "🇰🇿"),
    "BY": ("Беларусь", "🇧🇾"),
    "RU": ("Россия", "🇷🇺"),
    "UZ": ("Узбекистан", "🇺🇿"),
    "TJ": ("Таджикистан", "🇹🇯"),
    "KG": ("Кыргызстан", "🇰🇬"),
    "TM": ("Туркменистан", "🇹🇲"),
    "AZ": ("Азербайджан", "🇦🇿"),
    "AM": ("Армения", "🇦🇲"),
    "GE": ("Грузия", "🇬🇪"),
    "TR": ("Турция", "🇹🇷"),
    "AE": ("ОАЭ", "🇦🇪"),
    "QA": ("Катар", "🇶🇦"),
    "SA": ("Саудовская Аравия", "🇸🇦"),
    "IL": ("Израиль", "🇮🇱"),
    "EG": ("Египет", "🇪🇬"),
    "TH": ("Таиланд", "🇹🇭"),
    "VN": ("Вьетнам", "🇻🇳"),
    "MY": ("Малайзия", "🇲🇾"),
    "SG": ("Сингапур", "🇸🇬"),
    "ID": ("Индонезия", "🇮🇩"),
    "LK": ("Шри-Ланка", "🇱🇰"),
    "IN": ("Индия", "🇮🇳"),
    "MV": ("Мальдивы", "🇲🇻"),
    "CN": ("Китай", "🇨🇳"),
    "HK": ("Гонконг", "🇭🇰"),
    "KR": ("Южная Корея", "🇰🇷"),
    "JP": ("Япония", "🇯🇵"),
    "DE": ("Германия", "🇩🇪"),
    "FR": ("Франция", "🇫🇷"),
    "IT": ("Италия", "🇮🇹"),
    "ES": ("Испания", "🇪🇸"),
    "PT": ("Португалия", "🇵🇹"),
    "NL": ("Нидерланды", "🇳🇱"),
    "CZ": ("Чехия", "🇨🇿"),
    "AT": ("Австрия", "🇦🇹"),
    "PL": ("Польша", "🇵🇱"),
    "LT": ("Литва", "🇱🇹"),
    "LV": ("Латвия", "🇱🇻"),
    "EE": ("Эстония", "🇪🇪"),
    "FI": ("Финляндия", "🇫🇮"),
    "GR": ("Греция", "🇬🇷"),
    "CY": ("Кипр", "🇨🇾"),
    "HU": ("Венгрия", "🇭🇺"),
    "GB": ("Великобритания", "🇬🇧"),
    "IE": ("Ирландия", "🇮🇪"),
    "CH": ("Швейцария", "🇨🇭"),
    "RS": ("Сербия", "🇷🇸"),
    "ME": ("Черногория", "🇲🇪"),
    "HR": ("Хорватия", "🇭🇷"),
    "BG": ("Болгария", "🇧🇬"),
    "RO": ("Румыния", "🇷🇴"),
}


def _c(ru: str, en: str, country: str, *tags: str) -> City:
    return City(ru=ru, en=en, country=country, tags=frozenset(tags))


CITIES: Dict[str, City] = {
    # Казахстан
    "ALA": _c("Алматы", "Almaty", "KZ", "kz"),
    "NQZ": _c("Астана", "Astana", "KZ", "kz"),
    "CIT": _c("Шымкент", "Shymkent", "KZ", "kz"),
    "SCO": _c("Актау", "Aktau", "KZ", "kz", "beach"),
    "AKX": _c("Актобе", "Aktobe", "KZ", "kz"),
    "GUW": _c("Атырау", "Atyrau", "KZ", "kz"),
    "KGF": _c("Караганда", "Karaganda", "KZ", "kz"),
    "URA": _c("Уральск", "Oral", "KZ", "kz"),
    "KZO": _c("Кызылорда", "Kyzylorda", "KZ", "kz"),
    "PLX": _c("Семей", "Semey", "KZ", "kz"),
    "UKK": _c("Усть-Каменогорск", "Ust-Kamenogorsk", "KZ", "kz"),
    "PWQ": _c("Павлодар", "Pavlodar", "KZ", "kz"),
    "DMB": _c("Тараз", "Taraz", "KZ", "kz"),
    "KOV": _c("Кокшетау", "Kokshetau", "KZ", "kz"),
    "TDK": _c("Талдыкорган", "Taldykorgan", "KZ", "kz"),
    "BXH": _c("Балхаш", "Balkhash", "KZ", "kz"),
    # Беларусь и Россия (для полноты, РФ на витрину не выводим)
    "MSQ": _c("Минск", "Minsk", "BY", "cis"),
    "MOW": _c("Москва", "Moscow", "RU", "cis"),
    "LED": _c("Санкт-Петербург", "St. Petersburg", "RU", "cis"),
    "KZN": _c("Казань", "Kazan", "RU", "cis"),
    "AER": _c("Сочи", "Sochi", "RU", "cis", "beach"),
    "KGD": _c("Калининград", "Kaliningrad", "RU", "cis"),
    "SVX": _c("Екатеринбург", "Yekaterinburg", "RU", "cis"),
    "KUF": _c("Самара", "Samara", "RU", "cis"),
    "ROV": _c("Ростов-на-Дону", "Rostov-on-Don", "RU", "cis"),
    "MCX": _c("Махачкала", "Makhachkala", "RU", "cis", "caucasus"),
    "MRV": _c("Минеральные Воды", "Mineralnye Vody", "RU", "cis", "caucasus"),
    # Средняя Азия
    "TAS": _c("Ташкент", "Tashkent", "UZ", "cis", "asia"),
    "SAM": _c("Самарканд", "Samarkand", "UZ", "cis", "asia"),
    "BHK": _c("Бухара", "Bukhara", "UZ", "cis", "asia"),
    "NCU": _c("Нукус", "Nukus", "UZ", "cis", "asia"),
    "DYU": _c("Душанбе", "Dushanbe", "TJ", "cis", "asia"),
    "KQT": _c("Худжанд", "Khujand", "TJ", "cis", "asia"),
    "FRU": _c("Бишкек", "Bishkek", "KG", "cis", "asia"),
    "OSS": _c("Ош", "Osh", "KG", "cis", "asia"),
    "ASB": _c("Ашхабад", "Ashgabat", "TM", "cis", "asia"),
    # Кавказ
    "BAK": _c("Баку", "Baku", "AZ", "caucasus", "cis"),
    "GYD": _c("Баку", "Baku", "AZ", "caucasus", "cis"),
    "EVN": _c("Ереван", "Yerevan", "AM", "caucasus", "cis"),
    "TBS": _c("Тбилиси", "Tbilisi", "GE", "caucasus", "cis"),
    "BUS": _c("Батуми", "Batumi", "GE", "caucasus", "cis", "beach"),
    # Турция
    "IST": _c("Стамбул", "Istanbul", "TR", "turkey"),
    "SAW": _c("Стамбул (Сабиха)", "Istanbul Sabiha", "TR", "turkey"),
    "AYT": _c("Анталья", "Antalya", "TR", "turkey", "warm", "beach"),
    "IZM": _c("Измир", "Izmir", "TR", "turkey", "warm", "beach"),
    "ADB": _c("Измир", "Izmir", "TR", "turkey", "warm", "beach"),
    "ESB": _c("Анкара", "Ankara", "TR", "turkey"),
    "DLM": _c("Даламан", "Dalaman", "TR", "turkey", "warm", "beach"),
    "BJV": _c("Бодрум", "Bodrum", "TR", "turkey", "warm", "beach"),
    "TZX": _c("Трабзон", "Trabzon", "TR", "turkey"),
    "GZP": _c("Аланья", "Alanya", "TR", "turkey", "warm", "beach"),
    # Ближний Восток и Африка
    "DXB": _c("Дубай", "Dubai", "AE", "middle_east", "warm", "beach"),
    "SHJ": _c("Шарджа", "Sharjah", "AE", "middle_east", "warm", "beach"),
    "AUH": _c("Абу-Даби", "Abu Dhabi", "AE", "middle_east", "warm", "beach"),
    "DOH": _c("Доха", "Doha", "QA", "middle_east", "warm", "beach"),
    "RUH": _c("Эр-Рияд", "Riyadh", "SA", "middle_east", "warm"),
    "JED": _c("Джидда", "Jeddah", "SA", "middle_east", "warm", "beach"),
    "TLV": _c("Тель-Авив", "Tel Aviv", "IL", "middle_east", "warm", "beach"),
    "SSH": _c("Шарм-эль-Шейх", "Sharm el-Sheikh", "EG", "warm", "beach"),
    "HRG": _c("Хургада", "Hurghada", "EG", "warm", "beach"),
    "CAI": _c("Каир", "Cairo", "EG", "warm"),
    # Азия
    "HKT": _c("Пхукет", "Phuket", "TH", "asia", "warm", "beach", "long_haul"),
    "BKK": _c("Бангкок", "Bangkok", "TH", "asia", "warm", "long_haul"),
    "CNX": _c("Чиангмай", "Chiang Mai", "TH", "asia", "warm", "long_haul"),
    "SIN": _c("Сингапур", "Singapore", "SG", "asia", "warm", "long_haul"),
    "KUL": _c("Куала-Лумпур", "Kuala Lumpur", "MY", "asia", "warm", "long_haul"),
    "DPS": _c("Бали", "Bali", "ID", "asia", "warm", "beach", "long_haul"),
    "CGK": _c("Джакарта", "Jakarta", "ID", "asia", "warm", "long_haul"),
    "CMB": _c("Коломбо", "Colombo", "LK", "asia", "warm", "beach", "long_haul"),
    "MLE": _c("Мале", "Male", "MV", "asia", "warm", "beach", "long_haul"),
    "DEL": _c("Дели", "Delhi", "IN", "asia", "warm", "long_haul"),
    "BOM": _c("Мумбаи", "Mumbai", "IN", "asia", "warm", "long_haul"),
    "GOI": _c("Гоа", "Goa", "IN", "asia", "warm", "beach", "long_haul"),
    "HAN": _c("Ханой", "Hanoi", "VN", "asia", "warm", "long_haul"),
    "SGN": _c("Хошимин", "Ho Chi Minh City", "VN", "asia", "warm", "long_haul"),
    "PEK": _c("Пекин", "Beijing", "CN", "asia", "long_haul"),
    "PVG": _c("Шанхай", "Shanghai", "CN", "asia", "long_haul"),
    "HKG": _c("Гонконг", "Hong Kong", "HK", "asia", "long_haul"),
    "ICN": _c("Сеул", "Seoul", "KR", "asia", "long_haul"),
    "NRT": _c("Токио", "Tokyo", "JP", "asia", "long_haul"),
    "KIX": _c("Осака", "Osaka", "JP", "asia", "long_haul"),
    # Европа
    "BER": _c("Берлин", "Berlin", "DE", "europe"),
    "MUC": _c("Мюнхен", "Munich", "DE", "europe"),
    "FRA": _c("Франкфурт", "Frankfurt", "DE", "europe"),
    "PAR": _c("Париж", "Paris", "FR", "europe"),
    "CDG": _c("Париж", "Paris", "FR", "europe"),
    "NCE": _c("Ницца", "Nice", "FR", "europe", "beach"),
    "ROM": _c("Рим", "Rome", "IT", "europe"),
    "FCO": _c("Рим", "Rome", "IT", "europe"),
    "MIL": _c("Милан", "Milan", "IT", "europe"),
    "MXP": _c("Милан", "Milan", "IT", "europe"),
    "VCE": _c("Венеция", "Venice", "IT", "europe"),
    "BCN": _c("Барселона", "Barcelona", "ES", "europe", "beach"),
    "MAD": _c("Мадрид", "Madrid", "ES", "europe"),
    "LIS": _c("Лиссабон", "Lisbon", "PT", "europe", "beach"),
    "AMS": _c("Амстердам", "Amsterdam", "NL", "europe"),
    "PRG": _c("Прага", "Prague", "CZ", "europe"),
    "VIE": _c("Вена", "Vienna", "AT", "europe"),
    "WAW": _c("Варшава", "Warsaw", "PL", "europe"),
    "VNO": _c("Вильнюс", "Vilnius", "LT", "europe"),
    "RIX": _c("Рига", "Riga", "LV", "europe"),
    "TLL": _c("Таллин", "Tallinn", "EE", "europe"),
    "HEL": _c("Хельсинки", "Helsinki", "FI", "europe"),
    "ATH": _c("Афины", "Athens", "GR", "europe", "warm", "beach"),
    "LCA": _c("Ларнака", "Larnaca", "CY", "europe", "warm", "beach"),
    "BUD": _c("Будапешт", "Budapest", "HU", "europe"),
    "LON": _c("Лондон", "London", "GB", "europe"),
    "LHR": _c("Лондон", "London", "GB", "europe"),
    "DUB": _c("Дублин", "Dublin", "IE", "europe"),
    "ZRH": _c("Цюрих", "Zurich", "CH", "europe"),
    "BEG": _c("Белград", "Belgrade", "RS", "europe"),
    "TIV": _c("Тиват", "Tivat", "ME", "europe", "beach"),
    "ZAG": _c("Загреб", "Zagreb", "HR", "europe"),
    "SOF": _c("София", "Sofia", "BG", "europe"),
    "OTP": _c("Бухарест", "Bucharest", "RO", "europe"),
}


def city(code: str) -> City:
    """Город по IATA-коду. Неизвестный код остаётся кодом, но не ломает вывод."""
    key = (code or "").upper().strip()
    return CITIES.get(key) or City(ru=key, en=key, country="", tags=frozenset())


def city_name(code: str, lang: str = "ru") -> str:
    c = city(code)
    return c.en if lang == "en" and c.en else c.ru



COUNTRIES_EN: Dict[str, str] = {
    "KZ": "Kazakhstan", "BY": "Belarus", "RU": "Russia", "UZ": "Uzbekistan",
    "TJ": "Tajikistan", "KG": "Kyrgyzstan", "TM": "Turkmenistan", "AZ": "Azerbaijan",
    "AM": "Armenia", "GE": "Georgia", "TR": "Turkey", "AE": "UAE", "QA": "Qatar",
    "SA": "Saudi Arabia", "IL": "Israel", "EG": "Egypt", "TH": "Thailand",
    "VN": "Vietnam", "MY": "Malaysia", "SG": "Singapore", "ID": "Indonesia",
    "LK": "Sri Lanka", "IN": "India", "MV": "Maldives", "CN": "China",
    "HK": "Hong Kong", "KR": "South Korea", "JP": "Japan", "DE": "Germany",
    "FR": "France", "IT": "Italy", "ES": "Spain", "PT": "Portugal",
    "NL": "Netherlands", "CZ": "Czechia", "AT": "Austria", "PL": "Poland",
    "LT": "Lithuania", "LV": "Latvia", "EE": "Estonia", "FI": "Finland",
    "GR": "Greece", "CY": "Cyprus", "HU": "Hungary", "GB": "United Kingdom",
    "IE": "Ireland", "CH": "Switzerland", "RS": "Serbia", "ME": "Montenegro",
    "HR": "Croatia", "BG": "Bulgaria", "RO": "Romania",
}


def country_name(code: str, lang: str = "ru") -> str:
    key = (code or "").upper()
    if lang == "en":
        return COUNTRIES_EN.get(key, COUNTRIES.get(key, ("", ""))[0])
    return COUNTRIES.get(key, ("", ""))[0]


def flag(code: str) -> str:
    return COUNTRIES.get((code or "").upper(), ("", ""))[1]


def tags(code: str) -> FrozenSet[str]:
    return city(code).tags


def has_tag(code: str, tag: str) -> bool:
    return tag in tags(code)


def known(codes: Iterable[str]) -> list:
    """Какие из кодов есть в справочнике — для отчёта и тестов."""
    return [c for c in codes if c.upper() in CITIES]
