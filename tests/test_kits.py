import unittest

from survey_extract.kits import load_kits, normalize_kit

K = load_kits()


class NormalizeKit(unittest.TestCase):
    def check(self, text, std, state="ok"):
        self.assertEqual(normalize_kit(text, K), (std, state), text)

    def test_standard_names_map_to_themselves(self):
        for name in K:
            self.check(name, name)

    def test_modifiers_and_suffixes_are_ignored(self):
        self.check("노래하는 케이크", "노래하는 케익")
        self.check("케이크 만들기", "노래하는 케익")
        self.check("생일 축하 케이크", "노래하는 케익")
        self.check("스마트워치 만들기", "스마트 워치")
        self.check("메롱 개구리", "메롱하는 개구리")
        self.check("강아지 ", "인사하는 강아지")

    def test_synonyms_and_spelling(self):
        for t in ("마법봉 만들기", "요술봉", "유정", "요정 ", "마술봉 키트"):
            self.check(t, "마술봉")
        self.check("자벌레", "자벌래")
        self.check("메세지 키링", "메시지키링")
        self.check("키링", "메시지키링")

    def test_empty(self):
        self.check("", "", "empty")
        self.check("  ", "", "empty")

    def test_unmatched_and_ambiguous_are_not_guessed(self):
        self.check("설명", "", "unmatched")
        self.check("개구리 키링 만들기", "", "ambiguous")


if __name__ == "__main__":
    unittest.main()
