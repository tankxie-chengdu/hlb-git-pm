# Repository Data Inconsistency Bug Fix

**Commit**: `b6ae468` - 🐛 fix(repos): resolve repository data inconsistency from failed sync updates

## Problem Summary

The system experienced a critical bug where repositories would show **0 branches, 0 commits, and 0 contributors** in the database despite having valid git data locally.

### Symptom
WeFi-HLB/apigw appeared broken:
```
UI Display:
├─ 分支数: 0 ❌
├─ 提交数: 0 ❌
├─ 贡献者: 0 ❌
└─ 最后同步: 2026-07-17T08:08:14 (3 days ago)

Actual Git Repository:
├─ Branches: 7
├─ Commits: 333
└─ Contributors: 10
```

## Root Cause Analysis

### Issue 1: Silent Exception in `_update_repo_after_sync()`
The function caught all exceptions but never propagated them:
```python
except Exception as e:
    session.rollback()
    logger.warning("Repository 更新失败 %s: %s", full_name, e)  # ← Silent failure
    # Sync marked as "done" but data never updated
```

When `_update_repo_after_sync()` failed (for any reason), the sync job was still marked as "done" without updating the database. The exception was swallowed, leaving no trace except a warning log.

### Issue 2: Cache Bypass Logic
Even after the git repository was successfully fetched, subsequent sync attempts would skip updating the database because:
1. Repository marked as `is_cloned = True` and `synced_at = 2026-07-17`
2. `_needs_sync()` checked if `pushed_at > synced_at`
3. Since the last push (2026-07-16) was before last sync (2026-07-17), it returned False
4. Sync was skipped due to cache, so the corrupted data was never corrected

**The combination of these two issues created a permanent data inconsistency.**

## Solutions Implemented

### Solution 1: Enhanced Diagnostic Logging

Added checkpoint logging throughout `_update_repo_after_sync()`:
```python
logger.info("[SYNC_UPDATE] 开始更新: %s", full_name)
logger.info("[SYNC_UPDATE] 分支数: %d", branch_count)
logger.info("[SYNC_UPDATE] 提交数: %d", total_commits)
logger.info("[SYNC_UPDATE] 查询数据库...")
logger.info("[SYNC_UPDATE] 记录已修改: branch_count=%d, total_commits=%d", ...)
logger.info("[SYNC_UPDATE] ✓ 完成: branch_count=%d, total_commits=%d, synced_at=%s", ...)
```

If a failure occurs, the full exception traceback is logged with:
```python
logger.error("[SYNC_UPDATE] ❌ 更新失败: %s", full_name, exc_info=True)
```

### Solution 2: Automatic Recovery for Corrupted Data

Modified `_needs_sync()` to detect and recover from incomplete syncs:
```python
# Force sync if database shows 0 commits/branches (indicates failed _update_repo_after_sync)
if row.total_commits == 0 and row.branch_count == 0:
    logger.warning("强制同步: %s 数据库显示 0 提交/分支，可能同步失败", repo["full_name"])
    return True
```

This ensures that:
- Any repository with 0 commits AND 0 branches is re-synced
- The database is updated with correct values
- Users see corrected data in the next sync cycle

### Solution 3: Progress Tracking

Added debug logs at key points in `_sync_one()`:
```python
logger.debug("[SYNC_ONE] git clone/fetch 成功: %s -> %s", full_name, local_dir)
logger.debug("[SYNC_ONE] 贡献者持久化完成: %s", full_name)
logger.debug("[SYNC_ONE] 仓库信息更新完成: %s", full_name)
```

This helps identify exactly where in the sync pipeline any future failures occur.

## Verification

### Before Fix
```bash
$ sqlite3 .data/hlb-git-pm.db "SELECT branch_count, total_commits FROM repositories WHERE full_name='WeFi-HLB/apigw';"
0|0
```

### After Fix
```bash
$ sqlite3 .data/hlb-git-pm.db "SELECT branch_count, total_commits FROM repositories WHERE full_name='WeFi-HLB/apigw';"
7|333
```

### Server Logs During Fix
```
[INFO] 强制同步: WeFi-HLB/apigw 数据库显示 0 提交/分支，可能同步失败
[INFO] [SYNC_UPDATE] 开始更新: WeFi-HLB/apigw
[INFO] [SYNC_UPDATE] 分支数: 7
[INFO] [SYNC_UPDATE] 提交数: 333
[INFO] [SYNC_UPDATE] ✓ 完成: branch_count=7, total_commits=333, synced_at=2026-07-20T03:37:47
```

## Prevention for Future Issues

### Short-term (Implemented)
✅ Enhanced logging provides visibility into sync failures
✅ Automatic recovery detects and fixes corrupted data
✅ Progress tracking helps diagnose pipeline issues

### Medium-term (Recommended)
- [ ] Add automated checks for 0 commit/branch repositories in daily reports
- [ ] Implement sync job status monitoring with alerts
- [ ] Add retry logic for failed sync updates (optional retries)

### Long-term (Optional)
- [ ] Database constraints to prevent 0/0 combinations for is_cloned=true
- [ ] Sync pipeline unit tests to catch silent exceptions
- [ ] Monitoring dashboard for repository data health

## Files Changed
- `web/api/repos.py`:
  - Enhanced logging in `_update_repo_after_sync()` (31 lines added)
  - Added recovery logic in `_needs_sync()` (5 lines added)
  - Added progress tracking in `_sync_one()` (3 lines added)

## Impact
- **Data Consistency**: Repositories with incomplete sync data are now automatically corrected
- **Observability**: Sync failures are now visible through enhanced logging
- **User Experience**: Users see correct repository information after the next sync cycle
- **No Breaking Changes**: Existing sync logic unaffected for properly synced repositories

