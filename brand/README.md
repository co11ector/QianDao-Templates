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

## 🚀 在 README.md 中使用

将以下代码复制并粘贴到仓库 `README.md` 的最上方：

### 方案 1：随 GitHub 明暗模式自适应切换（推荐）

```markdown
<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="brand/qiandao-templates-banner-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="brand/qiandao-templates-banner-light.png">
    <img alt="QianDao Templates" src="brand/qiandao-templates-banner-light.png" width="100%">
  </picture>
</p>
```

### 方案 2：纯净居中静态展示

```markdown
<p align="center">
  <img src="brand/qiandao-templates-banner-light.png" alt="QianDao Templates" width="100%">
</p>
```
