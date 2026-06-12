# arXiv cs.CV Digest

一个部署在 GitHub Pages 上的 arXiv `cs.CV` 每日论文摘要页。GitHub Actions 每天定时抓取论文并更新 `docs/data/papers.json`，网页直接读取这个静态 JSON。

## 本地不保存论文

这个版本不再运行本地服务，也不再把抓取结果保存到电脑本地。论文数据由 GitHub Actions 在云端生成，并提交到仓库里的 `docs/data/papers.json`。

仓库里当前只有一个空的占位 JSON。第一次 Actions 跑完后，GitHub 仓库会保存最新论文列表，供 GitHub Pages 页面展示。

## GitHub Pages

推送到 GitHub 后，进入仓库：

1. 打开 `Settings` -> `Pages`。
2. Source 选择 `GitHub Actions`。
3. 打开 `Actions`，手动运行 `Update arXiv Papers` 一次，之后会每天自动运行。

## 中文翻译

如果需要中文摘要，在 GitHub 仓库 `Settings` -> `Secrets and variables` -> `Actions` 中添加：

- `DEEPSEEK_API_KEY`
- 可选：`OPENAI_BASE_URL`

默认使用 DeepSeek 的 OpenAI-compatible 接口，`OPENAI_BASE_URL` 不填时会使用 `https://api.deepseek.com`。没有配置 key 时，页面仍会展示英文内容，并在中文区提示未配置翻译服务。

## 关注方向

编辑 `config.json`：

```json
{
  "category": "cs.CV",
  "max_results": 50,
  "keywords": ["3D reconstruction", "NeRF", "Gaussian Splatting"],
  "exclude_keywords": [],
  "translate": true,
  "openai_model": "deepseek-chat"
}
```

- `keywords` 为空时显示整个 `cs.CV` recent 列表。
- `keywords` 非空时，只保留标题、摘要或分类中命中的论文。

## 定时频率

定时任务在 `.github/workflows/update-papers.yml` 中配置：

```yaml
schedule:
  - cron: "0 0 * * *"
```

这是 UTC 时间每天 00:00 运行，也就是北京时间每天 08:00。
