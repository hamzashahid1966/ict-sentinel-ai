import unittest

import numpy as np

from research import other_markets as om

MON = 1782691200          # 2026-06-29, a Monday, 00:00 UTC


class TestOtherMarkets(unittest.TestCase):
    def test_forex_weekend_removed(self):
        hours = np.array([MON + 4 * 86400 + 20 * 3600,    # Friday 20:00 open
                          MON + 4 * 86400 + 21 * 3600,    # Friday 21:00 closed
                          MON + 5 * 86400 + 12 * 3600,    # Saturday closed
                          MON + 6 * 86400 + 21 * 3600,    # Sunday 21:00 closed
                          MON + 6 * 86400 + 22 * 3600])   # Sunday 22:00 open
        self.assertEqual(om.forex_open(hours).tolist(), [True, False, False, False, True])

    def test_resample_hour(self):
        t = MON + 300 * np.arange(24)
        a = np.column_stack([t, np.arange(24) + 1.0, np.arange(24) + 2.0, np.arange(24) + 0.5,
                             np.arange(24) + 1.5, np.ones(24), np.ones(24)])
        b = om.resample(a, 3600)
        self.assertEqual(len(b), 2)
        self.assertEqual(b[0].tolist(), [MON, 1.0, 13.0, 0.5, 12.5, 12.0, 12.0])

    def test_costs_are_applied_to_every_module(self):
        from research import gianluca_vp, ict_mayne, range_reentry, tc_pullback
        mods = (ict_mayne, gianluca_vp, range_reentry, tc_pullback)
        saved = [{k: getattr(m, k) for k in ("FEE", "SLIP", "MIN_WIDTH") if hasattr(m, k)} for m in mods]
        self.addCleanup(lambda: [m.__dict__.update(v) for m, v in zip(mods, saved)])
        om.set_costs()
        self.assertEqual((ict_mayne.FEE, gianluca_vp.FEE), (om.FEE, om.FEE))
        self.assertEqual({ict_mayne.SLIP, gianluca_vp.SLIP, range_reentry.SLIP, tc_pullback.SLIP}, {om.SLIP})
        self.assertEqual({ict_mayne.MIN_WIDTH, gianluca_vp.MIN_WIDTH, range_reentry.MIN_WIDTH, tc_pullback.MIN_WIDTH},
                         {om.MIN_WIDTH})


if __name__ == "__main__":
    unittest.main()
