# Git Daily Report

一个无前端的 Git 日报服务：每天扫描指定仓库或 GitHub 组织下的全部仓库，生成 AI 分析，并通过邮件发送。

## 快速开始

需要 Python 3.10+ 和本机 `git`（Python 3.10 请先执行 `pip install -r requirements.txt`）。复制示例配置并填写仓库、SMTP 与 AI 信息：

```bash
cp config.example.toml config.toml
export ZAI_API_KEY=...
export SMTP_PASSWORD=...
python -m app --config config.toml --once --dry-run
```

确认输出后，常驻运行调度器：

```bash
python -m app --config config.toml
```

进程会按 `run_at` 和 `timezone` 每天运行一次；也可以交给 cron/systemd 调用 `--once`。日报 Markdown 会落到 `.data/reports/YYYY-MM-DD.md`，便于审计和补发。

## 部署

常驻方式可以直接使用仓库里的 `deploy/git-daily-report.service`：将项目放到 `/opt/git-daily-report`，准备好 `config.toml` 后执行 `systemctl enable --now git-daily-report`。容器方式需要把配置文件挂载到 `/app/config.toml`，并把 `.data` 持久化：

```bash
docker build -t git-daily-report .
docker run -d --name git-daily-report --restart unless-stopped \
  -v "$PWD/config.toml:/app/config.toml:ro" \
  -v "$PWD/.data:/app/.data" \
  --env-file .env git-daily-report
```

如果使用 cron，建议每天 18:35 执行一次并让进程退出：

```cron
35 18 * * * cd /opt/git-daily-report && /usr/bin/python3 -m app --config config.toml --once >> .data/cron.log 2>&1
```

## 配置说明

- `repositories` 支持 `url`（首次自动 clone）或 `path`（扫描已有本地仓库）。
- 配置 `[github]` 后，服务会使用 GitHub App 自动发现该 Installation 可访问的仓库；当前组织配置已填入 `WeFi-HLB`、App ID `4320314` 和 Installation ID `147107481`，只需要把 Private Key 保存到 `private_key_file` 指定的位置。
- GitHub App 需要 `Contents: Read-only` 和 `Metadata: Read-only`；Private Key 不要提交到仓库或发到聊天中。
- `branch` 为空时统计所有 refs（等价于 `git log --all`）；组织自动发现模式会为每个仓库建立 bare mirror，不创建工作区文件；`fetch = true` 会在扫描前执行 `git fetch --all --prune`。
- `ai.enabled = false` 或未设置 `api_key` 时使用本地规则摘要，不会阻断邮件发送。
- 默认示例使用 Z.AI Coding Plan 的 `https://api.z.ai/api/coding/paas/v4`；AI 接口使用 OpenAI-compatible `POST /chat/completions`，因此也可配置其他兼容网关的 `base_url`。
- `thinking_enabled = false` 会向支持该参数的模型关闭推理，避免日报正文被 reasoning token 耗尽；不支持该参数的供应商可删除此配置项。
- 邮件使用标准 SMTP；密码、API key 建议通过环境变量 `${NAME}` 注入，不要提交到仓库。

## 运行方式

```text
python -m app [--config config.toml] [--once] [--date YYYY-MM-DD] [--dry-run] [--verbose]
```

`--date` 默认是昨天，避免日报在当天结束前被提前发送；补发历史日报时可显式指定日期。
