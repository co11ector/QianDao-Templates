<p align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="brand/qiandao-templates-avatar-dark.png">
  <img alt="QianDao Templates" src="brand/qiandao-templates-avatar-light.png" width="200">
</picture>
</p>

<h1 align="center">QianDao Templates</h1>
<p align="center">QianDao 的公共模板模块 · 上游社区模板每日自动同步并按站点类型整理</p>

「QianDao 自动化运行台」的**公共模板模块**：把上游社区仓库 `qd-today/templates` 的模板每天自动同步、校验并按站点类型整理，供 [QianDao](https://github.com/co11ector/QianDao) 的用户一键创建定时签到任务。

- **开箱可用**：订阅本仓库即可在应用内挑选模板，不必自己收集
- **每日更新**：上游一有变化，24 小时内自动跟上
- **整理清楚**：按站点类型分目录，索引与文件一一对应
- **来源可查**：每个模板的作者与出处都保留在索引里

仓库与本地目录单独存在只因为两件事：模板必须能被**公开抓取**（主仓是私库，而 GitHub 的可见性是仓库级的），以及让本地文件管理更清楚。

## 模板概览

| 分类 | 说明 | 数量 |
| --- | --- | --- |
| [`pt/`](templates/pt) | PT 站 | 18 |
| [`forum/`](templates/forum) | 论坛社区 | 68 |
| [`video/`](templates/video) | 影音 | 8 |
| [`signin/`](templates/signin) | 通用签到 | 308 |

共 **402** 个模板，索引见 [`tpls_history.json`](tpls_history.json)。

## 自动同步

`.github/workflows/sync-upstream.yml` 每天 **03:17 UTC（北京时间 11:17）** 自动执行，也可以手动触发：

1. 先跑整理脚本的测试 —— **不通过就中止**，不会发布被改坏的索引；
2. 浅克隆上游仓库；
3. 校验每个 HAR 能否解析，按关键词分类，重写索引里的路径与直链；
4. 重新生成 README 与 CATEGORIES，有变化才提交推送。

全程使用仓库内置的 `GITHUB_TOKEN`，**不需要个人访问令牌**。

## 在 QianDao 中使用

应用内「模板库 → 公共模板」默认订阅本仓库。若需手动添加，在「已注册仓库」里填：

| 项 | 值 |
| --- | --- |
| 仓库地址 | `https://github.com/co11ector/QianDao-Templates` |
| 分支 | `master` |

## 许可与来源

本仓库的内容分属**三种不同的授权范围**，请分别看待：

| 内容 | 来源 | 授权 |
| --- | --- | --- |
| `templates/` 模板数据、`tpls_history.json` 索引 | 上游 [qd-today/templates](https://github.com/qd-today/templates) | 上游**未声明许可证** |
| `tools/`、`tests/`、`.github/`、`docs/` | 本项目（[QianDao](https://github.com/co11ector/QianDao)） | MIT License，Copyright © 2021 QD-Today、2026 co11ector |
| `brand/` 品牌资产 | 本项目（[QianDao](https://github.com/co11ector/QianDao)） | 同上（MIT） |

### 学习用途

上游 README 注明「项目中的模板均为开源模板，仅供学习参考使用，请勿用于商业用途」。本仓库按同样口径提供，**仅供个人学习参考，请勿商用**。

### 作者与出处

每个模板的 `author`、`comments`、`commenturl` 都保留在 [`tpls_history.json`](tpls_history.json) 里，**权利归原作者所有**。本仓库只做同步、校验与整理，不对模板数据主张任何权利。

### 请求移除

如果某个模板侵犯了你的权利、违反所在站点的规则，或你作为原作者希望移除它，请提 issue 说明，我们会尽快处理。

## 反馈

模板分类不合适、某个模板已经失效，或对整理方式有建议 —— 提 issue 说明即可。
