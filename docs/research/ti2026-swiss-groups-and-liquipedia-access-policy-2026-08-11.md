# TI 2026 Swiss 初始组与 Liquipedia 自动访问政策核验

- 调查截止（`as_of`）：`2026-08-11T00:30:00Z`
- 范围：Valve 官方规则/联赛快照；Liquipedia 官方 API Terms、`robots.txt` 与允许范围内的帮助入口
- 边界：未访问任何 Liquipedia 赛事或百科内容页；帮助入口返回 `403` 后即停止；未尝试 CAPTCHA、代理、IP/UA 轮换或其他规避
- 状态：研究补充；未修改 `AGENTS.md`、`src/`、`config/` 或发布报告

## 结论

1. **Valve 规则明确规定存在两个 initial groups，也明确规定 R2/R3 同 initial group、R4 跨 initial group。** 这几项不是社区推测。
2. **Valve 没有在所核对的 league API 中提供每支队伍的独立初始组字段。** 具体 A/B 成员是根据官方首轮节点名 `Match 1.A`…`Match 4.A` 与 `Match 1.B`…`Match 4.B`，再结合“首轮为组内对阵”的官方规则推断出来的。因此 `initial_group_provenance="derived"` 是准确表述。
3. **R5 不是所有比赛一律拉大排名距离。** 官方只对“负者将被淘汰”的 R5 比赛规定最大化排名距离；其他 R5 配对仍应落回一般 Swiss 规则。
4. Liquipedia 官方 API Terms 要求自动化只访问 API，不抓生成的 HTML 内容页；还要求长缓存、来源署名、限速、可联系的自定义 User-Agent、gzip 与连接复用。
5. 当前 `robots.txt` 的通配组明确 `Disallow: /dota2/api.php`，并对若干具名机器人（包括 `GPTBot`、`ChatGPT-User`）全站禁止。API Terms 与 robots 对旧 MediaWiki API 形成表面张力。**本项目应采用更严格口径：未取得 Liquipedia 明确书面许可/澄清前，不自动调用 `/dota2/api.php`；需要结构化数据时优先申请 LiquipediaDB API。**
6. 遇到 `403`、`429`、CAPTCHA 或封锁时必须停止。不得通过伪装 User-Agent、切换 IP/代理、改 URL 访问 HTML、并发重试或自动解 CAPTCHA 来规避限制。

## 1. Valve Swiss 规则：官方直接事实与派生事实

### 1.1 核对材料

仓库已保存 Valve 官方 English localization 快照：

- 官方 URL：[Valve TI 2026 rules localization chunk](https://www.dota2.com/public/javascript/dota_react/6777.js?contenthash=652ea487b0024989f20b&l=english&_cdn=fastly)
- 本地响应：[response.js](../../data/raw/valve/ti2026-rules/20260810T134512Z-e55e2d979f0d/response.js)
- 元数据：[metadata.json](../../data/raw/valve/ti2026-rules/20260810T134512Z-e55e2d979f0d/metadata.json)
- 抓取：`2026-08-10T13:45:12Z`
- SHA-256：`e55e2d979f0de1f2b16890b4ea6ed4d1e8ba0c47752a2bfdb1dc86e8829bbf6c`

首轮节点来自 Valve 官方联赛 API：

- 官方 URL：[GetLeagueData, league_id=19719](https://www.dota2.com/webapi/IDOTA2League/GetLeagueData/v001?league_id=19719)
- 本地响应：[response.json](../../data/raw/valve/ti2026-league/20260810T134512Z-73519bcb40a4/response.json)
- 元数据：[metadata.json](../../data/raw/valve/ti2026-league/20260810T134512Z-73519bcb40a4/metadata.json)
- 抓取：`2026-08-10T13:45:12Z`
- SHA-256：`73519bcb40a40a02de7a3b343ce3daf4a5786d449d058d3300569b1bbea84c2a`

本轮没有重新下载 Valve 内容；结论针对上述可复现快照。

### 1.2 规则正文明确写出的事实

| 规则项 | Valve token | 官方直接事实 | 证据等级 |
| --- | --- | --- | --- |
| 一般配对 | `ti15_swiss_rules2_1`–`2_3` | 同战绩配对；尽量避免重赛；可行时尽量缩小排名距离 | 直接 |
| R1 | `ti15_swiss_rules3_1_1`–`3_1_2` | 队伍拆成两个组；赛事方设置首轮，队伍与本组成员交手 | 直接 |
| R2 | `ti15_swiss_rules3_2_1` | 只能与自己 initial group 的成员匹配 | 直接 |
| R3 | `ti15_swiss_rules3_3_1` | 只能与自己 initial group 的成员匹配 | 直接 |
| R4 | `ti15_swiss_rules3_4_1` | 只能与另一个组的成员匹配 | 直接 |
| R5 | `ti15_swiss_rules3_5_1` | 对负者将被淘汰的比赛，最大化双方排名距离 | 直接，但只覆盖该类 R5 比赛 |

由此可确认：

- “initial group” 不是项目自行创造的概念；Valve 在 R2/R3 原文中直接使用它。
- R4 的“other group”与 R1 的两个组、R2/R3 的 initial group 构成同一规则链。
- R5 的特殊规则只覆盖 elimination-on-loss 配对。不能把它扩展成“R5 所有配对都最大化距离”。未被该特例覆盖的 R5 比赛应继续采用同战绩、避免重赛、尽量缩小排名距离的一般规则。
- 一般规则包含“尽量/可行时”，因此即使已知组别和战绩，也未必得到唯一配对。

### 1.3 具体 A/B 成员为何仍是推断

Valve league API 的 Swiss 节点组有 8 个首轮节点：前四个名为 `Match 1.A` 至 `Match 4.A`，后四个名为 `Match 1.B` 至 `Match 4.B`。但该对象的字段只有 `node_group_id`、`nodes`、`team_standings`、晋级关系等，没有逐队 `initial_group`/`group_id` 字段；所有 8 个节点本身都属于同一个 Swiss `node_group_id=2`。

因此证据链是：

1. 官方规则直接确认 R1 拆为两组且首轮为组内赛；
2. 官方 API 用 `.A` 和 `.B` 区分两批首轮节点；
3. 项目据此把 `.A` 节点内的八队派生为 A 组、`.B` 节点内的八队派生为 B 组。

第 1、2 步是官方直接事实，第 3 步是强依据推断。当前 [Swiss 配置](../../config/tournaments/ti2026-swiss-v1.json) 使用 `initial_group_provenance: "derived"`，没有冒充 Valve 独立发布的分组字段，口径正确。

如果未来 Valve API 新增显式初始组字段或发布名单，应保存新快照并以更高优先级替换该派生关系；不能无审计地回写旧快照。

## 2. Liquipedia 官方自动访问约束

### 2.1 API Terms 的直接要求

官方来源：[Liquipedia API Terms of Use](https://liquipedia.net/api-terms-of-use)。以下要求同时适用于其 MediaWiki API 与 LiquipediaDB API，除非另行注明：

- 尽可能长时间复用/缓存 API 结果，不重复请求相同数据。
- Liquipedia 内容按 CC BY-SA 3.0 提供；再利用时必须把 Liquipedia 标为数据来源。
- 自动访问生成的非 API HTML 页面不被允许。自动化数据采集不能把赛事页、百科页或 HTML fallback 当成 API 替代品。
- Liquipedia 可随时修改、中断或终止 API；调用方必须把不可用当成正常外部状态，不能以规避方式强行续取。

LiquipediaDB API：

- 需先申请并获批；获批后按 Dashboard 文档使用。
- 每小时不超过 60 个请求。
- API key 不得与第三方共享。

MediaWiki API：

- 全部 HTTP 请求不超过每 2 秒 1 次。
- `action=parse` 资源开销较大，不超过每 30 秒 1 次。
- User-Agent 必须是自定义值，标明项目/用途并包含可用联系信息；通用库默认 UA 很可能被阻止。
- HTTP 客户端必须支持 gzip `Content-Encoding`。
- 多请求时复用客户端/连接，不为每次请求新建连接。
- 只有确有需要时才做登录态 API 调用，以保留公共请求的缓存效率。

官方条款还警告：违规可能触发自动临时 IP 封锁，反复触发可能升级为永久封锁。条款提到 CAPTCHA 可解除临时封锁，但这不授权本项目自动求解、代填或围绕封锁建立重试规避流程。

### 2.2 `robots.txt` 的当前约束

官方来源：[Liquipedia robots.txt](https://liquipedia.net/robots.txt)，抓取快照显示：

- `GPTBot`、`ChatGPT-User`、`ClaudeBot` 等若干具名 User-Agent 的规则为全站 `Disallow: /`。
- 通配 `User-agent: *` 规则明确禁止 `/dota2/api.php`，同时禁止多类 Special、Template、动态列表等路径。
- Sitemap 的存在不是抓取内容页的授权；API Terms 仍明确禁止自动访问生成的 HTML 页面。

执行时必须按客户端实际发送的诚实 User-Agent 选择对应 robots 组：

- 若实际 UA 命中全站禁止的具名组，不能改名伪装成另一个 UA 来绕过。
- 若使用真实、可联系的项目 UA 且未命中具名组，则适用通配规则；当前仍不能自动访问 `/dota2/api.php`。

### 2.3 API Terms 与 robots 的保守合并

API Terms 描述了 MediaWiki API 在获准调用时的限速与客户端要求，但当前 robots 又对通配机器人禁止 Dota 2 的 `api.php`。两份材料没有在本次允许访问的文档中给出明确的优先/例外说明。

因此本项目的可执行默认值应为：

1. **禁用自动 `/dota2/api.php` 调用。** 不因 API Terms 列出限速就推定 robots 例外。
2. 需要 Liquipedia 结构化数据时，优先申请 LiquipediaDB API；在批准范围内执行 60 请求/小时、密钥保密、长缓存和署名要求。
3. 如确实需要 MediaWiki API，先通过 API Terms 指定的官方联系渠道取得书面澄清；澄清应作为来源快照进入仓库，再启用调用。
4. 即使获得澄清，也同时遵守更严格的调用条件：每 2 秒至多 1 请求、`action=parse` 每 30 秒至多 1 请求、诚实且可联系的 UA、gzip、连接复用、内容寻址缓存、必要时才认证。

## 3. 建议固化为代码/运维门禁的约束

本笔记不修改实现；后续若接入 Liquipedia，最低门禁应为：

| 门禁 | 可执行要求 |
| --- | --- |
| 允许路径 | 默认只允许批准的 LiquipediaDB API；`/dota2/api.php` 为 deny，HTML 内容页为 deny |
| User-Agent | 配置中必须提供真实项目名、用途和维护者联系 URL/邮箱；拒绝库默认 UA，也不得冒充浏览器/其他机器人 |
| 速率 | LiquipediaDB ≤60/小时；获书面许可后的 MediaWiki API ≤1/2 秒；`action=parse` ≤1/30 秒；单进程与多进程共享限流器 |
| 缓存 | 相同 URL+参数优先读不可变快照；记录抓取 UTC、响应 SHA-256、ETag/Last-Modified；不得因进程重启重复拉取相同数据 |
| 传输 | 开启 gzip；复用会话/连接；设置低并发、指数退避和有限重试，但对权限/封锁错误不重试 |
| 认证 | 只在必要时使用；API key 进入本地密钥存储，不写仓库、日志、产物或第三方消息 |
| 署名 | 派生数据和发布材料保留 Liquipedia 来源链接与 CC BY-SA 3.0 署名 |
| 封锁处理 | `401/403/429`、CAPTCHA、robots 禁止或挑战页立即 fail closed；不切 IP/代理、不变更 UA 伪装、不改抓 HTML、不自动解 CAPTCHA；交由人工联系 Liquipedia |
| 可用性 | API 中断时保留旧快照并标注陈旧度；不得把缺失当 0，也不得扩大到未授权来源 |

“指数退避和有限重试”只适用于明确的瞬时网络/`5xx`；对 `401/403/429`、CAPTCHA 或 robots 禁止必须零重试并停止。这能避免普通重试器演变为封锁规避。

## 4. 本次访问审计

| URL | 抓取 UTC | 结果 | SHA-256 / 说明 |
| --- | --- | --- | --- |
| [Valve rules chunk](https://www.dota2.com/public/javascript/dota_react/6777.js?contenthash=652ea487b0024989f20b&l=english&_cdn=fastly) | 2026-08-10T13:45:12Z | 使用仓库既有快照 | `e55e2d979f0de1f2b16890b4ea6ed4d1e8ba0c47752a2bfdb1dc86e8829bbf6c` |
| [Valve GetLeagueData](https://www.dota2.com/webapi/IDOTA2League/GetLeagueData/v001?league_id=19719) | 2026-08-10T13:45:12Z | 使用仓库既有快照 | `73519bcb40a40a02de7a3b343ce3daf4a5786d449d058d3300569b1bbea84c2a` |
| [Liquipedia API Terms](https://liquipedia.net/api-terms-of-use) | 2026-08-11T00:22:14Z | `200`；3,544 UTF-8 bytes；`Last-Modified: 2026-02-20T12:39:56Z` | `DCA318BC241B7E0ABB81A852066E7395F65DB76C0E73F5C312C7A7C23DCA83AC` |
| [Liquipedia robots.txt](https://liquipedia.net/robots.txt) | 2026-08-11T00:22:34Z | `200`；156,971 UTF-8 bytes；`Last-Modified: 2026-08-05T21:40:03Z` | `4BD44B1A0858DBFA8ACF3928DD4AA104C77BFF005B7161A0636C0A0243F2A0DD` |
| `https://liquipedia.net/commons/Liquipedia:API_Usage_Guidelines` | 2026-08-11 | `403` | 无内容结论；收到封锁后未尝试规避 |
| `https://liquipedia.net/commons/Liquipedia:API` | 2026-08-11 | `403` | 无内容结论；收到封锁后未尝试规避 |
| `https://liquipedia.net/commons/Help:API` | 2026-08-11 | `403` | 无内容结论；收到封锁后未尝试规避 |

本次对 Liquipedia 使用的研究 UA 为 `TI-Predictor-Research/1.0 (manual policy audit; no data scraping)`，只读取政策/robots，没有调用 API 或内容页。该 UA **不包含维护者联系信息**，因此它不满足未来 API 调用的完整 UA 要求；若实现 API 客户端，必须先配置真实联系人，不能沿用此研究 UA。
