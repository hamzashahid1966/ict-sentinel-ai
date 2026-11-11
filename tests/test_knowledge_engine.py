"""
Unit Test Suite for KnowledgeEngine
Verifies parsing of foundational concepts, execution rules, lecture citations, and episode recording.
"""

import os
import unittest
from ict_sentinel.knowledge_engine import KnowledgeEngine

class TestKnowledgeEngine(unittest.TestCase):
    def setUp(self):
        self.engine = KnowledgeEngine()

    def test_load_concepts_and_rules(self):
        self.assertTrue(len(self.engine.rules) >= 5, "Should have loaded at least 5 execution rules")
        self.assertIn("RULE_10AM_GATE", self.engine.rules)
        self.assertIn("RULE_CANDLE_BODY_MSS", self.engine.rules)
        self.assertIn("RULE_CONSEQUENT_ENCROACHMENT", self.engine.rules)

    def test_format_citation(self):
        cit1 = self.engine.format_citation("RULE_10AM_GATE")
        self.assertIn("Lecture 51", cit1)
        self.assertIn("10:00 AM New York Gate Filter", cit1)

        cit2 = self.engine.format_citation("RULE_CANDLE_BODY_MSS")
        self.assertIn("Lecture 48", cit2)

    def test_discussions_loaded(self):
        self.assertTrue(len(self.engine.discussions) >= 5, "Should have loaded chat discussions and decisions")
        topic_ids = [d.get("topic_id") for d in self.engine.discussions]
        self.assertIn("TIMEZONE_SYNCHRONIZATION", topic_ids)
        self.assertIn("ASIA_ZERO_TRADES_EXPLANATION", topic_ids)
        self.assertIn("FOUR_OUT_OF_FIVE_CONDITIONS", topic_ids)

if __name__ == "__main__":
    unittest.main()

