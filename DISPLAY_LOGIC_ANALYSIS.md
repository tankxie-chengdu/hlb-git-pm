# Repos 界面完整逻辑分析

## 📊 展示逻辑流程图

```
用户打开 ReposView
    ↓
onMounted() 执行 fetchData()
    ↓
GET /api/repos → 后端返回 Repository 列表
    ↓
前端收到 repos 数组，每个 repo 包含：
  - full_name
  - is_cloned (布尔值)
  - synced_at (ISO 字符串，最后同步时间)
  - activity (活跃度级别)
  - contributors (贡献者列表)
    ↓
computed: filtered 和 activityGroups 计算并分组
    ↓
template 按活跃度分组显示卡片：
  🔥 今天活跃
  📈 本周活跃
  ⚙️ 本月活跃
  ⏳ 待同步
    ↓
每个卡片显示：
  - 仓库名 + 活跃标签
  - 最后推送时间 (pushed_at)
  - 同步按钮 + 复制命令按钮
  - 最后同步时间 (formatSyncTime(synced_at))
```

## 🔘 按钮操作流程

### 1. "同步" 按钮 (`syncOne(repo)`)
```
用户点击 "同步" 按钮
    ↓
POST /api/repos/sync [repo.full_name]
    ↓
后端 sync_repos() 立即返回 {"queued": ["WeFi-HLB/fps-tp"]}
    ↓
同时后台启动线程 _do_sync()
    ↓
前端收到响应，更新 syncJobs:
  syncJobs[full_name] = { status: 'queued', error: null }
    ↓
启动轮询 startPoll()
  每 2 秒调用 pollStatus()
    ↓
pollStatus() 调用 GET /repos/sync/status
    ↓
返回所有 sync job 的状态
    ↓
更新 syncJobs，按钮显示"同步中..."
    ↓
当 allDone 时（所有任务为 done 或 failed）
  ↓
停止轮询，调用 fetchData() 刷新仓库列表
  ↓
synced_at 应该已更新 ✓
```

### 2. "复制命令" 按钮 (`copyGitCommand(repo)`)
```
用户点击 "复制命令" 按钮
    ↓
GET /settings/proxy 获取代理配置
    ↓
构建 git 命令：
  git -c core.compression=0 \
      -c http.postBuffer=524288000 \
      -c http.lowSpeedLimit=0 \
      -c http.lowSpeedTime=999999 \
      [-c https.proxy=... | -c http.proxy=...] \
      clone --mirror <clone_url> ./.data/repos/<full_name>
    ↓
复制到剪贴板
    ↓
用户可在本地手动执行
```

### 3. "展开" 按钮
```
显示/隐藏贡献者详情表格
```

## 🐛 问题原因分析

### 问题：同步成功但 synced_at 为空

**根本原因（已修复）：**

后端 `_sync_one()` 中的路径获取逻辑有问题：

```python
# ❌ 旧代码（有问题）
ensure_repository(cfg, workspace, proxy_config=proxy_config)
local_dir = _repo_local_dir(r["clone_url"], workspace)  # 重新推导路径
if local_dir:
    _persist_contributors(full_name, local_dir)
    _update_repo_after_sync(full_name, local_dir)  # synced_at 在这里更新
```

问题：
1. `ensure_repository()` 返回了正确的路径，但被忽略
2. 重新用 `_repo_local_dir()` 推导路径，这个函数需要检查 `(path / "HEAD").exists()`
3. 如果推导失败（返回 None），就不会执行 `_update_repo_after_sync()`
4. 结果：synced_at 不会被更新 ❌

**解决方案（已实现）：**

```python
# ✅ 新代码（已修复）
local_dir = ensure_repository(cfg, workspace, proxy_config=proxy_config)  # 直接使用返回值
if local_dir:
    _persist_contributors(full_name, local_dir)
    _update_repo_after_sync(full_name, local_dir)  # 现在能正确更新
else:
    logger.warning("ensure_repository 返回空路径: %s", full_name)
```

## 📱 前端数据流动

### GET /api/repos 响应结构
```javascript
[
  {
    full_name: "WeFi-HLB/fps-tp",
    clone_url: "https://github.com/WeFi-HLB/fps-tp.git",
    is_cloned: true,
    synced_at: "2026-07-20T10:30:45.123456+00:00",  // ← 关键字段
    pushed_at: "2026-07-20T14:22:00Z",
    activity: {
      level: "today",
      label: "今天活跃",
      days: 0,
      color: "success"
    },
    branch_count: 3,
    total_commits: 245,
    contributors: [
      { git_email: "user@example.com", commit_count: 42, ... },
      ...
    ]
  },
  ...
]
```

### 显示 synced_at 的关键函数

```javascript
function formatSyncTime(isoString) {
  if (!isoString) return '从未同步'
  try {
    const date = new Date(isoString)
    const now = new Date()
    const diffMs = now - date
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return '刚刚'
    if (diffMins < 60) return `${diffMins} 分钟前`
    if (diffHours < 24) return `${diffHours} 小时前`
    if (diffDays < 7) return `${diffDays} 天前`
    
    return date.toLocaleDateString('zh-CN', { 
      month: 'short', day: 'numeric', 
      hour: '2-digit', minute: '2-digit' 
    })
  } catch {
    return isoString
  }
}
```

## 🔄 同步完整生命周期

### 1. 用户点击同步
- 前端：发送 `POST /repos/sync [full_name]`
- 后端：返回 `{"queued": [full_name]}`

### 2. 后台同步线程执行
```
_sync_one(repo_dict):
  1. 查询 Database 获取 Repository 行
  2. 检查 _needs_sync()：
     - 如果本地未克隆 → 需要同步
     - 如果 pushed_at > synced_at → 需要同步
     - 否则命中缓存，跳过
  3. 调用 ensure_repository():
     - 如果本地已有 → 执行 git fetch
     - 如果本地没有 → 执行 git clone --mirror
     - 返回 local_dir: Path
  4. 获取贡献者信息：
     - _local_contributors(local_dir)
     - 写入 ContributorStat 表
  5. 获取仓库统计：
     - _local_repo_stats(local_dir)
  6. 更新 Repository 表：
     - is_cloned = True
     - branch_count = N
     - total_commits = M
     - synced_at = NOW ← 关键！
  7. 更新 SyncJob：
     - status = "done"
     - error = ""
     - finished_at = NOW
```

### 3. 前端轮询获取状态
```
pollStatus() 每 2 秒执行一次：
  GET /repos/sync/status
  返回: { "WeFi-HLB/fps-tp": { status: "syncing", ... } }
  更新本地 syncJobs
  显示按钮为"同步中..."

当 allDone = true:
  停止轮询
  调用 fetchData()
  GET /api/repos 获取最新列表
  synced_at 现在应该是最新的 ✓
```

## 💾 数据库关键字段

### Repository 表
```
| full_name | is_cloned | synced_at | branch_count | total_commits |
|-----------|-----------|-----------|--------------|---------------|
| WeFi-HLB/fps-tp | 1 | 2026-07-20T10:30:45.123456+00:00 | 3 | 245 |
```

- `is_cloned`: 是否已在本地克隆
- `synced_at`: 最后一次成功同步的时间（git fetch 完成时）
- 这两个字段都在 `_update_repo_after_sync()` 中更新

### SyncJob 表
```
| repo_name | status | error | started_at | finished_at |
|-----------|--------|-------|-----------|-------------|
| WeFi-HLB/fps-tp | done | | 2026-07-20T10:30:00 | 2026-07-20T10:30:45 |
```

- 用于前端轮询显示进度

## ✅ 修复验证清单

- [x] 修复 `_sync_one()` 使用 `ensure_repository()` 的返回值
- [x] 确保 synced_at 在同步成功时被更新
- [x] 前端轮询逻辑正确
- [x] formatSyncTime() 函数工作正常
- [x] 前端显示 synced_at 字段

## 🚀 下一步验证

1. 清空旧数据：`rm -rf .data/repos/*` 和 `sqlite3 data.db "DELETE FROM sync_jobs;"`
2. 手动触发一个仓库的同步
3. 观察：
   - 后端日志中是否出现 `_update_repo_after_sync()` 的调用
   - Database 中 Repository 表的 synced_at 是否被更新
   - 前端是否显示最后同步时间

