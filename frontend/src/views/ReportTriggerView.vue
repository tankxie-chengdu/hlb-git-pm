<template>
  <div class="trigger-page">
    <div class="page-heading">
      <div>
        <h2>生成报告</h2>
        <p>选择报告类型，系统会自动对应活跃标签和统计周期。</p>
      </div>
    </div>

    <section class="trigger-surface">
      <div class="step-block">
        <div class="step-index">1</div>
        <div class="step-content">
          <div class="step-title">选择报告类型</div>
          <el-segmented v-model="form.report_type" :options="reportTypeOptions" @change="handleTypeChange" />
          <div class="period-band">
            <span class="period-label">统计周期</span>
            <strong v-if="period.start">{{ period.start }}<template v-if="period.end !== period.start"> 至 {{ period.end }}</template></strong>
            <span v-else>选择类型后自动计算</span>
            <span class="period-rule">{{ periodRule }}</span>
            <span class="activity-label">活跃标签：{{ activityLabel }}</span>
          </div>
        </div>
      </div>

      <div class="step-divider" />

      <div class="step-block">
        <div class="step-index">2</div>
        <div class="step-content">
          <div class="step-title-row">
            <div>
              <div class="step-title">选择项目（可选）</div>
              <div class="step-hint">留空表示生成该标签下的全部项目。</div>
            </div>
            <el-button :icon="Refresh" :loading="activeLoading" @click="loadActiveRepositories">重新筛选</el-button>
          </div>

          <div v-if="activeLoading" class="filtering-state">
            <el-icon class="spinning"><Loading /></el-icon>
            <div>
              <strong>正在筛选活跃项目</strong>
              <span>使用本地 mirror 检查该周期内的提交，不会自动 fetch。</span>
            </div>
          </div>

          <template v-else>
            <div class="filter-summary" v-if="period.start">
              <span>扫描 {{ activeSummary.scanned }} 个项目</span>
              <span class="summary-active">{{ activeRepositories.length }} 个活跃项目</span>
              <span v-if="activeSummary.failed" class="summary-failed">{{ activeSummary.failed }} 个失败</span>
            </div>

            <el-select
              v-model="form.repo_name"
              filterable
              clearable
              placeholder="该标签下的全部项目"
              class="repo-select"
              :disabled="!activeRepositories.length"
            >
              <el-option v-for="repo in activeRepositories" :key="repo.name" :label="repo.name" :value="repo.name">
                <div class="repo-option">
                  <span>{{ repo.name }}</span>
                  <span>{{ repo.commits ? `${repo.commits} 次提交 · ${repo.contributors} 人` : '本周期无提交' }}</span>
                </div>
              </el-option>
            </el-select>

            <el-empty v-if="period.start && !activeRepositories.length" description="该活跃标签下没有可用项目" :image-size="72" />
          </template>
        </div>
      </div>

      <div class="step-divider" />

      <div class="step-block compact-step">
        <div class="step-index">3</div>
        <div class="step-content">
          <div class="step-title">生成方式</div>
          <div class="mode-row">
            <div>
              <strong>{{ form.dry_run ? '仅生成预览' : '生成并发送邮件' }}</strong>
              <span>{{ form.dry_run ? '报告会保存到历史记录，不发送邮件。' : '生成完成后发送给该类型的订阅收件人。' }}</span>
            </div>
            <el-switch v-model="form.dry_run" active-text="仅预览" inactive-text="发送邮件" />
          </div>
        </div>
      </div>

      <div class="action-bar">
        <div class="action-summary">
          {{ typeLabel(form.report_type) }} · {{ activityLabel }} ·
          {{ form.repo_name ? `仅生成 ${form.repo_name}` : `全部 ${activeRepositories.length} 个项目` }}
        </div>
        <el-button
          type="primary"
          size="large"
          :loading="triggering"
          :disabled="activeLoading || !activeRepositories.length"
          @click="handleTrigger"
        >
          生成{{ typeLabel(form.report_type) }}
        </el-button>
      </div>
    </section>

    <el-alert v-if="result" :title="resultMessage" type="success" show-icon :closable="false" class="result-alert">
      <el-button link type="primary" @click="$router.push(`/reports/${result.id}`)">查看生成工作流</el-button>
    </el-alert>
  </div>
</template>

<script setup>
import { reactive, ref, computed, onMounted } from 'vue'
import client from '../api/client'
import { ElMessage } from 'element-plus'
import { Loading, Refresh } from '@element-plus/icons-vue'

const reportTypeOptions = [
  { label: '日报', value: 'daily' },
  { label: '周报', value: 'weekly' },
  { label: '月报', value: 'monthly' },
]
const form = reactive({ report_type: 'daily', repo_name: '', dry_run: true })
const period = reactive({ start: '', end: '' })
const activeRepositories = ref([])
const activeLoading = ref(false)
const activeSummary = reactive({ scanned: 0, failed: 0 })
const snapshotId = ref(null)
const triggering = ref(false)
const result = ref(null)

const periodRule = computed(() => ({
  daily: '昨天',
  weekly: '上一个自然周（周一至周日）',
  monthly: '上一个自然月',
}[form.report_type]))
const activityWindow = computed(() => ({
  daily: 'today',
  weekly: 'this_week',
  monthly: 'this_month',
}[form.report_type]))
const activityLabel = computed(() => ({
  today: '今天活跃',
  this_week: '本周活跃',
  this_month: '本月活跃',
}[activityWindow.value]))
const resultMessage = computed(() => result.value ? `报告 #${result.value.id} 已开始生成` : '')

function typeLabel(type) { return { daily: '日报', weekly: '周报', monthly: '月报' }[type] || type }

async function loadActiveRepositories() {
  activeLoading.value = true
  result.value = null
  form.repo_name = ''
  snapshotId.value = null
  try {
    const { data } = await client.post('/reports/active-repositories', {
      report_type: form.report_type,
      skip_fetch: true,
      activity_window: activityWindow.value,
    }, { timeout: 10 * 60 * 1000 })
    period.start = data.period_start
    period.end = data.period_end
    activeRepositories.value = data.active_repositories
    snapshotId.value = data.snapshot_id
    activeSummary.scanned = data.scanned_repositories
    activeSummary.failed = data.failed_repositories.length
  } catch (error) {
    activeRepositories.value = []
    period.start = ''
    period.end = ''
    ElMessage.error(error.response?.data?.detail || '筛选活跃项目失败')
  } finally {
    activeLoading.value = false
  }
}

function handleTypeChange() {
  loadActiveRepositories()
}

async function handleTrigger() {
  triggering.value = true
  try {
    const { data } = await client.post('/reports/trigger', {
      report_type: form.report_type,
      repo_names: form.repo_name ? [form.repo_name] : [],
      // Active-project filtering already fetched the latest refs.
      skip_fetch: true,
      snapshot_id: snapshotId.value,
      activity_window: activityWindow.value,
      dry_run: form.dry_run,
    })
    result.value = data
    ElMessage.success('报告已开始生成')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '触发失败')
  } finally {
    triggering.value = false
  }
}

onMounted(loadActiveRepositories)
</script>

<style scoped>
.trigger-page { max-width: 920px; margin: 0 auto; }
.page-heading { margin-bottom: 18px; }
.page-heading h2 { margin: 0 0 6px; font-size: 24px; }
.page-heading p { margin: 0; color: #606266; }
.trigger-surface { background: #fff; border: 1px solid #e4e7ed; border-radius: 6px; overflow: hidden; }
.step-block { display: grid; grid-template-columns: 38px minmax(0, 1fr); gap: 14px; padding: 24px; }
.compact-step { padding-bottom: 20px; }
.step-index { width: 30px; height: 30px; border-radius: 50%; background: #0d9488; color: #fff; display: grid; place-items: center; font-weight: 700; }
.step-content { min-width: 0; }
.step-title { font-size: 16px; font-weight: 650; margin-bottom: 12px; }
.step-title-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
.step-title-row .step-title { margin-bottom: 4px; }
.step-hint { color: #909399; font-size: 13px; }
.step-divider { height: 1px; background: #ebeef5; margin-left: 76px; }
.period-band { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-top: 16px; padding: 13px 16px; background: #f5f7fa; border-left: 3px solid #0d9488; }
.period-label { color: #606266; }
.period-rule { margin-left: auto; color: #909399; font-size: 12px; }
.filtering-state { min-height: 126px; display: flex; align-items: center; justify-content: center; gap: 14px; background: #f8fafc; border: 1px dashed #c0c4cc; }
.filtering-state .el-icon { font-size: 28px; color: #0d9488; }
.filtering-state strong, .filtering-state span { display: block; }
.filtering-state span { color: #909399; font-size: 12px; margin-top: 5px; }
.spinning { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.filter-summary { display: flex; gap: 16px; color: #606266; font-size: 13px; margin-bottom: 10px; }
.summary-active { color: #059669; }
.summary-failed { color: #dc2626; }
.repo-select { width: 100%; }
.repo-option { width: 100%; display: flex; justify-content: space-between; gap: 20px; }
.repo-option span:last-child { color: #909399; font-size: 12px; }
.mode-row { display: flex; justify-content: space-between; align-items: center; gap: 24px; }
.mode-row strong, .mode-row span { display: block; }
.mode-row span { color: #909399; font-size: 13px; margin-top: 5px; }
.action-bar { display: flex; justify-content: space-between; align-items: center; padding: 18px 24px; background: #f8fafc; border-top: 1px solid #e4e7ed; }
.action-summary { color: #606266; font-size: 13px; }
.result-alert { margin-top: 16px; }
@media (max-width: 700px) {
  .step-block { grid-template-columns: 32px minmax(0, 1fr); padding: 18px 14px; gap: 10px; }
  .step-divider { margin-left: 56px; }
  .period-rule { margin-left: 0; width: 100%; }
  .step-title-row, .mode-row, .action-bar { align-items: stretch; flex-direction: column; }
}
</style>
