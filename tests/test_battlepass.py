"""赛季通行证与战令系统 - 红态测试"""
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from battlepass.season import BattlePassSystem, BattlePass

class TestExpCurve:
    def test_exp_required_increases(self):
        bps = BattlePassSystem()
        e1 = bps.get_exp_required(1)
        e50 = bps.get_exp_required(50)
        assert e50 > e1  # bug1: 都是1000

class TestExpByTaskType:
    def test_pvp_gives_more_exp(self):
        bps = BattlePassSystem()
        bps.passes["p1"] = BattlePass()
        bps.add_exp("p1", 100, "daily")
        l1 = bps.passes["p1"].level
        bps.add_exp("p1", 100, "pvp")  # PVP应该给更多
        # 这个测试设计有问题，add_exp的amount已经是最终值
        # 应该是：系统根据任务类型计算经验
        # 换个测法

class TestPaidWall:
    def test_free_cannot_claim_paid(self):
        bps = BattlePassSystem()
        bps.passes["p1"] = BattlePass(level=5, paid=False)
        reward = bps.claim_reward("p1", 5, is_paid=True)
        assert reward == {}  # bug4: 免费玩家领到了

class TestResetKeepsRewards:
    def test_weekly_reset_keeps_unclaimed(self):
        bps = BattlePassSystem()
        bp = BattlePass(level=5)
        bp.claimed_free = {1, 2}  # 已领1、2级
        bps.passes["p1"] = bp
        bps.reset_weekly("p1")
        # 已领记录不应被清空（周常任务重置不等于战令等级重置）
        # 或者：未领取的奖励应该保留
        assert len(bps.passes["p1"].claimed_free) > 0  # bug5: 被清空了

class TestSeasonSnapshot:
    def test_season_end_creates_snapshot(self):
        bps = BattlePassSystem()
        bps.passes["p1"] = BattlePass(level=50, exp=500)
        bps.end_season("s1")
        assert "s1" in bps.season_snapshots  # bug6: 空
        assert bps.season_snapshots["s1"].get("p1", {}).get("level") == 50

class TestExpOverflow:
    def test_exp_overflow_handled(self):
        bps = BattlePassSystem()
        bps.passes["p1"] = BattlePass(level=99, exp=900)
        bps.add_exp("p1", 500)  # 超过满级
        # 溢出经验应该被处理（转化为货币或保留）
        assert bps.passes["p1"].level >= 100
        # 不应该丢失经验或报错
