# Local runbook

All cutoffs are ISO-8601 timestamps with an explicit timezone. The group lock is
`2026-08-13T02:00:00Z`; use an earlier cutoff for the final run.

## First setup

```powershell
uv sync --extra dev
uv run ti rules snapshot --as-of 2026-08-12T23:00:00Z
uv run ti rules validate
```

The rules snapshot locates Dota and the pinned ValveResourceFormat CLI via
`DOTA_PATH` and `VRF_CLI` when the default Windows locations do not apply.

For paid OpenDota access, copy `.env.example` to the Git-ignored `.env`, place the key only in
`OPENDOTA_API_KEY`, and run commands with `uv run --env-file .env ...`. Do not put the key on the
command line. The local paid-request ceiling is 50,000 keyed attempts per UTC month ($5 at the
currently verified price) and cannot be raised through environment configuration. Full details are
in [OpenDota API usage and safety](opendota-api-usage.md).

## Refresh and generate

```powershell
uv run --env-file .env ti data sync --as-of 2026-08-12T23:00:00Z --year 2026 --request-limit 500
uv run ti forecast backtest --as-of 2026-08-12T23:00:00Z
uv run ti forecast group --as-of 2026-08-12T23:00:00Z --profile all
uv run ti fantasy recommend --as-of 2026-08-12T23:00:00Z --period group --profile all
uv run ti audit <run_id>
uv run ti web
```

Run the TI 2025 holdout before the 2026 group Forecast. Continue to the group command only when the
backtest has no blocking issue; the default holdout league and all weighting constants come from
the versioned team-strength policy selected by `config/ti2026.yaml`. Policy replacement and
post-holdout changes follow [model policy governance](model-governance.md).

The strength model derives the target-team evidence network from the complete time-bounded
`/proMatches` catalog after patch/tier weighting. It does not discover that network by recursively
calling every opponent's team-history endpoint. Each run records the selected match-ID hash and
observed network size; no exact catalog count is a release gate.

The default sync walks OpenDota `/proMatches` backwards until it covers the requested UTC calendar
year, then joins `/leagues` and `/constants/patch`. `--no-pro-catalog` skips this year catalog when
only a targeted league refresh is needed. `/proMatches` summaries are complete for the requested
time window as exposed by OpenDota; replay-level player details remain a separately bounded set.
Without `OPENDOTA_API_KEY`, the client respects the anonymous minute window and pauses between
pagination batches; a full-year first sync therefore takes several minutes.

Madstone, Smoke, Watcher, Lotus and Tormentor require Java 21+ and a separate native-replay pass after
`fantasy-history`. Build the pinned parser once, then run the resumable backfill with the same
explicit cutoff:

```powershell
Push-Location src/ti_replay_parser
.\mvnw.cmd -q '-DskipTests' package
Pop-Location
uv run ti data replay-fantasy --as-of 2026-08-12T23:00:00Z --year 2026 --workers 4
```

The command defaults to one atomic Parquet checkpoint per completed match and refreshes DuckDB when
the command exits normally. `--max-matches` bounds a batch,
repeatable `--match-id` targets known fixtures, and `--refresh` intentionally creates a new immutable
capture instead of reusing the latest verified URL/hash. Do not run two replay backfills against the
same processed directory concurrently. After a fully accounted run, the status table records every
scoped match as `exact`, `missing`, `download_failed`, `decompress_failed`, `parse_failed`,
`join_failed` or `build_untrusted`; bounded batches additionally report the not-yet-attempted count.
Rerunning retries non-final failures and reuses complete rows only when both parser version and JAR
SHA-256 match. A JAR change during one sync fails closed; restart the command after an intentional
rebuild. OpenDota event-map values are diagnostic-only and never fill a native `null`.

Use `fantasy_replay_status.parquet` and `fantasy_watcher_support.parquet` as release gates before a
recommendation. The implementation order and acceptance contract are in the
[Group 40-Roll v2 implementation plan](plans/group-roll-playbook-v2-implementation.md); measured
coverage and performance are in the
[P1 implementation report](reports/p1-native-replay-stats-implementation-2026-08-06.md).

The Group Stat evidence and its optional team-ranking extension use the same cached snapshot and
explicit cutoff:

```powershell
uv run ti fantasy group-evidence --as-of 2026-08-06T17:27:00Z --bootstrap
uv run ti fantasy group-evidence --as-of 2026-08-06T17:27:00Z --bootstrap --team-rank-bootstrap
```

The first command remains the compatibility default and preserves the frozen v2 schema and
semantic hash. The second adds 16 team rows to each of the 42 role/color/Stat groups and writes
`group-stat-team-top3-publication.md`. The publication table labels the internal `P1` and `P3`
fields as first-place and Top-3 stability rates; they remain deterministic Series-cluster bootstrap
frequencies, not calibrated future probabilities or confidence intervals. Names are display-only
and joins use stable team IDs. Each role/color table also ranks its six Stats from 1 through 6 and
renders the frozen Baseline Stat grade as a player-facing handling suggestion with its relative
strength; that suggestion is not an unconditional Roll action. See the promoted
[v2 Stat team Top 3 publication table](playbooks/group-roll/stat-team-top3-publication-v2.md) and its
[r4 publication report](reports/group-stat-team-top3-publication-r4-2026-08-08.md).

The frozen Group manual validation is a separate cached-snapshot command:

```powershell
uv run ti fantasy group-playbook-evidence --as-of 2026-08-06T17:27:00Z --playbook-version v2
```

It first reproduces the P3 source hash, then evaluates both independently frozen manuals over the
nine non-probability-weighted starting-state strata. It does not invoke the Reference Roll solver.
The current v2 result is `warning`: both editions remain `draft`. Primary has no standalone 10%
Common loss failure but does not pass every rule/risk gate; Rate has 23 such failures. Consult the
[manual index](playbooks/group-roll/README.md) and
[v2 standalone report](reports/group-roll-playbook-v2-p3-standalone-validation-2026-08-07.md)
before operational use. Omit `--playbook-version v2` only when intentionally reproducing v1.
For a player-facing explanation ordered by evidence certainty rather than candidate rule identity,
use the [Group 40 Roll publication manual](playbooks/group-roll/group-roll-publication-manual-v2.md).
It preserves both frozen editions as `draft` and does not define a new validated policy.

The bounded P5 Reference Roll solver has its own historical v1 cached-snapshot evidence command:

```powershell
uv run ti fantasy group-solver-evidence --as-of 2026-08-06T08:15:00Z
```

It requires the immutable P4 artifact, rebuilds and verifies the P3/Rule context, then runs the
frozen one-hour effectiveness protocol. The v1 run completed all 18 fixed-offer short-horizon
diagnostics but only 7/216 full-session units; its status is
`failed-escalation-review-required`. Do not use it as a reliable or globally optimal recommendation,
and do not enable the dormant Full configuration planner from this failure. See the
[P5 report](reports/p5-branch-capped-solver-2026-08-06.md).
There is no new v2 full-session P5 run; v2 uses the historical failure only as explicitly labelled
diagnostic evidence.

The P6 read-only audit is a separate command and never rewrites either manual:

```powershell
uv run ti fantasy group-cross-audit --as-of 2026-08-06T17:27:00Z --cross-audit-version v2
```

It reconstructs standalone/P5 validation indexes, draws an audit Scenario subset explicitly
disjoint from both, and compares the frozen manual, bounded solver and conditional exact oracle.
The path-pinned v2 run completes 108/108 in about 45 minutes. Rate has no material exception in this
conditional matrix; Primary has one directionally wrong Common case. Both labels remain `draft`
because the audit can never promote a failed standalone candidate. See the
[v2 cross-audit report](reports/group-roll-playbook-v2-p4-read-only-cross-audit-2026-08-07.md).

The current local advisor is started with:

```powershell
uv run ti web
```

Open `Group Roll 实时顾问` and choose whether the three role Teams should be selected automatically
or specified manually. Enter all nine Emblems, the three distinct operations currently visible in
Dota, and the remaining Roll count, then press `计算现在应该怎么选`. The page returns one of three
action grades: a clear apply, a conditional apply with its risk, or refresh because none of the
three current operations has acceptable direct value. It also shows the current role-specific Team
lineup and a lineup-weighted Prefix/Suffix Top 3.

On local Windows, the same page can observe and fill those fields automatically:

```powershell
uv sync --extra dev --extra ocr
uv run ti web
```

Click `识别下一次稳定的 Dota 画面` in the advisor, then switch to Dota's complete Group Roll screen.
On a single monitor, Alt+Tab is the intended workflow; on two monitors the button can be clicked while
Dota is already visible. The reader waits for two stable frames, recognises only the finite client
vocabulary, and requires all 31 fields (nine Stat/Quality/Trait triples, three distinct operations,
and the remaining Roll count) to be confirmed before it recalculates. An incomplete observation updates only
high-confidence fields and lists what still needs manual confirmation; it never triggers a new
recommendation. Confirmed and incomplete target observations both finish that one capture request.
While armed, a minimized Dota window, a covered/not-yet-visible Dota surface, or a non-Group page keeps
waiting instead of filling the form; use `取消本次识别` to stop waiting. The latest target screenshot and
observation JSON overwrite the local ignored cache under `data/cache/ocr/live-roll/`; no screenshot
history is retained.

The browser and Dota may be on the same or different monitors. The capture path verifies `dota2.exe`, resolves
the exact Windows monitor handle, and maps that handle to the corresponding DXcam output; it does not
assume that Dota is on the primary display. Keep Dota restored because a minimized window is rejected
explicitly. On a full client frame, the reader first locates the aligned `CORE / MID / SUPPORT`
headings, crops and enlarges the Fantasy region, and only then performs detailed OCR, so the side
navigation, top bar and chat area do not determine Banner fields.

After acting in Dota, edit only what the client actually changed: the realised Banner attributes,
the three new operations, and the remaining count. Calculate again from that complete observed
screen, or click the one-shot capture button again and switch back to Dota. The advisor
does not generate or value the unknown next offer, does not control Dota, and does not support Main
five-slot execution. It reads pixels from the local window only and never sends mouse, keyboard,
memory or Steam operations.

The old P7 evidence command remains available only for reproducing its historical v1 session and
failed P5 diagnostics:

```powershell
uv run ti fantasy group-advisor-evidence --as-of 2026-08-06T08:15:00Z
```

It is compatibility/evidence tooling and is not called by the current page. See the historical
[P7 report](reports/p7-local-interactive-group-roll-advisor-2026-08-06.md).

The OpenDota `data sync` and `data fantasy-history` commands stop before exceeding their per-run
`--request-limit` (default 5,000), and keyed
attempts are reserved in `data/cache/opendota_api_usage.json` before the network call. A repeated
successful path/query in one process stops immediately. Transient network/5xx responses receive at
most four total attempts with 1/2/4-second backoff; `429` honors `Retry-After`.

`--max-matches 5` limits detailed match downloads for a smoke test while still collecting
current-team summary history. Use `--no-team-history` only for isolated tests. Detailed matches
resume by `match_id`; use `--refresh-details` only when intentionally replacing the normalized copy
with a newly captured OpenDota response.

## Main Event

玩家现在模拟 Fantasy 只运行服务：

```powershell
uv run ti web
```

服务启动时自动验证 `current.json` 与 `main-current.json` 并加载其指向的当前发布包。当前 Main
已是 `ready / actual`：数据截止 `2026-08-16T15:31:30Z`，三个位置各使用正式八队与赛后
Fantasy pool。16 队 `projected` 只保留为名单形成前的维护者历史流程。玩家不运行下面的发布
命令，也不需要填写 `as_of`。`--manual` 可关闭 Windows 本地 OCR，只保留手动录入。

Main 页面提供两个正式入口策略：默认 `G` 只比较当前可见动作的一步期望价值；用户可切换到
`G-Lite`，后者仅在前两项差距不超过当前价值的 0.05% 时，对两项各抽 4 个固定下一轮样本，
覆盖 G 至少还需 0.01% 的二步优势，每局最多触发 4 次。重复计算同一画面不重复占用预算；新局
须点击“重置本局预算”。`G-Lite` 仍标记为开发状态正向、未独立确认，失败的 0.10%/5 配置不在
Web 策略目录中。

以下是维护者更新后台证据与当前指针的流程，不是玩家启动步骤。

Main Fantasy 与 Group Fantasy 是两个发布栈，但 Main 的可计算性不依赖实际八队已经形成。
正式名单形成前，用当前 16 队和 Group 联合晋级情景发布可计算的 `projected` 五槽包：

```powershell
uv run ti fantasy main-solver-release --mode projected --as-of 2026-08-13T13:23:17Z
uv run pytest tests/test_fantasy_main_solver_release.py tests/test_fantasy_main_current_advisor.py tests/test_web.py
```

该模式保留 16 个客户端候选 Team，但每个 Main Scenario 只让 Group 情景中的 8 支晋级队进入
双败 bracket；选中的 Team 未在某情景晋级时，该情景的 Main 分数为 0。预测种子顺序是显式
proxy，页面会显示 provisional 警告，但计算按钮保持可用。

Group 与淘汰轮结束、实际八队和种子形成后，必须先更新比赛与 Fantasy 原始证据，再缩减候选集：

```powershell
uv run ti data main-actual-materialize `
  --as-of 2026-08-16T15:31:30Z `
  --catalog-audit data/raw/opendota/audits/20260816T122321Z/manifest.json `
  --workspace data/processed/work/main-actual-20260816T153130Z
uv run ti data replay-fantasy `
  --as-of 2026-08-16T15:31:30Z `
  --year 2026 `
  --workers 4 `
  --processed-dir data/processed/work/main-actual-20260816T153130Z
uv run ti data main-actual-freeze `
  --workspace data/processed/work/main-actual-20260816T153130Z
uv run ti fantasy main-solver-release `
  --mode actual `
  --as-of 2026-08-16T15:31:30Z `
  --hero-source data/raw/rules-title/20260810T134512Z-7d89d1a71895/scripts/npc/npc_heroes.txt
uv run ti fantasy main-publication-evidence `
  --as-of 2026-08-16T15:31:30Z `
  --hero-source data/raw/rules-title/20260810T134512Z-7d89d1a71895/scripts/npc/npc_heroes.txt
```

`main-actual-materialize` 只读取不可变 OpenDota raw 和全年目录审计，不发网络请求；它会生成隔离
workspace，并把 replay 范围缩到实际八队在本届 TI 已打的比赛。`replay-fantasy` 在该 workspace
中复用既有 exact 结果，只补齐剩余比赛。若 replay 的实际抓取时间晚于第一次 materialize 的
`as_of`，必须把最终 `as_of` 推进到最后一次抓取之后，重新 materialize 并从已缓存 raw 复算，
然后才允许 freeze。Group 的 processed 数据和发布指针始终不被覆盖。

`actual` 模式会从指针选中的内容寻址 Main snapshot 重建并内嵌 Fantasy Series pools；它要求存在
晚于 Group 冻结点的本届赛事 Fantasy Game，并要求八支实际参赛队都已有本届赛事 Fantasy 行。
如果池仍与 Group 冻结包相同、名单不是 8 队、截止时间晚于 `main_lock_at` 或模型/证据被阻断，
发布命令会失败。默认 `--mode auto` 在没有 8 个种子时选择 `projected`，有 8 个种子时选择
`actual`。

## Exit meanings

- `publishable`: no blocking audit issue.
- `warning`: usable only after reading the listed caveats.
- `blocked`: must not be copied into the game.

The app never logs into Steam and never writes a game selection.
