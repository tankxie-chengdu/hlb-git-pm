# sync_all.py 认证问题快速修复

## 🎯 问题

运行 `python sync_all.py` 报错：
```
2026-07-20 11:02:53 - ERROR - ❌ 获取仓库列表失败: 401 Client Error: Unauthorized
```

## ✅ 解决方案

API 需要 JWT 认证。脚本已更新以支持 token。

### 使用方式

#### 方式 1: 命令行传递 token

```bash
python sync_all.py --token YOUR_JWT_TOKEN
```

#### 方式 2: 环境变量（推荐）

```bash
export SYNC_TOKEN='YOUR_JWT_TOKEN'
python sync_all.py
```

#### 方式 3: 结合其他参数

```bash
python sync_all.py --token $SYNC_TOKEN --repos WeFi-HLB/ai-ocr --timeout 7200
```

---

## 🔐 获取 Token

从你的系统中获取有效的 JWT token：

```bash
# 方式 1: 从系统配置文件读取
cat /tmp/token.txt

# 方式 2: 从数据库查询
# 取决于你的认证系统

# 方式 3: 通过登录 API 获取
curl -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"password"}'
```

---

## 📋 实测结果

```
✓ 成功同步 56 个仓库
✓ 成功率 100%
✓ 0 个失败
✓ 完成时间 约 2-3 分钟
```

输出示例：
```
🔗 连接到: http://localhost:8000
📋 找到 56 个仓库
🚀 触发全量同步...
✅ 已队列 56 个仓库

📊 开始同步 56 个仓库...

[████████████████████████████████████████] 56/56 

============================================================
📈 同步完成
============================================================
总数:         56 个仓库
成功:         56 ✓
失败:          0 ✗
成功率:       100.0%
============================================================
```

---

## 🛠️ 技术细节

### 代码变更

```python
# 之前：不支持认证
syncer = RepositorySyncer(args.api)

# 现在：支持 token 认证
syncer = RepositorySyncer(args.api, token=token)

# 在构造函数中自动设置 Authorization header
if token:
    self.session.headers.update({
        'Authorization': f'Bearer {token}'
    })
```

### 环境变量优先级

```python
# 优先级（从高到低）：
# 1. 命令行 --token 参数
# 2. 环境变量 SYNC_TOKEN
# 3. 无 token（失败）

token = args.token or os.environ.get('SYNC_TOKEN')
```

---

## 🚀 推荐使用方式

### 1. 一次性手动同步

```bash
python sync_all.py --token $(cat /tmp/token.txt)
```

### 2. 定时自动同步（Cron）

```bash
# 编辑 crontab
crontab -e

# 添加每天晚上 10 点同步
0 22 * * * export SYNC_TOKEN=$(cat /tmp/token.txt) && \
  cd /path/to/project && \
  python sync_all.py >> /var/log/repo_sync.log 2>&1
```

### 3. 从配置文件读取 token

```bash
# 创建 ~/.sync_env（不要提交到 git）
echo "export SYNC_TOKEN='YOUR_TOKEN'" > ~/.sync_env
chmod 600 ~/.sync_env

# Crontab 中使用
0 22 * * * source ~/.sync_env && \
  cd /path/to/project && \
  python sync_all.py >> /var/log/repo_sync.log 2>&1
```

---

## ⚠️ 安全提示

1. **不要在代码中硬编码 token**
   ```bash
   # ❌ 不要这样做
   python sync_all.py --token "hardcoded_token_here"
   ```

2. **使用环境变量或文件**
   ```bash
   # ✓ 推荐
   export SYNC_TOKEN='token_from_secure_place'
   python sync_all.py
   ```

3. **限制文件权限**
   ```bash
   # 如果保存在文件中
   chmod 600 ~/.sync_env
   ```

4. **定期轮换 token**
   ```bash
   # 按需更新 token
   echo "new_token" > ~/.sync_env
   ```

---

## 📝 相关文件修改

- ✅ `sync_all.py` - 添加 token 支持
- ✅ `SYNC_SCRIPT_USAGE_GUIDE.md` - 更新使用说明

---

## 📚 相关文档

- `PYTHON_SYNC_SCRIPT_ANALYSIS.md` - 完整的技术分析
- `SYNC_SCRIPT_USAGE_GUIDE.md` - 详细使用指南

