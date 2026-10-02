# QianDao Templates 品牌视觉规范与使用指南

本目录包含 `QianDao-Templates` 仓库的官方品牌视觉资产。

## 📁 资产清单

- `qiandao-templates-banner-light.png`：亮色顶头横幅（2560 × 720 Retina 高清渲染）
- `qiandao-templates-banner-dark.png`：暗黑极客顶头横幅（2560 × 720 Retina 高清渲染）
- `qiandao-templates-avatar-light.png`：亮色官方正方图标 / 头像（1024 × 1024）
- `qiandao-templates-avatar-dark.png`：暗色官方正方图标 / 头像（1024 × 1024）
- `qiandao-templates-lockup-light.png`：亮色透明横版 Logo（1600 × 480）
- `qiandao-templates-lockup-dark.png`：暗色透明横版 Logo（1600 × 480）
- `preview.html`：本地交互式预览页面（双击即可打开并体验明暗模式切换）

## 🚀 各自用在哪

| 资产 | 用途 |
| --- | --- |
| `avatar-*`（1024×1024） | **仓库 LOGO**：README 顶部正中，约 140px 宽；也可作为仓库头像 |
| `banner-*`（2560×720） | **不进 README** ✗：用于**仓库社交预览图**（仓库 Settings → Social preview 手动上传）、文档封面等通栏场合 |
| `lockup-*`（1600×480，透明） | 文档、幻灯片、需要透明底的场合 |

README 顶部由生成器 `tools/normalize.py` 输出，固定为：**方形 LOGO → 居中标题 → 副标题**，跟随读者的明暗主题。**横幅不放在 README 里**（README 保持简洁，横幅留给社交预览）。改动版式请改生成器，不要直接编辑 README（下次同步会覆盖）。

参考写法（与生成的 README 一致）：

```markdown
<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="brand/qiandao-templates-avatar-dark.png">
    <img alt="QianDao Templates" src="brand/qiandao-templates-avatar-light.png" width="140">
  </picture>
</p>

<h1 align="center">QianDao Templates</h1>
<p align="center">QianDao 的公共模板模块 · 上游社区模板每日自动同步并按站点类型整理</p>
```