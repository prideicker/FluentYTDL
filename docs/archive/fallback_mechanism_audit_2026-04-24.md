# FluentYTDL 回退机制审计报告（2026-04-24）

## 1. 报告目标

本报告整合两轮分析结果，针对以下问题给出证据化结论：

1. 日志中出现的失败是否为偶发，还是系统性回退失效。
2. 回退机制有哪些不严谨点，会给用户造成什么困扰。
3. 哪些问题可在当前仓库源码中直接定位，哪些属于运行版本与源码漂移导致的差异。
4. 修复优先级与可执行改进建议。

---

## 2. 结论摘要

### 2.1 总体判断

本次故障不是单点异常，而是“业务风控拦截 + 回退链路低效 + 错误派发缺陷”叠加：

1. 业务侧：YouTube 403 与 not a bot 持续触发，Cookie 与 POT 都已可用时仍反复失败。
2. 回退侧：多次刷新 Cookie、重复下载、最终降级后仍失败，呈现明显循环。
3. 稳定性侧：错误信号参数不匹配导致未捕获异常，放大用户感知故障。

### 2.2 关键量化（app_2026-04-24.log）

1. TypeError: task_updated() only accepts 0 argument(s), 1 given!：13 次（首行 432）
2. Cookie 刷新重试仍失败：13 次（首行 315）
3. 最终降级（剥离 Cookie + 链式回退）：13 次（首行 360）
4. fallback 失效触发全局修复弹窗：13 次（首行 430）
5. 使用刷新后的 Cookie 重试下载 (player_client=default)：13 次（首行 297）
6. [DLE] 静默重提取 WebView2 Cookie：6 次（首行 283）
7. Resuming download at byte：13 次（首行 472）
8. HTTP Error 403: Forbidden：39 次（首行 282）
9. Sign in to confirm：19 次（首行 50）
10. Skipping unsupported client "android_creator"：3 次（首行 48）

这些计数直接说明：回退链路在同一失败模式下多轮重复，缺少有效“止损条件”。

---

## 3. 证据时间线（日志）

### 3.1 启动与依赖状态

1. POT 服务启动并预热完成：[app_2026-04-24.log](../app_2026-04-24.log#L7), [app_2026-04-24.log](../app_2026-04-24.log#L9)
2. 早期无 Cookie，进入无登录态路径：[app_2026-04-24.log](../app_2026-04-24.log#L20)
3. 首次检测 POT 插件未就位，但随后完成同步：[app_2026-04-24.log](../app_2026-04-24.log#L24), [app_2026-04-24.log](../app_2026-04-24.log#L35)

### 3.2 首轮失败与回退

1. 解析回退到 android_creator,ios，出现不支持客户端警告：[app_2026-04-24.log](../app_2026-04-24.log#L36), [app_2026-04-24.log](../app_2026-04-24.log#L48)
2. 直接触发 not a bot：[app_2026-04-24.log](../app_2026-04-24.log#L50)

### 3.3 Cookie 可用后仍失败

1. DLE 登录成功并写入 Cookie：[app_2026-04-24.log](../app_2026-04-24.log#L203)
2. 进入 Cookies 模式（Web+mweb）：[app_2026-04-24.log](../app_2026-04-24.log#L209)
3. 下载到约 10MB 后 403：[app_2026-04-24.log](../app_2026-04-24.log#L282)
4. 静默重提取 Cookie 后继续重试：[app_2026-04-24.log](../app_2026-04-24.log#L283), [app_2026-04-24.log](../app_2026-04-24.log#L297)
5. 重试仍 403，进入最终降级：[app_2026-04-24.log](../app_2026-04-24.log#L315), [app_2026-04-24.log](../app_2026-04-24.log#L360)
6. fallback 失效并出现全局异常：[app_2026-04-24.log](../app_2026-04-24.log#L430), [app_2026-04-24.log](../app_2026-04-24.log#L432)

### 3.4 循环复现

同样链路在后续时间段持续重复（11:37、11:39、11:41、11:45、11:48、11:51、11:54、11:57、11:58、12:37、13:07），典型样例：

1. [app_2026-04-24.log](../app_2026-04-24.log#L474)
2. [app_2026-04-24.log](../app_2026-04-24.log#L506)
3. [app_2026-04-24.log](../app_2026-04-24.log#L523)
4. [app_2026-04-24.log](../app_2026-04-24.log#L579)
5. [app_2026-04-24.log](../app_2026-04-24.log#L581)

---

## 4. 回退机制不严谨点（合并两轮）

## 4.1 P0：错误信号参数不匹配，导致未捕获异常

### 现象

下载失败后频繁出现：

1. TypeError: task_updated() only accepts 0 argument(s), 1 given!

### 代码证据

1. task_updated 为无参信号：[src/fluentytdl/download/download_manager.py](../src/fluentytdl/download/download_manager.py#L19)
2. worker.error 为带 dict 参数信号：[src/fluentytdl/download/workers.py](../src/fluentytdl/download/workers.py#L128)
3. 直接 connect 到 self.task_updated.emit：[src/fluentytdl/download/download_manager.py](../src/fluentytdl/download/download_manager.py#L176)

### 影响

1. 真正错误被二次异常污染，用户看到“崩上加崩”。
2. 回退流程末端 UI 状态刷新可能中断，增加“卡住/假死”感。

---

## 4.2 P1：回退提示与实际执行不一致，误导用户

### 现象

日志提示“使用刷新后的 Cookie 重试下载 (player_client=default)”，但紧接着实际 extractor_args 仍显示 web,mweb。

### 日志证据

1. 提示 default：[app_2026-04-24.log](../app_2026-04-24.log#L297)
2. 实际日志显示 Web+mweb：[app_2026-04-24.log](../app_2026-04-24.log#L301)

### 影响

1. 用户和开发者难以判断“到底跑了哪条策略”。
2. 排障时容易误判为“策略未生效”或“日志写错”。

---

## 4.3 P1：重复重试缺少止损，形成失败循环

### 现象

同一视频同一错误链反复执行：静默重提取 Cookie -> 重试 -> 403 -> 最终降级 -> fallback 失效 -> 再来一轮。

### 证据

1. 回退链条相关关键日志均出现 13 次（见第 2.2 节）。
2. 大量 Resuming download at byte，说明断点续传在“已知 403 场景”仍继续尝试：[app_2026-04-24.log](../app_2026-04-24.log#L472)

### 源码侧相关点

1. 续传默认开启：[src/fluentytdl/download/workers.py](../src/fluentytdl/download/workers.py#L316), [src/fluentytdl/download/workers.py](../src/fluentytdl/download/workers.py#L317)

### 影响

1. 用户耗时被显著拉长。
2. 失败体验从“单次失败”放大为“持续折腾”。

---

## 4.4 P1：客户端回退链包含低收益节点，且与设计目标冲突

### 现象

1. 回退中出现 android_creator,ios，并报 unsupported client。
2. 最终降级出现 web_safari,mweb,android_creator，仍失败。

### 证据

1. unsupported client 警告：[app_2026-04-24.log](../app_2026-04-24.log#L48)
2. 最终降级链：[app_2026-04-24.log](../app_2026-04-24.log#L360)

### 代码与文档对照

1. 代码中 auth blocked fallback 为 android_creator,ios：[src/fluentytdl/youtube/youtube_service.py](../src/fluentytdl/youtube/youtube_service.py#L1222)
2. 代码注释明确提醒不要 default：[src/fluentytdl/youtube/youtube_service.py](../src/fluentytdl/youtube/youtube_service.py#L320)
3. 文档也强调 default 风险：[docs/ADVANCED_GUIDE.md](./ADVANCED_GUIDE.md#L57)

### 影响

1. 回退链有分支本身已知兼容性较差，增加无效重试概率。
2. 用户看到“多次尝试”但结果无改善，会认为软件在盲试。

---

## 4.5 P2：错误分级虽有框架，但业务动作与分级未充分闭环

### 现象

1. error_parser 已将 403 标记为 AMBIGUOUS：[src/fluentytdl/utils/error_parser.py](../src/fluentytdl/utils/error_parser.py#L129), [src/fluentytdl/utils/error_parser.py](../src/fluentytdl/utils/error_parser.py#L133)
2. 但从日志看，动作仍偏向“重复刷新 Cookie + 重试”，对“IP/节点风控”场景止损不足。

### 用户困扰

1. 明明已登录且 Cookie 新鲜，仍被引导反复登录。
2. “网络/IP 风控”提示不够前置，修复建议排序不理想。

---

## 4.6 P2：运行版本与仓库源码存在漂移，增加定位成本

### 现象

1. 日志显示运行版本 3.0.14：[app_2026-04-24.log](../app_2026-04-24.log#L14)
2. 仓库 pyproject 版本为 2.0.1：[pyproject.toml](../pyproject.toml#L3)

### 影响

1. 仅靠仓库源码无法完全复盘日志中的回退实现细节。
2. 修复验证容易出现“源码已改、运行包未变”错位。

---

## 5. 用户可感知困扰清单

1. 时间成本高：一次失败会被拉长成多轮重试。
2. 心智负担高：提示文案与实际行为不一致，难以判断当前阶段。
3. 操作负担高：反复弹窗与反复登录，且收益不稳定。
4. 信任感下降：同一错误重复出现并伴随程序级异常。

---

## 6. 修复优先级建议

## 6.1 P0（立即）

1. 修复信号参数不匹配：worker.error 不应直接 connect 到无参 emit。
2. 确保错误尾路径不会再抛二次异常。

## 6.2 P1（高优）

1. 引入“回退熔断”：同视频同错误签名在短窗口内达到阈值后停止自动重试。
2. 在 403 场景的重试分支中禁用 continuedl 并清理对应 part，避免重复撞同一断点。
3. 收敛客户端回退链：剔除低收益或已知不支持节点，减少盲试。
4. 统一“提示文案”和“真实执行参数”来源，避免 default/web,mweb 口径冲突。

## 6.3 P2（中优）

1. 按错误分类动态排序修复建议：当 Cookie 新鲜且连续 403 时，将“更换节点/IP”前置。
2. 强化版本可观测性：日志打印 app 版本、git/hash、yt-dlp 版本、回退策略版本号。
3. 增加回退链路测试：模拟 not a bot、403、unsupported client、signal error 路径。

---

## 7. 备注

1. 本报告基于 [app_2026-04-24.log](../app_2026-04-24.log) 与当前仓库源码联合分析。
2. 由于运行版本与仓库版本存在漂移，建议后续在相同构建产物上复验一次并补充回归报告。
