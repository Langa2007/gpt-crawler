import unittest

from python_ai.app.ai_synthesizer import AISynthesizer


class TestHeuristicSynthesis(unittest.TestCase):
    def test_date_question_returns_date_from_relevant_source(self):
        result = AISynthesizer()._heuristic_synthesis(
            "when is kenyan independence day",
            [
                {
                    "title": "Jamhuri Day - Wikipedia",
                    "url": "https://en.wikipedia.org/wiki/Jamhuri_Day",
                    "text": "Jamhuri Day is celebrated annually on 12 December in Kenya.",
                },
                {
                    "title": "Independence Day (Jamaica)",
                    "url": "https://example.test/jamaica",
                    "text": "Jamaica celebrates independence on 6 August.",
                },
            ],
            [],
        )
        self.assertIn("12 December", result["answer"])
        self.assertNotIn("6 August", result["answer"])

    def test_recurring_date_beats_publication_date(self):
        result = AISynthesizer()._heuristic_synthesis(
            "when is christmas",
            [
                {
                    "title": "Christmas - Wikipedia",
                    "text": (
                        "Christmas is celebrated on December 25 each year. "
                        "A related article was published on December 9, 2023."
                    ),
                }
            ],
            [],
        )
        self.assertIn("December 25", result["answer"])
        self.assertNotIn("December 9, 2023", result["answer"])


if __name__ == "__main__":
    unittest.main()
