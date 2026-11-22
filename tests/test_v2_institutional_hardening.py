"""
ICT Sentinel AI - Phase 1 Institutional Hardening Verification Suite
Validates:
1. Timezone & DST Protection (zoneinfo America/New_York & Europe/London pinning)
2. Portfolio USD Correlation Guard (Blocks stacked same-direction USD exposure)
3. CME Futures Indivisibility (Discrete Single-Contract Protocol: 100% exit at 2.0R, BE at 1.0R)
4. Multi-Contract / Forex Partial Scaling (Divisible contracts)
"""

import os
import unittest
import tests  # noqa: F401  (bootstraps ICT_KNOWLEDGE_DIR so test trades never touch the real ledger)
import datetime
import tempfile
from zoneinfo import ZoneInfo

from ict_sentinel.config import ASSET_SPECS, NY_TZ, LON_TZ
from ict_sentinel.models import Candle, PDArray, Position
from ict_sentinel.order_manager import OrderManager
from ict_sentinel.storage import StorageEngine
from ict_sentinel.ai_advisor import AIAdvisor
from ict_sentinel.memory_engine import MemoryEngine
from ict_sentinel.ipda_engine import AlgorithmicSignal, IPDAEngine

class TestV2InstitutionalHardening(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.storage = StorageEngine(db_path=self.temp_db.name)
        self.advisor = AIAdvisor()
        self.memory = MemoryEngine(self.storage, self.advisor)
        self.order_mgr = OrderManager(self.storage, self.advisor, self.memory)
        self.ipda = IPDAEngine()

    def tearDown(self):
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    # ---------------- 1. TIMEZONE & DST PROTECTION TESTS ----------------
    def test_timezone_dst_pinning(self):
        """Verify ZoneInfo properly resolves summer and winter offsets without static drift."""
        # US Daylight Saving Time (e.g. July): NY is UTC-4
        summer_dt = datetime.datetime(2026, 7, 15, 12, 0, tzinfo=datetime.timezone.utc)
        ny_summer = summer_dt.astimezone(NY_TZ)
        self.assertEqual(ny_summer.hour, 8, "Summer NY time should be UTC-4 (12 UTC -> 8 AM EDT)")

        # US Standard Time (e.g. January): NY is UTC-5
        winter_dt = datetime.datetime(2026, 1, 15, 12, 0, tzinfo=datetime.timezone.utc)
        ny_winter = winter_dt.astimezone(NY_TZ)
        self.assertEqual(ny_winter.hour, 7, "Winter NY time should be UTC-5 (12 UTC -> 7 AM EST)")

        # London Summer (BST, July): London is UTC+1
        lon_summer = summer_dt.astimezone(LON_TZ)
        self.assertEqual(lon_summer.hour, 13, "Summer London time should be UTC+1 (12 UTC -> 1 PM BST)")

        # London Winter (GMT, January): London is UTC+0
        lon_winter = winter_dt.astimezone(LON_TZ)
        self.assertEqual(lon_winter.hour, 12, "Winter London time should be UTC+0 (12 UTC -> 12 PM GMT)")

    # ---------------- 2. PORTFOLIO USD CORRELATION GUARD TESTS ----------------
    def test_usd_correlation_guard_blocks_duplicate_short_usd(self):
        """
        Verify that holding an active LONG Gold position (which is SHORT USD)
        blocks an incoming LONG GBPUSD position (which is also SHORT USD).
        """
        now = datetime.datetime.now(NY_TZ)

        # 1. Open Long Gold (Short USD)
        sig_gold = AlgorithmicSignal(
            asset='GOLD',
            session='LONDON_CORE',
            direction='LONG',
            entry_price=3850.0,
            stop_loss=3847.0,
            risk_pts=3.0,
            target_center_mass=3856.0,
            target_head_shot=3859.0,
            pd_array=PDArray('ASIA_SWEEP', 3870.0, 3850.0, None, now),
            ai_rationale='Gold long setup'
        )
        pos_gold = self.order_mgr.open_position_from_signal(sig_gold, now)
        self.assertIsNotNone(pos_gold, "Initial Gold position should be accepted")

        # 2. Incoming Long GBPUSD (also Short USD) -> MUST BE BLOCKED
        sig_gbpusd_long = AlgorithmicSignal(
            asset='GBPUSD',
            session='LONDON',
            direction='LONG',
            entry_price=1.3150,
            stop_loss=1.3135,
            risk_pts=0.0015,
            target_center_mass=1.3175,
            target_head_shot=1.3195,
            pd_array=PDArray('BISI', 1.3155, 1.3145, 1.3150, now),
            ai_rationale='GBPUSD long setup'
        )
        pos_gbp_blocked = self.order_mgr.open_position_from_signal(sig_gbpusd_long, now)
        self.assertIsNone(pos_gbp_blocked, "Correlation Guard MUST block duplicate Short-USD risk (Long Gold + Long GBPUSD)")

        # 3. Incoming Short GBPUSD (Long USD) -> APPROVED (Hedged currency beta)
        sig_gbpusd_short = AlgorithmicSignal(
            asset='GBPUSD',
            session='LONDON',
            direction='SHORT',
            entry_price=1.3150,
            stop_loss=1.3165,
            risk_pts=0.0015,
            target_center_mass=1.3125,
            target_head_shot=1.3105,
            pd_array=PDArray('SIBI', 1.3155, 1.3145, 1.3150, now),
            ai_rationale='GBPUSD short setup'
        )
        pos_gbp_approved = self.order_mgr.open_position_from_signal(sig_gbpusd_short, now)
        self.assertIsNotNone(pos_gbp_approved, "Opposite USD direction (Short GBPUSD = Long USD) should be approved")

        # 4. Incoming NASDAQ (Neutral USD relation) -> APPROVED
        sig_nasdaq = AlgorithmicSignal(
            asset='NASDAQ',
            session='NEW_YORK_AM',
            direction='LONG',
            entry_price=20500.0,
            stop_loss=20485.0,
            risk_pts=15.0,
            target_center_mass=20530.0,
            target_head_shot=20545.0,
            pd_array=PDArray('BISI', 20505.0, 20495.0, 20500.0, now),
            ai_rationale='Nasdaq equity long'
        )
        pos_nasdaq = self.order_mgr.open_position_from_signal(sig_nasdaq, now)
        self.assertIsNotNone(pos_nasdaq, "Neutral asset (NASDAQ) should not be blocked by currency correlation")

    # ---------------- 3. DISCRETE SINGLE-CONTRACT FUTURES PROTOCOL TESTS ----------------
    def test_single_contract_futures_breakeven_trail_at_1r(self):
        """
        On CME Micro Gold (MGC) with quantity = 1:
        Verify reaching 1.0R expansion locks stop to Breakeven + Friction Buffer.
        """
        session_time = datetime.datetime(2026, 11, 18, 5, 30, tzinfo=NY_TZ)
        sig_gold = AlgorithmicSignal(
            asset='GOLD',
            session='LONDON_CORE',
            direction='LONG',
            entry_price=3800.0,
            stop_loss=3797.0, # risk_pts = 3.0
            risk_pts=3.0,
            target_center_mass=3806.0,
            target_head_shot=3809.0,
            pd_array=PDArray('ASIA_SWEEP', 3820.0, 3800.0, None, session_time),
            ai_rationale='Gold test'
        )
        pos = self.order_mgr.open_position_from_signal(sig_gold, session_time)
        self.assertEqual(pos.target_center_mass, 3806.0, "Single contract target should be set to 2.0R (3800 + 2*3 = 3806)")

        # Send bar reaching 1.0R expansion (high >= 3803.0) at 05:35 EST
        bar_time = session_time + datetime.timedelta(minutes=5)
        bar_1r = Candle(bar_time, bar_time, 3801.0, 3803.5, 3800.5, 3803.0, 100)
        closed = self.order_mgr.update_positions_with_bar('GOLD', bar_1r)
        self.assertEqual(len(closed), 0, "Position remains open with runner towards 2.0R target")
        self.assertTrue(pos.center_mass_filled, "Center mass filled flag should indicate 1.0R shield active")
        self.assertGreater(pos.active_trailing_stop, pos.entry_price, "Stop should be trailed above entry to cover friction")

        # Now send bar triggering the trailed stop at 05:40 EST
        bar_time_stop = session_time + datetime.timedelta(minutes=10)
        bar_stop = Candle(bar_time_stop, bar_time_stop, 3802.0, 3802.5, pos.active_trailing_stop - 0.5, pos.active_trailing_stop - 0.1, 100)
        closed_stop = self.order_mgr.update_positions_with_bar('GOLD', bar_stop)
        self.assertEqual(len(closed_stop), 1)
        tr = closed_stop[0]
        self.assertEqual(tr.outcome, 'DEFENSIVE_STOP')
        self.assertGreaterEqual(tr.dollar_pnl, 0.0, "Trailing stop cushion MUST prevent loss after 1.0R expansion")

    def test_single_contract_futures_full_win_at_2r(self):
        """
        On CME Micro Gold (MGC) with quantity = 1:
        Verify reaching 2.0R exits 100% of the single contract cleanly with FULL_WIN.
        """
        session_time = datetime.datetime(2026, 11, 18, 5, 30, tzinfo=NY_TZ)
        sig_gold = AlgorithmicSignal(
            asset='GOLD',
            session='LONDON_CORE',
            direction='LONG',
            entry_price=3800.0,
            stop_loss=3797.0, # risk_pts = 3.0, target 2.0R = 3806.0
            risk_pts=3.0,
            target_center_mass=3806.0,
            target_head_shot=3809.0,
            pd_array=PDArray('ASIA_SWEEP', 3820.0, 3800.0, None, session_time),
            ai_rationale='Gold win test'
        )
        pos = self.order_mgr.open_position_from_signal(sig_gold, session_time)

        # Bar hitting 2.0R target directly at 05:35 EST (high = 3806.5)
        bar_time = session_time + datetime.timedelta(minutes=5)
        bar_target = Candle(bar_time, bar_time, 3802.0, 3806.5, 3801.5, 3806.0, 100)
        closed = self.order_mgr.update_positions_with_bar('GOLD', bar_target)
        self.assertEqual(len(closed), 1, "Should exit 100% on target hit")
        tr = closed[0]
        self.assertEqual(tr.outcome, 'FULL_WIN')
        self.assertEqual(tr.exit_price, 3806.0)
        # Expected PnL: 6 pts * $10/pt - friction ($1.25 + $1.00 = $2.25) = $57.75
        self.assertAlmostEqual(tr.dollar_pnl, 57.75, places=1)
        self.assertEqual(len(self.order_mgr._get_active_positions()), 0, "No lingering positions")

    # ---------------- 4. MULTI-CONTRACT / FOREX PARTIAL SCALING TESTS ----------------
    def test_forex_divisible_double_tap_partial(self):
        """
        On Forex (EURUSD) where positions are fractional/divisible mini lots:
        Verify standard Double Tap (50% partial at Center Mass 1.5R, runner at Head Shot 3.0R).
        """
        session_time = datetime.datetime(2026, 11, 18, 9, 30, tzinfo=NY_TZ)
        sig_fx = AlgorithmicSignal(
            asset='EURUSD',
            session='NEW_YORK_AM',
            direction='LONG',
            entry_price=1.0800,
            stop_loss=1.0790, # risk_pts = 0.0010 (10 pips)
            risk_pts=0.0010,
            target_center_mass=1.0815, # 1.5R
            target_head_shot=1.0830,   # 3.0R
            pd_array=PDArray('BISI', 1.0805, 1.0795, 1.0800, session_time),
            ai_rationale='Forex Double Tap test'
        )
        pos = self.order_mgr.open_position_from_signal(sig_fx, session_time)
        self.assertEqual(pos.target_center_mass, 1.0815)
        self.assertEqual(pos.target_head_shot, 1.0830)

        # Bar hitting Center Mass at 09:35 EST (high = 1.0818)
        bar_time = session_time + datetime.timedelta(minutes=5)
        bar_cm = Candle(bar_time, bar_time, 1.0805, 1.0818, 1.0802, 1.0815, 100)
        closed = self.order_mgr.update_positions_with_bar('EURUSD', bar_cm)
        self.assertEqual(len(closed), 0, "Center Mass partial banks 50% without closing the position")
        self.assertTrue(pos.center_mass_filled)
        self.assertEqual(pos.status, 'PARTIAL')
        self.assertGreater(pos.realized_pnl, 0.0, "Realized partial PnL banked")

        # Bar hitting Head Shot terminus at 09:40 EST (high = 1.0832)
        bar_time_hs = session_time + datetime.timedelta(minutes=10)
        bar_hs = Candle(bar_time_hs, bar_time_hs, 1.0820, 1.0832, 1.0818, 1.0830, 100)
        closed_hs = self.order_mgr.update_positions_with_bar('EURUSD', bar_hs)
        self.assertEqual(len(closed_hs), 1, "Head Shot closes the position")
        tr = closed_hs[0]
        self.assertEqual(tr.outcome, 'FULL_WIN')
        self.assertEqual(tr.exit_price, 1.0830)

if __name__ == '__main__':
    unittest.main()
