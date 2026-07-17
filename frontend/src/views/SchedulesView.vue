<template>
  <div>
    <div style="display: flex; justify-content: space-between; margin-bottom: 16px">
      <h2 style="margin: 0">调度管理</h2>
      <el-button type="primary" @click="openDialog()">新增调度</el-button>
    </div>

    <el-card>
      <el-table :data="schedules" v-loading="loading" stripe>
        <el-table-column label="类型" width="80">
          <template #default="{ row }">
            <el-tag :type="typeTag(row.report_type)" size="small">{{ typeLabel(row.report_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="run_time" label="执行时间" width="100" />
        <el-table-column label="执行日" width="100">
          <template #default="{ row }">
            <span v-if="row.report_type === 'weekly'">周{{ weekDay(row.day_of_week) }}</span>
            <span v-else-if="row.report_type === 'monthly'">{{ row.day_of_month }} 日</span>
            <span v-else>每天</span>
          </template>
        </el-table-column>
        <el-table-column prop="timezone" label="时区" min-width="140" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_enabled ? 'success' : 'danger'" size="small">{{ row.is_enabled ? '启用' : '禁用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editId ? '编辑调度' : '新增调度'" width="500">
      <el-form :model="form" label-width="100px">
        <el-form-item label="报告类型">
          <el-select v-model="form.report_type" style="width: 100%">
            <el-option label="日报" value="daily" />
            <el-option label="周报" value="weekly" />
            <el-option label="月报" value="monthly" />
          </el-select>
        </el-form-item>
        <el-form-item label="执行时间">
          <el-time-select v-model="form.run_time" start="00:00" step="00:30" end="23:30" style="width: 100%" />
        </el-form-item>
        <el-form-item v-if="form.report_type === 'weekly'" label="星期">
          <el-select v-model="form.day_of_week" style="width: 100%">
            <el-option v-for="(d, i) in ['一','二','三','四','五','六','日']" :key="i" :label="'周' + d" :value="i" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.report_type === 'monthly'" label="日期">
          <el-input-number v-model="form.day_of_month" :min="1" :max="28" />
        </el-form-item>
        <el-form-item label="时区">
          <el-input v-model="form.timezone" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.is_enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import client from '../api/client'
import { ElMessage, ElMessageBox } from 'element-plus'

const schedules = ref([])
const loading = ref(true)
const dialogVisible = ref(false)
const saving = ref(false)
const editId = ref(null)
const form = reactive({ report_type: 'daily', run_time: '18:30', day_of_week: 0, day_of_month: 1, timezone: 'Asia/Shanghai', is_enabled: true })

function typeLabel(t) { return { daily: '日报', weekly: '周报', monthly: '月报' }[t] || t }
function typeTag(t) { return { daily: '', weekly: 'success', monthly: 'warning' }[t] || 'info' }
function weekDay(d) { return ['一','二','三','四','五','六','日'][d] || d }

async function fetchData() {
  loading.value = true
  const { data } = await client.get('/schedules')
  schedules.value = data
  loading.value = false
}

function openDialog(row) {
  if (row) {
    editId.value = row.id
    Object.assign(form, row)
  } else {
    editId.value = null
    Object.assign(form, { report_type: 'daily', run_time: '18:30', day_of_week: 0, day_of_month: 1, timezone: 'Asia/Shanghai', is_enabled: true })
  }
  dialogVisible.value = true
}

async function handleSave() {
  saving.value = true
  try {
    const payload = { ...form }
    if (payload.report_type !== 'weekly') payload.day_of_week = null
    if (payload.report_type !== 'monthly') payload.day_of_month = null
    if (editId.value) {
      await client.put(`/schedules/${editId.value}`, payload)
    } else {
      await client.post('/schedules', payload)
    }
    dialogVisible.value = false
    ElMessage.success('保存成功')
    await fetchData()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
  saving.value = false
}

async function handleDelete(row) {
  await ElMessageBox.confirm('确定删除该调度？', '确认')
  await client.delete(`/schedules/${row.id}`)
  ElMessage.success('删除成功')
  await fetchData()
}

onMounted(fetchData)
</script>
