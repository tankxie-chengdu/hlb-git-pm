# 仓库看板 - 展开页面内容分析

## 🎯 整体结构概览

仓库看板 (`ReposView.vue`) 是一个多层次的仓库管理和查看界面，主要分为以下几个区域：

### 1. 顶部操作栏（第3-22行）
```
┌─────────────────────────────────────────────────────────────────┐
│ 仓库看板 | [搜索框]  [56 个仓库]  [刷新列表]  [全量更新/同步未同步仓库] │
└─────────────────────────────────────────────────────────────────┘
```

**功能**：
- 显示标题 "仓库看板"
- 搜索框：支持按仓库名和描述搜索（实时过滤）
- 统计仓库数量
- 刷新按钮：从 GitHub 重新获取元数据
- 全量同步按钮：
  - 优先同步未同步仓库
  - 如果全部已同步，则全量更新所有仓库

---

## 2. 同步进度卡片（第24-48行）

显示全量同步时的实时进度：

```
┌──────────────────────────────────────────────────────────────────┐
│ 同步进度                         3 / 56          [清除]           │
├──────────────────────────────────────────────────────────────────┤
│ ⏳ WeFi-HLB/ai-ocr                    [排队]                     │
│ ✓ WeFi-HLB/fps-tp                     [完成]                     │
│ ✗ WeFi-HLB/bnbs                       [失败]  git clone超时      │
│ ⟳ WeFi-HLB/apigw                     [同步中]                     │
└──────────────────────────────────────────────────────────────────┘
```

**显示内容**：
- 每个同步任务的当前状态
- 进度计数：`完成数 / 总数`
- 状态图标和标签：
  - ⏳ `queued` - 排队中（灰色）
  - ⟳ `syncing` - 同步中（橙色）
  - ✓ `done` - 完成（绿色）
  - ✗ `failed` - 失败（红色）
- 失败原因简要说明

---

## 3. 仓库分组展示（第53-170行）

### 3.1 分组逻辑

仓库按活跃程度分为4组：

```
🔥 今天活跃        (N 个)
├─ WeFi-HLB/ai-ocr
├─ WeFi-HLB/apigw
└─ ...

📈 本周活跃        (N 个)
├─ WeFi-HLB/fps-tp
├─ ...
└─ ...

⚙️ 本月活跃        (N 个)
├─ WeFi-HLB/cocvs-service_app
└─ ...

⏳ 待同步           (N 个)
└─ WeFi-HLB/unknown-repo
```

**活跃程度判断**：
- `today`: 今天有提交
- `this_week`: 本周有提交
- `this_month`: 本月有提交
- `pending`: 未同步过
- 后端从 GitHub API 返回 `activity` 对象，包含：
  - `level`: 活跃级别
  - `label`: 显示文本（如 "待同步"）
  - `days`: 天数（如 "3d"）
  - `color`: 标签颜色

### 3.2 仓库卡片结构

每个仓库显示为一个卡片，包含以下信息：

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│ WeFi-HLB/apigw  [⏳ 待同步 (3d)]  [Java]  [7个分支·333次提交·10位贡献者]
│                                                [重新同步] [复制命令] [展开]│
│                                                                     │
│ 仓库描述: API Gateway Service for WeFi-HLB platform                │
│                                                                     │
│ 最后推送：2026-07-16  ·  默认分支：main                              │
│ 最后同步：2 小时前  ·  ★ 0                                          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**卡片内容分布**：

#### 左侧 - 仓库信息（第69-95行）
```
仓库名称 + 标签行：
├─ 仓库全名 (bold, 15px)
├─ [活跃程度标签]  例: [⏳ 待同步 (3d)]
├─ [语言标签]      例: [Java]
├─ [归档]          (if archived)
├─ [Fork]          (if fork)
└─ [同步状态]      [已同步] / [同步中] / [失败] / [未同步]

描述文本（如果有）：
└─ 灰色小字，最多1行

底部信息行：
├─ 最后推送日期 + 默认分支
├─ 最后同步时间（相对时间）或 "未同步过"
└─ Star数（如果 > 0）
```

#### 右侧 - 统计和按钮（第98-136行）
```
统计信息：
├─ 7 个分支 · 333 次提交 · 10 位贡献者
└─ （仅在 is_cloned=true 时显示）

按钮组：
├─ [重新同步]    - 触发单个仓库同步
├─ [复制命令]    - 复制 git 命令到剪贴板
└─ [展开/收起]   - 切换贡献者详情表格
```

**按钮状态**：
- 同步按钮：
  - 已同步时显示 "重新同步"
  - 未同步时显示 "同步"
  - 同步中时禁用并显示 "同步中"
- 复制命令按钮：始终可用
- 展开按钮：仅在已同步且有贡献者时显示

---

## 4. 展开详情 - 贡献者表格（第139-167行）

点击 **[展开]** 后显示完整的贡献者明细表：

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│ 7 个分支  ·  333 次提交（全分支去重）  ·  10 位贡献者               │
│                                                                     │
│ ┌────────────────────────────────────────────────────────────────┐ │
│ │ 姓名/Git用户名  │ 部门 │ 邮箱 │ 提交数 │ 首次提交 │ 最近提交 │ │
│ ├────────────────────────────────────────────────────────────────┤ │
│ │ 张三 (zhangsan) │ 后端 │ ... │ [42]  │ 2024-03 │ 2026-07  │ │
│ │ 李四 (lisi)    │ 后端 │ ... │ [28]  │ 2024-06 │ 2026-07  │ │
│ │ 王五           │ 前端 │ ... │ [15]  │ 2025-01 │ 2026-06  │ │
│ │ ...            │ ... │ ... │  ...  │  ...   │  ...    │ │
│ └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.1 汇总行（第142-147行）

显示仓库的关键指标：
```
7 个分支  ·  333 次提交（全分支去重）  ·  10 位贡献者
```

### 4.2 贡献者表格（第148-165行）

**表格列**（el-table）：

| 列名 | 显示内容 | 备注 |
|------|--------|------|
| 姓名/Git用户名 | 如果有 `real_name`，显示 "张三 (git_name)"；否则显示 `git_name` 或 `git_email` | min-width: 140px |
| 部门 | 从 `department` 字段取值 | width: 120px |
| 邮箱 | `git_email` | min-width: 180px |
| 提交数 | 数字，显示为蓝色标签 `[42]` | width: 90px, 右对齐 |
| 首次提交 | `first_commit_at`（日期格式） | width: 110px |
| 最近提交 | `last_commit_at`（日期格式） | width: 110px |

**表格特性**：
- `stripe`: true - 行间隔条纹
- `size="small"` - 紧凑显示
- 按提交数排序（后端返回时已排序，最多的在前）
- 可折叠/展开动画（el-collapse-transition）

---

## 5. 数据流向分析

### 5.1 初始加载
```
onMounted()
  └─ fetchData()
      └─ GET /api/repos
          ├─ 获取 repos 列表
          ├─ 每个 repo 包含：
          │  ├─ full_name, description, language, ...
          │  ├─ branch_count, total_commits
          │  ├─ is_cloned, synced_at
          │  ├─ activity { level, label, days, color }
          │  └─ contributors [ { git_name, git_email, commit_count, ... } ]
          └─ 更新 repos.value
```

### 5.2 搜索和分组
```
computed (filtered)
  ├─ 按搜索词过滤 (full_name + description)
  └─ 按 activity.level 分组（前端）

computed (activityGroups)
  ├─ 遍历 filtered
  ├─ 按 activity.level 分类到 4 个分组
  └─ 生成显示所需的分组结构
```

### 5.3 同步流程
```
用户点击 [同步] / [全量更新]
  │
  ├─ syncOne(repo) 或 syncAll()
  │
  ├─ POST /api/repos/sync (body: [repo_full_name] 或 [所有未同步])
  │
  ├─ 响应: { queued: ["WeFi-HLB/apigw", ...] }
  │
  ├─ 创建 syncJobs 对象: { "WeFi-HLB/apigw": { status: "queued", error: null } }
  │
  ├─ startPoll() - 启动轮询
  │
  └─ 每 2 秒调用一次 pollStatus()
      │
      ├─ GET /api/repos/sync/status
      │
      ├─ 返回: { "WeFi-HLB/apigw": { status: "syncing", ... }, ... }
      │
      ├─ 更新 syncJobs 中的状态
      │
      └─ 当所有任务完成（status="done" 或 "failed"）
          ├─ stopPoll()
          └─ fetchData() - 重新获取仓库数据并刷新页面
```

### 5.4 复制命令流程
```
用户点击 [复制命令]
  │
  ├─ copyGitCommand(repo)
  │
  ├─ GET /settings/proxy 获取代理配置
  │
  ├─ 构建 git 命令：
  │  ├─ 基础参数：compression, buffer size, timeout
  │  ├─ 代理参数（根据 URL 协议选择 http.proxy 或 https.proxy）
  │  └─ 操作：clone --mirror (未同步) 或 fetch --all (已同步)
  │
  ├─ navigator.clipboard.writeText(command)
  │
  └─ 显示成功提示
```

---

## 6. 关键计算逻辑

### 6.1 同步状态标签（cloneLabel）
```javascript
function cloneLabel(repo) {
  const j = syncJobs.value[repo.full_name]
  if (j?.status === 'queued') return '排队中'
  if (j?.status === 'syncing') return '同步中'
  if (j?.status === 'done') return '已同步'
  if (j?.status === 'failed') return '同步失败'
  return repo.is_cloned ? '已同步' : '未同步'
}
```

优先级：
1. 如果有进行中的同步任务，显示任务状态
2. 否则，根据 `repo.is_cloned` 显示持久状态

### 6.2 标签颜色（cloneTagType）
```javascript
function cloneTagType(repo) {
  const j = syncJobs.value[repo.full_name]
  if (j?.status === 'failed') return 'danger'        // 红色
  if (j?.status === 'queued' || j?.status === 'syncing')
    return 'warning'  // 橙色
  if (j?.status === 'done') return 'success'         // 绿色
  return repo.is_cloned ? 'success' : 'danger'       // 绿/红
}
```

### 6.3 相对时间格式化（formatSyncTime）
```javascript
function formatSyncTime(isoString) {
  if (!isoString) return '从未同步'

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

  // 7天以上显示完整日期
  return date.toLocaleDateString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}
```

例如：
- ISO: `2026-07-20T03:37:47.313589+00:00` → `2 小时前`
- ISO: `2026-07-17T08:08:14.359486+00:00` → `Jul 17 08:08`

### 6.4 展开状态管理
```javascript
const expanded = ref(new Set())  // 存储展开的仓库名称

function toggle(name) {
  if (expanded.value.has(name))
    expanded.value.delete(name)  // 收起
  else
    expanded.value.add(name)     // 展开
}
```

条件：仅在 `repo.is_cloned && repo.contributors.length` 时显示展开按钮

---

## 7. UI 交互流程图

### 7.1 页面加载
```
┌─────────────────────────────────────┐
│ 页面挂载 (onMounted)                 │
│  ├─ loading = true                  │
│  └─ fetchData() → GET /repos        │
│      └─ repos 数据加载完成          │
├─────────────────────────────────────┤
│ 前端计算处理                         │
│  ├─ filtered (按搜索和活跃度排序)   │
│  ├─ activityGroups (4个分组)        │
│  └─ 页面渲染                         │
└─────────────────────────────────────┘
```

### 7.2 同步交互
```
用户 [点击同步/全量更新]
        ↓
    syncOne/syncAll()
        ↓
  POST /repos/sync
        ↓
响应 { queued: [...] }
        ↓
创建 syncJobs 并展示进度卡片
        ↓
startPoll (每2秒查询一次)
        ↓
    GET /repos/sync/status
        ↓
更新 syncJobs 状态 → UI 实时更新
        ↓
全部完成? → fetchData() 重新加载
```

### 7.3 展开/搜索交互
```
用户输入搜索词
    ↓
search.value 更新
    ↓
computed (filtered) 自动重算
    ↓
computed (activityGroups) 自动重算
    ↓
模板根据新数据 re-render

用户 [点击展开]
    ↓
toggle(repo.full_name)
    ↓
expanded Set 更新
    ↓
el-collapse-transition 动画
    ↓
贡献者表格展开/折叠
```

---

## 8. 性能优化点

1. **虚拟滚动**: 当仓库数量很多时，可考虑使用虚拟滚动（未实现）
2. **轮询精度**: 同步时每2秒轮询一次，相对频繁，但合理
3. **搜索过滤**: 前端过滤，性能良好
4. **贡献者表格**: 大仓库（100+贡献者）可能需要分页（未实现）

---

## 9. 后端返回的数据结构

### GET /api/repos 响应示例
```json
[
  {
    "org_name": "WeFi-HLB",
    "full_name": "WeFi-HLB/apigw",
    "description": "API Gateway Service",
    "language": "Java",
    "default_branch": "main",
    "pushed_at": "2026-07-16T09:30:09Z",
    "stars": 0,
    "is_archived": false,
    "is_fork": false,
    "clone_url": "https://github.com/WeFi-HLB/apigw.git",
    "is_cloned": true,
    "synced_at": "2026-07-20T03:37:47.313589+00:00",
    "is_active": false,
    "activity": {
      "level": "pending",
      "label": "待同步",
      "days": 3,
      "color": "danger"
    },
    "branch_count": 7,
    "total_commits": 333,
    "contributors": [
      {
        "git_name": "zhangsan",
        "git_email": "zhangsan@example.com",
        "real_name": "张三",
        "department": "后端",
        "commit_count": 42,
        "first_commit_at": "2024-03-15",
        "last_commit_at": "2026-07-16"
      },
      ...
    ]
  }
]
```

---

## 10. 总结

| 功能 | 实现方式 | 关键点 |
|------|--------|-------|
| **搜索** | 前端 filter | 支持全名和描述 |
| **分组** | 前端 computed | 按 activity.level 分组 |
| **同步** | POST + 轮询 | 2秒轮询一次，完成后重新加载 |
| **复制命令** | 构建字符串 + clipboard API | 包含代理配置 |
| **展开** | Set 存储状态 | 动画折叠/展开贡献者表 |
| **相对时间** | 客户端计算 | 1分钟/小时/天/日期 |

