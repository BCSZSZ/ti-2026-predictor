# MediaWiki Action API 与 Liquipedia 当前允许操作核验

- 调查截止（`as_of`）：`2026-08-11T00:51:20Z`
- 调查范围：MediaWiki 官方 Action API 文档、Liquipedia 官方 API Terms/`robots.txt` 既有政策快照、IETF Robots Exclusion Protocol、仓库既有 Liquipedia 请求元数据
- 访问边界：未访问 Liquipedia 赛事或百科内容页；未调用 Liquipedia API；本轮政策页/`robots.txt` 首次访问返回 `403` 后未重试；未尝试 CAPTCHA、代理、IP/UA 轮换或其他规避
- 用语：本文的“合法/允许”指本项目的保守工程合规判断，不构成法律意见
- 状态：研究补充；初始调查未修改 `src/`、`config/` 或发布报告；用户确认解封后，仓库级访问规则已另行更新

> 后续状态（2026-08-11，用户确认）：用户已通过正常 CAPTCHA 流程完成人工解封；本项目未为验证解封而追加网络请求。下文“当前暂停”记录的是调查时点的运行状态，不再表示解封后的状态。恢复访问后仍须完整遵守本文限速与客户端条件，新的 `403`、`429`、CAPTCHA 或封锁提示会再次触发立即停机。

## 结论先行

1. 用户给出的 [MediaWiki Action API](https://www.mediawiki.org/wiki/API:Action_API) 页面说明的是 **MediaWiki 软件能提供哪些 `action` 模块**，不是 Liquipedia 对第三方的授权清单。MediaWiki 官方还明确要求调用者同时遵守目标 wiki 自己的政策。
2. 不存在一张适用于所有 wiki 的固定“合法指令表”。Action API 是模块化的，扩展可以增添模块，站点也可以禁用内建模块；某站实际启用的模块只能由该站的 `action=help`、`action=paraminfo` 或 ApiSandbox 自描述确认。
3. `action=query&prop=revisions`、`action=query&list=search`、`action=parse` 都是 MediaWiki 技术上有效的读模块，但这只回答“语法/软件是否支持”，不能回答“Liquipedia 是否允许本项目现在调用”。
4. [Liquipedia API Terms](https://liquipedia.net/api-terms-of-use) 先明确表示为自行项目提供其 MediaWiki API 的免费访问，随后才列出每 2 秒至多 1 request 等条件。**因此访问许可来自前一句免费访问条款；“每 2 秒 1 次”本身只是该许可的速率条件。** LiquipediaDB 则是另一套需申请获批的 API。
5. 现有 `robots.txt` 的通配组虽有 `Disallow: /dota2/api.php`，但 [RFC 9309 §1](https://www.rfc-editor.org/rfc/rfc9309.html#section-1) 明确说明 robots 规则不是访问授权机制。它是 crawler 协调协议：真正递归抓取/索引的 crawler 应遵守；不能用它否定 Liquipedia Terms 对定向 API client 的专项许可，也不能用它创造许可。
6. 调查时点的访问环境出现了真实 `403/CAPTCHA` 阻断，当时必须暂停且不得重试或规避；用户随后确认已通过正常流程人工解封。解封后，定向只读 MediaWiki API client 可依 Terms 恢复运行，无需仅因 robots 另取书面许可；若再次收到封锁信号则重新停机。
7. 仓库 2026-08-08 的三次历史请求都使用技术有效且 Terms 涵盖的 `action=query`，均返回 `200`，请求间隔也满足速率条件。`200` 仍不替代 Terms、客户端条件或实时访问控制；完全相同的数据已有缓存，也不应无理由重复抓取。

## 1. 必须拆开的三层含义

| 层级 | 回答的问题 | 权威来源 | 本次结论 |
| --- | --- | --- | --- |
| A. MediaWiki 软件能力 | 某个 `action`/子模块的语法是否存在、作用是什么？ | MediaWiki 官方 Action API/模块文档 | `query`、`revisions`、`search`、`parse` 等均为技术有效模块 |
| B. Liquipedia 站点条款 | Liquipedia 提供哪些 API 类型，调用时须满足哪些条件？ | Liquipedia API Terms | 条款认可 LiquipediaDB API 与 MediaWiki API 两条路径，但不是逐模块许可清单 |
| C. 本项目当前可调用范围 | 结合专项 Terms、crawler 属性与实时封锁后，现在能否实际自动请求？ | Liquipedia API Terms、`robots.txt`、RFC 9309、当前响应 | 条款允许定向 MediaWiki API client，但当前因真实 `403/CAPTCHA` 暂停；LiquipediaDB 仍需单独获批 |

MediaWiki 官方总览明确指出，Action API 由 `api.php` 暴露认证、页面操作、搜索等功能，同时提醒调用者遵守目标 wiki 的适用政策；这些政策对浏览器和 API 访问同样生效。另一个官方总览进一步说明，Action API 可以被扩展、模块因站点而异，内建模块也可能被禁用。因此不能把 MediaWiki.org 当前生成的模块列表直接当成 Liquipedia 的安装清单或授权清单。来源：[Action API](https://www.mediawiki.org/wiki/API:Action_API)、[MediaWiki API 总览](https://www.mediawiki.org/wiki/API/en)。

## 2. A 层：MediaWiki 技术上有哪些指令

### 2.1 指令不是 wiki 文本命令，而是 `api.php` 模块

Action API 请求以 `action=<模块名>` 选择操作。MediaWiki.org 当前自生成的主模块帮助包含大量模块，可按用途概括为：

| 类别 | 官方示例模块 | 技术含义 | 对 Liquipedia 是否获准 |
| --- | --- | --- | --- |
| 自描述/发现 | `help`、`paraminfo` | 查看当前站点实际模块及参数 | Terms 涵盖；当前因实时阻断暂停 |
| 只读查询/转换 | `query`、`parse`、`expandtemplates`、`compare`、`opensearch` | 读取数据、解析 wikitext、展开模板、比较版本、搜索 | 技术存在不等于站点许可 |
| 认证/会话 | `login`、`clientlogin`、`logout`、`createaccount` | 建立/结束会话或创建账号 | 另需站点账户、权限与用途授权 |
| 内容写入 | `edit`、`move`、`upload`、`rollback`、`watch` | 修改页面或用户状态 | 本项目当前读数据范围内禁用 |
| 管理/高权限 | `delete`、`undelete`、`protect`、`block`、`unblock`、`revisiondelete`、`userrights` | 管理页面、版本或用户 | 需要相应 wiki 权限；本项目禁用 |
| 扩展特有 | MediaWiki.org 主列表中的 AbuseFilter、Translate、DiscussionTools 等模块 | 由安装的扩展增加 | 不能外推到 Liquipedia |

上述类别是对 [Action API 主模块帮助](https://www.mediawiki.org/wiki/API:Action_API) 的归纳，不是穷举，也不是任何站点的授权表。

### 2.2 如何发现目标站真正启用的模块

- [`action=help`](https://www.mediawiki.org/wiki/API:Help) 返回指定模块的帮助，并可递归列出子模块。
- [`action=paraminfo`](https://www.mediawiki.org/wiki/API:Parameter_information) 返回模块、参数、限制及子模块信息，是程序化发现能力的接口。
- [`Special:ApiSandbox`](https://www.mediawiki.org/wiki/Help:ApiSandbox/en) 是调用 `api.php` 的交互表单，不是隔离环境；官方特别提醒，Sandbox 中的写请求会真实修改 wiki。

Liquipedia Terms 已提供 MediaWiki API 的项目使用许可。正常访问恢复后，合理流程是先低频抓取一次 `help`/`paraminfo` 并保存快照，再据此建立站点特定 allowlist。**当前仍不能调用这些模块或 ApiSandbox**，原因是已经出现真实 `403/CAPTCHA`；Sandbox 也不会绕过实时访问控制。

### 2.3 与仓库历史调用直接相关的模块

| 请求形式 | MediaWiki 技术状态 | 官方定义 | Liquipedia 当前状态 |
| --- | --- | --- | --- |
| `action=query` | 有效；需读权限 | 从 MediaWiki 及其存储数据取信息；下分 `prop`、`list`、`meta` 等子模块 | Terms 涵盖；当前因实时阻断暂停 |
| `action=query&prop=revisions` | 有效；需读权限 | 按标题、page ID 或 revision ID 取版本元数据/内容；取内容时有更严格数量上限 | Terms 涵盖；普通上限 ≤1/2 秒 |
| `action=query&list=search` | 有效；需读权限 | 按标题或正文做全文搜索；具体高级语法依目标站搜索后端 | Terms 涵盖；普通上限 ≤1/2 秒 |
| `action=parse` | 有效；需读权限 | 解析页面、指定 revision 或传入 wikitext，返回 parser output | Terms 单列较严格限速，但当前仍不得调用 |

官方依据：[`action=query`](https://www.mediawiki.org/wiki/API:Query)、[`prop=revisions`](https://www.mediawiki.org/wiki/API:Revisions)、[`list=search`](https://www.mediawiki.org/wiki/API:Search)、[`action=parse`](https://www.mediawiki.org/wiki/API:Parsing_wikitext)。

需要特别注意：

- `prop=revisions` 返回版本源内容；`action=parse` 返回解析器输出，两者不是同义指令。
- MediaWiki 的 `parse` 文档建议，获取页面当前版本的一般信息可优先使用 `query` 的各个 prop 模块。
- MediaWiki 礼仪文档说明按固定 revision 解析时 `revid` 路径成本较高，建议用 `oldid`；Liquipedia Terms 又把 `action=parse` 限为每 30 秒至多一次。因此即使未来获准，也不应拿 `parse` 代替常规 `revisions` 数据读取。来源：[MediaWiki API 礼仪](https://www.mediawiki.org/wiki/API:Etiquette)、[Parsing wikitext](https://www.mediawiki.org/wiki/API:Parsing_wikitext)。

## 3. B 层：Liquipedia API Terms 实际允许与要求什么

Liquipedia 官方条款入口：[API Terms of Use](https://liquipedia.net/api-terms-of-use)。本节使用仓库此前于 `2026-08-11T00:22:14Z` 核验的官方响应：3,544 UTF-8 bytes，`Last-Modified: 2026-02-20T12:39:56Z`，SHA-256 `DCA318BC241B7E0ABB81A852066E7395F65DB76C0E73F5C312C7A7C23DCA83AC`；访问审计见既有[研究笔记](./ti2026-swiss-groups-and-liquipedia-access-policy-2026-08-11.md)。

条款可执行要求如下：

| 范围 | 条款要求 | 能否据此推导具体 Action 模块已获准 |
| --- | --- | --- |
| 所有 Liquipedia API | 尽可能长时间缓存/复用，不重复相同请求；按 CC BY-SA 3.0 署名；自动访问生成的非 API HTML 页面不被允许；服务可更改或中断 | 不能 |
| LiquipediaDB API | 先申请并获批；遵循 Dashboard 文档；不共享 API key；每小时不超过 60 请求 | 只能调用批准范围内的 DB 端点 |
| MediaWiki API | 每 2 秒至多 1 请求；`action=parse` 每 30 秒至多 1 请求；使用标明项目/用途和可用联系方式的自定义 UA；支持 gzip；复用 HTTP 客户端/连接；仅必要时认证 | 条款描述调用条件，但没有列出 `query/revisions/search` allowlist |

### 3.1 “每 2 秒 1 次”本身是速率条件；访问许可来自 Terms 前文

Terms 的许可原文核心是其先表示愿意为用户自己的项目提供 MediaWiki API 免费访问；随后才列条件。精确解释如下：

1. **它位于 Liquipedia Terms 的 MediaWiki API 条件中。** 对本项目而言，对应路径是 `https://liquipedia.net/dota2/api.php`；仓库历史的 `action=query` 请求也正是发往该 endpoint。MediaWiki 官方把 Action API 定义为站点的 `api.php` endpoint，并明确要求调用者另行遵守目标 wiki 的政策。来源：[Liquipedia API Terms](https://liquipedia.net/api-terms-of-use)、[MediaWiki Action API](https://www.mediawiki.org/wiki/API:Action_API)。
2. **它约束的是 request 频率，不是许可来源。** 定向 API client 的条款许可来自前述免费访问声明。即使客户端做到相邻请求至少间隔 2 秒，也只满足多个必要条件中的一个；仍须满足真实且可联系的自定义 UA、gzip、连接复用、长缓存/不重复请求、署名、必要时才认证，以及目标站实际启用模块与账号权限等条件。
3. **它不适用于所有 Liquipedia URL。** 自动访问生成的 HTML 内容页被 Terms 直接禁止，不能靠降到 1 次/2 秒变成允许；LiquipediaDB 是另一套需先申请获批并使用 key 的 API，适用每小时 60 请求上限，而不是 MediaWiki 的 2 秒规则；读取本地冻结快照不产生 request，因而不涉及网络限速。
4. **它覆盖 MediaWiki API 的普通 HTTP 请求，而不是某个 `action` 白名单。** 在 Terms 许可下，`action=help`、`action=paraminfo`、`action=query&prop=revisions`、`action=query&list=search` 等都至少受“每 2 秒至多 1 次”约束；模块是否实际启用仍由目标站决定。
5. **`action=parse` 同时受额外的 30 秒规则。** 两个限制并不冲突：`parse` 也是 MediaWiki API request，所以同时落入一般 2 秒上限；其专门上限更严格，实际应按每 30 秒至多 1 次。不能在两个 `parse` 之间穿插普通 `query` 来规避总体 MediaWiki API 限流。
6. **这是 ceiling，不是 service entitlement。** 以 2 秒或更慢频率发送请求，并不保证服务器必须返回 `200`，也不保证不会因模块关闭、权限、负载、风控或条款变化而拒绝。Liquipedia 条款保留修改、中断或终止 API 的能力；MediaWiki 官方也说明模块可因站点而异并可被禁用。来源：[MediaWiki API 总览](https://www.mediawiki.org/wiki/API/en)。

可用一个必要条件表达式概括：

`可调用 = Terms 涵盖该 client/用途 ∧ 模块已启用 ∧ 调用者具备权限 ∧ 客户端条件全部满足 ∧ 当前未被拒绝 ∧（若属于 crawler，则遵守 robots）`

`rate <= 1 request / 2 seconds` 只属于“客户端条件”中的一项，单独为真不能推出“可调用”。

### 3.2 endpoint 与操作的适用矩阵

| endpoint / 操作 | 2 秒规则是否适用 | 其他门槛 | 当前项目状态 |
| --- | --- | --- | --- |
| `/dota2/api.php?action=help` / `paraminfo` | 是 | Terms 许可；模块可用；全部客户端条件 | 当前因 `403/CAPTCHA` 暂停；恢复后可列入最小白名单 |
| `/dota2/api.php?action=query`，含 `prop=revisions`、`list=search` | 是 | Terms 许可；读权限；全部客户端条件 | 当前暂停；恢复后可按需调用并优先缓存 |
| `/dota2/api.php?action=parse` | 是，并额外受每 30 秒至多 1 次 | Terms 许可；读权限；仅确有解析需求 | 当前暂停；恢复后仍单独严格限流 |
| `/dota2/api.php` 写入/管理 action | 是，但速率合规不授予写权限 | 账号权限、站点授权、CSRF token；本项目另行显式授权 | 本项目禁用 |
| LiquipediaDB API | 否，使用独立的每小时 60 请求上限 | 预先申请获批、key、Dashboard 规则 | 未发现批准记录，当前不调用 |
| 赛事/百科 HTML 内容页 | 不适用 | Terms 禁止自动访问生成的非 API HTML | 禁用；慢速也不改变结论 |
| 本地不可变快照 | 不适用 | 保留来源、抓取 UTC、SHA-256 与署名 | 阻断期间的当前白名单 |

`action=parse` 被条款点名限速，说明它在 MediaWiki API 免费访问条款覆盖内，但适用更严格条件；这仍不能覆盖实时拒绝。`query/revisions/search` 不需要因 robots 单独申请书面许可，但必须满足 Terms、模块权限、缓存和实时访问控制。

MediaWiki 自己的通用礼仪还建议：请求串行化、一次批量请求多个标题、开启 gzip、使用含联系方式的真实 UA、缓存结果、读请求优先 GET、非交互任务使用 `maxlag`。这些是获准调用后的最低行为要求，不是对 Liquipedia 的独立授权。来源：[MediaWiki API 礼仪](https://www.mediawiki.org/wiki/API:Etiquette)。

## 4. C 层：本项目现在真正可自动调用的范围

### 4.1 robots 是 crawler 协议，不是访问授权

仓库既有 Liquipedia 官方 [`robots.txt`](https://liquipedia.net/robots.txt) 核验快照：

- 抓取：`2026-08-11T00:22:34Z`
- 156,971 UTF-8 bytes
- `Last-Modified: 2026-08-05T21:40:03Z`
- SHA-256：`4BD44B1A0858DBFA8ACF3928DD4AA104C77BFF005B7161A0636C0A0243F2A0DD`
- 通配 `User-agent: *` 明确 `Disallow: /dota2/api.php`
- `GPTBot`、`ChatGPT-User`、`ClaudeBot` 等若干具名 UA 为全站 `Disallow: /`

[RFC 9309 §1](https://www.rfc-editor.org/rfc/rfc9309.html#section-1) 把 crawler 描述为自动客户端，例如递归遍历链接进行索引的搜索引擎；它同时明确说明 robots 规则不是访问授权。结论必须分流：

- 若实现递归发现/遍历页面、构建通用索引，属于 crawler，应按其真实 product token 匹配并遵守上述 `Disallow`。
- 本项目历史请求是按预定标题/查询参数访问 MediaWiki API 的定向 API client。其访问许可由 Liquipedia 专项 API Terms 提供，不能仅用通配 robots 行撤销，也不需要仅因此另取书面许可。
- 不得把 client 冒充浏览器或改成别的产品名来逃避 crawler 规则；UA 仍须真实、可联系。

### 4.2 调查时点的阻断与后续人工解封

本轮约 `2026-08-11T00:35Z` 各对 API Terms 和 `robots.txt` 做了一次读取，均返回 `403`；此前还出现了 CAPTCHA/封锁信号。收到后没有重试或更换身份。该结果只证明当前访问环境受到真实访问控制，**本次没有探测 `/dota2/api.php`，不能把政策页 `403` 冒充 API endpoint 的实测状态**。

实时拒绝优先于静态速率合规：即使某请求距上一请求超过 2 秒，只要收到 `401/403/429`、CAPTCHA、challenge page 或其他封锁信号，本项目就必须停止。不得把“我没有超速”当成重试、换 UA、换 IP/代理或改抓 HTML 的理由。本次任务没有调用 `/dota2/api.php`，因此不会把政策页的 `403` 错写成 API endpoint 的实测状态。

因此需同时记录政策、调查时点与后续状态：

- **政策状态：** Liquipedia Terms 允许为自己的项目使用 MediaWiki API，受全部条件约束；不要求仅因 robots 另取书面许可。
- **调查时点：** 当时已见真实 `403/CAPTCHA`，所以暂停所有新 Liquipedia 网络请求；阻断期间只读本地不可变快照。
- **后续状态：** 用户于 2026-08-11 确认已完成人工解封；本项目没有为验证状态而追加探测请求。定向只读 API client 此后可按 Terms 恢复，新的封锁信号会重新触发停机。
- **正常访问时：** 可启用 `help`、`paraminfo`、`query+revisions`、`query+search`；`parse` 仅按需且 ≤1/30 秒。完全相同数据优先缓存，不重新拉取。
- **独立路径：** LiquipediaDB 仍须先申请获批并使用 key；自动抓取生成的 HTML 始终被 Terms 禁止。

“阻断期间不请求”是临时运行门禁，不应误写成 Terms 未授权或 robots 永久禁止 API client。

## 5. 仓库既有 Liquipedia 调用审计

全仓库只发现以下 3 个已保存的 `/dota2/api.php` 请求元数据：

| 抓取 UTC | 请求 | 规模 | HTTP | SHA-256 | 技术判定 | 当前能否重复 |
| --- | --- | --- | --- | --- | --- | --- |
| `2026-08-08T06:02:03.925433Z` | `GET action=query&prop=revisions` | 11 titles | `200` | `29ef52e69514b118fb863238c20ccdbd10a25dd598ae72bd812d71241f0b4716` | MediaWiki 有效；Terms 涵盖 | 当前暂停；已有内容不得无理由重拉 |
| `2026-08-08T06:05:36.899163Z` | `GET action=query&list=search` | `srlimit=50` | `200` | `f01c31bbab11d0b89690bc391ed61ccbb742a1fad144a35a8c139c4a56b80169` | MediaWiki 有效；Terms 涵盖 | 当前暂停；恢复后新查询按需调用 |
| `2026-08-08T06:05:52.250767Z` | `GET action=query&prop=revisions` | 2 titles | `200` | `5396b6738b7b2938156dbaeefdc32252e038a2b70884e3e275cefe4e0c983d3d` | MediaWiki 有效；Terms 涵盖 | 当前暂停；已有内容不得无理由重拉 |

对应元数据：

- [event-tier-prize metadata](../../data/raw/publication/liquipedia-dota2-api-event-tier-prize/20260808T060203Z-29ef52e69514/metadata.json)
- [qualifier-search metadata](../../data/raw/publication/liquipedia-blast-slam-vii-qualifier-search/20260808T060536Z-f01c31bbab11/metadata.json)
- [qualifier-pages metadata](../../data/raw/publication/liquipedia-blast-slam-vii-qualifier-pages/20260808T060552Z-5396b6738b7b/metadata.json)

三次请求均为 GET，UA 均为 `ti-2026-predictor/0.1 (https://github.com/BCSZSZ/ti-2026-predictor; reproducible research)`；相邻间隔约 `212.974` 秒和 `15.352` 秒，均慢于 Terms 的每 2 秒最多一次。首、末请求还按 MediaWiki 礼仪把多个标题合并到单个请求。没有发现 `action=parse` 历史调用。

审计边界：

- `200` 证明相关模块当时被服务器识别并执行；站点许可依据是 Liquipedia API Terms，而不是该状态码。
- robots 不是访问授权，缺少 contemporaneous robots 响应不能单独推翻专项 Terms。是否完全合规仍需核对每项客户端条件。
- 现有响应已缓存；Terms 要求尽可能复用，因此完全相同请求没有重复抓取依据。
- 元数据记录了自定义 UA，但没有记录实际发出的 `Accept-Encoding`，所以不能仅凭这些文件确认 gzip 要求是否满足。

## 6. 执行矩阵

| 档位 | 操作 | 理由/门槛 |
| --- | --- | --- |
| **白名单（阻断期间）** | 只读本地已保存的 Liquipedia 响应及元数据；不联网 | 当前 `403/CAPTCHA` 后按要求停止 |
| **白名单（访问正常后）** | 定向 API client 的 `help`、`paraminfo`、`query+revisions`、`query+search`；按需 `parse` | Terms 已提供许可；普通请求 ≤1/2 秒、parse ≤1/30 秒，并满足 UA/gzip/缓存/署名等全部条件 |
| **白名单（LiquipediaDB 获批后）** | 仅调用批准范围内的 LiquipediaDB API | 先保存批准、Dashboard 规则和 key 管理证据；≤60 请求/小时、长缓存、署名 |
| **crawler 禁用** | 递归遍历/索引 `/dota2/api.php` | crawler 应遵守 robots；不要把定向 API client 扩张为通用爬虫 |
| **禁用** | 自动抓取赛事/百科 HTML；`edit`、`move`、`upload`、`delete`、`protect`、`rollback`、`block`、账号创建等写入/管理动作；通过 Sandbox、URL 别名或 HTML fallback 绕过 | 与本项目只读研究范围不符，且 HTML 自动访问被 Terms 禁止 |
| **禁用** | 对 `401/403/429`、CAPTCHA 或 challenge 进行重试、换 UA、换 IP/代理、并发探测或自动解题 | 属于封锁规避；必须停止并等待正常恢复或走官方人工渠道 |

访问正常后仍应建立“显式 allowlist，其他默认拒绝”，而不是把 `action=*` 全开放。建议初始 allowlist 仅含 `help`、`paraminfo`、`query+revisions`、`query+search`；`parse` 单独按需求审批并应用独立 30 秒限流器。写入、认证、管理及扩展私有模块继续 deny。

## 7. 官方来源与本次访问审计

| 来源 | 核验用途 | 本次状态 |
| --- | --- | --- |
| [MediaWiki Action API](https://www.mediawiki.org/wiki/API:Action_API) | `api.php`、主模块、目标站政策要求 | 2026-08-11 官方页面 |
| [MediaWiki API 总览](https://www.mediawiki.org/wiki/API/en) | 模块因扩展/站点而异，也可被禁用 | 2026-08-11 官方页面 |
| [API:Etiquette](https://www.mediawiki.org/wiki/API:Etiquette) | 串行、批量、gzip、UA、缓存、GET、`maxlag` | 2026-08-11 官方页面 |
| [API:Query](https://www.mediawiki.org/wiki/API:Query) | `action=query` 与 `prop/list/meta` | 2026-08-11 官方页面 |
| [API:Revisions](https://www.mediawiki.org/wiki/API:Revisions) | `prop=revisions` 技术定义 | 2026-08-11 官方页面 |
| [API:Search](https://www.mediawiki.org/wiki/API:Search) | `list=search` 技术定义 | 2026-08-11 官方页面 |
| [API:Parsing wikitext](https://www.mediawiki.org/wiki/API:Parsing_wikitext) | `action=parse` 技术定义 | 2026-08-11 官方页面 |
| [API:Help](https://www.mediawiki.org/wiki/API:Help) | 站点自描述模块帮助 | 2026-08-11 官方页面 |
| [API:Parameter information](https://www.mediawiki.org/wiki/API:Parameter_information) | 程序化查询实际模块/参数 | 2026-08-11 官方页面 |
| [Help:ApiSandbox](https://www.mediawiki.org/wiki/Help:ApiSandbox/en) | Sandbox 会真实调用 API，写操作会修改站点 | 2026-08-11 官方页面 |
| [Liquipedia API Terms](https://liquipedia.net/api-terms-of-use) | API 类型、限速、UA、缓存、HTML 禁止 | 复用 `2026-08-11T00:22:14Z` 官方快照；本轮单次访问 `403` 后停止 |
| [Liquipedia robots.txt](https://liquipedia.net/robots.txt) | crawler product-token/path 协调规则 | 复用 `2026-08-11T00:22:34Z` 官方快照；本轮单次访问 `403` 后停止 |
| [RFC 9309 §1](https://www.rfc-editor.org/rfc/rfc9309.html#section-1) | robots 面向 crawler，且不是访问授权机制 | 2026-08-11 IETF Standards Track 原文 |
