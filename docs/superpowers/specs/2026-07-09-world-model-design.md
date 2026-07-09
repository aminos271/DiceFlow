# 通用世界模型底座 — 设计文档

- 日期：2026-07-09
- 状态：已通过设计评审，待写实现计划
- 范围：在 DiceFlow 中引入一组可复用、题材无关的"通用底座"子系统，世界可随用随改。MVP 落地两个厚子系统：NPC 好感/关系、时间。

## 1. 背景与目标

DiceFlow 当前的世界状态散落在 `GameState` 的多个字段里：`favorability` 是实体上的裸 int，`disposition` 是裸字符串，变化全靠 talk 结果表的 `favorability_delta` 硬编码，没有阈值反应、没有关系历史；时间方面只有 `turn_id`（回合计数），没有一天中的时刻、天数、天气。这些"通用能力"的语义是隐式的、靠 id 字符串手工串联的。

本设计的目标是把这些通用能力抽成**有清晰接口的通用底座子系统**：每个子系统自带类型化数据模型 + 规则引擎 + 配置点 + 注册阶段，题材无关，世界通过声明式配置 + 规则表随用随改，不碰 Python。

非目标（本轮不做）：
- 地点系统、状态/标记系统的薄活儿改造（后续）。
- WorldGraph 统一关系图视图（后续可选层）。
- NPC↔NPC 关系、派系、日程、经济。
- 时间对 NPC 可用性的硬性门控（MVP 只把时钟暴露给 LLM）。

## 2. 关键决策（承重点）

| 决策 | 选择 | 否决的替代 |
|---|---|---|
| 与 GameState 关系 | **封装层/视图**：GameState 仍是唯一存储底层，底座是架在其上的读写接口 + 规则 + 阶段 | 全量替换为图内核（改动过大）；并行"世界心智层"（两套状态同步成本与一致性风险） |
| 子系统边界 | **混合厚度**：核心子系统做厚（数据+规则+配置），辅助的只做数据 schema；MVP 两个都做厚 | 一刀切全厚或全薄 |
| 定制机制 | **只配置 + 规则**：世界通过 world 契约声明参数 + bootstrap 规则表改写，无代码钩子 | 三层全开（配置+规则+Python 钩子，过重）；只声明式配置（弹性不足） |
| 回合接入 | **自注册阶段**：子系统注册成回合阶段，run_turn 只驱动阶段列表 | 被动库（每加子系统改 run_turn）；事件触发才跑 |
| 时间推进 | **动作驱动**：默认不推进，等待/休息/过夜/赶路/离开场景等动作触发时间大跳 | 每回合自动推进（玩家无控）；规则混合（复杂） |
| 好感/时间数值 | **LLM 定性 + 代码数值**：LLM 给桶，代码用可配置表换算成数值；`--no-llm` 走启发式回退 | 写死信号→delta 规则表为主路径（违背项目哲学） |

LLM 判断属于引擎内置行为（与现有 adjudicator 的 LLM 同性质），不是世界定制钩子；世界仍只通过配置改参数，不违反"只配置 + 规则"。

## 3. 总体架构

新建 `diceflow/world_model/` 包作为通用底座。三个机制落地：

### 3.1 自注册阶段
把 `Game.run_turn` 在 resolution 之后那段硬编码链 `[reaction → open_ended]` 改成注册表驱动。引入 `PhaseRegistry`：每个阶段是 `(name, order, run(ctx) -> StateChanges)`。任何分支（标准/动态裁决/无效/过渡）解算出初始 `turn_changes` 后，统一调 `registry.run_all(ctx)`。每阶段产出先 fold 进 `ctx.turn_changes` 再跑下一个。**加子系统不改 run_turn。**

每个阶段根据 `resolution_kind` + 信号**自行决定是否作用**（返回 `{}` 即本轮不作用），从而四个分支行为统一，且现有分支语义靠"阶段自判"保持。

默认注册顺序：
```
reaction（迁移） → open_ended（迁移） → time（新） → favorability（新）
```

### 3.2 只配置 + 规则
- **配置**：world 契约新增 `world_model` 段，声明各子系统参数。
- **规则**：bootstrap 新增各子系统规则表（时间触发规则、好感阈值反应规则、magnitude 换算表），格式对齐现有 `reaction_rules / dc_modifiers`。
- 不读 Python 钩子。

### 3.3 混合厚度
MVP 两个厚子系统各自带规则引擎。地点/状态的薄活儿后续。

### 3.4 包结构
```
diceflow/world_model/
  __init__.py
  registry.py        # PhaseRegistry + Phase 协议 + PhaseContext
  base.py            # Subsystem 基类/协议
  favorability.py    # 好感/关系子系统（厚）
  time.py            # 时间子系统（厚）
  schemas.py         # 各子系统配置/规则 schema 与默认表 + 校验
```

## 4. NPC 好感/关系子系统（厚）

### 4.1 数据模型（落在实体上，子系统做读写视图）
```
entity["favorability"]      # int，保留，向后兼容
entity["relationship"] = {
  "history": [ {turn_id, delta, reason, sentiment} ],  # 关系事件流
  "trust": int,                                          # 长期信任（可选，由历史聚合）
}
entity["disposition"]       # 仍存，由阈值规则派生/可被规则覆盖
```
MVP 只管玩家↔NPC；NPC↔NPC 关系留后续。

### 4.2 规则引擎（action 无关，LLM 定性 + 代码数值）
**LLM 路径**：每回合对受影响的 NPC，LLM 判断本次行动对关系的定性影响，输出 JSON：
```
{ "sentiment": "positive|negative|neutral",
  "magnitude": "small|medium|large",
  "reason": "..." }
```
LLM 只给定性桶，不给数值（守项目护栏）。任何 action 都可触发，不限于 talk。

**代码映射**：用可配置 `magnitude → delta` 表换算（默认 small=±1, medium=±2, large=±3），世界可覆盖。delta 追加进 `relationship.history`。

**无 LLM 回退**（`--no-llm`）：简单启发式兜底——NPC 受伤 → -2、outcome 表直接给的 `favorability_delta` 透传。信号→delta 规则表降级为 fallback，不是主路径。

**阈值反应规则**（确定性，机械护栏）：好感越线 → disposition/hostile 翻转 + 写一条 `npc_memory`（正/负面）+ 追加叙事 event。默认表：
```
[{at: -5, set: {hostile: true, disposition: "hostile"}},
 {at:  5, set: {disposition: "friendly"}}]
```
世界可覆盖。

### 4.3 配置点（world 契约 `world_model.favorability`）
`magnitude_table`、`thresholds`、是否启用 trust 聚合、默认 disposition 映射。缺省用 `schemas.py` 默认表。

### 4.4 注册阶段 `favorability_phase`
post-resolution 链末尾（open_ended 之后、time 之后——实际排在 time_phase 之后）。
1. 扫描 `turn_changes` 全量信号（不限来源、不限 action 类型）：`favorability_delta`、NPC 上的 `hp_delta`、`hostile` 翻转、action 的 `approach_tags` 等。
2. LLM 判断定性桶 → 代码换算总 delta → 追加 `relationship.history`。
3. 跑阈值反应，产出派生 changes（disposition/hostile 翻转走现有 `entities` 键；memory 走现有 `add_npc_memory` 键）。
4. `resolution_kind` 为 `invalid` 或无 NPC 卷入时返回 `{}`。

### 4.5 收敛现有
talk 结果表的 `favorability_delta` 格式不变，`_apply_object_changes` 的 delta 处理照旧。新阶段在其之上加 LLM 判断 + 阈值反应 + 历史。零现有内容迁移。

## 5. 时间子系统（厚，动作驱动）

### 5.1 数据模型（新 GameState 槽 `state.world_clock`）
```
world_clock = {
  "day": int,            # 第几天
  "segment": str,        # morning/noon/evening/night/deep_night（世界可配置段名）
  "weather": str,        # 可选，由时段规则或 LLM 派生
}
```
`turn_id` 保留不动（仍是回合计数）。

### 5.2 规则引擎（动作驱动，LLM 定性 + 代码数值，与好感同构）
**脚本触发表**（快路径 + no-LLM 回退）：`wait → +1 segment`、`rest/sleep/过夜 → 跳到次日 morning`、`travel/leave_scene/transition → +1 segment`。世界可配置。

**LLM 路径**：对非显然触发，LLM 判断时间影响桶：
```
{ "impact": "none|small|medium|large", "reason": "..." }
```
代码用 `magnitude → segment 推进` 表换算（世界可覆盖）。LLM 只给桶，不给数值。

**时段推进**：segment 走到末尾自动滚到次日 `day+1`。

### 5.3 配置点（world 契约 `world_model.time`）
`segments`（段名 + 可选 hour 范围）、`magnitude_table`、`triggers`、可选 `weather_table`。缺省用默认表。

### 5.4 注册阶段 `time_phase`
post-resolution 链里，**排在 favorability_phase 之前**，让好感反应能看到更新后的时间上下文。
1. 先查脚本触发表；未命中且 LLM 可用 → LLM 判断时间影响桶。
2. 算出推进量，更新 `world_clock`，产出 event（如"夜深了，炉火将熄"）供 narrator。
3. `resolution_kind` 为 `invalid` 时返回 `{}`；`transition` 分支按"赶路/离开场景"触发。

### 5.5 反馈进叙事/行为（厚的价值）
- `world_clock` 并入 `turn_resolution` / `_compact_state`，narrator 和 adjudicator 都能看到当前时段，叙事自然带时间感。
- 时段硬性影响 NPC 可用性留后续，MVP 只暴露给 LLM。

## 6. 接入点与迁移

### 6.1 PhaseRegistry（`world_model/registry.py`）
```python
class Phase:
    name: str
    order: int
    def run(self, ctx: PhaseContext) -> StateChanges  # 返回 {} 即本轮不作用

class PhaseRegistry:
    def register(self, phase) -> None: ...
    def run_all(self, ctx: PhaseContext) -> StateChanges  # 按 order 跑，每阶段产出先 fold 进 ctx.turn_changes 再跑下一个
```
`PhaseContext` 字段：`action / validation / check / turn_changes（累计）/ state / llm / lorebook / resolution_kind`。

### 6.2 run_turn 改造（`app/game.py`）
四个分支解算出初始 `turn_changes` 后，统一调 `registry.run_all(ctx)`，替换各自手搓的 `reaction → open_ended` 调用。默认注册顺序：`reaction → open_ended → time → favorability`。每阶段按 `resolution_kind` + 信号自判是否作用，复刻现有跳过语义。

### 6.3 GameState 改动（`core/state.py`）
- 新增 `self.world_clock: dict`（初始化 `{day:1, segment:"morning", weather:""}`）
- 实体新增 `relationship` 子 dict（懒初始化）
- `get_snapshot` 加 `world_clock`
- `apply_changes` 新认三键：`advance_time` / `set_clock` / `relationship_events`

### 6.4 LLM 客户端（`llm/client.py`）
加 `judge_favorability_effect(action, turn_changes, state)` 和 `judge_time_impact(action, state)`，走 narration_client（与现有生成器同路），各配 prompt：`content/prompts/favorability_judge.txt`、`time_judge.txt`，输出 JSON 桶。`--no-llm` 时两阶段走启发式回退。

### 6.5 世界契约（`core/bootstrap.py`）
`WorldBootstrap` 加 `world_model: dict` 字段，`to_script_dict` 透传。形如：
```yaml
world_model:
  favorability:
    magnitude_table: {small: 1, medium: 2, large: 3}
    thresholds: [{at: -5, set: {hostile: true, disposition: hostile}}, {at: 5, set: {disposition: friendly}}]
  time:
    segments: [morning, noon, evening, night, deep_night]
    magnitude_table: {small: 1, medium: 2, large: 4}
    triggers: [{action: wait, advance: {segments: 1}}, {action: [rest, sleep], advance: {next_day: true}}]
```
缺省时用 `schemas.py` 默认表，现有世界零改动即可跑。

### 6.6 Web 暴露（`web/server.py`）
`StatusData` 加 `world_clock` 和每 NPC 的 `relationship` 摘要；`_build_status` 填充。前端最小展示（时段/天数）后续可选。

### 6.7 迁移顺序（增量、每步可验证）
1. 建 `world_model/` 包：registry + base + schemas，无行为。
2. run_turn 后处理链改注册表；reaction/open_ended 迁成注册阶段，靠 resolution_kind 复刻现有跳过逻辑。跑全部现有测试确保绿。
3. GameState 加 world_clock/relationship/变更键。
4. 实现 time_phase、favorability_phase（LLM + 回退）。
5. LLM 方法 + prompts。
6. Web 暴露。
7. 给 border_town_tavern 加一份 `world_model` 配置作 demo。

## 7. 测试

现有测试必须保持绿：`test_game_loop`、`test_reaction_phase`、`test_open_ended_content`、`test_threads`、`test_npc_memory`、`test_dynamic_adjudicator`、`test_web_api` 等。

新增测试：
- PhaseRegistry 注册顺序与 fold 语义。
- time_phase：脚本触发、LLM 桶→推进、segment 滚日、invalid 跳过、transition 触发。
- favorability_phase：LLM 桶→delta、阈值反应（disposition/hostile 翻转 + memory）、history 追加、no-llm 回退、invalid 跳过。
- 世界配置覆盖默认表。
- world_clock 序列化与 Web 暴露。

## 8. 风险与回退

- **run_turn 后处理链重构**：风险点在第 6.7 步 2。缓解：迁移 reaction/open_ended 时严格按 resolution_kind 复刻现有跳过，先跑全部现有测试再继续。
- **LLM 桶→数值的可控性**：LLM 可能给极端桶。缓解：magnitude 表是有限枚举，delta 上限受表约束；阈值反应是确定性护栏。
- **--no-llm 可玩性**：两阶段都有启发式回退，离线可跑。
