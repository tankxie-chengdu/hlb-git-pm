<template>
  <div class="dashboard">
    <!-- 顶部统计卡片 -->
    <el-row :gutter="16" class="stat-row">
      <el-col :xs="12" :sm="12" :md="6">
        <div class="stat-card" v-loading="loading">
          <div class="stat-icon-wrap" style="--icon-bg: #dbeafe; --icon-color: #2563eb">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 17H7A5 5 0 0 1 7 7h2" /><path d="M15 7h2a5 5 0 1 1 0 10h-2" />
              <line x1="8" y1="12" x2="16" y2="12" />
            </svg>
          </div>
          <div class="stat-text">
            <span class="stat-label">最近 7 天报告</span>
            <span class="stat-value">{{ data.reports_7d }}</span>
            <span class="stat-sub">共 {{ data.total_reports }} 份</span>
          </div>
        </div>
      </el-col>

      <el-col :xs="12" :sm="12" :md="6">
        <div class="stat-card" v-loading="loading">
          <div class="stat-icon-wrap" style="--icon-bg: #d1fae5; --icon-color: #059669">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
          </div>
          <div class="stat-text">
            <span class="stat-label">近 7 天提交</span>
            <span class="stat-value">{{ data.commits_7d }}</span>
            <span class="stat-sub">近 30 天 {{ data.commits_30d }}</span>
          </div>
        </div>
      </el-col>

      <el-col :xs="12" :sm="12" :md="6">
        <div class="stat-card" v-loading="loading">
          <div class="stat-icon-wrap" style="--icon-bg: #ede9fe; --icon-color: #7c3aed">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
              <circle cx="9" cy="7" r="4" />
              <path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" />
            </svg>
          </div>
          <div class="stat-text">
            <span class="stat-label">人员数</span>
            <span class="stat-value">{{ data.member_count }}</span>
            <span class="stat-sub">收件人 {{ data.recipient_count }}</span>
          </div>
        </div>
      </el-col>

      <el-col :xs="12" :sm="12" :md="6">
        <div class="stat-card" v-loading="loading">
          <div class="stat-icon-wrap" style="--icon-bg: #fef3c7; --icon-color: #d97706">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
            </svg>
          </div>
          <div class="stat-text">
            <span class="stat-label">运行中调度</span>
            <span class="stat-value">{{ data.active_schedule_count }}</span>
            <span class="stat-sub sub-success" v-if="data.sent_count > 0">
              已发送 {{ data.sent_count }}
            </span>
            <span class="stat-sub sub-danger" v-if="data.failed_count > 0">
              失败 {{ data.failed_count }}
            </span>
            <span class="stat-sub" v-if="!data.sent_count && !data.failed_count">—</span>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 中部：趋势图 + Top贡献者 -->
    <el-row :gutter="16" class="mid-row">
      <!-- 提交趋势折线图 -->
      <el-col :md="16" :xs="24">
        <div class="panel" v-loading="loading">
          <div class="panel-header">
            <span class="panel-title">
              <svg class="panel-icon" style="color:#10b981" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
              </svg>
              近 30 天每日提交趋势
            </span>
          </div>
          <div class="chart-area">
            <svg v-if="trendPoints.length" :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="none" class="trend-svg">
              <!-- 网格线 -->
              <line v-for="y in gridYs" :key="y" :x1="PAD" :y1="y" :x2="W - PAD" :y2="y"
                stroke="#e5e7eb" stroke-width="1" />
              <!-- 填充区域 -->
              <path :d="areaPath" fill="#10b98118" />
              <!-- 折线 -->
              <path :d="linePath" fill="none" stroke="#10b981" stroke-width="2" stroke-linejoin="round" />
              <!-- 数据点 -->
              <circle v-for="(p, i) in trendPoints" :key="i" :cx="p.x" :cy="p.y" r="3"
                fill="#fff" stroke="#10b981" stroke-width="2" />
              <!-- X 轴标签（只显示每隔 5 天）-->
              <text v-for="(p, i) in trendPoints" :key="'l'+i"
                v-if="i % 5 === 0 || i === trendPoints.length - 1"
                :x="p.x" :y="H - 2" text-anchor="middle" font-size="10" fill="#9ca3af">
                {{ p.label }}
              </text>
            </svg>
            <div v-else class="empty-chart">暂无提交数据</div>
          </div>
        </div>
      </el-col>

      <!-- Top 贡献者 -->
      <el-col :md="8" :xs="24">
        <div class="panel" style="height:100%" v-loading="loading">
          <div class="panel-header">
            <span class="panel-title">
              <svg class="panel-icon" style="color:#8b5cf6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
              Top 贡献者
            </span>
          </div>
          <div class="contributor-list">
            <div v-if="!data.top_contributors?.length" class="empty-chart">暂无贡献者数据</div>
            <div v-else v-for="(c, idx) in data.top_contributors" :key="c.git_email" class="contributor-row">
              <span class="rank-badge" :class="rankClass(idx)">{{ idx + 1 }}</span>
              <div class="contributor-info">
                <span class="contributor-name">{{ c.real_name || c.git_name || c.git_email }}</span>
                <div class="contributor-bar-wrap">
                  <div class="contributor-bar"
                    :style="{ width: barWidth(c.total_commits) + '%', background: barColor(idx) }" />
                </div>
              </div>
              <span class="contributor-count">{{ c.total_commits }}</span>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 底部：最近报告 -->
    <div class="panel" v-loading="loading">
      <div class="panel-header">
        <span class="panel-title">
          <svg class="panel-icon" style="color:#3b82f6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" /><polyline points="10 9 9 9 8 9" />
          </svg>
          最近报告
        </span>
        <el-button link type="primary" size="small" @click="$router.push('/reports')">查看全部</el-button>
      </div>
      <el-table :data="data.recent_reports" stripe size="small" class="report-table">
        <el-table-column prop="report_type" label="类型" width="72">
          <template #default="{ row }">
            <el-tag :type="typeTag(row.report_type)" size="small" effect="plain">
              {{ typeLabel(row.report_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="周期" min-width="160">
          <template #default="{ row }">{{ row.period_start }} ~ {{ row.period_end }}</template>
        </el-table-column>
        <el-table-column prop="total_commits" label="提交数" width="80" align="right" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <span class="status-dot" :class="statusDotClass(row.status)"></span>
            <el-tag :type="statusTag(row.status)" size="small" effect="plain">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" min-width="160">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="" width="60" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="$router.push(`/reports/${row.id}`)">
              查看
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import client from '../api/client'

const loading = ref(true)
const data = ref({
  total_reports: 0, reports_7d: 0, sent_count: 0, failed_count: 0,
  by_type: {}, total_commits: 0, commits_7d: 0, commits_30d: 0,
  member_count: 0, recipient_count: 0, active_schedule_count: 0,
  commit_trend: [], top_contributors: [], recent_reports: []
})

onMounted(async () => {
  try {
    const res = await client.get('/dashboard')
    data.value = res.data
  } catch { /* ignore */ }
  loading.value = false
})

// --- SVG 折线图常量 ---
const W = 600
const H = 120
const PAD = 28

const trendPoints = computed(() => {
  const trend = data.value.commit_trend
  if (!trend || trend.length === 0) return []
  const maxVal = Math.max(...trend.map(d => d.commits), 1)
  return trend.map((d, i) => ({
    x: PAD + (i / Math.max(trend.length - 1, 1)) * (W - PAD * 2),
    y: (H - 20) - (d.commits / maxVal) * (H - 36),
    label: d.date?.slice(5),
    commits: d.commits
  }))
})

const linePath = computed(() => {
  const pts = trendPoints.value
  if (!pts.length) return ''
  return pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')
})

const areaPath = computed(() => {
  const pts = trendPoints.value
  if (!pts.length) return ''
  const bottom = H - 20
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')
  return `${line} L${pts[pts.length - 1].x},${bottom} L${pts[0].x},${bottom} Z`
})

const gridYs = computed(() => {
  return Array.from({ length: 3 }, (_, i) => {
    return (H - 20) - (i / 2) * (H - 36)
  })
})

// --- Top 贡献者进度条 ---
const maxContributorCommits = computed(() => {
  const arr = data.value.top_contributors
  if (!arr?.length) return 1
  return Math.max(...arr.map(c => c.total_commits), 1)
})
function barWidth(commits) {
  return Math.max(4, Math.round((commits / maxContributorCommits.value) * 100))
}
const BAR_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444']
function barColor(idx) { return BAR_COLORS[idx % BAR_COLORS.length] }
function rankClass(idx) {
  return ['rank-gold', 'rank-silver', 'rank-bronze', 'rank-default', 'rank-default'][idx] || 'rank-default'
}

// --- 标签辅助 ---
function typeLabel(t) { return { daily: '日报', weekly: '周报', monthly: '月报', yearly: '年报' }[t] || t }
function typeTag(t) { return { daily: '', weekly: 'success', monthly: 'warning', yearly: 'danger' }[t] || 'info' }
function statusLabel(s) { return { running: '运行中', completed: '已完成', sent: '已发送', failed: '失败' }[s] || s }
function statusTag(s) { return { running: 'warning', completed: 'success', sent: 'success', failed: 'danger' }[s] || 'info' }
function statusDotClass(s) { return { running: 'dot-warning', completed: 'dot-success', sent: 'dot-success', failed: 'dot-danger' }[s] || '' }
function formatTime(t) {
  if (!t) return '-'
  return t.replace('T', ' ').slice(0, 16)
}
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 统计卡片 */
.stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
  background: #fff;
  border-radius: 12px;
  padding: 18px 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,.07), 0 0 0 1px rgba(0,0,0,.04);
  transition: box-shadow .2s;
  margin-bottom: 16px;
}
.stat-card:hover {
  box-shadow: 0 4px 16px rgba(0,0,0,.12), 0 0 0 1px rgba(0,0,0,.05);
}
.stat-icon-wrap {
  flex-shrink: 0;
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: var(--icon-bg);
  color: var(--icon-color);
  display: flex;
  align-items: center;
  justify-content: center;
}
.stat-icon-wrap svg { width: 22px; height: 22px; }
.stat-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.stat-label { font-size: 12px; color: #6b7280; white-space: nowrap; }
.stat-value { font-size: 24px; font-weight: 700; color: #111827; line-height: 1.1; }
.stat-sub { font-size: 11px; color: #9ca3af; }
.sub-success { color: #059669; }
.sub-danger { color: #dc2626; }

/* 面板 */
.panel {
  background: #fff;
  border-radius: 12px;
  padding: 18px 20px;
  box-shadow: 0 1px 4px rgba(0,0,0,.07), 0 0 0 1px rgba(0,0,0,.04);
  margin-bottom: 16px;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.panel-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}
.panel-icon { width: 16px; height: 16px; flex-shrink: 0; }

/* 趋势图 */
.chart-area { height: 130px; position: relative; }
.trend-svg { width: 100%; height: 100%; }
.empty-chart {
  display: flex; align-items: center; justify-content: center;
  height: 100%; font-size: 13px; color: #9ca3af;
}

/* 贡献者 */
.contributor-list { display: flex; flex-direction: column; gap: 10px; }
.contributor-row { display: flex; align-items: center; gap: 10px; }
.rank-badge {
  flex-shrink: 0; width: 20px; height: 20px; border-radius: 50%;
  font-size: 11px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
}
.rank-gold   { background: #fef3c7; color: #d97706; }
.rank-silver { background: #f3f4f6; color: #6b7280; }
.rank-bronze { background: #fef0e8; color: #b45309; }
.rank-default { background: #f3f4f6; color: #6b7280; }
.contributor-info { flex: 1; min-width: 0; }
.contributor-name {
  font-size: 12px; font-weight: 500; color: #374151;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  display: block; margin-bottom: 4px;
}
.contributor-bar-wrap { height: 5px; background: #f3f4f6; border-radius: 99px; overflow: hidden; }
.contributor-bar { height: 100%; border-radius: 99px; transition: width .4s ease; }
.contributor-count { flex-shrink: 0; font-size: 12px; font-weight: 600; color: #6b7280; min-width: 28px; text-align: right; }

/* 状态点 */
.status-dot {
  display: inline-block; width: 7px; height: 7px; border-radius: 50%;
  margin-right: 4px; vertical-align: middle;
}
.dot-success { background: #10b981; }
.dot-warning { background: #f59e0b; animation: pulse 1.4s infinite; }
.dot-danger  { background: #ef4444; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: .4; }
}
</style>
