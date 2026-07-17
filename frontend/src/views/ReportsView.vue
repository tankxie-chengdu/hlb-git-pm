<template>
  <div>
    <h2>报告历史</h2>
    <el-card>
      <el-table :data="reports" v-loading="loading" stripe>
        <el-table-column label="类型" width="80">
          <template #default="{ row }">
            <el-tag :type="typeTag(row.report_type)" size="small">{{ typeLabel(row.report_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="周期" min-width="180">
          <template #default="{ row }">{{ row.period_start }} ~ {{ row.period_end }}</template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column prop="total_commits" label="提交数" width="90" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="$router.push(`/reports/${row.id}`)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top: 16px; text-align: right">
        <el-button :disabled="page <= 1" @click="page--; fetchData()">上一页</el-button>
        <span style="margin: 0 8px">第 {{ page }} 页</span>
        <el-button :disabled="reports.length < pageSize" @click="page++; fetchData()">下一页</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import client from '../api/client'

const reports = ref([])
const loading = ref(true)
const page = ref(1)
const pageSize = 20

function typeLabel(t) { return { daily: '日报', weekly: '周报', monthly: '月报' }[t] || t }
function typeTag(t) { return { daily: '', weekly: 'success', monthly: 'warning' }[t] || 'info' }
function statusLabel(s) { return { running: '运行中', completed: '已完成', sent: '已发送', failed: '失败' }[s] || s }
function statusTag(s) { return { running: 'warning', completed: 'success', sent: 'success', failed: 'danger' }[s] || 'info' }

async function fetchData() {
  loading.value = true
  const { data } = await client.get('/reports', { params: { page: page.value, page_size: pageSize } })
  reports.value = data
  loading.value = false
}

onMounted(fetchData)
</script>
