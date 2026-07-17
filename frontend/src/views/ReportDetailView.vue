<template>
  <div>
    <div class="page-header">
      <el-button @click="$router.push('/reports')">返回列表</el-button>
      <div>
        <h2>报告运行详情</h2>
        <div v-if="report" class="subtitle">{{ typeLabel(report.report_type) }} · {{ report.period_start }} ~ {{ report.period_end }}</div>
      </div>
      <div class="header-spacer" />
      <el-tag v-if="report" :type="statusTag(report.status)" size="large">{{ statusLabel(report.status) }}</el-tag>
      <el-button type="warning" @click="handleResend" :loading="resending" v-if="report && report.html">重新发送</el-button>
    </div>

    <div v-if="loading && !report" v-loading="true" class="loading-block" />

    <template v-if="report">
      <section class="overview-band">
        <div class="overview-item">
          <span>总体进度</span>
          <strong>{{ overallProgress }}%</strong>
        </div>
        <div class="overview-item">
          <span>完成步骤</span>
          <strong>{{ completedSteps }}/{{ steps.length }}</strong>
        </div>
        <div class="overview-item">
          <span>提交数</span>
          <strong>{{ report.total_commits }}</strong>
        </div>
        <div class="overview-item">
          <span>运行耗时</span>
          <strong>{{ totalDuration }}</strong>
        </div>
        <div class="overview-item">
          <span>邮件发送</span>
          <strong>{{ report.email_sent_at ? '已发送' : '未发送' }}</strong>
        </div>
      </section>

      <el-progress :percentage="overallProgress" :status="progressStatus" :stroke-width="10" class="overall-progress" />

      <div class="workflow-layout">
        <section class="workflow-panel">
          <div class="section-title">
            <span>生成工作流</span>
            <el-button :icon="Refresh" circle size="small" :loading="refreshing" @click="refreshAll" title="刷新" />
          </div>

          <div v-if="!steps.length" class="empty-workflow">此报告创建于工作流记录功能上线之前，暂无步骤数据。</div>
          <button
            v-for="step in steps"
            :key="step.id"
            class="step-row"
            :class="[{ active: selectedStep?.id === step.id }, `status-${step.status}`]"
            @click="selectedStep = step"
          >
            <span class="step-marker">
              <el-icon v-if="step.status === 'success'"><CircleCheckFilled /></el-icon>
              <el-icon v-else-if="step.status === 'failed'"><CircleCloseFilled /></el-icon>
              <el-icon v-else-if="step.status === 'warning'"><WarningFilled /></el-icon>
              <el-icon v-else-if="step.status === 'skipped'"><RemoveFilled /></el-icon>
              <el-icon v-else-if="step.status === 'running'" class="spinning"><Loading /></el-icon>
              <span v-else class="pending-dot" />
            </span>
            <span class="step-main">
              <span class="step-name">{{ step.sequence }}. {{ step.step_name }}</span>
              <span class="step-meta">
                {{ stepStatusLabel(step.status) }}
                <template v-if="step.duration_ms != null"> · {{ formatDuration(step.duration_ms) }}</template>
              </span>
              <el-progress
                v-if="step.status === 'running'"
                :percentage="step.progress"
                :show-text="false"
                :stroke-width="4"
                class="step-progress"
              />
            </span>
            <span class="step-summary">{{ stepSummary(step) }}</span>
          </button>
        </section>

        <section class="detail-panel">
          <template v-if="selectedStep">
            <div class="section-title">
              <span>{{ selectedStep.step_name }}</span>
              <el-tag :type="stepTag(selectedStep.status)" size="small">{{ stepStatusLabel(selectedStep.status) }}</el-tag>
            </div>

            <el-descriptions :column="2" border size="small" class="step-descriptions">
              <el-descriptions-item label="开始时间">{{ formatTime(selectedStep.started_at) }}</el-descriptions-item>
              <el-descriptions-item label="结束时间">{{ formatTime(selectedStep.finished_at) }}</el-descriptions-item>
              <el-descriptions-item label="耗时">{{ selectedStep.duration_ms == null ? '-' : formatDuration(selectedStep.duration_ms) }}</el-descriptions-item>
              <el-descriptions-item label="进度">{{ selectedStep.progress }}%</el-descriptions-item>
            </el-descriptions>

            <el-alert v-if="selectedStep.error" :title="selectedStep.error" type="error" show-icon :closable="false" class="step-error" />

            <div class="io-block">
              <h4>输入摘要</h4>
              <pre>{{ prettyJson(selectedStep.input_summary) }}</pre>
            </div>
            <div class="io-block">
              <h4>输出摘要</h4>
              <pre>{{ prettyJson(selectedStep.output_summary) }}</pre>
            </div>
          </template>
          <el-empty v-else description="选择一个步骤查看输入和输出" />
        </section>
      </div>

      <section v-if="report.error" class="report-error">
        <el-alert :title="report.error" type="error" show-icon :closable="false" />
      </section>

      <el-card v-if="report.html" class="report-preview">
        <template #header><span>最终报告预览</span></template>
        <div v-html="report.html" class="report-html" />
      </el-card>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import client from '../api/client'
import { ElMessage } from 'element-plus'
import { CircleCheckFilled, CircleCloseFilled, WarningFilled, RemoveFilled, Loading, Refresh } from '@element-plus/icons-vue'

const props = defineProps({ id: [String, Number] })
const route = useRoute()
const report = ref(null)
const steps = ref([])
const selectedStep = ref(null)
const loading = ref(true)
const refreshing = ref(false)
const resending = ref(false)
let timer = null

const terminalStatuses = new Set(['completed', 'sent', 'failed'])
const doneStepStatuses = new Set(['success', 'warning', 'failed', 'skipped'])

const completedSteps = computed(() => steps.value.filter(step => doneStepStatuses.has(step.status)).length)
const overallProgress = computed(() => {
  if (!steps.value.length) return terminalStatuses.has(report.value?.status) ? 100 : 0
  const total = steps.value.reduce((sum, step) => {
    if (doneStepStatuses.has(step.status)) return sum + 100
    if (step.status === 'running') return sum + step.progress
    return sum
  }, 0)
  return Math.round(total / steps.value.length)
})
const progressStatus = computed(() => report.value?.status === 'failed' ? 'exception' : report.value?.status === 'sent' || report.value?.status === 'completed' ? 'success' : '')
const totalDuration = computed(() => {
  const ms = steps.value.reduce((sum, step) => sum + (step.duration_ms || 0), 0)
  return formatDuration(ms)
})

function typeLabel(t) { return { daily: '日报', weekly: '周报', monthly: '月报' }[t] || t }
function statusLabel(s) { return { running: '运行中', completed: '已完成', sent: '已发送', failed: '失败' }[s] || s }
function statusTag(s) { return { running: 'warning', completed: 'success', sent: 'success', failed: 'danger' }[s] || 'info' }
function stepStatusLabel(s) { return { pending: '等待中', running: '执行中', success: '成功', warning: '部分成功', failed: '失败', skipped: '已跳过' }[s] || s }
function stepTag(s) { return { pending: 'info', running: 'warning', success: 'success', warning: 'warning', failed: 'danger', skipped: 'info' }[s] || 'info' }
function formatTime(value) { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-' }
function formatDuration(ms) {
  if (!ms) return '0 秒'
  if (ms < 1000) return `${ms} 毫秒`
  const seconds = Math.round(ms / 1000)
  if (seconds < 60) return `${seconds} 秒`
  return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`
}
function prettyJson(value) { return JSON.stringify(value || {}, null, 2) }
function stepSummary(step) {
  const output = step.output_summary || {}
  if (step.step_key === 'scan_repositories' && output.total_repositories != null) return `${output.completed_repositories ?? output.total_repositories}/${output.total_repositories} 仓库`
  if (step.step_key === 'aggregate_metrics' && output.commits != null) return `${output.commits} 次提交`
  if (step.step_key === 'discover_repositories' && output.discovered_repositories != null) return `${output.discovered_repositories} 个仓库`
  if (step.step_key === 'send_email' && output.recipient_count != null) return `${output.recipient_count} 位收件人`
  return ''
}

async function refreshAll(showLoading = true) {
  if (showLoading) refreshing.value = true
  const reportId = props.id || route.params.id
  try {
    const [reportRes, stepsRes] = await Promise.all([
      client.get(`/reports/${reportId}`),
      client.get(`/reports/${reportId}/steps`),
    ])
    report.value = reportRes.data
    steps.value = stepsRes.data
    if (!selectedStep.value && steps.value.length) {
      selectedStep.value = steps.value.find(step => step.status === 'running') || steps.value[0]
    } else if (selectedStep.value) {
      selectedStep.value = steps.value.find(step => step.id === selectedStep.value.id) || selectedStep.value
    }
    const workflowFinished = !steps.value.length || steps.value.every(step => doneStepStatuses.has(step.status))
    if (terminalStatuses.has(report.value.status) && workflowFinished && timer) {
      clearInterval(timer)
      timer = null
    }
  } catch (e) {
    if (showLoading) ElMessage.error(e.response?.data?.detail || '加载报告工作流失败')
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

async function handleResend() {
  resending.value = true
  try {
    const reportId = props.id || route.params.id
    await client.post(`/reports/${reportId}/resend`)
    ElMessage.success('重新发送成功')
    await refreshAll(false)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '发送失败')
  }
  resending.value = false
}

onMounted(async () => {
  await refreshAll(false)
  const workflowFinished = !steps.value.length || steps.value.every(step => doneStepStatuses.has(step.status))
  if (!terminalStatuses.has(report.value?.status) || !workflowFinished) timer = setInterval(() => refreshAll(false), 2000)
})
onBeforeUnmount(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 18px; }
.page-header h2 { margin: 0; font-size: 22px; }
.subtitle { color: #606266; font-size: 13px; margin-top: 4px; }
.header-spacer { flex: 1; }
.loading-block { height: 360px; }
.overview-band { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); border: 1px solid #e4e7ed; background: #fff; border-radius: 6px; }
.overview-item { padding: 16px 18px; border-right: 1px solid #ebeef5; }
.overview-item:last-child { border-right: 0; }
.overview-item span { display: block; color: #909399; font-size: 12px; margin-bottom: 6px; }
.overview-item strong { font-size: 20px; color: #303133; }
.overall-progress { margin: 14px 0 20px; }
.workflow-layout { display: grid; grid-template-columns: minmax(360px, 0.9fr) minmax(440px, 1.1fr); gap: 16px; align-items: start; }
.workflow-panel, .detail-panel { background: #fff; border: 1px solid #e4e7ed; border-radius: 6px; padding: 16px; min-height: 500px; }
.section-title { display: flex; align-items: center; justify-content: space-between; font-weight: 600; margin-bottom: 14px; }
.step-row { width: 100%; min-height: 72px; display: grid; grid-template-columns: 30px minmax(0, 1fr) auto; gap: 10px; align-items: center; border: 0; border-top: 1px solid #ebeef5; background: transparent; padding: 12px 8px; text-align: left; cursor: pointer; color: inherit; }
.step-row:hover, .step-row.active { background: #f5f7fa; }
.step-row.active { box-shadow: inset 3px 0 #409eff; }
.step-marker { font-size: 22px; display: flex; justify-content: center; color: #909399; }
.status-success .step-marker { color: #67c23a; }
.status-warning .step-marker, .status-running .step-marker { color: #e6a23c; }
.status-failed .step-marker { color: #f56c6c; }
.pending-dot { width: 12px; height: 12px; border: 2px solid #c0c4cc; border-radius: 50%; }
.step-main { min-width: 0; }
.step-name { display: block; font-weight: 600; }
.step-meta { display: block; color: #909399; font-size: 12px; margin-top: 5px; }
.step-summary { color: #606266; font-size: 12px; white-space: nowrap; }
.step-progress { margin-top: 8px; }
.spinning { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.step-descriptions { margin-bottom: 16px; }
.step-error { margin-bottom: 16px; }
.io-block { margin-top: 18px; }
.io-block h4 { margin: 0 0 8px; font-size: 13px; color: #606266; }
.io-block pre { margin: 0; background: #f6f8fa; border: 1px solid #ebeef5; padding: 12px; border-radius: 4px; overflow: auto; max-height: 260px; white-space: pre-wrap; word-break: break-word; font-size: 12px; }
.empty-workflow { color: #909399; padding: 40px 12px; text-align: center; }
.report-error { margin-top: 16px; }
.report-preview { margin-top: 18px; }
.report-html { max-height: 720px; overflow: auto; }
@media (max-width: 1000px) {
  .overview-band { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .overview-item { border-bottom: 1px solid #ebeef5; }
  .workflow-layout { grid-template-columns: 1fr; }
}
</style>
