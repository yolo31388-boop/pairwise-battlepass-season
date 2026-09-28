"""赛季通行证与战令系统 - 含6个bug"""
from dataclasses import dataclass, field

@dataclass
class BattlePass:
    level: int = 1
    exp: int = 0
    paid: bool = False
    claimed_free: set = field(default_factory=set)
    claimed_paid: set = field(default_factory=set)

class BattlePassSystem:
    def __init__(self):
        self.passes: dict[str, BattlePass] = {}
        self.exp_per_level = 1000  # bug1: 线性
        self.season_end_time: float = 0
        self.season_snapshots: dict = {}  # bug2: 无结算

    def add_exp(self, player: str, amount: int, task_type: str = "daily"):
        # bug3: 所有任务经验一样
        bp = self.passes.setdefault(player, BattlePass())
        bp.exp += amount
        while bp.exp >= self.exp_per_level:
            bp.exp -= self.exp_per_level
            bp.level += 1

    def get_exp_required(self, level: int) -> int:
        # bug1续: 线性
        return 1000

    def claim_reward(self, player: str, level: int, is_paid: bool) -> dict:
        # bug4: 免费玩家能领付费奖励
        bp = self.passes.get(player, BattlePass())
        if level > bp.level:
            return {}
        if is_paid and not bp.paid:
            return {}  # 这个检查有，但bug在别处
        return {"gold": 100}

    def reset_weekly(self, player: str):
        # bug5: 重置时清掉已完成未领奖励
        bp = self.passes.get(player, BattlePass())
        bp.claimed_free.clear()
        bp.claimed_paid.clear()

    def end_season(self, season_id: str):
        # bug6: 无结算快照
        pass
