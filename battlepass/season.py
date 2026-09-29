"""赛季通行证与战令系统

修复点：
1. 任务经验按类型(pvp/pve/daily/weekly)与难度(easy/normal/hard)分级。
2. 升级经验按曲线递增，后期需要更多经验。
3. 免费 / 付费奖励分轨存储，付费墙校验。
4. 周常任务重置时，已完成但未领取的任务奖励保留到赛季结束。
5. 满级后经验溢出自动转化为溢出货币，不会凭空消失。
6. 赛季结束生成结算快照，等级 / 奖励 / 完成任务永久可查。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

MAX_LEVEL = 100

# 任务类型系数：PVP 强度最高，周常高于日常，PVE 居中
TASK_TYPE_MULTIPLIER = {
    "pvp": 2.0,
    "pve": 1.5,
    "daily": 1.0,
    "weekly": 1.2,
}

# 任务难度系数
TASK_DIFFICULTY_MULTIPLIER = {
    "easy": 1.0,
    "normal": 1.5,
    "hard": 2.0,
}

# 各等级免费 / 付费奖励（分轨存储）
FREE_REWARDS = {lvl: {"gold": 100 + lvl * 10} for lvl in range(1, MAX_LEVEL + 1)}
PAID_REWARDS = {lvl: {"gem": 50 + lvl * 5} for lvl in range(1, MAX_LEVEL + 1)}


@dataclass
class Task:
    task_id: str
    task_type: str = "daily"
    difficulty: str = "normal"
    base_exp: int = 100
    free_reward: Optional[dict] = None
    paid_reward: Optional[dict] = None
    completed: bool = False
    reward_claimed: bool = False
    expired: bool = False  # 已完成但跨重置周期，保留至赛季结束


@dataclass
class BattlePass:
    level: int = 1
    exp: int = 0
    paid: bool = False
    claimed_free: set = field(default_factory=set)   # 已领取的免费等级奖励
    claimed_paid: set = field(default_factory=set)   # 已领取的付费等级奖励
    tasks: dict = field(default_factory=dict)        # task_id -> Task
    overflow_currency: int = 0                       # 满级后溢出经验转化的货币
    total_exp_earned: int = 0                        # 赛季累计获得经验


class BattlePassSystem:
    def __init__(self):
        self.passes: dict[str, BattlePass] = {}
        self.current_season_id: Optional[str] = None
        # 永久存档：赛季结算快照与历史归档
        self.season_snapshots: dict[str, dict] = {}
        self.season_history: dict[str, dict] = {}

    # ---- 经验曲线 ----
    def get_exp_required(self, level: int) -> int:
        """从 level 升到 level+1 所需经验，按曲线递增。"""
        if level < 1:
            raise ValueError("level must be >= 1")
        if level >= MAX_LEVEL:
            return 0  # 已满级
        # 1 级需 900，之后每级按指数曲线递增，后期成长感明显
        return int(900 * (1.0045 ** (level - 1)))

    # ---- 任务经验分级 ----
    def get_task_exp(self, base_exp: int, task_type: str = "daily",
                     difficulty: str = "normal") -> int:
        type_mult = TASK_TYPE_MULTIPLIER.get(task_type, 1.0)
        diff_mult = TASK_DIFFICULTY_MULTIPLIER.get(difficulty, 1.0)
        return int(base_exp * type_mult * diff_mult)

    def add_task(self, player: str, task_id: str, task_type: str = "daily",
                 difficulty: str = "normal", base_exp: int = 100,
                 free_reward: Optional[dict] = None,
                 paid_reward: Optional[dict] = None) -> Task:
        bp = self.passes.setdefault(player, BattlePass())
        task = Task(
            task_id=task_id,
            task_type=task_type,
            difficulty=difficulty,
            base_exp=base_exp,
            free_reward=free_reward if free_reward is not None else {"gold": 50},
            paid_reward=paid_reward if paid_reward is not None else {"gem": 20},
        )
        bp.tasks[task_id] = task
        return task

    def complete_task(self, player: str, task_id: str) -> int:
        """完成任务：按类型/难度发放经验，标记完成（奖励仍可稍后领取）。"""
        bp = self.passes.setdefault(player, BattlePass())
        task = bp.tasks.get(task_id)
        if task is None or task.completed:
            return 0
        task.completed = True
        gained = self.get_task_exp(task.base_exp, task.task_type, task.difficulty)
        self._grant_exp(bp, gained)
        return gained

    def add_exp(self, player: str, amount: int, task_type: str = "daily",
                difficulty: str = "normal") -> int:
        """直接加经验（同样按任务类型/难度分级），返回实际发放经验。"""
        bp = self.passes.setdefault(player, BattlePass())
        gained = self.get_task_exp(amount, task_type, difficulty)
        self._grant_exp(bp, gained)
        return gained

    def _grant_exp(self, bp: BattlePass, amount: int) -> None:
        bp.total_exp_earned += amount
        if bp.level >= MAX_LEVEL:
            # 满级：溢出经验 1:1 转化为溢出货币
            bp.overflow_currency += amount
            bp.exp = 0
            return
        bp.exp += amount
        while bp.level < MAX_LEVEL and bp.exp >= self.get_exp_required(bp.level):
            bp.exp -= self.get_exp_required(bp.level)
            bp.level += 1
        if bp.level >= MAX_LEVEL:
            # 升级过程中最后一段的溢出经验同样转化为货币
            leftover = bp.exp
            if leftover > 0:
                bp.overflow_currency += leftover
            bp.exp = 0

    # ---- 奖励分轨 + 付费墙 ----
    def claim_reward(self, player: str, level: int, is_paid: bool) -> dict:
        bp = self.passes.get(player)
        if bp is None or level < 1 or level > bp.level:
            return {}
        if is_paid:
            if not bp.paid:
                return {}  # 付费墙：免费玩家无法领取付费奖励
            if level in bp.claimed_paid:
                return {}
            bp.claimed_paid.add(level)
            return dict(PAID_REWARDS.get(level, {}))
        if level in bp.claimed_free:
            return {}
        bp.claimed_free.add(level)
        return dict(FREE_REWARDS.get(level, {}))

    def purchase_pass(self, player: str) -> None:
        self.passes.setdefault(player, BattlePass()).paid = True

    def claim_task_reward(self, player: str, task_id: str, is_paid: bool) -> dict:
        """领取任务奖励：已完成的任务在赛季结束前都可以领。"""
        bp = self.passes.get(player)
        if bp is None:
            return {}
        task = bp.tasks.get(task_id)
        if task is None or not task.completed or task.reward_claimed:
            return {}
        if is_paid:
            if not bp.paid:
                return {}
            task.reward_claimed = True
            return dict(task.paid_reward or {})
        task.reward_claimed = True
        return dict(task.free_reward or {})

    # ---- 周常重置：保留已完成未领取的奖励 ----
    def reset_weekly(self, player: str) -> None:
        """重置日常/周常任务进度，但已完成未领取的奖励保留到赛季结束。"""
        bp = self.passes.get(player)
        if bp is None:
            return
        kept: dict[str, Task] = {}
        for task in bp.tasks.values():
            if task.completed and not task.reward_claimed:
                # 冻结保留：仍可领取，直到赛季结算
                task.expired = True
                kept[task.task_id] = task
        bp.tasks = kept
        # 注意：等级奖励的领取记录(claimed_free/paid)不受任务重置影响

    # ---- 赛季结算快照 ----
    def end_season(self, season_id: str) -> dict:
        """生成赛季结算快照：等级/经验/奖励/完成任务永久可查，并归档。"""
        snapshot: dict = {}
        for player, bp in self.passes.items():
            completed_tasks = [
                {
                    "task_id": t.task_id,
                    "task_type": t.task_type,
                    "difficulty": t.difficulty,
                    "reward_claimed": t.reward_claimed,
                }
                for t in bp.tasks.values() if t.completed
            ]
            unclaimed_levels = {
                "free": sorted(l for l in FREE_REWARDS
                               if l <= bp.level and l not in bp.claimed_free),
                "paid": sorted(l for l in PAID_REWARDS
                               if l <= bp.level and l not in bp.claimed_paid),
            }
            snapshot[player] = {
                "level": bp.level,
                "exp": bp.exp,
                "paid": bp.paid,
                "claimed_free": sorted(bp.claimed_free),
                "claimed_paid": sorted(bp.claimed_paid),
                "overflow_currency": bp.overflow_currency,
                "total_exp_earned": bp.total_exp_earned,
                "completed_tasks": completed_tasks,
                "unclaimed_levels": unclaimed_levels,
            }
        self.season_snapshots[season_id] = snapshot
        self.season_history[season_id] = snapshot
        # 新赛季从零开始；旧数据已在快照中永久可追溯
        self.passes = {}
        self.current_season_id = None
        return snapshot

    def get_season_record(self, season_id: str, player: str) -> dict:
        """查询某玩家在历史赛季的结算记录。"""
        return self.season_history.get(season_id, {}).get(player, {})
