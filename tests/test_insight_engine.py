import unittest

from insight_engine import WEIGHTS, rank_financial_insights


class InsightEngineTest(unittest.TestCase):
    def test_weights_reward_utility_and_penalize_risk(self):
        self.assertGreater(WEIGHTS["financial_impact"], 0)
        self.assertGreater(WEIGHTS["actionability"], 0)
        self.assertLess(WEIGHTS["anxiety_risk"], 0)
        self.assertLess(WEIGHTS["distraction_risk"], 0)

    def test_partial_close_prioritizes_data_completion(self):
        insights = rank_financial_insights(
            {"income": 40000, "profit": 25000, "fuel_cost": 8000, "expenses": 7000},
            confidence="PARTIAL",
        )
        self.assertEqual("complete_data", insights[0].kind)
        self.assertLessEqual(len(insights), 3)

    def test_negative_profit_and_cash_gap_produce_actions(self):
        insights = rank_financial_insights(
            {"income": 10000, "profit": -3000, "fuel_cost": 8000, "expenses": 5000},
            confidence="CONFIRMED",
            cash_difference=-1500,
        )
        kinds = {item.kind for item in insights}
        self.assertIn("negative_profit", kinds)
        self.assertIn("cash_mismatch", kinds)
        self.assertTrue(all(item.action for item in insights))

    def test_seen_insight_is_penalized(self):
        metrics = {"income": 50000, "profit": 35000, "fuel_cost": 11000, "expenses": 4000}
        fresh = rank_financial_insights(metrics, confidence="CONFIRMED")
        repeated = rank_financial_insights(
            metrics,
            confidence="CONFIRMED",
            seen_kinds={"fuel_share"},
        )
        fresh_score = next(item.score for item in fresh if item.kind == "fuel_share")
        repeated_score = next(item.score for item in repeated if item.kind == "fuel_share")
        self.assertLess(repeated_score, fresh_score)


if __name__ == "__main__":
    unittest.main()
