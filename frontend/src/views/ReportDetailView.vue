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
          <strong>{{ report.status === 'sent' ? '已发送' : '未发送' }}</strong>
          <small v-if="report.status === 'sent' && report.email_recipients?.length" class="overview-recipients">
            发送至：{{ report.email_recipients.join('、') }}
          </small>
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
                {{ stepStatusLabel(step.status, step) }}
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
              <el-tag :type="stepTag(selectedStep.status)" size="small">{{ stepStatusLabel(selectedStep.status, selectedStep) }}</el-tag>
            </div>

            <el-descriptions :column="2" border size="small" class="step-descriptions">
              <el-descriptions-item label="开始时间">{{ formatTime(selectedStep.started_at) }}</el-descriptions-item>
              <el-descriptions-item label="结束时间">{{ formatTime(selectedStep.finished_at) }}</el-descriptions-item>
              <el-descriptions-item label="耗时">{{ selectedStep.duration_ms == null ? '-' : formatDuration(selectedStep.duration_ms) }}</el-descriptions-item>
              <el-descriptions-item label="进度">{{ selectedStep.progress }}%</el-descriptions-item>
            </el-descriptions>

            <el-alert v-if="selectedStep.error" :title="selectedStep.error" type="error" show-icon :closable="false" class="step-error" />

            <div class="process-block">
              <h4>处理过程</h4>
              <p>{{ processSummary(selectedStep) }}</p>
            </div>

            <div v-if="repositoryDetails(selectedStep).length" class="structured-block">
              <h4>仓库处理明细</h4>
              <el-table :data="repositoryDetails(selectedStep)" size="small" border max-height="300">
                <el-table-column prop="name" label="仓库" min-width="180" />
                <el-table-column prop="status" label="状态" width="76" />
                <el-table-column prop="commits" label="提交" width="70" align="right" />
                <el-table-column prop="contributors" label="贡献者" width="76" align="right" />
                <el-table-column prop="files_changed" label="文件" width="70" align="right" />
                <el-table-column prop="additions" label="新增" width="82" align="right" />
                <el-table-column prop="deletions" label="删除" width="82" align="right" />
                <el-table-column prop="error" label="错误" min-width="180" show-overflow-tooltip />
              </el-table>
            </div>

            <div v-if="topContributors(selectedStep).length" class="structured-block">
              <h4>贡献者聚合</h4>
              <el-table :data="topContributors(selectedStep)" size="small" border>
                <el-table-column prop="name" label="成员" min-width="140">
                  <template #default="{ row }"><span :class="{ 'outsourced-name': isOutsourced(row) }">{{ row.name }}</span></template>
                </el-table-column>
                <el-table-column prop="commits" label="提交" width="76" align="right" />
                <el-table-column prop="repositories" label="仓库" width="76" align="right" />
                <el-table-column prop="additions" label="新增" width="82" align="right" />
                <el-table-column prop="deletions" label="删除" width="82" align="right" />
              </el-table>
            </div>

            <div v-if="selectedStep.step_key === 'ai_analysis' && aiPrompt(selectedStep)" class="prompt-block">
              <h4>AI 使用的提示词</h4>
              <p class="prompt-hint">{{ aiPromptHint(selectedStep) }}</p>
              <div v-if="promptSources(selectedStep).length" class="source-overview">
                <div class="source-overview-item">
                  <span>上下文来源</span>
                  <strong>{{ promptSources(selectedStep).length }} 类</strong>
                </div>
                <div class="source-overview-item">
                  <span>仓库数据</span>
                  <strong>{{ promptSourceRecords(selectedStep, 'repository_activity') }} 个</strong>
                </div>
                <div class="source-overview-item">
                  <span>提交明细</span>
                  <strong>{{ promptSourceRecords(selectedStep, 'commit_details', 'included_records') }} 条</strong>
                </div>
                <div class="source-overview-item">
                  <span>省略提交</span>
                  <strong :class="{ 'is-warning': promptSourceRecords(selectedStep, 'commit_details', 'omitted_records') > 0 }">{{ promptSourceRecords(selectedStep, 'commit_details', 'omitted_records') }} 条</strong>
                </div>
              </div>
              <div v-if="promptSources(selectedStep).length" class="source-overview source-overview-secondary">
                <div class="source-overview-item">
                  <span>用户提示词</span>
                  <strong>{{ formatCount(selectedStep.input_summary.prompt_characters) }} 字符</strong>
                </div>
                <div class="source-overview-item source-overview-wide">
                  <span>数据处理口径</span>
                  <strong>按报告周期聚合，提交明细最多 {{ formatCount(selectedStep.input_summary.max_commits) }} 条</strong>
                </div>
              </div>
              <div v-if="promptSources(selectedStep).length" class="source-table-block">
                <h5>提示词数据来源</h5>
                <el-table :data="promptSources(selectedStep)" size="small" border>
                  <el-table-column prop="label" label="来源" width="116" />
                  <el-table-column prop="origin" label="生成方式" min-width="220" show-overflow-tooltip />
                  <el-table-column label="记录写入" width="116" align="right">
                    <template #default="{ row }">{{ row.included_records }}/{{ row.records }}</template>
                  </el-table-column>
                  <el-table-column label="字符数" width="92" align="right">
                    <template #default="{ row }">{{ formatCount(row.characters) }}</template>
                  </el-table-column>
                  <el-table-column label="上下文占比" width="150">
                    <template #default="{ row }">
                      <el-progress :percentage="sourceShare(row, selectedStep)" :stroke-width="8" />
                    </template>
                  </el-table-column>
                  <el-table-column label="状态" width="88">
                    <template #default="{ row }">
                      <el-tag :type="sourceTag(row)" size="small">{{ sourceStatus(row) }}</el-tag>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
              <div v-for="source in promptSources(selectedStep)" :key="source.key" class="source-detail-block">
                <template v-if="sourceMetricEntries(source).length">
                  <h5>{{ source.label }}明细</h5>
                  <div class="source-facts">
                    <div v-for="item in sourceMetricEntries(source)" :key="item.label" class="source-fact">
                      <span>{{ item.label }}</span>
                      <strong>{{ item.value }}</strong>
                    </div>
                  </div>
                </template>
                <template v-if="source.key === 'repository_activity' && sourceRepositories(source).length">
                  <h5>仓库活动写入内容</h5>
                  <el-table :data="sourceRepositories(source)" size="small" border max-height="260">
                    <el-table-column prop="name" label="仓库" min-width="170" />
                    <el-table-column prop="branch" label="分支" min-width="110" />
                    <el-table-column prop="status" label="状态" width="76" />
                    <el-table-column prop="commits" label="提交" width="70" align="right" />
                    <el-table-column prop="contributors" label="贡献者" width="76" align="right" />
                    <el-table-column prop="files_changed" label="文件" width="70" align="right" />
                    <el-table-column prop="additions" label="新增" width="76" align="right" />
                    <el-table-column prop="deletions" label="删除" width="76" align="right" />
                  </el-table>
                </template>
                <template v-if="source.key === 'project_contributions' && sourceProjects(source).length">
                  <h5>项目维度写入内容</h5>
                  <el-table :data="sourceProjects(source)" size="small" border max-height="300">
                    <el-table-column prop="name" label="项目" min-width="180" />
                    <el-table-column prop="status" label="状态" width="76" />
                    <el-table-column prop="commit_count" label="提交" width="70" align="right" />
                    <el-table-column prop="contributor_count" label="人员" width="70" align="right" />
                    <el-table-column prop="files_changed" label="文件" width="70" align="right" />
                    <el-table-column prop="additions" label="新增" width="78" align="right" />
                    <el-table-column prop="deletions" label="删除" width="78" align="right" />
                  </el-table>
                </template>
                <template v-if="source.key === 'person_contributions' && sourcePeople(source).length">
                  <h5>人员维度写入内容</h5>
                  <el-table :data="sourcePeople(source)" size="small" border max-height="340">
                    <el-table-column prop="name" label="人员" min-width="180">
                      <template #default="{ row }"><span :class="{ 'outsourced-name': isOutsourced(row) }">{{ row.name }}</span></template>
                    </el-table-column>
                    <el-table-column prop="department" label="部门" width="100" />
                    <el-table-column prop="commit_count" label="提交" width="70" align="right" />
                    <el-table-column prop="active_days" label="活跃天" width="76" align="right" />
                    <el-table-column prop="repository_count" label="项目" width="70" align="right" />
                    <el-table-column prop="files_changed" label="文件" width="70" align="right" />
                    <el-table-column prop="additions" label="新增" width="78" align="right" />
                    <el-table-column prop="deletions" label="删除" width="78" align="right" />
                  </el-table>
                </template>
                <template v-if="source.key === 'daily_trend' && sourceTrend(source).length">
                  <h5>按日趋势写入内容</h5>
                  <el-table :data="sourceTrend(source)" size="small" border>
                    <el-table-column prop="date" label="日期" width="120" />
                    <el-table-column prop="commits" label="提交" width="80" align="right" />
                    <el-table-column prop="repositories" label="仓库" width="80" align="right" />
                    <el-table-column prop="contributors" label="贡献者" width="90" align="right" />
                  </el-table>
                </template>
                <template v-if="source.key === 'commit_details' && sourceRepositories(source).length">
                  <h5>提交明细截取情况</h5>
                  <el-table :data="sourceRepositories(source)" size="small" border>
                    <el-table-column prop="name" label="仓库" min-width="170" />
                    <el-table-column prop="branch" label="分支" min-width="110" />
                    <el-table-column prop="total_commits" label="原始提交" width="92" align="right" />
                    <el-table-column prop="included_commits" label="写入提示词" width="104" align="right" />
                    <el-table-column prop="omitted_commits" label="省略" width="76" align="right" />
                    <el-table-column prop="error" label="错误" min-width="160" show-overflow-tooltip />
                  </el-table>
                </template>
              </div>
              <div v-if="projectAnalyses(selectedStep).length" class="source-detail-block">
                <h5>逐项目结构化分析结果</h5>
                <el-table :data="projectAnalyses(selectedStep)" size="small" border max-height="420">
                  <el-table-column prop="repository" label="项目" min-width="180" />
                  <el-table-column label="质量信号" width="92">
                    <template #default="{ row }">
                      <el-tag :type="qualityTag(row.quality_level)" size="small">{{ row.quality_level }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="work_summary" label="工作内容" min-width="260" />
                  <el-table-column prop="quality_signal" label="客观分析" min-width="280" />
                  <el-table-column prop="confidence" label="置信度" width="72" align="center" />
                </el-table>
              </div>
              <div class="prompt-part">
                <div class="prompt-label">System · 系统提示词</div>
                <pre>{{ aiSystemPrompt(selectedStep) }}</pre>
              </div>
              <div class="prompt-part">
                <div class="prompt-label">User · 用户提示词（包含统计上下文）</div>
                <pre>{{ aiPrompt(selectedStep) }}</pre>
              </div>
            </div>

            <div class="io-block">
              <h4>输入数据（JSON）</h4>
              <pre>{{ prettyJson(selectedStep.input_summary) }}</pre>
            </div>
            <div class="io-block">
              <h4>输出数据（JSON）</h4>
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

function typeLabel(t) { return { daily: '日报', weekly: '周报', monthly: '月报', yearly: '年报' }[t] || t }
function statusLabel(s) { return { running: '运行中', completed: '已完成', sent: '已发送', failed: '失败' }[s] || s }
function statusTag(s) { return { running: 'warning', completed: 'success', sent: 'success', failed: 'danger' }[s] || 'info' }
function isOutsourced(row) {
  if (typeof row?.is_outsourced === 'boolean') return row.is_outsourced
  return String(row?.name || '').trim().toLowerCase().startsWith('v_')
}
function stepStatusLabel(s, step) {
  if (s === 'skipped' && step?.output_summary?.operation === 'reuse_snapshot') return '已复用快照'
  return { pending: '等待中', running: '执行中', success: '成功', warning: '部分成功', failed: '失败', skipped: '已跳过' }[s] || s
}
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
function processSummary(step) {
  return step?.output_summary?.process || '该步骤已执行，暂无处理说明。'
}
function repositoryDetails(step) {
  return Array.isArray(step?.output_summary?.repository_details) ? step.output_summary.repository_details : []
}
function topContributors(step) {
  return Array.isArray(step?.output_summary?.top_contributors) ? step.output_summary.top_contributors : []
}
function aiSystemPrompt(step) { return step?.input_summary?.system_prompt || '' }
function aiPrompt(step) { return step?.input_summary?.user_prompt || '' }
function aiPromptHint(step) {
  return step?.input_summary?.enabled
    ? '以下内容就是本次请求发送给模型的提示词。系统提示词和用户提示词分别对应 API 请求中的两个 message。'
    : '以下内容是按当前报告数据生成的提示词预览；AI 未启用或缺少 API Key 时不会发送请求。'
}
function promptSources(step) { return Array.isArray(step?.input_summary?.prompt_sources) ? step.input_summary.prompt_sources : [] }
function promptSource(step, key) { return promptSources(step).find(source => source.key === key) || {} }
function promptSourceRecords(step, key, field = 'records') { return promptSource(step, key)[field] || 0 }
function formatCount(value) { return Number(value || 0).toLocaleString('zh-CN') }
function sourceShare(source, step) {
  const total = promptSources(step).reduce((sum, item) => sum + (item.characters || 0), 0)
  return total ? Math.round((source.characters || 0) * 100 / total) : 0
}
function sourceStatus(source) { return source.omitted_records > 0 ? '已截断' : '完整' }
function sourceTag(source) { return source.omitted_records > 0 ? 'warning' : 'success' }
function sourceDetails(source) { return source?.details || {} }
function sourceRepositories(source) { return Array.isArray(sourceDetails(source).repositories) ? sourceDetails(source).repositories : [] }
function sourceProjects(source) { return Array.isArray(sourceDetails(source).projects) ? sourceDetails(source).projects : [] }
function sourcePeople(source) { return Array.isArray(sourceDetails(source).people) ? sourceDetails(source).people : [] }
function sourceTrend(source) { return Array.isArray(sourceDetails(source).trend) ? sourceDetails(source).trend : [] }
function projectAnalyses(step) { return Array.isArray(step?.output_summary?.project_analyses) ? step.output_summary.project_analyses : [] }
function qualityTag(level) { return { '稳定': 'success', '需关注': 'warning', '证据不足': 'info' }[level] || 'info' }
function sourceMetricEntries(source) {
  const details = sourceDetails(source)
  if (source.key === 'scope') {
    return Object.entries(details).map(([key, value]) => ({
      label: { report_type: '报告类型', report_date: '日报日期', period_start: '开始日期', period_end: '结束日期' }[key] || key,
      value,
    }))
  }
  if (source.key === 'metrics') {
    return [
      ['scanned_repositories', '扫描仓库'], ['active_repositories', '活跃仓库'], ['empty_repositories', '无提交仓库'],
      ['failed_repositories', '扫描失败'], ['contributors', '贡献者'], ['commits', '总提交'], ['files_changed', '文件变更'],
      ['additions', '新增行'], ['deletions', '删除行'],
    ].map(([key, label]) => ({ label, value: formatCount(details[key]) }))
  }
  return []
}
function stepSummary(step) {
  const output = step.output_summary || {}
  if (step.step_key === 'scan_repositories' && output.total_repositories != null) return `${output.completed_repositories ?? output.total_repositories}/${output.total_repositories} 仓库${output.operation === 'reuse_snapshot' ? '（复用快照）' : ''}`
  if (step.step_key === 'aggregate_metrics' && output.commits != null) return `${output.commits} 次提交`
  if (step.step_key === 'discover_repositories' && output.selected_repositories != null) return `${output.selected_repositories.length} 个仓库${output.operation === 'reuse_snapshot' ? '（复用快照）' : ''}`
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
.overview-recipients { display: block; margin-top: 5px; color: #606266; font-size: 11px; line-height: 1.4; overflow-wrap: anywhere; }
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
.process-block { margin-top: 16px; padding: 12px 14px; background: #f0fdfa; border-left: 3px solid #0d9488; }
.process-block h4, .structured-block h4 { margin: 0 0 8px; font-size: 13px; color: #475467; }
.process-block p { margin: 0; color: #344054; line-height: 1.6; font-size: 13px; }
.structured-block { margin-top: 18px; }
.structured-block :deep(.el-table) { width: 100%; }
.outsourced-name { color: #2563eb; font-weight: 600; }
.prompt-block { margin-top: 18px; padding: 14px; background: #fffaf0; border: 1px solid #f3d19e; border-radius: 4px; }
.prompt-block h4 { margin: 0 0 6px; font-size: 13px; color: #7c4a03; }
.prompt-hint { margin: 0 0 12px; color: #8a6d3b; line-height: 1.5; font-size: 12px; }
.prompt-part + .prompt-part { margin-top: 12px; }
.prompt-label { margin-bottom: 6px; color: #606266; font-size: 12px; font-weight: 600; }
.prompt-part pre { margin: 0; background: #fff; border: 1px solid #ead7b0; padding: 12px; border-radius: 4px; overflow: auto; max-height: 360px; white-space: pre-wrap; word-break: break-word; font-size: 12px; line-height: 1.55; }
.source-overview { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border: 1px solid #ead7b0; background: #fff; margin: 14px 0; }
.source-overview-item { padding: 10px 12px; border-right: 1px solid #ead7b0; }
.source-overview-item:last-child { border-right: 0; }
.source-overview-item span { display: block; color: #8a6d3b; font-size: 11px; margin-bottom: 4px; }
.source-overview-item strong { color: #7c4a03; font-size: 17px; }
.source-overview-item strong.is-warning { color: #d97706; }
.source-overview-secondary { grid-template-columns: 1fr 3fr; margin-top: -14px; border-top: 0; }
.source-overview-secondary .source-overview-item { border-top: 1px solid #ead7b0; }
.source-overview-wide { grid-column: span 1; }
.source-table-block, .source-detail-block { margin-top: 14px; }
.source-table-block h5, .source-detail-block h5 { margin: 0 0 8px; color: #7c4a03; font-size: 12px; }
.source-table-block :deep(.el-table), .source-detail-block :deep(.el-table) { width: 100%; }
.source-table-block :deep(.el-progress__text) { font-size: 11px !important; min-width: 34px; }
.source-facts { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); border: 1px solid #ead7b0; background: #fff; }
.source-fact { padding: 8px 10px; border-right: 1px solid #ead7b0; border-bottom: 1px solid #ead7b0; }
.source-fact span { display: block; color: #909399; font-size: 11px; margin-bottom: 3px; }
.source-fact strong { color: #606266; font-size: 13px; }
.io-block { margin-top: 18px; }
.io-block h4 { margin: 0 0 8px; font-size: 13px; color: #606266; }
.io-block pre { margin: 0; background: #f6f8fa; border: 1px solid #ebeef5; padding: 12px; border-radius: 4px; overflow: auto; max-height: 260px; white-space: pre-wrap; word-break: break-word; font-size: 12px; }
.empty-workflow { color: #909399; padding: 40px 12px; text-align: center; }
.report-error { margin-top: 16px; }
.report-preview { margin-top: 18px; }
.report-html { max-height: 720px; overflow: auto; }
@media (max-width: 1000px) {
  .overview-band { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .source-overview { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .source-overview-item:nth-child(2) { border-right: 0; }
  .source-facts { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .overview-item { border-bottom: 1px solid #ebeef5; }
  .workflow-layout { grid-template-columns: 1fr; }
}
</style>
