# WeFi-HLB/apigw 仓库数据问题深度分析

## 🔍 问题现象

UI 显示：
```
WeFi-HLB/apigw
├─ 分支数: 0 ❌
├─ 提交数: 0 ❌
├─ 贡献者: 0 ❌
└─ 最后同步: 2026-07-17T08:08:14 (3 天前)
```
## ✅ 实际情况

```
📂 仓库目录: ✓ 存在
📋 实际分支数: 7 个
  - refs/heads/23.06.26.DEV_rookietang
  - refs/heads/26.06.26.DEV
  - refs/heads/26.07.25.DEV
  - refs/heads/cc
  - refs/heads/main
  + 2 更多

📊 实际提交数: 333 个
🔗 HEAD: ref: refs/heads/main
```

---

## 🔴 根本原因

**最后一次同步（2026-07-17）时，`_update_repo_after_sync()` 更新失败！**

### 数据库状态

```
Repository 表:
full_name: "WeFi-HLB/apigw"
is_cloned: 1 (true)
synced_at: "2026-07-17T08:08:14.359486+00:00"
branch_count: 0 ❌
total_commits: 0 ❌

ContributorStat 表:
贡献者数: 0 ❌
```

### 可能的原因

1. **Git 命令超时** - `timeout=120s` 对大仓库可能不够
2. **内存不足** - 大型仓库的 git log 很耗内存
3. **网络中断** - 导致 git 操作部分失败
4. **磁盘满** - 无法写入临时文件
5. **权限问题** - 无法访问仓库

---

## 🛠️ 解决方案

### 快速修复（现在）

```bash
# 重新同步这个特定仓库
python sync_all.py --token $SYNC_TOKEN \
  --repos WeFi-HLB/apigw \
  --verbose

# 验证修复
sqlite3 .data/hlb-git-pm.db \
  "SELECT branch_count, total_commits FROM repositories WHERE full_name='WeFi-HLB/apigw';"

# 预期输出: 7|333
```

### 长期改进

1. **添加检查点日志** - 在 `_update_repo_after_sync()` 中添加详细日志
2. **实现重试机制** - 失败时自动重试 3 次
3. **改进错误处理** - 区分 git 成功和数据更新成功

---

## 🔍 为什么会出现这个问题

```
时间线：2026-07-17 08:08:14

├─ ensure_repository() 成功 ✓
├─ SyncJob 标记为 "done" ✓
├─ _update_repo_after_sync() 被调用
├─ 但数据库中仍然记录 0 分支 0 提交 ❌
└─ 原因：异常被 catch，未能更新数据

3 天过去...
└─ 数据仍然没有更新
```

代码中的异常处理：

```python
def _update_repo_after_sync(full_name: str, local_dir: Path) -> None:
    try:
        branch_count = _local_repo_stats(local_dir)["branch_count"]
        _, total_commits = _local_contributors(local_dir)
        # 更新数据库
    except Exception as e:
        session.rollback()
        logger.warning("Repository 更新失败 %s: %s", full_name, e)
        # ❌ 异常被吞掉，同步标记为"成功"，但数据未更新
```

---

## 📋 核心要点

```
✓ 仓库文件: 完好
✓ Git 数据: 完好 (7 分支, 333 提交)
✗ 数据库: 过时 (0 分支, 0 提交)
✓ 原因: _update_repo_after_sync() 更新失败
✓ 解决: 重新同步
```
