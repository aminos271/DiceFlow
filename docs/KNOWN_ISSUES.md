# DiceFlow 已知问题（KNOWN_ISSUES）

- 最后更新：2026-07-09
- 范围：游戏机制（gameplay mechanics）层面的问题。UI 微调、配色等不在本表。
- 状态标记：🔴 严重 / 🟠 高 / 🟡 中 / 🟢 低（设计取舍）

> 已修复（不在下表）：世界模型持久化（world_clock/world_model 重载丢失）、好感度阈值对脚本 delta 不生效、时间 LLM 调用未门控。详见 git 历史。

---

## 🔴 严重 — 核心机制不成立

### 1. 没有胜利条件，游戏不可赢
- **现状**：`border_town_tavern`（及所有世界）的 `ending_conditions` 只有 `death`（HP≤0）与 `timeout`（回合耗尽）。开场文案称"15 回合内找到同伴或线索"，但**没有任何机制会触发 `victory` 结局**——`victory` 只出现在 `app/game.py` `_ending_text` 的显示标签里。
- **后果**：每局只能以超时或死亡结束，目标文案是纯摆设。
- **修法方向**：定义"目标完成→置 victory 结局"的机制。可挂在线索/任务完成（见 #2）或特定 flag/实体状态上，在 `_refresh_end_state` 增加非 death/timeout 的结局判定。

### 2. 线索/任务从不推进
- **现状**：`add_thread` 能被动态裁决创建（`adjudicator_heuristics`），但**全代码无任何处推进 `progress` 或置 `completed`**——`update_thread` 只在 `validation.py` 被校验，没有规则/阶段调用它。
- **后果**：任务加了永远 active，永不完成。
- **修法方向**：在 `reaction_rules` / `derivation_rules` / 新增阶段里，按行动结果发 `update_thread`（progress_delta / status=completed），并让完成触发 #1 的胜利。

### 3. NPC 自治是死代码
- **现状**：`NPC_AUTONOMY_ENABLED = False`；`npc_autonomy_phase` 在 `app/game.py` 只 import、从不调用（全仓无调用点）。
- **后果**：NPC 永远只在回合内被动反击（reaction 阶段），从不会主动行动。整个 `diceflow/core/npc_autonomy.py` + `npc_autonomy.txt` prompt 闲置。
- **修法方向**：把 `npc_autonomy_phase` 注册成回合阶段（order 在 favorability 之后），或由 reaction 触发；先在 no-llm 下给个占位回退再开 LLM。

---

## 🟠 高 — 有数据无效果

### 4. 属性完全不生效
- **现状**：`strength/agility/charm/will/endurance/intellect`（默认各 10）在 `core/rules.py / adjudicator*.py / scripting/resolver.py / core/updater.py` 里**零引用**——不改 DC、不改伤害、不改任何判定。也无升级/成长。
- **修法方向**：让属性参与 DC 修正（如 agility→闪避/潜行 DC，charm→交涉 DC）或伤害（strength→近战伤害）。可走 `dc_modifiers` 的属性模式。

### 5. 装备完全不生效
- **现状**：`equipped` 字段只被从 LLM 上下文 strip（`llm/client.py _strip_keys`），不影响 DC/伤害。
- **修法方向**：装备在 `rules.resolve` / `updater` 里读 `player.equipped`，按装备属性修正 DC/伤害/防御。

### 6. disposition 是装饰；好感度基本是二值的
- **现状**：`disposition`（friendly/suspicious/neutral）只被 `lorebook.py` 拿来显示"态度:"，**无任何机制消费**。只有 `hostile` 这个**独立 flag** 有机械权重（reaction 阶段读它决定是否反击）。所以 `+5→friendly` 无效果，只有 `-5→hostile` 有意义；而好感度只靠 `hp_delta` 下降，又只在有脚本 attack 的 NPC 上发生 → 好感度基本不动。
- **修法方向**：让 disposition 进入判定（如 suspicious 提高 talk DC，friendly 降低），或让 reaction/adjudicator 读 disposition 调整反应；并把好感度变化源扩到非伤害路径（已在 world_model/favorability 里部分做了 LLM 判断，但触发面仍窄）。

### 7. 没有回血/恢复机制
- **现状**：`GENERIC_ACTION_SPECS` 里所有 `hp_delta` 都是负的（伤害）。`休息/过夜` 只推进时间，不回血。无治疗物品/动作。
- **后果**：一旦受伤 → 单向死亡螺旋，无恢复；配合"只有超时/死亡结局" → 体验很丧。
- **修法方向**：给 `rest/过夜` 加正向 `player.hp_delta`（按时间段回血），或加治疗物品/动作；可由 world_model.time 的时段触发（如过夜回满）。

---

## 🟡 中 — 场景性

### 8. 战斗只在"脚本定义了 attack+敌对"的 NPC 上成立
- **现状**：攻击一个没有脚本 `attack` 动作的 NPC（如 worlds 版 barkeeper，`allowed_actions:[talk,inspect]`）→ 校验失败 → 走动态裁决 → `adjudicator_heuristics` **不出 hp_delta** → 只产调味文本（"分心/警觉"），不造成伤害。
- **后果**：打不动非战斗 NPC，攻击变味儿。战斗只在脚本显式定义了 attack+hostility 的对象上（如 tomb_entrance 守卫）有效。
- **修法方向**：动态裁决的 `intent_kind=forceful/use` 在命中 NPC 时产出 `hp_delta`（受 `max_runtime_dc` / 上限护栏），或让"攻击非战斗 NPC"先把它置 hostile 再走标准攻击。

### 9. no-llm 意图解析很脆
- **现状**：`llm/heuristics.py` 关键词解析；"和老板攀谈"→unknown、"拿起告示板"→无 take 动作。大量自然输入在无 LLM 时解析成 unknown/invalid → 走动态或无效。
- **修法方向**：扩充 `ACTION_KEYWORDS` / 动词同义词；或在 no-llm 下对 unknown 输入更倾向走动态裁决（而不是 invalid）。

### 10. demo 世界（border_town_tavern）无可拾取物
- **现状**：`notice_board` 是 inspect-only（无 take），所以该世界背包永远空 → 拾取/背包机制在此世界完全没用（叠加前端"背包不列实体物品"过滤，更空）。
- **修法方向**：给 border_town_tavern 加一两个可 take 的物品（钥匙/金币/酒），让拾取链路可被体验。

---

## 🟢 低 / 设计取舍

### 11. 时间无机械牙齿
- **现状**：`world_clock` 纯影响叙事（narrator 看得到），不门控 NPC 可用性/事件。
- **备注**：设计文档里本就标为"后续"，非 bug。

### 12. DC 固定
- **现状**：DC 不随玩家状态/局势缩放，`dc_modifiers` 有但少用。
- **修法方向**：可做动态 DC（按威胁等级/时段/属性），属增强非修复。
