<template>
  <div>
    <div style="display: flex; justify-content: space-between; margin-bottom: 16px">
      <h2 style="margin: 0">收件人管理</h2>
      <el-button type="primary" @click="openDialog()">新增收件人</el-button>
    </div>

    <el-card>
      <el-table :data="recipients" v-loading="loading" stripe>
        <el-table-column prop="email" label="邮箱" min-width="200" />
        <el-table-column prop="name" label="姓名" min-width="100" />
        <el-table-column label="接收日报" width="90" align="center">
          <template #default="{ row }"><el-tag :type="row.receive_daily ? 'success' : 'info'" size="small">{{ row.receive_daily ? '是' : '否' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="接收周报" width="90" align="center">
          <template #default="{ row }"><el-tag :type="row.receive_weekly ? 'success' : 'info'" size="small">{{ row.receive_weekly ? '是' : '否' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="接收月报" width="90" align="center">
          <template #default="{ row }"><el-tag :type="row.receive_monthly ? 'success' : 'info'" size="small">{{ row.receive_monthly ? '是' : '否' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'danger'" size="small">{{ row.is_active ? '启用' : '禁用' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editId ? '编辑收件人' : '新增收件人'" width="500">
      <el-form :model="form" label-width="100px">
        <el-form-item label="邮箱">
          <el-input v-model="form.email" />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="接收日报">
          <el-switch v-model="form.receive_daily" />
        </el-form-item>
        <el-form-item label="接收周报">
          <el-switch v-model="form.receive_weekly" />
        </el-form-item>
        <el-form-item label="接收月报">
          <el-switch v-model="form.receive_monthly" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.is_active" />
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

const recipients = ref([])
const loading = ref(true)
const dialogVisible = ref(false)
const saving = ref(false)
const editId = ref(null)
const form = reactive({ email: '', name: '', receive_daily: true, receive_weekly: true, receive_monthly: true, is_active: true })

async function fetchData() {
  loading.value = true
  const { data } = await client.get('/recipients')
  recipients.value = data
  loading.value = false
}

function openDialog(row) {
  if (row) {
    editId.value = row.id
    Object.assign(form, row)
  } else {
    editId.value = null
    Object.assign(form, { email: '', name: '', receive_daily: true, receive_weekly: true, receive_monthly: true, is_active: true })
  }
  dialogVisible.value = true
}

async function handleSave() {
  saving.value = true
  try {
    if (editId.value) {
      await client.put(`/recipients/${editId.value}`, form)
    } else {
      await client.post('/recipients', form)
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
  await ElMessageBox.confirm(`确定删除 ${row.name || row.email}？`, '确认')
  await client.delete(`/recipients/${row.id}`)
  ElMessage.success('删除成功')
  await fetchData()
}

onMounted(fetchData)
</script>
