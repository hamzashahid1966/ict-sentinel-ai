"""
ICT Sentinel AI - Institutional Knowledge Engine
Loads and indexes the ICT 2024 Mentorship machine-readable knowledge base.
Provides real-time lecture citation, execution rule lookup, and episodic learning synchronization.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("ICTSentinel.Knowledge")

class KnowledgeEngine:
    def __init__(self, knowledge_dir: Optional[str] = None):
        if knowledge_dir is None:
            # Locate relative to project root
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            knowledge_dir = os.path.join(base_dir, "ict_mentorship_knowledge")
        
        self.knowledge_dir = os.path.abspath(knowledge_dir)
        self.concepts: Dict[str, Any] = {}
        self.rules: Dict[str, Any] = {}
        self.lectures: Dict[int, Any] = {}
        self.adaptive_log: Dict[str, Any] = {}
        self.discussions: List[Dict[str, Any]] = []
        self.framework: Dict[str, Any] = {}
        
        self.reload()

    def reload(self):
        """Loads or reloads all JSON knowledge files from disk."""
        if not os.path.exists(self.knowledge_dir):
            logger.warning(f"Knowledge directory not found: {self.knowledge_dir}")
            return

        # 1. Foundational Concepts
        p1 = os.path.join(self.knowledge_dir, "01_foundational_concepts.json")
        if os.path.exists(p1):
            try:
                with open(p1, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for c in data.get("concepts", []):
                        self.concepts[c.get("id")] = c
            except Exception as e:
                logger.error(f"Error loading {p1}: {e}")

        # 2. Execution Rules
        p2 = os.path.join(self.knowledge_dir, "02_execution_rules.json")
        if os.path.exists(p2):
            try:
                with open(p2, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for r in data.get("rules", []):
                        self.rules[r.get("id")] = r
            except Exception as e:
                logger.error(f"Error loading {p2}: {e}")

        # 3. Lecture Catalog
        p3 = os.path.join(self.knowledge_dir, "03_lecture_catalog.json")
        if os.path.exists(p3):
            try:
                with open(p3, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for lec in data.get("lectures", []):
                        lec_num = lec.get("lecture")
                        if lec_num is not None:
                            self.lectures[lec_num] = lec
            except Exception as e:
                logger.error(f"Error loading {p3}: {e}")

        # 4. Adaptive Learning Log
        p4 = os.path.join(self.knowledge_dir, "04_adaptive_learning_log.json")
        if os.path.exists(p4):
            try:
                with open(p4, "r", encoding="utf-8") as f:
                    self.adaptive_log = json.load(f)
            except Exception as e:
                logger.error(f"Error loading {p4}: {e}")

        # 5. Discussions & Decisions
        p5 = os.path.join(self.knowledge_dir, "05_chat_discussions_and_decisions.json")
        if os.path.exists(p5):
            try:
                with open(p5, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.discussions = data.get("discussions", [])
            except Exception as e:
                logger.error(f"Error loading {p5}: {e}")

        # 6. Self-Learning Framework
        p6 = os.path.join(self.knowledge_dir, "06_self_learning_ai_framework.json")
        if os.path.exists(p6):
            try:
                with open(p6, "r", encoding="utf-8") as f:
                    self.framework = json.load(f)
            except Exception as e:
                logger.error(f"Error loading {p6}: {e}")

    def get_concept(self, concept_id: str) -> Optional[Dict[str, Any]]:
        return self.concepts.get(concept_id)

    def get_rule(self, rule_id: str) -> Optional[Dict[str, Any]]:
        return self.rules.get(rule_id)

    def get_lecture(self, lecture_num: int) -> Optional[Dict[str, Any]]:
        return self.lectures.get(lecture_num)

    def format_citation(self, rule_id: str) -> str:
        rule = self.get_rule(rule_id)
        if not rule:
            return f"[ICT Rule: {rule_id}]"
        lec = rule.get("lecture")
        name = rule.get("name", rule_id)
        if lec:
            return f"[Lecture {lec}: {name}]"
        return f"[ICT 2024: {name}]"

    def record_learning_episode(self, episode: Dict[str, Any]) -> bool:
        """Appends a new trade or observation episode into 04_adaptive_learning_log.json."""
        p4 = os.path.join(self.knowledge_dir, "04_adaptive_learning_log.json")
        try:
            if not self.adaptive_log:
                self.adaptive_log = {
                    "system": "ICT Sentinel AI - Adaptive Learning & Self-Improving Memory Ledger",
                    "version": "1.0",
                    "episodes": [],
                    "current_regime_weights": {}
                }
            if "episodes" not in self.adaptive_log:
                self.adaptive_log["episodes"] = []
            
            self.adaptive_log["episodes"].append(episode)
            
            # Write back atomically
            with open(p4, "w", encoding="utf-8") as f:
                json.dump(self.adaptive_log, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to record learning episode: {e}")
            return False
