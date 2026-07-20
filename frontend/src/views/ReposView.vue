<template>
  <div>
    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px">
      <h2 style="margin: 0">仓库看板</h2>
      <el-input
        v-model="search"
        placeholder="搜索仓库名..."
        clearable
        style="width: 240px"
      />
      <div style="flex: 1" />
      <span style="color: #909399; font-size: 13px">{{ filtered.length }} 个仓库</span>
      <el-button :loading="refreshing" @click="refreshFromGitHub">刷新列表</el-button>
      <el-button
        type="primary"
        :loading="syncingAll"
        :disabled="syncingAll"
        @click="syncAll"
      >
        {{ syncingAll ? '同步中...' : hasUnsynced ? '同步未同步仓库' : '全量更新' }}
      </el-button>
    </div>

    <!-- 全量同步进度 -->
    <el-card v-if="Object.keys(syncJobs).length" style="margin-bottom: 16px">
      <template #header>
        <div style="display: flex; align-items: center; gap: 8px">
          <span>同步进度</span>
          <el-tag size="small" type="info">{{ doneCount }} / {{ Object.keys(syncJobs).length }}</el-tag>
          <el-button link size="small" @click="syncJobs = {}" style="margin-left: auto">清除</el-button>
        </div>
      </template>
      <div style="max-height: 200px; overflow-y: auto">
        <div
          v-for="(job, name) in syncJobs"
          :key="name"
          style="display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 13px"
        >
          <el-icon v-if="job.status === 'syncing'" class="is-loading"><Loading /></el-icon>
          <el-icon v-else-if="job.status === 'done'" style="color: #67c23a"><CircleCheck /></el-icon>
          <el-icon v-else-if="job.status === 'failed'" style="color: #f56c6c"><CircleClose /></el-icon>
          <el-icon v-else style="color: #909399"><Clock /></el-icon>
          <span style="flex: 1">{{ name }}</span>
          <el-tag :type="statusTagType(job.status)" size="small">{{ statusLabel(job.status) }}</el-tag>
          <span v-if="job.error" style="color: #f56c6c; font-size: 12px">{{ job.error }}</span>
        </div>
      </div>
    </el-card>


    <div v-if="loading && !repos.length" v-loading="true" style="height: 300px" />

    <!-- 按活跃程度分组展示 -->
    <template v-for="(group, level) in activityGroups" :key="level">
      <template v-if="group.repos.length > 0">
        <div style="display: flex; align-items: center; gap: 8px; margin: 20px 0 12px 0">
          <span style="font-size: 14px; font-weight: 600">{{ group.label }}</span>
          <span style="font-size: 12px; color: #909399">({{ group.repos.length }} 个)</span>
        </div>

        <el-card
          v-for="repo in group.repos"
          :key="repo.full_name"
          style="margin-bottom: 12px"
          shadow="hover"
        >
          <div style="display: flex; align-items: flex-start; gap: 12px">
            <!-- 仓库信息 -->
            <div style="flex: 1; min-width: 0">
              <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap">
                <span style="font-size: 15px; font-weight: 600">{{ repo.full_name }}</span>
                <!-- 活跃程度标签 -->
                <el-tag :type="repo.activity.color" size="small">
                  {{ repo.activity.label }} ({{ repo.activity.days }}d)
                </el-tag>
                <el-tag v-if="repo.language" size="small" type="info">{{ repo.language }}</el-tag>
                <el-tag v-if="repo.is_archived" size="small" type="warning">归档</el-tag>
                <el-tag v-if="repo.is_fork" size="small" type="info">Fork</el-tag>
                <el-tag :type="cloneTagType(repo)" size="small">{{ cloneLabel(repo) }}</el-tag>
              </div>
              <div v-if="repo.description" style="color: #606266; font-size: 13px; margin-top: 4px">
                {{ repo.description }}
              </div>
              <div style="color: #909399; font-size: 12px; margin-top: 4px">
                <div>最后推送：{{ repo.pushed_at ? repo.pushed_at.slice(0, 10) : '-' }} &nbsp;·&nbsp; 默认分支：{{ repo.default_branch }}</div>
                <div style="margin-top: 4px">
                  <span v-if="repo.is_cloned">
                    最后同步：<span style="color: #606266">{{ formatSyncTime(repo.synced_at) }}</span>
                  </span>
                  <span v-else style="color: #c0c4cc; font-style: italic">
                    未同步过
                  </span>
                  <span v-if="repo.stars"> &nbsp;·&nbsp; ★ {{ repo.stars }}</span>
                </div>
              </div>
            </div>

            <!-- 贡献者汇总 -->
            <div style="text-align: right; white-space: nowrap; color: #606266; font-size: 13px">
              <span v-if="repo.is_cloned">
                {{ repo.branch_count }} 个分支 &nbsp;·&nbsp;
                {{ repo.total_commits }} 次提交 &nbsp;·&nbsp;
                {{ repo.contributors.length }} 位贡献者
              </span>
              <span v-else style="color: #c0c4cc">未同步</span>
            </div>

            <!-- 单仓库同步按钮 -->
            <el-button
              size="small"
              :loading="isSyncing(repo.full_name)"
              :disabled="isSyncing(repo.full_name)"
              @click.stop="syncOne(repo)"
            >
              {{ isSyncing(repo.full_name) ? '同步中' : repo.is_cloned ? '重新同步' : '同步' }}
            </el-button>

            <!-- 复制命令按钮 -->
            <el-button
              type="info"
              size="small"
              @click.stop="copyGitCommand(repo)"
            >
              <el-icon style="margin-right: 4px"><DocumentCopy /></el-icon>
              复制命令
            </el-button>

            <!-- 展开按钮 -->
            <el-button
              v-if="repo.is_cloned && repo.contributors.length"
              link
              @click="toggle(repo.full_name)"
              style="padding: 0"
            >
              {{ expanded.has(repo.full_name) ? '收起' : '展开' }}
            </el-button>
          </div>

          <!-- 贡献者明细 -->
          <el-collapse-transition>
            <div v-if="expanded.has(repo.full_name)" style="margin-top: 12px">
              <!-- 汇总行 -->
              <div style="display: flex; gap: 24px; margin-bottom: 10px; font-size: 13px; color: #606266">
                <span><b>{{ repo.branch_count }}</b> 个分支</span>
                <span><b>{{ repo.total_commits }}</b> 次提交（全分支去重）</span>
                <span><b>{{ repo.contributors.length }}</b> 位贡献者</span>
              </div>
              <el-table :data="repo.contributors" size="small" stripe>
                <el-table-column label="姓名 / Git 用户名" min-width="140">
                  <template #default="{ row }">
                    <span v-if="row.real_name" style="font-weight: 500">{{ row.real_name }}</span>
                    <span v-if="row.real_name && row.git_name" style="color: #909399"> ({{ row.git_name }})</span>
                    <span v-if="!row.real_name">{{ row.git_name || row.git_email }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="department" label="部门" width="120" />
                <el-table-column prop="git_email" label="邮箱" min-width="180" />
                <el-table-column prop="commit_count" label="提交数" width="90" align="right">
                  <template #default="{ row }">
                    <el-tag type="primary" size="small">{{ row.commit_count }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="first_commit_at" label="首次提交" width="110" />
                <el-table-column prop="last_commit_at" label="最近提交" width="110" />
              </el-table>
            </div>
          </el-collapse-transition>
        </el-card>
      </template>
    </template>

    <el-empty v-if="!loading && filtered.length === 0" description="暂无仓库数据" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Loading, CircleCheck, CircleClose, Clock, DocumentCopy } from '@element-plus/icons-vue'
import client from '../api/client'
import { ElMessage } from 'element-plus'

const repos = ref([])
const loading = ref(false)
const refreshing = ref(false)
const search = ref('')
const expanded = ref(new Set())
const syncJobs = ref({})
const syncingAll = ref(false)
let pollTimer = null

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  const all = !q ? repos.value : repos.value.filter(r =>
    r.full_name.toLowerCase().includes(q) || r.description?.toLowerCase().includes(q)
  )

  // Group by activity level
  const levels = {
    today: [],
    this_week: [],
    this_month: [],
    pending: [],
    unknown: []
  }

  for (const repo of all) {
    const level = repo.activity?.level || 'unknown'
    if (levels[level]) {
      levels[level].push(repo)
    }
  }

  // Flatten in order
  return [
    ...levels.today,
    ...levels.this_week,
    ...levels.this_month,
    ...levels.pending,
    ...levels.unknown
  ]
})

const activityGroups = computed(() => {
  const groups = {
    today: { label: '🔥 今天活跃', repos: [] },
    this_week: { label: '📈 本周活跃', repos: [] },
    this_month: { label: '⚙️ 本月活跃', repos: [] },
    pending: { label: '⏳ 待同步', repos: [] },
  }

  for (const repo of filtered.value) {
    const level = repo.activity?.level || 'unknown'
    if (groups[level]) {
      groups[level].repos.push(repo)
    }
  }

  return groups
})

const doneCount = computed(() =>
  Object.values(syncJobs.value).filter(j => j.status === 'done' || j.status === 'failed').length
)

const allDone = computed(() => {
  const jobs = Object.values(syncJobs.value)
  return jobs.length > 0 && jobs.every(j => j.status === 'done' || j.status === 'failed')
})

const hasUnsynced = computed(() => repos.value.some(r => !r.is_cloned))

function toggle(name) {
  if (expanded.value.has(name)) expanded.value.delete(name)
  else expanded.value.add(name)
}

function isSyncing(name) {
  const j = syncJobs.value[name]
  return j && (j.status === 'queued' || j.status === 'syncing')
}

function cloneLabel(repo) {
  const j = syncJobs.value[repo.full_name]
  if (j?.status === 'queued') return '排队中'
  if (j?.status === 'syncing') return '同步中'
  if (j?.status === 'done') return '已同步'
  if (j?.status === 'failed') return '同步失败'
  return repo.is_cloned ? '已同步' : '未同步'
}

function cloneTagType(repo) {
  const j = syncJobs.value[repo.full_name]
  if (j?.status === 'failed') return 'danger'
  if (j?.status === 'queued' || j?.status === 'syncing') return 'warning'
  if (j?.status === 'done') return 'success'
  return repo.is_cloned ? 'success' : 'danger'
}

function statusTagType(s) {
  return { queued: 'info', syncing: 'warning', done: 'success', failed: 'danger' }[s] || 'info'
}

function statusLabel(s) {
  return { queued: '排队', syncing: '同步中', done: '完成', failed: '失败' }[s] || s
}

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

    // Show date for older syncs
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return isoString
  }
}

async function fetchData() {
  loading.value = true
  try {
    const { data } = await client.get('/repos')
    repos.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '获取仓库失败')
  }
  loading.value = false
}

async function refreshFromGitHub() {
  refreshing.value = true
  try {
    const { data } = await client.post('/repos/refresh')
    repos.value = data
    ElMessage.success('已从 GitHub 刷新仓库元数据')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '刷新失败')
  }
  refreshing.value = false
}

async function pollStatus() {
  try {
    const { data } = await client.get('/repos/sync/status')
    // Only update status for jobs we're currently tracking; ignore stale server-side entries
    const tracked = Object.keys(syncJobs.value)
    if (tracked.length === 0) return
    const updated = {}
    for (const name of tracked) {
      updated[name] = data[name] ?? syncJobs.value[name]
    }
    syncJobs.value = updated
    if (allDone.value) {
      syncingAll.value = false
      stopPoll()
      await fetchData()
    }
  } catch { /* ignore */ }
}

function startPoll() {
  if (pollTimer) return
  pollTimer = setInterval(pollStatus, 2000)
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function syncOne(repo) {
  try {
    await client.post('/repos/sync', [repo.full_name])
    syncJobs.value = { ...syncJobs.value, [repo.full_name]: { status: 'queued', error: null } }
    startPoll()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '同步失败')
  }
}

async function copyGitCommand(repo) {
  try {
    // Fetch proxy config to include in the command
    const proxyResp = await client.get('/settings/proxy')
    const proxy = proxyResp.data

    let command = 'git'

    // Add performance parameters for stable large transfers
    command += ` -c core.compression=0`
    command += ` -c http.postBuffer=524288000`
    command += ` -c http.lowSpeedLimit=0`
    command += ` -c http.lowSpeedTime=999999`

    // Add proxy options based on URL protocol (only if enabled)
    if (proxy.enabled) {
      // Determine protocol from clone URL
      const isHttps = repo.clone_url?.startsWith('https://')
      const isHttp = repo.clone_url?.startsWith('http://')

      if (isHttps && proxy.https_proxy) {
        // For HTTPS URLs, only set https.proxy
        command += ` -c https.proxy=${proxy.https_proxy}`
      } else if (isHttp && proxy.http_proxy) {
        // For HTTP URLs, only set http.proxy
        command += ` -c http.proxy=${proxy.http_proxy}`
      } else if (!isHttps && !isHttp && proxy.https_proxy) {
        // For SSH URLs, set both (git may use HTTP internally)
        if (proxy.http_proxy) command += ` -c http.proxy=${proxy.http_proxy}`
        if (proxy.https_proxy) command += ` -c https.proxy=${proxy.https_proxy}`
      }
    }

    // Add clone or fetch command based on sync status
    const isClone = !repo.is_cloned
    if (isClone) {
      command += ` clone --mirror ${repo.clone_url} ./.data/repos/${repo.full_name}`
    } else {
      command += ` -C ./.data/repos/${repo.full_name} fetch --all --prune`
    }

    // Copy to clipboard
    await navigator.clipboard.writeText(command)
    ElMessage.success(`已复制${isClone ? '克隆' : '更新'}命令到剪贴板`)
  } catch (e) {
    ElMessage.error('复制失败: ' + (e.message || '未知错误'))
  }
}

async function syncAll() {
  syncingAll.value = true
  try {
    // Prefer unsynced repos first; only fall back to all if everything is already synced
    const all = repos.value.map(r => r.full_name)
    const unsynced = repos.value.filter(r => !r.is_cloned).map(r => r.full_name)
    const body = unsynced.length > 0 ? unsynced : all
    const { data } = await client.post('/repos/sync', body)
    const jobs = {}
    for (const name of data.queued) {
      jobs[name] = { status: 'queued', error: null }
    }
    syncJobs.value = jobs
    const hint = unsynced.length > 0
      ? `已提交 ${data.queued.length} 个未同步仓库`
      : `已提交 ${data.queued.length} 个仓库更新任务`
    ElMessage.success(hint)
    startPoll()
  } catch (e) {
    syncingAll.value = false
    ElMessage.error(e.response?.data?.detail || '全量同步失败')
  }
}

onMounted(() => {
  fetchData()
})
onUnmounted(() => stopPoll())
</script>
