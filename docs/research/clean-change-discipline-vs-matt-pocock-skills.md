# `clean-change-discipline` 与 Matt Pocock Skills 的兼容性评估

- 日期：2026-08-02
- 核对基准：Matt Pocock `skills` 仓库提交 [`2ab958093e83e0ec752e6c1c5932da465bf23e0c`](https://github.com/mattpocock/skills/tree/2ab958093e83e0ec752e6c1c5932da465bf23e0c)

> 处理结果：原全局技能已由 `verified-replacement-cleanup` 取代。新技能保留隐式调用，
> 但只在替代实现通过约定验证并进入 review/cleanup 后触发；本报告保留为设计证据。

## 执行结论

`clean-change-discipline` 的目标是合理的：被否定或被替代的生产实现不应以死分支、临时 shim、废弃接口或注释代码继续堆积。它与 Matt 强调的 YAGNI、去除 speculative generality、保持单一事实来源大体同向。

但当前版本不适合作为一个宽泛、自动触发、跨仓库生效的模型技能。它把“最终清理阶段应做的事”表达成了“改变方向、调试、重写、回应 review 时随时都应做的事”，又以较绝对的删除措辞覆盖了原型、调试夹具、TDD 中间态、迁移兼容层和真实多实现适配器。这会与 Matt 的阶段化工作流发生实际冲突。

综合判断：

- 意图与原则：合适，约 **8/10**。
- 当前触发和 AI harness 设计：需要收窄，约 **5/10**。
- 与 Matt Skills 的关系：**没有根本理念冲突，但存在明显的阶段、优先级和证据门槛冲突**。
- 推荐处理：保留其核心思想，但重构为“验证完成后的替换清理”技能，或并入 `code-review` 的收尾清单；不建议维持当前的全局宽触发版本。

## 作用域与配置证据

本机的 `clean-change-discipline` 位于：

`C:\Users\liaow\.codex\skills\clean-change-discipline\SKILL.md`

它不在 `E:\Code\TI预测` 项目根目录。项目根目录中的 `AGENTS.md` 和 `docs/agents/*` 是项目级规则；前者则是用户级技能，因此会跨仓库参与技能匹配。

当前技能同时包含 `SKILL.md` 和 `agents/openai.yaml`，但前者没有 `disable-model-invocation: true`，后者也没有 `policy.allow_implicit_invocation: false`；`openai.yaml` 目前只提供显示名、短描述和默认提示。因此两个 harness 配置都没有把它限制为仅用户调用。结合 description 中的 “changes direction”“responds to review feedback”“rewrites a feature”等宽泛触发语，它实际上可能覆盖大量普通工程任务。

Matt 的调用模型明确区分 user-invoked 编排技能和 model-invoked 可复用纪律；模型技能需要有独立、可辨认的触发价值，否则会增加上下文负担和误触发概率。参见 [invocation 规范](https://github.com/mattpocock/skills/blob/2ab958093e83e0ec752e6c1c5932da465bf23e0c/.agents/invocation.md) 与 [`writing-great-skills`](https://github.com/mattpocock/skills/blob/2ab958093e83e0ec752e6c1c5932da465bf23e0c/skills/productivity/writing-great-skills/SKILL.md)。

## 与 Matt Skills 的逐项比较

| Matt 内容 | 一致之处 | 当前冲突或张力 | 应采用的优先级 |
|---|---|---|---|
| [`writing-great-skills`](https://github.com/mattpocock/skills/blob/2ab958093e83e0ec752e6c1c5932da465bf23e0c/skills/productivity/writing-great-skills/SKILL.md) | 都希望减少沉积、重复和无效路径，并维持单一事实来源。 | Matt 把“可预测调用”和独特触发词视为技能设计核心，并警告大量否定式指令会让被禁止行为更显著。当前技能触发面过宽，正文又主要由“不要保留/删除”构成。 | Matt 的调用与写作规范应优先；把技能改为积极目标、窄触发、明确阶段。 |
| [`tdd`](https://github.com/mattpocock/skills/blob/2ab958093e83e0ec752e6c1c5932da465bf23e0c/skills/engineering/tdd/SKILL.md) | 最终都要求生产路径可验证、测试通过。 | Matt 明确将 refactoring 放到 review 阶段，而不是 red→green 循环中。当前技能可能在实现尚未变绿时删除中间接口、fixture 或对照路径，破坏短反馈循环。 | TDD 在 red→green 阶段拥有流程控制权；只有替代实现验证通过后才进入清理。 |
| [`prototype`](https://github.com/mattpocock/skills/blob/2ab958093e83e0ec752e6c1c5932da465bf23e0c/skills/engineering/prototype/SKILL.md) | 原型不应无标记地进入主生产路径。 | Matt 允许把原型保留在 throwaway branch 作为探索证据，同时让 main 只留下验证后的决定。当前技能笼统要求删除 abandoned/generated artifacts，可能过早抹去仍有价值的实验证据。 | 原型阶段由 `prototype` 管理；结论捕获后把原型移出 main，而不是无条件销毁。 |
| [`diagnosing-bugs`](https://github.com/mattpocock/skills/blob/2ab958093e83e0ec752e6c1c5932da465bf23e0c/skills/engineering/diagnosing-bugs/SKILL.md) | 修复完成后都要求移除调试日志、临时 instrumentation 和无用 harness。 | Matt 允许在诊断期间创建 throwaway harness、instrumentation 或 prototype，并在修复验证后删除或移入明确 debug 位置。当前技能可能在诊断闭环完成前将其判为“临时垃圾”。 | 诊断技能先完成可复现→修复→验证；清理仅作为最后阶段。 |
| [`code-review`](https://github.com/mattpocock/skills/blob/2ab958093e83e0ec752e6c1c5932da465bf23e0c/skills/engineering/code-review/SKILL.md) | 对 Speculative Generality、Middle Man、重复实现的警惕高度一致。 | Matt 将 code smells 视为需要结合 spec 和仓库标准判断的线索，而不是硬性违规；仓库规范可以覆盖通用基线。当前技能把删除写成接近无条件义务，缺少 spec、ADR 和运行证据门槛。 | repo `AGENTS.md`、spec、ADR 先决定“是否无用”；清理技能执行已确认的结论。 |
| [`codebase-design`](https://github.com/mattpocock/skills/blob/2ab958093e83e0ec752e6c1c5932da465bf23e0c/skills/engineering/codebase-design/SKILL.md) | 都反对为假想未来设计 adapter/seam；“一个 adapter 可能只是想象中的 seam”与清理目标同向。 | Matt 同时承认当确有多个实现时 seam 是真实的。当前技能“偏好一个实现、避免并行路径”的表述可能误删合理的 provider、平台、策略或版本适配器。 | 先用领域和运行证据判断 variation 是否真实；真实多实现不是兼容垃圾。 |
| [`resolving-merge-conflicts`](https://github.com/mattpocock/skills/blob/2ab958093e83e0ec752e6c1c5932da465bf23e0c/skills/engineering/resolving-merge-conflicts/SKILL.md) | 都希望合并后没有含混、不可达或半完成路径。 | Matt 要求先理解双方意图，并尽可能保留二者；只有意图不可兼容时才依据 merge goal 选择。清理技能若先入为主地追求“单一路径”，容易把一侧误判为旧实现。 | 冲突解决技能优先；双方意图和 merge goal 确认后才能清理真正被淘汰的一侧。 |

Matt 的 [`setup-matt-pocock-skills`](https://github.com/mattpocock/skills/blob/2ab958093e83e0ec752e6c1c5932da465bf23e0c/skills/engineering/setup-matt-pocock-skills/SKILL.md) 主要负责把 issue tracker、domain docs 和 agent 规则接入仓库，不等于它定义或安装了本机的 `clean-change-discipline`。两者需要分别管理。

## 独立的 AI harness 评估

### 1. 最大风险不是“删除”，而是错误分类

模型很难只凭名称区分以下类别：

- 真正不可达的死代码；
- 当前调试或 TDD 循环仍需要的临时资产；
- 有期限的迁移兼容层；
- 受公共 API、序列化格式、存量数据或滚动部署约束的兼容路径；
- 为可复现研究保留的基线、fixture、golden file 和历史模型；
- 具有两个真实实现的 adapter 或 strategy。

只要 trigger 强而证据门槛弱，模型就会把“看起来多余”误等同于“已证明无用”。这在长期维护和数据项目中比偶尔留下小段死代码更危险。

### 2. 全局技能会把局部偏好升级为跨仓库政策

用户级自动技能会作用于采用不同兼容策略、发布方式和审计要求的仓库。对于应用、库、数据管道和研究项目，“正确清理”的边界并不相同。因此通用技能应只定义最小不变量，把最终判断交给 repo 级 `AGENTS.md`、spec 和 ADR。

### 3. 宽触发会制造技能竞争

“重写功能”“改变方向”“回应 review”几乎涵盖实现、调试、TDD、架构改善和冲突解决。多个 model-invoked 技能同时自认拥有流程，会降低 harness 的可预测性。阶段明确的技能通常比价值观式的常驻警察更可靠。

### 4. 负面清单容易诱导机械搜索与过度修复

当前收尾命令搜索 `TODO`、`temporary`、`compat`、`shim` 等通用词。命中不代表违规：TODO 可能是合法待办，compat 可能是已批准契约，fixture 名称也可能刻意保留。机械“清零搜索结果”会扩大任务范围并修改用户未授权的既有代码。

### 5. “显式用户要求或外部公共契约”不足以覆盖兼容需求

合理兼容来源还包括：repo spec/ADR、已存储数据、数据库迁移、序列化格式、滚动部署、插件生态、供应商接口、离线产物和可复现实验。是否保留不应只由“用户有没有明确说”决定。

## 推荐重构方案

### 推荐定位

把技能改名为 `cleanup-after-replacement` 或 `verified-replacement-cleanup`，核心目标改为：

> 在替代实现已经通过约定验证后，留下一个清晰、受支持的生产路径；保留仍受 spec、repo 规则、ADR、运行证据或审计要求约束的资产，并明确记录原因。

这比“不要留下任何旧代码”更正向，也把触发锚定在一个可观察事件：**替代方案已经验证完成**。

### 推荐触发策略

二选一：

1. **最稳妥：仅用户调用。** 增加 `disable-model-invocation: true`，并在 `agents/openai.yaml` 禁止隐式调用。适合用户只在大型重写或 review 收尾时显式启动。
2. **保留自动调用：严格收窄 description。** 仅在“已验证的替代实现准备收尾，并有具体旧路径待移除”时触发；删除 “changes direction”“responds to review feedback”“rewrites a feature”等泛化词。

如果目的是配合 Matt 流程，最佳落点是 `code-review` 后的修复/收尾阶段，而不是所有实现阶段的常驻规则。

### 推荐证据门槛

删除前必须依次确认：

1. 新路径已通过目标测试或其他预先约定的验证。
2. 旧资产被分类为 dead、temporary、migration、compatibility、evidence 或 active variation，而不是仅凭命名判断。
3. 代码引用、运行时配置、命令入口、spec、ADR、文档、fixture 和数据格式中没有仍需它的证据。
4. 删除范围只包含当前任务产生或明确覆盖的内容，不顺手清理用户无关改动。
5. 运行聚焦测试，再按风险运行完整检查；失败时修复新路径，除非失败证明旧路径仍属于契约。

### 明确保留项与优先级

以下内容不得被自动视为垃圾：

- 尚未结束的 prototype、debug、red→green 循环资产；
- active migration、feature rollout 和 rolling-deployment 兼容层；
- 公共 API、存量数据、序列化格式、插件或 provider 契约；
- 可复现研究所需的基线、fixture、golden file、历史模型和审计记录；
- 具有多个真实实现的 adapter/strategy；
- ADR 和历史文档；
- 合并冲突中尚未确认意图的一侧。

优先级应写明为：

`用户当前指令 > repo AGENTS/spec/ADR > 专项流程技能（prototype / diagnosing-bugs / tdd / resolving-merge-conflicts）> cleanup-after-replacement`

### 改进收尾检查

不要全局搜索通用的 `TODO|temporary|compat|shim` 并追求零命中。应搜索此次替代涉及的旧标识符、旧入口、特定 feature flag、临时 debug tag 和被拒方案名称。报告中区分：

- 已删除的旧路径及验证证据；
- 有意保留的兼容/迁移/审计路径及依据；
- 尚未能证明可删的项目，不擅自扩展范围。

## 最终建议

保留这项纪律，但不要保留它当前的 harness 形态。它最适合作为一个**窄触发、后验证、服从仓库事实和专项流程的收尾技能**。这样可以保住你真正想解决的问题——模型在转向后留下双轨实现和临时垃圾——同时避免与 Matt 的 TDD、原型、诊断、review 和冲突解决流程互相抢夺控制权。

官方仓库总览与调用分类可见 [Matt Pocock Skills README](https://github.com/mattpocock/skills/blob/2ab958093e83e0ec752e6c1c5932da465bf23e0c/README.md)。
