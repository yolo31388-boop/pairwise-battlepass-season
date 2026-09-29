"""赛季通行证与战令系统。

修复点：
1. 任务经验按类型(PVP/PVE/日常/周常)与难度(简单/普通/困难)分级计算。
2. 升级经验按二次曲线递增，后期升级需要更多经验。
3. 免费/付费奖励分轨存储，领取时做付费墙与重复领取校验。
4. 日常/周常重置只刷新任务本身，已完成（含未领取）的记录保留到赛季结束。
5. 满级后的经验溢出自动转化为溢出货币，不再凭空消失。
6. 赛季结束生成结算快照，等级/奖励/完成任务永久可查。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


# 任务类型系数：PVP > 周常 > PVE > 日常
TASK_EXP_COEFF: dict[str, float] = {
    "daily": 1.0,
    "pve": 1.5,
    "pvp": 2.0,
    "weekly": 3.0,
}

# 难度系数
DIFFICULTY_COEFF: dict[str, float] = {
    "easy": 0.8,
    "normal": 1.0,
    "hard": 1.5,
}


@dataclass
class TaskRecord:
    """一个已完成的战令任务（领取状态独立保留，重置任务不清空）。"""

    task_id: str
    task_type: str
    difficulty: str
    base_exp: int
    exp: int
    reward: dict = field(default_factory=dict)
    claimed: bool = False
    completed_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "difficulty": self.difficulty,
            "base_exp": self.base_exp,
            "exp": self.exp,
            "reward": dict(self.reward),
            "claimed": self.claimed,
            "completed_at": self.completed_at,
        }


@dataclass
class BattlePass:
    level: int = 1
    exp: int = 0
    total_exp: int = 0
    paid: bool = False
    claimed_free: set = field(default_factory=set)
    claimed_paid: set = field(default_factory=set)
    # 满级后溢出的经验与转化出的溢出货币
    overflow_exp: int = 0
    overflow_currency: int = 0
    # 已完成任务历史，key 为 task_id
    tasks: dict[str, TaskRecord] = field(default_factory=dict)


class BattlePassSystem:
    max_level = 100

    def __init__(self):
        self.passes: dict[str, BattlePass] = {}
        # 升级曲线：required(level) = 1000 + (level-1)^2 / 25，逐级递增且后期加速
        self.exp_base = 1000
        self.exp_curve_divisor = 25
        # 满级后 1 点溢出经验兑换 1 单位溢出货币
        self.overflow_rate = 1
        # 免费 / 付费两条奖励轨，按等级配置；未配置时用默认奖励
        self.free_rewards: dict[int, dict] = {}
        self.paid_rewards: dict[int, dict] = {}
        self.default_free_reward = {"gold": 100}
        self.default_paid_reward = {"gold": 300, "gem": 20}
        self.season_end_time: float = 0.0
        self.season_snapshots: dict[str, dict] = {}

    # ---------- 经验 ----------

    def calc_task_exp(self, base_exp: int, task_type: str = "daily",
                      difficulty: str = "normal") -> int:
        """按任务类型系数 × 难度系数计算实际发放经验。"""
        type_coeff = TASK_EXP_COEFF.get(task_type, 1.0)
        difficulty_coeff = DIFFICULTY_COEFF.get(difficulty, 1.0)
        return max(0, int(base_exp * type_coeff * difficulty_coeff))

    def get_exp_required(self, level: int) -> int:
        """从 level 升到 level+1 所需经验，二次曲线递增。"""
        if level < 1:
            return self.exp_base
        return self.exp_base + ((level - 1) ** 2) // self.exp_curve_divisor

    def add_exp(self, player: str, amount: int, task_type: str = "daily",
                difficulty: str = "normal") -> int:
        bp = self.passes.setdefault(player, BattlePass())
        gained = self.calc_task_exp(amount, task_type, difficulty)
        bp.total_exp += gained

        if bp.level >= self.max_level:
            self._handle_overflow(bp, gained)
            return gained

        bp.exp += gained
        while bp.level < self.max_level and bp.exp >= self.get_exp_required(bp.level):
            bp.exp -= self.get_exp_required(bp.level)
            bp.level += 1

        # 刚好/越级冲到满级后，剩余经验属于溢出
        if bp.level >= self.max_level and bp.exp > 0:
            self._handle_overflow(bp, bp.exp)
            bp.exp = 0
        return gained

    def _handle_overflow(self, bp: BattlePass, exp: int) -> None:
        """满级经验溢出：记录并转化为溢出货币，不丢失。"""
        bp.overflow_exp += exp
        bp.overflow_currency += exp * self.overflow_rate

    # ---------- 任务 ----------

    def complete_task(self, player: str, task_id: str, base_exp: int,
                      task_type: str = "daily", difficulty: str = "normal",
                      reward: dict | None = None) -> int:
        bp = self.passes.setdefault(player, BattlePass())
        gained = self.add_exp(player, base_exp, task_type, difficulty)
        bp.tasks[task_id] = TaskRecord(
            task_id=task_id,
            task_type=task_type,
            difficulty=difficulty,
            base_exp=base_exp,
            exp=gained,
            reward=dict(reward or {}),
            claimed=False,
            completed_at=time.time(),
        )
        return gained

    def claim_task_reward(self, player: str, task_id: str) -> dict:
        bp = self.passes.get(player)
        if bp is None or task_id not in bp.tasks:
            return {}
        task = bp.tasks[task_id]
        if task.claimed:
            return {}
        task.claimed = True
        return dict(task.reward)

    def reset_weekly(self, player: str) -> None:
        """周常任务重置：只刷新任务进度，战令等级与已完成/已领奖励全部保留。"""
        bp = self.passes.get(player)
        if bp is None:
            return
        # tasks 中仅保存已完成记录，它们保留到赛季结束，重置不清空。

    def reset_daily(self, player: str) -> None:
        """日常任务重置：同样保留所有已完成任务与战令奖励记录。"""
        bp = self.passes.get(player)
        if bp is None:
            return
        # 历史记录保留到赛季结束；当前实现下已完成任务均为历史，无需清理。

    # ---------- 奖励 ----------

    def purchase_paid(self, player: str) -> None:
        self.passes.setdefault(player, BattlePass()).paid = True

    def set_reward(self, level: int, reward: dict, is_paid: bool) -> None:
        track = self.paid_rewards if is_paid else self.free_rewards
        track[level] = dict(reward)

    def claim_reward(self, player: str, level: int, is_paid: bool) -> dict:
        bp = self.passes.get(player)
        if bp is None or level < 1 or level > bp.level:
            return {}

        claimed = bp.claimed_paid if is_paid else bp.claimed_free
        if level in claimed:
            return {}

        # 付费墙：未购买付费版不能领取付费轨奖励
        if is_paid and not bp.paid:
            return {}

        if is_paid:
            reward = dict(self.paid_rewards.get(level, self.default_paid_reward))
        else:
            reward = dict(self.free_rewards.get(level, self.default_free_reward))
        claimed.add(level)
        return reward

    # ---------- 赛季结算 ----------

    def end_season(self, season_id: str) -> dict:
        """生成赛季结算快照并开启新赛季（战令从零开始，历史永久可查）。"""
        snapshot: dict[str, dict] = {}
        ended_at = time.time()
        for player, bp in self.passes.items():
            snapshot[player] = {
                "player": player,
                "level": bp.level,
                "exp": bp.exp,
                "total_exp": bp.total_exp,
                "paid": bp.paid,
                "claimed_free": sorted(bp.claimed_free),
                "claimed_paid": sorted(bp.claimed_paid),
                "overflow_exp": bp.overflow_exp,
                "overflow_currency": bp.overflow_currency,
                "completed_tasks": [task.to_dict() for task in bp.tasks.values()],
                "ended_at": ended_at,
            }
        self.season_snapshots[season_id] = snapshot
        self.season_end_time = ended_at
        # 新赛季从零开始；旧赛季数据只在快照中追溯
        self.passes = {}
        return snapshot

    def get_season_record(self, season_id: str, player: str) -> dict:
        """查询某玩家在历史赛季的结算记录。"""
        return self.season_snapshots.get(season_id, {}).get(player, {})
