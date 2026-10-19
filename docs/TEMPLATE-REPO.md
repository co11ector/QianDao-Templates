# 公共模板仓库：co11ector/QianDao-Templates

我们不再把上游的 `qd-today/templates` 当作产品里展示和抓取的仓库，而是订阅**自己的**
公开仓库 `co11ector/QianDao-Templates`。它由上游自动同步并**按站点类型整理**后发布。

## 这套东西放在哪（已定案）

这是 **QianDao 项目的模板模块**，不是独立项目。模块的全部材料 —— 整理器、它的测试、品牌
资产、同步工作流、本文档 —— 都放在**它服务的这个仓库里**，而不是嵌套在私有的主仓里。

仓库单独、本地目录也单独，只因为两件事：

- **可见性**：模板必须能被公开抓取（应用按 raw 链接取文件，而 GitHub 的可见性是仓库级的），
  主仓是私库，所以模块需要一个自己的公开仓库；
- **本地管理**：`QianDao Templates/` 与主仓同级单独成文件夹，便于管理文件。

本地这个工作副本的**版本控制以本仓为准**。私有主仓 `co11ector/QianDao` 里**不再**嵌套任何
模块材料：那里只保留**应用依赖的契约**（默认仓库地址的种子与历史写法迁移、抓取逻辑），
并由 `tests/test_template_repo_material.py` 断言"不再嵌套"与契约未变。

## 为什么必须是公开仓库

应用按 `https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<filename>` 抓取模板。
我们的主仓库 `co11ector/QianDao` 是**私库**，raw 链接需要 token 才能访问；而 GitHub 的
可见性是**仓库级**的，无法只公开某个目录。所以模板仓库是**独立的公开仓库**。

## 目录结构

```
templates/
  pt/         PT 站
  forum/      论坛社区
  video/      影音
  shop/       购物
  signin/     通用签到（未命中的归入此处）
tpls_history.json   索引；filename 是相对路径，例如 templates/forum/s1-forum.har
README.md  CATEGORIES.md
tools/normalize.py  整理器（本仓库即规范版本）
tests/test_normalize.py  整理器的测试；同步前由工作流先跑
brand/              品牌资产（横幅 / 头像 / 透明锁定图，各含明暗两版）
  README.md         资产清单与 Markdown 引用代码
  preview.html      本地交互预览（明暗切换）
.github/workflows/sync-upstream.yml  同步工作流
docs/TEMPLATE-REPO.md  本文档
```

应用按 `<仓库地址>/<filename>` 抓取，`urllib.parse.quote` 默认保留 `/`，所以索引里带
路径的文件名与放在根目录时一样能取到。

## 同步

`.github/workflows/sync-upstream.yml`：

1. 先 `pip install pytest` 并跑 `python -m pytest tests -q` —— **整理器自检不过就中止**，
   不会发布被改坏的索引；
2. 每天 03:17 UTC（可手动触发）浅克隆上游；
3. 运行 `tools/normalize.py upstream curated` —— 自动清理抓包中的真实 Cookie、硬编码
   User-Agent、静态凭据 Header，以及请求/响应 Cookie 元数据；为每个外部 HTTP(S) 请求
   补齐且只保留一份 `Cookie: {{cookie}}` 与一份 `User-Agent: {{user_agent}}`。拒绝
   `browser://`、`browser_worker`、`browser-worker`；没有外部 HTTP(S) 请求的模板跳过并
   上报，其他无法规范化的上游条目同样跳过并上报，项目自有的 `local/` 模板不合规则直接
   中止同步。通过后按关键词分类、重写索引里的路径与 `url`、生成
   README/CATEGORIES。索引内嵌的 HAR 统一规范化为 UTF-8 + LF，`local/` 模板时间取 Git
   commit epoch 并按 UTC 输出，避免 Windows 与 Ubuntu runner 因 CRLF 或本地时区生成
   不同索引；
4. 把整理结果覆盖到本仓库，再跑发布树硬门禁：至少 400 个模板、索引与 HAR 一一对应、
   内嵌内容与文件逐字一致、全部通过 Cookie-only 校验；
5. 校验通过后才提交推送（用内置 `GITHUB_TOKEN`，不需要 PAT）。

**只替换** `templates/`、`tpls_history.json`、`README.md`、`CATEGORIES.md` 四处；
`brand/`、`tools/`、`tests/`、`docs/` 不受影响。

现状核对：该仓库**不是 Fork**（因此定时任务默认可用）、**公开**、默认分支 `master`、
工作流状态 active、已实测跑通。当前同步 407 条上游索引，其中 388 条可规范化为
Cookie-only HTTP 模板、14 条因没有外部 HTTP(S) 请求跳过、2 条因请求体含不可公开的字面
凭据被拒绝；再合并 `local/` 下 24 个项目自有模板，最终发布 406 个唯一模板。发布集包含
PT 17、论坛 73、影音 9、通用签到 307。
若是将来重建为 Fork，需到 Actions 页**启用 schedule**（GitHub 默认禁用 fork 的定时任务）。

整理器对文件名保持保守 ✓：只**移动或按分类落位**，不改名（上游文件名已被应用记录和用户
引用）；损坏或缺失的文件**跳过并上报**，无法安全转换为 Cookie-only 的上游模板同样跳过并
上报。项目自有的 `local/` 模板违反 Cookie-only 规则属于回归，因此直接中止整次同步。索引的
两种历史形态都支持：上游实际用的是 `{"har": {"<名称>": {...}}}` 映射，旧的列表形态也接受，
输出保持输入形态。

## 应用侧（契约留在私有主仓）

- 新装的默认仓库：`db/migrations/template_records.py`、`legacy_schema_core.py` 的种子；
- 老库迁移：`TemplateRecordStepsMixin.upgrade_repository_state` —— 同时识别
  `qiandao-today/templates` 与 `qd-today/templates` 两种历史写法，改写成我们的仓库，
  并删除旧行，让下一次刷新从新仓库取回；
- 抓取与刷新：`web/services/public_template_refresh.py`（按 `<base>/<filename>` 取）。

## 校验

`tests/test_normalize.py` 覆盖：分类落位、抓包敏感字段清理、Cookie/UA 补齐、无外网请求
跳过、浏览器模板拒绝、400 条发布下限、索引路径与真实文件一致、索引内嵌内容与发布文件
逐字一致、损坏/缺失上报、项目自有模板回归中止、README 生成（含横幅引用）、CRLF checkout
的索引规范化、UTC 时间戳，以及**映射形态索引**的回归（该形态曾在真实上游上暴露过 bug）。
`tests/test_official_templates.py` 还会校验发布树包含全部 `local/` 模板，且每个已发布模板
的每个外部 HTTP(S) 请求都成对携带 Cookie 与 User-Agent。
主仓侧另有 `tests/test_template_repo_material.py`，断言主仓**不再**嵌套这些材料，
并断言默认仓库地址的契约仍然指向 `co11ector/QianDao-Templates`。
