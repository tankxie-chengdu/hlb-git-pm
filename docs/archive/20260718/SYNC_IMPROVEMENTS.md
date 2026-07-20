# Git 同步改进方案实施报告

**日期:** 2026-07-18
**状态:** 已实施优先级 1 方案

---

## 问题总结

### 失败仓库
共 7 个仓库因网络超时同步失败：
- WeFi-HLB/cweredis-admin
- WeFi-HLB/um-sso
- WeFi-HLB/fps-tp
- WeFi-HLB/hlbdocs
- WeFi-HLB/bcmss
- WeFi-HLB/bedm
- WeFi-HLB/bnbs_cc

### 失败原因
```
Failed to connect to github.com port 443 after ~29255 ms
```

根本原因：系统级 TCP 连接超时（默认 30 秒），超过中国到 GitHub 的网络延迟

---

## 实施方案

### 优先级 1: SSH 优先策略 ✅ 已实施

**修改文件:** `app/git_service.py`

**实现逻辑:**
```
1. 若 URL 为 HTTPS (GitHub)
   ↓
2. 尝试转换为 SSH URL 并克隆
   ↓ (失败时)
3. 降级到 HTTPS + GitHub App Token
```

**优势:**
- SSH 使用持久连接，更稳定
- SSH 不依赖 HTTP 超时配置
- GitHub SSH 速度通常更快
- 向后兼容 (失败时降级到现有方案)

**代码变更:**
```python
def _https_to_ssh(https_url: str) -> str:
    """Convert HTTPS to SSH for better stability"""
    if https_url.startswith("https://github.com/"):
        path = https_url[len("https://github.com/"):]
        return f"git@github.com:{path}"
    return https_url

def ensure_repository(...):
    # Try SSH first
    if ssh_url != remote_url:
        try:
            _run_git(["clone", "--mirror", ssh_url, str(target)], workspace)
            return target
        except GitError:
            pass  # Fallback to HTTPS

    # HTTPS with token
    _run_git(["clone", "--mirror", remote_url, str(target)], workspace, env=env)
```

---

## 数据库准备

已重置 7 个失败仓库为待同步状态：
```sql
UPDATE repositories
SET is_cloned=0, branch_count=0, total_commits=0
WHERE full_name IN (7 failed repos)
```

已清除本地不完整的克隆目录

---

## 下一步

### 立即
1. ✅ 代码修改已完成
2. 需要通过 Web UI 重新触发同步
   - 访问 http://localhost:8000/repos
   - 点击 "同步未同步仓库"

### 监控指标
- SSH 成功率
- 网络延迟变化
- 克隆时间对比

### 备选方案 (如果 SSH 仍失败)

**方案 B: Shallow Clone**
```python
_run_git(["clone", "--mirror", "--depth=1", url, str(target)])
```

**方案 C: 系统级 TCP 调优**
```bash
# 增加 TCP 重试次数
sysctl -w net.ipv4.tcp_syn_retries=10

# 增加持久连接超时
git config --global http.keepalive 600
```

---

## 效果预测

| 指标 | 当前 | 预期 |
|------|------|------|
| 已同步仓库 | 49/56 (87.5%) | 52-56/56 (93-100%) |
| 总提交数 | 132,139 | 135,000+ |
| 平均克隆时间 | 不适用 | SSH 快 20-30% |
| 网络稳定性 | 不稳定 | 显著改善 |

---

## 风险评估

**低风险:**
- SSH 失败时自动降级到 HTTPS
- 不影响已成功克隆的仓库
- 可随时回滚代码改动

---

## 测试建议

1. 手动测试单个失败仓库
   ```bash
   python -c "
   from app.config import load_config
   from app.git_service import ensure_repository
   config = load_config('config.toml')
   # ... 测试 ensure_repository
   "
   ```

2. Web UI 全量同步测试
   - 监控日志输出
   - 观察同步成功/失败情况
   - 对比克隆时间

3. 生产验证
   - 生成日报验证数据完整性
   - 确认贡献者统计准确

---

**状态:** 等待 Web UI 重新同步以验证效果
