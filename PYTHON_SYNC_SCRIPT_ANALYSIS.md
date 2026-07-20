# Python 同步脚本可行性分析

## 🎯 你的需求

写一个 Python 脚本来同步本地所有仓库的最新提交。

## ✅ 可行性结论

**完全可行！**

但需要理解与现有系统的关系。

---

## 📊 现有系统架构分析

### 当前同步方式

```
你的系统架构:
┌─ web/api/repos.py (API 层)
│  └─ sync_repos() 端点
│     └─ _do_sync() 后台线程
│        └─ ensure_repository() (app/git_service.py)
│           └─ _run_git() 执行 git 命令
└─ 前端 UI
   └─ 点击"同步"按钮 → POST /api/repos/sync

特点:
├─ 异步后台执行
├─ 多线程并发 (8 个 worker)
├─ 有进度追踪 (SyncJob 表)
├─ 更新 synced_at 时间戳
├─ 采用代理 + 性能优化
└─ 前端轮询显示进度
```

### 三种可能的脚本方式

#### 方式 1: 独立脚本（不使用现有 API）

```python
# 直接调用 git 命令
import subprocess
from pathlib import Path

def sync_all_repos():
    repos_dir = Path('.data/repos')
    for repo_path in repos_dir.rglob('HEAD'):
        repo = repo_path.parent
        subprocess.run([
            'git', '-c', 'core.compression=0',
            '-c', 'http.postBuffer=524288000',
            '-C', str(repo),
            'fetch', '--all', '--prune'
        ])
```

**优点**:
- 简单直接
- 不需要启动 Web 服务
- 可以定时运行

**缺点**:
- ❌ 不更新数据库 (synced_at 不会改变)
- ❌ 不显示进度
- ❌ 没有错误追踪
- ❌ 与现有系统脱离

---

#### 方式 2: 调用现有 API

```python
import requests
import time

def sync_all_via_api():
    # 获取所有仓库
    repos = requests.get('http://localhost:8000/api/repos').json()
    
    # 触发同步
    full_names = [r['full_name'] for r in repos]
    response = requests.post(
        'http://localhost:8000/api/repos/sync',
        json=full_names
    )
    
    # 轮询等待完成
    while True:
        status = requests.get(
            'http://localhost:8000/api/repos/sync/status'
        ).json()
        if all(s['status'] in ['done', 'failed'] for s in status.values()):
            break
        time.sleep(2)
    
    return status
```

**优点**:
- ✓ 充分利用现有系统
- ✓ 自动更新 synced_at
- ✓ 有进度追踪
- ✓ 应用所有优化参数
- ✓ 与 UI 一致

**缺点**:
- 需要 Web 服务运行
- 需要认证

---

#### 方式 3: 直接调用后端函数（最优）

```python
import sys
sys.path.insert(0, '/path/to/project')

from web.api.repos import _do_sync, _build_repo_list
from web.database import get_session
from web.db_models import Repository

def sync_all_directly():
    db = get_session()
    
    # 获取所有仓库
    repos_data = _build_repo_list(db)
    
    # 调用同步函数
    _do_sync(repos_data)
    
    db.close()
```

**优点**:
- ✓ 完全复用现有逻辑
- ✓ 无需 HTTP 开销
- ✓ 同样的参数优化
- ✓ 同样的进度追踪
- ✓ 同样的数据库更新

**缺点**:
- 需要正确的 Python 环境
- 需要处理导入和配置

---

## 🎯 推荐方案

### 方案对比

```
指标              | 方式1      | 方式2        | 方式3
-----------------|-----------|--------------|----------
实现复杂度        | ⭐        | ⭐⭐⭐       | ⭐⭐
性能              | ⭐⭐⭐⭐⭐ | ⭐⭐⭐       | ⭐⭐⭐⭐⭐
代码复用          | ✗         | ✓✓           | ✓✓✓
系统一致性        | ✗         | ✓✓           | ✓✓✓
错误追踪          | ✗         | ✓            | ✓✓
推荐指数          | ⭐⭐      | ⭐⭐⭐⭐     | ⭐⭐⭐⭐⭐
```

### 我的推荐：方式 2 (调用 API)

**原因**:
1. 不需要修改现有系统代码
2. 充分利用现有的所有功能
3. 实现简单但功能完整
4. 便于监控和调试
5. 支持远程执行

---

## 💻 完整脚本实现

### 方式 2: 完整的 API 调用脚本

```python
#!/usr/bin/env python3
"""
同步所有本地仓库到最新状态

使用方式:
  python sync_all.py
  python sync_all.py --api http://localhost:8000
  python sync_all.py --wait-timeout 3600
"""

import argparse
import json
import requests
import time
import sys
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path

class RepositorySyncer:
    def __init__(self, api_base: str = "http://localhost:8000"):
        self.api_base = api_base
        self.session = requests.Session()
        
    def get_all_repos(self) -> List[Dict[str, Any]]:
        """获取所有仓库列表"""
        url = f"{self.api_base}/api/repos"
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ 获取仓库列表失败: {e}")
            sys.exit(1)
    
    def trigger_sync(self, repo_names: List[str] = None) -> Dict[str, Any]:
        """触发同步"""
        url = f"{self.api_base}/api/repos/sync"
        body = repo_names or []  # 空列表表示全量同步
        
        try:
            response = self.session.post(
                url,
                json=body,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ 触发同步失败: {e}")
            sys.exit(1)
    
    def get_sync_status(self) -> Dict[str, Dict[str, Any]]:
        """获取同步状态"""
        url = f"{self.api_base}/api/repos/sync/status"
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ 获取同步状态失败: {e}")
            return {}
    
    def print_progress(self, status: Dict, total: int):
        """打印同步进度"""
        done = sum(1 for s in status.values() if s['status'] in ['done', 'failed'])
        syncing = sum(1 for s in status.values() if s['status'] == 'syncing')
        queued = sum(1 for s in status.values() if s['status'] == 'queued')
        
        bar_width = 40
        filled = int(bar_width * done / total)
        bar = '█' * filled + '░' * (bar_width - filled)
        
        print(f"\r[{bar}] {done}/{total} "
              f"(完成: {done}, 同步中: {syncing}, 队列: {queued})", 
              end='', flush=True)
    
    def wait_for_completion(self, timeout: int = 3600, poll_interval: int = 2):
        """等待所有同步任务完成"""
        start_time = time.time()
        
        # 获取初始状态确定总数
        status = self.get_sync_status()
        if not status:
            print("❌ 无同步任务")
            return False
        
        total = len(status)
        print(f"\n📊 开始同步 {total} 个仓库...")
        print(f"⏱️  超时设置: {timeout} 秒")
        print()
        
        while True:
            elapsed = time.time() - start_time
            
            # 检查超时
            if elapsed > timeout:
                print(f"\n⏰ 超时！已等待 {int(elapsed)} 秒")
                self.print_failed_repos(status)
                return False
            
            # 获取状态
            status = self.get_sync_status()
            if not status:
                break
            
            # 显示进度
            self.print_progress(status, total)
            
            # 检查是否完成
            all_done = all(s['status'] in ['done', 'failed'] for s in status.values())
            if all_done:
                print()  # 换行
                break
            
            time.sleep(poll_interval)
        
        return self.print_summary(status)
    
    def print_failed_repos(self, status: Dict):
        """打印失败的仓库"""
        failed = {name: s for name, s in status.items() if s['status'] == 'failed'}
        if failed:
            print("\n❌ 失败的仓库:")
            for name, s in failed.items():
                error = s.get('error', 'Unknown error')
                print(f"  - {name}: {error[:80]}")
    
    def print_summary(self, status: Dict) -> bool:
        """打印总结"""
        done = sum(1 for s in status.values() if s['status'] == 'done')
        failed = sum(1 for s in status.values() if s['status'] == 'failed')
        total = len(status)
        success_rate = (done / total * 100) if total > 0 else 0
        
        print("\n" + "="*60)
        print("📈 同步完成")
        print("="*60)
        print(f"总数:   {total}")
        print(f"成功:   {done} ✓")
        print(f"失败:   {failed} ✗")
        print(f"成功率: {success_rate:.1f}%")
        print("="*60)
        
        self.print_failed_repos(status)
        
        return failed == 0

def main():
    parser = argparse.ArgumentParser(
        description='同步所有本地仓库到最新状态'
    )
    parser.add_argument(
        '--api',
        default='http://localhost:8000',
        help='API 服务器地址 (默认: http://localhost:8000)'
    )
    parser.add_argument(
        '--repos',
        nargs='+',
        help='仅同步指定的仓库 (默认: 全量同步)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=3600,
        help='同步超时时间（秒，默认: 3600）'
    )
    parser.add_argument(
        '--poll-interval',
        type=int,
        default=2,
        help='轮询间隔（秒，默认: 2）'
    )
    parser.add_argument(
        '--no-wait',
        action='store_true',
        help='触发同步后不等待完成'
    )
    
    args = parser.parse_args()
    
    syncer = RepositorySyncer(args.api)
    
    print(f"🔗 连接到: {args.api}")
    
    # 获取仓库列表
    repos = syncer.get_all_repos()
    print(f"📋 找到 {len(repos)} 个仓库")
    
    # 触发同步
    if args.repos:
        print(f"🚀 同步指定的 {len(args.repos)} 个仓库...")
        result = syncer.trigger_sync(args.repos)
    else:
        print(f"🚀 触发全量同步...")
        result = syncer.trigger_sync()
    
    queued = result.get('queued', [])
    print(f"✅ 已队列 {len(queued)} 个仓库")
    
    if args.no_wait:
        print("⏭️  不等待，直接返回")
        return True
    
    # 等待完成
    success = syncer.wait_for_completion(
        timeout=args.timeout,
        poll_interval=args.poll_interval
    )
    
    return success

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
```

---

## 🚀 使用方式

### 基础使用

```bash
# 全量同步所有仓库
python sync_all.py

# 同步指定的仓库
python sync_all.py --repos WeFi-HLB/ai-ocr WeFi-HLB/fps-tp

# 连接到远程 API
python sync_all.py --api http://192.168.1.100:8000

# 设置自定义超时
python sync_all.py --timeout 7200

# 触发后不等待
python sync_all.py --no-wait
```

---

## ⏰ 定时执行

### Cron 定时任务

```bash
# 每天晚上 10 点同步
0 22 * * * cd /path/to/project && python sync_all.py >> /var/log/sync_all.log 2>&1

# 每 6 小时同步一次
0 */6 * * * cd /path/to/project && python sync_all.py --timeout 1800
```

### Systemd Timer

```ini
# /etc/systemd/system/repo-sync.service
[Unit]
Description=Repository Sync Service
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /path/to/sync_all.py
User=git
WorkingDirectory=/path/to/project

# /etc/systemd/system/repo-sync.timer
[Unit]
Description=Repository Sync Timer
Requires=repo-sync.service

[Timer]
OnBootSec=5min
OnUnitActiveSec=6h

[Install]
WantedBy=timers.target
```

启用:
```bash
systemctl enable repo-sync.timer
systemctl start repo-sync.timer
systemctl status repo-sync.timer
```

---

## 📊 输出示例

```
🔗 连接到: http://localhost:8000
📋 找到 42 个仓库
🚀 触发全量同步...
✅ 已队列 42 个仓库

📊 开始同步 42 个仓库...
⏱️  超时设置: 3600 秒

[████████████████░░░░░░░░░░░░░░░░░░░░░░] 18/42 (完成: 18, 同步中: 2, 队列: 22)
```

完成后:
```
============================================================
📈 同步完成
============================================================
总数:   42
成功:   41 ✓
失败:   1 ✗
成功率: 97.6%
============================================================

❌ 失败的仓库:
  - WeFi-HLB/bnbs: git clone --mirror https://github.com/WeFi-HLB/bnbs...
```

---

## 🔄 与现有系统的集成

### 数据库同步

脚本调用 API 时，系统会自动:
- ✓ 更新 `Repository.synced_at`
- ✓ 创建 `SyncJob` 记录
- ✓ 更新 `ContributorStat` 表
- ✓ 应用所有代理和性能优化
- ✓ 前端实时显示同步进度

### 架构图

```
你的脚本
  ↓
POST /api/repos/sync
  ↓
Web API (FastAPI)
  ↓
后台线程执行同步
  ├─ _do_sync()
  ├─ ensure_repository()
  ├─ _update_repo_after_sync()
  └─ _persist_contributors()
  ↓
数据库更新
  ├─ Repository.synced_at
  ├─ SyncJob.status
  └─ ContributorStat
  ↓
前端 UI 实时显示 ← 也会反映最新状态
```

---

## ⚠️ 注意事项

### 1. 认证

如果 API 需要认证:
```python
syncer.session.headers.update({
    'Authorization': f'Bearer {your_token}'
})
```

### 2. 并发限制

系统默认 8 个并发 worker，脚本不会改变这个限制。

### 3. 代理配置

脚本会自动使用系统设置中的代理配置。

### 4. 错误处理

脚本有完整的错误处理，但如果 API 宕机会失败。

### 5. 磁盘空间

确保 `.data/repos/` 有足够空间 (可能需要 100GB+)

---

## 🎯 额外功能建议

### 添加到你的系统

```bash
# 将脚本保存到项目目录
cp sync_all.py /path/to/project/

# 设置可执行权限
chmod +x /path/to/project/sync_all.py

# 加入 git
git add sync_all.py
git commit -m "feat: add bulk repository sync script"
```

### 扩展功能

1. **发送通知** (成功/失败时发邮件)
2. **性能监控** (记录同步耗时)
3. **智能调度** (根据仓库大小分配超时)
4. **备份功能** (定期备份)
5. **对比检查** (检查本地和远程差异)

---

## ✅ 总结

| 问题 | 答案 |
|------|------|
| 可行性 | ✓ 完全可行 |
| 推荐方式 | API 调用 (方式 2) |
| 复杂度 | 中等 (100+ 行) |
| 与现有系统的集成 | ✓ 完美集成 |
| 性能 | ✓ 高效 |
| 错误处理 | ✓ 完整 |
| 易于维护 | ✓ 代码清晰 |

