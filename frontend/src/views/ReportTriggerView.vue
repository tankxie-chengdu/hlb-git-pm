<template>
  <div>
    <h2>手动触发报告</h2>
    <el-card style="max-width: 640px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="报告类型">
          <el-select v-model="form.report_type" style="width: 100%">
            <el-option label="日报" value="daily" />
            <el-option label="周报" value="weekly" />
            <el-option label="月报" value="monthly" />
          </el-select>
        </el-form-item>
        <el-form-item label="开始日期">
          <el-date-picker v-model="form.start_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="结束日期">
          <el-date-picker v-model="form.end_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" placeholder="不填则等于开始日期" />
        </el-form-item>

        <!-- Repo selector -->
        <el-form-item label="指定仓库">
          <el-select
            v-model="form.repo_names"
            multiple filterable clearable
            placeholder="不选则覆盖全部仓库"
            style="width: 100%"
            :loading="reposLoading"
          >
            <el-option
              v-for="name in filteredRepoOptions"
              :key="name" :label="name" :value="name"
            />
          </el-select>
          <div style="color: #909399; font-size: 12px; margin-top: 4px">留空表示扫描全部仓库</div>
        </el-form-item>

        <!-- skip_fetch toggle -->
        <el-form-item label="更新仓库">
          <el-switch v-model="form.fetch_latest" />
          <span style="margin-left: 8px; color: #606266; font-size: 13px">
            {{ form.fetch_latest ? '触发前先 git fetch 拉取最新提交' : '直接使用本地缓存，不联网' }}
          </span>
        </el-form-item>

        <el-form-item label="仅预览">
          <el-switch v-model="form.dry_run" />
          <span style="margin-left: 8px; color: #909399; font-size: 13px">不发送邮件</span>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="handleTrigger" :loading="triggering">触发报告</el-button>
        </el-form-item>
      </el-form>

      <el-alert v-if="result" :title="resultMessage" :type="result.status === 'running' ? 'info' : 'success'" show-icon style="margin-top: 16px">
        <el-button link type="primary" @click="$router.push(`/reports/${result.id}`)">查看报告</el-button>
      </el-alert>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref, computed, onMounted } from 'vue'
import client from '../api/client'
import { ElMessage } from 'element-plus'

const form = reactive({
  report_type: 'daily',
  start_date: '',
  end_date: '',
  repo_names: [],
  fetch_latest: true,
  dry_run: false,
})
const triggering = ref(false)
const result = ref(null)
const repoOptions = ref([])
const reposLoading = ref(false)

// All repo options directly available (single org)
const filteredRepoOptions = computed(() => repoOptions.value)

const resultMessage = computed(() => {
  if (!result.value) return ''
  return `报告 #${result.value.id} 已提交 (${result.value.status})`
})

async function loadRepoNames() {
  reposLoading.value = true
  try {
    const { data } = await client.get('/reports/repo-names')
    repoOptions.value = data
  } catch {
    // non-critical
  }
  reposLoading.value = false
}

async function handleTrigger() {
  if (!form.start_date) {
    ElMessage.warning('请选择开始日期')
    return
  }
  triggering.value = true
  try {
    const payload = {
      report_type: form.report_type,
      start_date: form.start_date,
      repo_names: form.repo_names,
      skip_fetch: !form.fetch_latest,
      dry_run: form.dry_run,
    }
    if (form.end_date) payload.end_date = form.end_date
    const { data } = await client.post('/reports/trigger', payload)
    result.value = data
    ElMessage.success('报告已提交生成')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '触发失败')
  }
  triggering.value = false
}

onMounted(loadRepoNames)
</script>
