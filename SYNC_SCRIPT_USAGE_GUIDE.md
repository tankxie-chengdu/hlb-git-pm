# sync_all.py 使用指南

## 🎯 快速开始

### 最简单的使用

```bash
# 全量同步所有仓库
python sync_all.py
```

### 常见用法

```bash
# 同步指定仓库
python sync_all.py --repos WeFi-HLB/ai-ocr WeFi-HLB/fps-tp

# 设置 2 小时超时
python sync_all.py --timeout 7200

# 连接到远程服务器
python sync_all.py --api http://192.168.1.100:8000

# 触发后不等待（返回立即）
python sync_all.py --no-wait
```

---

## 📊 工作原理

```
sync_all.py (你的脚本)
    ↓
GET /api/repos (获取所有仓库)
    ↓
POST /api/repos/sync (触发后台同步)
    ↓
后台线程启动 (8 个并发 worker)
    │
    ├─ ensure_repository() (clone 或 fetch)
    ├─ _update_repo_after_sync() (更新 synced_at)
    ├─ _persist_contributors() (统计贡献者)
    └─ 创建 SyncJob 记录 (进度追踪)
    ↓
轮询 GET /api/repos/sync/status
    ↓
显示进度条和统计
    ↓
完成后打印总结
```

---

## 🔧 参数详解

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--api` | http://localhost:8000 | API 服务器地址 |
| `--repos` | 无 | 指定要同步的仓库 (空表示全量) |
| `--timeout` | 3600 (1小时) | 超时时间（秒） |
| `--poll-interval` | 2 | 轮询间隔（秒） |
| `--no-wait` | - | 触发后立即返回 |
| `-v, --verbose` | - | 显示详细日志 |

---

## 📈 输出示例

### 进行中

```
🔗 连接到: http://localhost:8000
📋 找到 42 个仓库
触发全量同步
✓ 已队列 42 个仓库

📊 开始同步 42 个仓库...
⏱️  超时设置: 3600 秒 (1h 0m)

[████████████░░░░░░░░░░░░░░░░░░░░░░░] 18/42 (完成: 18, 同步中: 3, 队列: 21)
```

### 完成

```
============================================================
📈 同步完成
============================================================
总数:        42 个仓库
成功:        41 ✓
失败:         1 ✗
成功率:     97.6%
============================================================

❌ 失败的仓库:
  • WeFi-HLB/bnbs
    └─ git clone --mirror https://github.com/WeFi-HLB/bnbs...
```

---

## ⏰ 定时执行

### 方式 1: Cron (简单)

编辑 crontab:
```bash
crontab -e
```

添加任务:
```bash
# 每天晚上 10 点同步一次
0 22 * * * cd /path/to/project && python sync_all.py >> /var/log/repo_sync.log 2>&1

# 每 6 小时同步一次
0 */6 * * * cd /path/to/project && python sync_all.py --timeout 1800

# 每周一凌晨 2 点做一次完整同步
0 2 * * 1 cd /path/to/project && python sync_all.py --timeout 14400
```

查看已有任务:
```bash
crontab -l
```

### 方式 2: Systemd Timer (推荐，更灵活)

创建 service 文件:
```bash
sudo vi /etc/systemd/system/repo-sync.service
```

内容:
```ini
[Unit]
Description=Repository Synchronization Service
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /path/to/project/sync_all.py
User=git
WorkingDirectory=/path/to/project
StandardOutput=journal
StandardError=journal
```

创建 timer 文件:
```bash
sudo vi /etc/systemd/system/repo-sync.timer
```

内容:
```ini
[Unit]
Description=Repository Sync Timer
Requires=repo-sync.service

[Timer]
OnBootSec=5min
OnUnitActiveSec=6h
Persistent=true

[Install]
WantedBy=timers.target
```

启用:
```bash
sudo systemctl daemon-reload
sudo systemctl enable repo-sync.timer
sudo systemctl start repo-sync.timer

# 查看状态
sudo systemctl status repo-sync.timer

# 查看日志
sudo journalctl -u repo-sync.service -f
```

---

## 🐛 故障排查

### 问题 1: 连接失败

```
❌ 获取仓库列表失败: Connection refused
```

**解决**:
```bash
# 检查服务是否运行
curl http://localhost:8000/api/repos

# 如果返回 JSON，说明服务正常
# 否则启动服务
python -m app  # 或你的启动命令
```

### 问题 2: 超时

```
⏰ 超时！已等待 3600 秒
```

**解决**:
```bash
# 增加超时时间
python sync_all.py --timeout 7200  # 2 小时

# 或只同步部分仓库
python sync_all.py --repos org/repo1 org/repo2
```

### 问题 3: 某个仓库失败

```
❌ 失败的仓库:
  • WeFi-HLB/bnbs
    └─ git clone --mirror...
```

**解决**:
```bash
# 查看详细日志
python sync_all.py -v

# 手动同步该仓库
git -C .data/repos/WeFi-HLB/bnbs fetch --all --prune

# 或通过 UI 同步单个仓库
```

### 问题 4: 内存或磁盘不足

```
ERROR: No space left on device
```

**解决**:
```bash
# 检查磁盘空间
df -h .data/repos/

# 清理不需要的仓库
rm -rf .data/repos/old-org/*

# 或选择性同步小仓库
python sync_all.py --repos WeFi-HLB/small-repo
```

---

## 📝 日志输出

### 查看完整日志

```bash
# 启用详细日志
python sync_all.py -v

# 重定向到文件
python sync_all.py >> sync.log 2>&1

# 实时查看日志
tail -f sync.log
```

### 日志位置

如果配置了 cron:
```bash
tail -f /var/log/repo_sync.log
```

如果使用 systemd:
```bash
sudo journalctl -u repo-sync.service -f
```

---

## 🚀 高级用法

### 1. 只同步特定的大仓库

```bash
python sync_all.py --repos \
  WeFi-HLB/wecube-platform \
  WeFi-HLB/credios-websr \
  WeFi-HLB/cocvs-service_app \
  --timeout 7200
```

### 2. 快速检查（不等待完成）

```bash
# 触发同步后立即返回
python sync_all.py --no-wait

# 脚本会运行脚本 0~5 秒就返回
# 后台同步会继续执行
```

### 3. 远程执行

```bash
# 从另一台机器触发同步
python sync_all.py --api http://server.com:8000

# 这对 CI/CD 流程很有用
```

### 4. 自定义轮询频率

```bash
# 快速轮询（适合小仓库）
python sync_all.py --poll-interval 1

# 慢速轮询（适合网络慢的情况）
python sync_all.py --poll-interval 5
```

---

## 💡 最佳实践

### 1. 定期备份

```bash
# 每周一完整备份
30 1 * * 1 tar -czf /backup/repos-$(date +\%Y\%m\%d).tar.gz /path/to/project/.data/repos/
```

### 2. 监控同步状态

```bash
# 发送成功/失败通知
0 22 * * * python sync_all.py | mail -s "Repo Sync Report" admin@example.com
```

### 3. 分阶段同步

```bash
# 早上同步小仓库（快速）
0 2 * * * python sync_all.py --timeout 1800 --repos WeFi-HLB/small-repo

# 晚上同步大仓库（耐心等待）
0 22 * * * python sync_all.py --timeout 7200
```

### 4. 监控磁盘空间

```bash
#!/bin/bash
DISK_USAGE=$(df .data/repos/ | awk 'NR==2 {print $5}' | cut -d'%' -f1)
if [ $DISK_USAGE -gt 80 ]; then
  echo "磁盘使用 $DISK_USAGE%，中止同步"
  exit 1
fi
python sync_all.py
```

---

## 📊 性能指标

### 预期耗时

| 场景 | 仓库数 | 耗时 |
|------|--------|------|
| 小型组织 | 10-20 | 10-20m |
| 中型组织 | 40-50 | 30-60m |
| 大型组织 | 100+ | 2-4h |

### 参考配置

```
系统资源:
├─ CPU: 2+ 核 (推荐 4+)
├─ 内存: 4GB+ (推荐 8GB+)
├─ 磁盘: 100GB+ (根据仓库大小)
└─ 网络: 稳定的国际连接 (或配置代理)

并发数: 8 (系统配置，脚本不改变)
```

---

## 🔄 与 UI 的集成

### UI 会实时显示

脚本触发同步后，打开浏览器访问 `http://localhost:8000/repos`:

1. **同步进度** - 会显示实时进度 (1/42, 2/42, ...)
2. **仓库状态** - "已同步" 状态会实时更新
3. **最后同步时间** - 同步完成后会显示 "刚刚"、"N分钟前"
4. **错误信息** - 失败的仓库会显示错误原因

---

## 📚 相关文档

- `PYTHON_SYNC_SCRIPT_ANALYSIS.md` - 详细的技术分析
- `GIT_COMMAND_ANALYSIS.md` - Git 命令参数详解
- `QUICK_REFERENCE.md` - 快速参考指南

---

## ✅ 检查清单

使用前：
- [ ] 确认 Web 服务正在运行
- [ ] 确认 API 可以访问 `curl http://localhost:8000/api/repos`
- [ ] 确认磁盘有足够空间
- [ ] 代理配置正确（如果需要）

首次运行：
- [ ] 运行 `python sync_all.py --help` 查看帮助
- [ ] 试运行一个小规模同步 `python sync_all.py --repos WeFi-HLB/ai-ocr`
- [ ] 观察日志输出，确保一切正常

定时执行：
- [ ] 配置 cron 或 systemd timer
- [ ] 验证定时任务已启用
- [ ] 检查日志确保正常运行

---

## 🎓 学习更多

```bash
# 查看脚本帮助
python sync_all.py --help

# 启用详细日志了解过程
python sync_all.py -v

# 查看源代码了解实现
cat sync_all.py
```

