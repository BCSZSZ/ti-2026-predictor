# OpenDota API 价格与限额核查

- 调查日期：2026-08-02
- 研究范围：OpenDota 免费 API 与 Premium API 的当前价格、调用限额、计费排除项，以及本仓库计划中的约 160–190 个普通 GET 是否需要付费。
- 主来源版本：[`odota/core@2d67379`](https://github.com/odota/core/tree/2d67379fbba90b2fd015c6f0f4080d394a5741e9)、[`odota/web@64d658b`](https://github.com/odota/web/tree/64d658bc8673ebb34f4a2b2d8ca812f2ff951509)。

## 结论

OpenDota 存在独立的 Premium API，采用按量付费，而不是固定月费：

| 项目 | 免费层 | Premium API |
|---|---:|---:|
| API key | 不需要 | 需要，并须关联支付方式 |
| 调用价格 | 免费 | 每 100 次 `$0.01` |
| 日调用上限 | 3,000 次 | 不限 |
| 分钟限速 | 60 次 | 300 次 |
| 支持 | 社区支持 | 核心开发者优先支持 |

这些数值来自 OpenDota 的官方 API 页面实现：页面把 Premium 定义为 `$0.01 / 100 calls`，免费与付费层的日限额分别显示为 3,000 和 Unlimited，并从服务端元数据取得两档分钟限速；见 [`Api.tsx`](https://github.com/odota/web/blob/64d658bc8673ebb34f4a2b2d8ca812f2ff951509/src/components/Api/Api.tsx#L238-L249)及[价格与限额表](https://github.com/odota/web/blob/64d658bc8673ebb34f4a2b2d8ca812f2ff951509/src/components/Api/Api.tsx#L391-L461)。服务端默认配置与之相符：免费日额度 3,000、计费单位 100、带 key 300 次/分钟、无 key 60 次/分钟；见 [`config.ts`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/config.ts#L59-L63)。

本仓库的约 160–190 个普通 GET **不需要为了总调用量而购买 Premium API**：它们远低于一次完整免费日额度 3,000。前一轮请求响应头曾显示匿名当日剩余 112 次；这只是该请求时点的运行状态，不是长期额度或本文件重新采集的当前值。若执行时仍只剩 112 次，推荐等待额度重置后以无 key 方式运行；按 60 次/分钟节流即可。

若必须在当前额度周期内完成，可以先用剩余 112 次匿名额度，再把余下约 48–78 次改用付费 key。由于 Premium 按每 100 次一个计费单位、向上取整，这部分预计为 `$0.01`。如果 160–190 次全部使用付费 key，则预计为两个计费单位，即 `$0.02`。

## 计费口径

Premium 页面要求登录、API key 和已关联的支付方式，并说明费用在月初自动扣取；官方英文文案见 [`en-US.json`](https://github.com/odota/web/blob/64d658bc8673ebb34f4a2b2d8ca812f2ff951509/src/lang/en-US.json#L28-L49)。请求通过查询参数 `api_key` 使用该 key。

需要特别区分两个口径：

1. 无 key 请求属于免费层，受每天 3,000 次和每分钟 60 次限制。
2. 带有效 key 的合格响应从第一笔开始进入 `api_key_usage`；当前计费实现没有先减去 3,000 次免费额度，而是把使用量按 `ceil(usage / 100)` 转成计费单位。请求记录逻辑见 [`svc/web.ts`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/svc/web.ts#L73-L115)，月度计费汇总见 [`svc/apiadmin.ts`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/svc/apiadmin.ts#L39-L75)。

因此，“使用 key 后只对超过免费日额度的部分收费”不是当前实现的准确描述。想保留免费额度，应在免费阶段不携带 key；只有需要提高分钟限速或越过匿名日上限的请求才切换到付费 key。

### 不计费的失败响应

官方 API 页面明确列出：HTTP `404`、`429` 和 `500` 响应不计费。服务端完成请求后的用量记录也明确排除了这三个状态码；见 [`svc/web.ts`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/svc/web.ts#L73-L115)和[官方英文页面文案](https://github.com/odota/web/blob/64d658bc8673ebb34f4a2b2d8ca812f2ff951509/src/lang/en-US.json#L47-L49)。

这不是“所有失败响应都不计费”的承诺；例如官方页面没有把其他 `4xx` 状态列入免费失败响应。采集器仍应避免无效参数，并对 `429` 按响应头退避。

## 限速实现

服务端根据请求是否带有效 key 选择每分钟 300 或 60 的限速。只有无 key 请求会检查免费日额度并返回 `X-Rate-Limit-Remaining-Day`；带 key 请求不受该日额度阻断，但仍受每分钟 300 次限制。具体判断、计数、响应头和 `429` 分支见 [`svc/web.ts`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/svc/web.ts#L421-L508)。官网展示的三个数值来自相同配置映射，见 [`queries.ts`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/svc/util/queries.ts#L386-L388)。

源码配置可由生产部署环境覆盖。因此正式采集前仍应以实际响应中的 `X-Rate-Limit-Remaining-Minute`、无 key 请求的 `X-Rate-Limit-Remaining-Day` 以及 `Retry-After` 为运行时事实；本文件的价格和名义上限适用于上述调查日期与固定源码版本。

## `$5/月` Subscription 与 Premium API 的区别

OpenDota 的 `$5/月` Subscription 是面向玩家资料的订阅，官方列出的核心权益是自动解析该用户的比赛、订阅者资料图标以及支持项目维护；见[订阅页面文案](https://github.com/odota/web/blob/64d658bc8673ebb34f4a2b2d8ca812f2ff951509/src/lang/en-US.json#L692-L701)和[`Subscription.tsx`](https://github.com/odota/web/blob/64d658bc8673ebb34f4a2b2d8ca812f2ff951509/src/components/Subscription/Subscription.tsx#L170-L190)。

Premium API 则是另一套按调用量计费的产品，用于获得 API key、无限日调用量和更高分钟限速。官方订阅权益没有包含 Premium API key 或 API 调用额度，因此不能用 `$5/月` Subscription 替代 Premium API，也不能据此认为 API 调用已经付费。

## 对本仓库运行的建议

- 默认继续使用无 key 请求，显式限制在 60 次/分钟以内，并保留少量日额度安全余量。
- 若运行前响应头仍显示只剩 112 次，等待免费日额度重置最简单；160–190 次完整任务在新额度内有充足空间。112 是前一轮的时点观测，必须在正式运行前重新读取响应头。
- 只有必须立即完成、或未来单日工作量超过 3,000 次时，才配置付费 key；不要把 key 写入仓库、日志或原始响应元数据。
- 若临时混用两档，先完成匿名请求，再只对剩余请求携带 key；按付费请求数每 100 次向上取整估算费用。
