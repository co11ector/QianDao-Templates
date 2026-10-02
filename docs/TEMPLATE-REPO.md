# 公共模板仓库：co11ector/QianDao-Templates

我们不再把上游的 `qd-today/templates` 当作产品里展示和抓取的仓库，而是订阅**自己的**
公开仓库 `co11ector/QianDao-Templates`。它由上游自动同步并**按站点类型整理**后发布。

## 这套东西放在哪（已定案）

模板仓库的全部材料 —— 整理器、它的测试、品牌资产、同步工作流、本文档 —— 都放在
**它服务的那个仓库里**（也就是本仓库），与私有的 `QianDao` 主仓、`QianDao Cookie
Extractor` 扩展仓**平行独立**。

私有主仓 `co11ector/QianDao` 里**不再**嵌套任何模板仓库材料：那里只保留**属于主仓的
契约**（默认仓库地址的种子与迁移、抓取逻辑），因为主仓是私库、模板仓是公开库，两者
的可见性与发布节奏都不同，混在一起容易两边漂移。

本地的 `QianDao Templates/` 工作目录（与主仓同级）是本仓的工作副本；**版本控制以本仓
为准**。

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
3. 运行 `tools/normalize.py upstream curated` —— 校验 HAR 可读性、按关键词分类、重写索引里的
   路径与 `url`、生成 README/CATEGORIES；
4. 把整理结果覆盖到本仓库并提交推送（用内置 `GITHUB_TOKEN`，不需要 PAT）。

**只替换** `templates/`、`tpls_history.json`、`README.md`、`CATEGORIES.md` 四处；
`brand/`、`tools/`、`tests/`、`docs/` 不受影响。

现状核对：该仓库**不是 Fork**（因此定时任务默认可用）、**公开**、默认分支 `master`、
工作流状态 active、已实测跑通（402 个模板、自动提交、success）。若是将来重建为 Fork，
需到 Actions 页**启用 schedule**（GitHub 默认禁用 fork 的定时任务）。

整理器是保守的 ✓：只**移动**不改名（上游文件名已被应用记录和用户引用），损坏或缺失的
文件**跳过并上报**，不会中断同步。索引的两种历史形态都支持：上游实际用的是
`{"har": {"<名称>": {...}}}` 映射，旧的列表形态也接受，输出保持输入形态。

## 应用侧（契约留在私有主仓）

- 新装的默认仓库：`db/migrations/template_records.py`、`legacy_schema_core.py` 的种子；
- 老库迁移：`TemplateRecordStepsMixin.upgrade_repository_state` —— 同时识别
  `qiandao-today/templates` 与 `qd-today/templates` 两种历史写法，改写成我们的仓库，
  并删除旧行，让下一次刷新从新仓库取回；
- 抓取与刷新：`web/services/public_template_refresh.py`（按 `<base>/<filename>` 取）。

## 校验

`tests/test_normalize.py` 覆盖：分类落位、索引路径与真实文件一致、损坏/缺失上报、
README 生成（含横幅引用）、以及**映射形态索引**的回归（该形态曾在真实上游上暴露过 bug）。
主仓侧另有 `tests/test_template_repo_material.py`，断言主仓**不再**嵌套这些材料，
并断言默认仓库地址的契约仍然指向 `co11ector/QianDao-Templates`。
