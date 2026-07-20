# 最近提交 Tab 页面 - 功能说明

## 📋 功能概述

在仓库看板的展开详情中添加了一个新的 Tab 页面，用于查看仓库的最近 10 次提交。

## 🎯 界面布局

### 展开后显示 Tab 页面

```
点击 [展开] 按钮
    ↓
┌────────────────────────────────────────────────────────┐
│ [贡献者]  [最近提交]                                    │
├────────────────────────────────────────────────────────┤
│ 选择的 Tab 内容...                                      │
└────────────────────────────────────────────────────────┘
```

### Tab 1: 贡献者（原始功能）
- 显示仓库的贡献者列表
- 按提交数降序排列
- 显示部门、邮箱、首次提交、最近提交时间

### Tab 2: 最近提交（新增功能）
显示仓库的最近 10 次提交：

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│ 提交号: abc1234d                    分支: [main]   │
│ 修复登录页面显示问题                                 │
│ 李四 <lisi@example.com>                            │
│ 2 小时前                                            │
│                                                     │
├─────────────────────────────────────────────────────┤
│                                                     │
│ 提交号: def5678e                    分支: [dev]    │
│ 添加新的用户界面组件                                 │
│ 张三 <zhangsan@example.com>                         │
│ 1 天前                                              │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## 🔧 技术实现

### 前端改动

#### 1. 界面结构
```vue
<el-tabs type="border-card">
  <!-- Tab 1: 贡献者 -->
  <el-tab-pane label="贡献者">
    <!-- 原来的贡献者表格 -->
  </el-tab-pane>

  <!-- Tab 2: 最近提交 -->
  <el-tab-pane label="最近提交" lazy>
    <!-- 新的提交列表 -->
  </el-tab-pane>
</el-tabs>
```

#### 2. 新增数据和函数
```javascript
// 数据存储
const recentCommits = ref({})  // {repo_name: [commits]}
const recentCommitsLoading = ref({})  // 加载状态

// 函数
function toggle(name) {
  // 展开时自动加载最近提交
  if (!recentCommits.value[name]) {
    loadRecentCommits(name)
  }
}

async function loadRecentCommits(repoFullName) {
  // 调用 API 获取最近提交
}

function formatCommitDate(isoString) {
  // 格式化提交日期为相对时间
}
```

#### 3. 功能特性
- **Lazy Loading**: 使用 `lazy` 属性，只在点击时加载
- **自动加载**: 展开时自动获取最近提交
- **缓存**: 已加载过的数据不会重复获取
- **相对时间**: 使用 "N 分钟前"、"N 小时前" 等格式

### 后端改动

#### API 端点
```
GET /repos/{full_name}/recent-commits?limit=10
```

**参数**:
- `full_name`: 仓库全名，如 "WeFi-HLB/apigw"
- `limit`: 返回提交数，默认 10（可选）

**响应格式**:
```json
{
  "commits": [
    {
      "sha": "abc1234d567890",
      "author_name": "张三",
      "author_email": "zhangsan@example.com",
      "date": "2026-07-20T14:30:45+08:00",
      "subject": "修复登录页面显示问题",
      "branches": ["main", "develop"]
    },
    ...
  ]
}
```

#### 实现细节

1. **验证**: 检查仓库是否存在且已克隆
2. **定位**: 获取本地仓库目录
3. **获取提交**: 运行 `git log --all -10` 获取最近 10 次提交
4. **获取分支**: 对每个提交运行 `git branch -r --contains <sha>` 获取所在分支
5. **清理**: 去除分支名中的 `origin/` 和 `remotes/` 前缀
6. **返回**: 返回结构化的提交数据

**超时设置**:
- Git log 操作: 30 秒
- Git branch 查询: 5 秒

**错误处理**:
- 仓库不存在: 404
- 仓库未克隆: 400
- 本地目录不存在: 400
- 其他错误: 500（返回错误信息）

## 📊 提交数据字段详解

| 字段 | 类型 | 说明 |
|------|------|------|
| sha | string | 提交的完整 SHA，前 8 位在界面显示 |
| author_name | string | 提交作者名 |
| author_email | string | 提交作者邮箱 |
| date | string | ISO8601 格式的提交时间 |
| subject | string | 提交信息（第一行） |
| branches | array | 包含此提交的分支列表（最多 3 个） |

## 🎬 使用流程

1. **打开仓库看板**
   - 导航到仓库看板页面

2. **搜索或找到仓库**
   - 使用搜索框找到目标仓库，如 "WeFi-HLB/apigw"

3. **点击展开按钮**
   - 仓库卡片右侧有 [展开] 按钮
   - 点击后卡片展开显示 Tab 页面

4. **查看贡献者**
   - 默认显示"贡献者"tab
   - 显示仓库的所有贡献者及其提交统计

5. **查看最近提交**
   - 点击"最近提交"tab
   - 系统自动加载该仓库的 10 次最近提交
   - 显示提交信息、作者、分支、时间

## ⚡ 性能优化

1. **Lazy Loading**
   - 只在点击"最近提交"tab 时才加载数据
   - 减少初始页面加载时间

2. **缓存机制**
   - 已加载过的提交数据存储在内存中
   - 重新打开同一仓库不会重复请求

3. **超时保护**
   - Git 操作设置 30 秒超时
   - 防止大型仓库的 git log 操作耗时过长

4. **分支查询优化**
   - 限制显示最多 3 个分支
   - 避免大量分支导致的性能问题

## 🔍 实际场景

### 场景 1: 查看仓库的最近活动
```
1. 打开仓库看板
2. 搜索 "apigw"
3. 点击 [展开]
4. 默认显示贡献者列表
5. 点击 "最近提交" tab
6. 看到最近 10 次提交
   ├─ 8 小时前: "修复登录Bug"
   ├─ 1 天前: "添加新功能"
   ├─ 2 天前: "重构代码"
   └─ ...
```

### 场景 2: 快速了解提交活跃度
```
1. 展开仓库详情
2. 查看最近提交
3. 根据时间戳判断：
   ├─ 都是"刚刚"或"N分钟前" → 正在活跃开发
   ├─ 都是"N天前" → 长期未更新
   └─ 混合时间 → 定期维护
```

### 场景 3: 追踪特定提交
```
1. 在最近提交列表找到目标提交
2. 看到 SHA 值（如 abc1234d）
3. 看到所属分支
4. 看到作者和提交信息
5. 可以在本地运行 git show abc1234d 查看详细信息
```

## 📝 注意事项

### 性能考虑
- 对于大型仓库（100+ 分支），获取分支信息可能较慢
- 建议不要频繁打开/关闭 tab（已有缓存保护）

### 限制
- 默认只显示最近 10 次提交（可通过 API 参数调整）
- 每个提交最多显示 3 个分支名（减少视觉混乱）
- 分支信息可能有延迟（取决于本地仓库状态）

### 未来改进
- 添加提交搜索功能
- 显示提交的详细 diff 信息
- 支持自定义返回提交数量
- 添加提交筛选（按分支、作者等）

## 🔗 相关 API

| 端点 | 说明 |
|------|------|
| `GET /api/repos` | 获取所有仓库（包括贡献者列表） |
| `GET /repos/{full_name}/recent-commits` | 获取特定仓库的最近提交 |
| `POST /api/repos/sync` | 触发仓库同步 |
| `GET /api/repos/sync/status` | 获取同步状态 |

## 💾 提交信息

```
✨ feat: add recent commits tab to repos detail view

Commit: eb4428c
Date: 2026-07-20

Changes:
- Added Tab interface to repository detail view
- Tab 1: Contributors (original functionality)
- Tab 2: Recent Commits (10 most recent commits)
- New API endpoint: GET /repos/{full_name}/recent-commits
- Lazy loading for performance optimization
- Relative time formatting for user-friendly display
```

