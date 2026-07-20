<template>
  <div>
    <h2 style="margin-bottom: 16px">人员管理</h2>

    <el-tabs v-model="activeTab">
      <!-- ── Tab 1: 贡献者总览 ─────────────────────────────────── -->
      <el-tab-pane label="贡献者总览" name="contributors">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px">
          <el-input v-model="contribSearch" placeholder="搜索姓名 / 邮箱..." clearable style="width: 260px" />
          <span style="color: #909399; font-size: 13px">{{ filteredContribs.length }} 人</span>
          <div style="flex: 1" />
          <el-button :loading="contribLoading" @click="fetchContributors">刷新</el-button>
        </div>

        <el-alert
          v-if="!contribLoading && contributors.length === 0"
          title="暂无数据，请先在「仓库看板」执行同步"
          type="info"
          show-icon
          :closable="false"
          style="margin-bottom: 12px"
        />

        <el-card v-loading="contribLoading">
          <el-table :data="filteredContribs" :row-class-name="activityRowClass" stripe>
            <!-- 姓名 / git 账号 -->
            <el-table-column label="姓名 / Git 账号" min-width="160">
              <template #default="{ row }">
                <span v-if="row.real_name" style="font-weight: 500">{{ row.real_name }}</span>
                <span v-if="row.real_name" style="color: #909399; font-size: 12px"> ({{ row.git_name || row.git_email }})</span>
                <span v-if="!row.real_name" style="color: #606266">{{ row.git_name || row.git_email }}</span>
                <el-tag v-if="row.is_outsourced" size="small" type="primary" class="identity-tag">外包</el-tag>
                <el-tag v-if="!row.member_id" size="small" type="warning" style="margin-left: 6px">未认领</el-tag>
              </template>
            </el-table-column>

            <el-table-column prop="department" label="部门" width="120" />
            <el-table-column prop="git_email" label="邮箱" min-width="180" />

            <!-- 提交总数 -->
            <el-table-column label="提交总数" width="100" align="right">
              <template #default="{ row }">
                <el-tag type="primary" size="small">{{ row.total_commits }}</el-tag>
              </template>
            </el-table-column>

            <!-- 参与仓库 -->
            <el-table-column label="参与仓库" min-width="220">
              <template #default="{ row }">
                <div style="display: flex; flex-wrap: wrap; gap: 4px">
                  <el-tooltip
                    v-for="r in row.repos"
                    :key="r.repo_name"
                    :content="`${r.commit_count} 次提交  ${r.first_commit_at} ~ ${r.last_commit_at}`"
                    placement="top"
                  >
                    <el-tag size="small" type="info" style="cursor: default">
                      {{ repoShortName(r.repo_name) }}
                    </el-tag>
                  </el-tooltip>
                </div>
              </template>
            </el-table-column>

            <el-table-column label="最近提交" width="164">
              <template #default="{ row }">
                <span>{{ displayLastCommit(row.last_commit_at) }}</span>
                <el-tag v-if="isStale(row.last_commit_at)" size="small" type="info" class="stale-tag">
                  {{ row.last_commit_at ? '超过六个月' : '无提交记录' }}
                </el-tag>
              </template>
            </el-table-column>

            <!-- 操作 -->
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-if="!row.member_id"
                  link type="primary" size="small"
                  @click="openClaimDialog(row)"
                >认领</el-button>
                <el-button
                  v-else
                  link type="primary" size="small"
                  @click="openEditFromContrib(row)"
                >编辑</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- ── Tab 2: 人员信息 CRUD ───────────────────────────────── -->
      <el-tab-pane label="人员信息" name="members">
        <div style="display: flex; justify-content: flex-end; margin-bottom: 12px">
          <el-button type="primary" @click="openDialog()">新增人员</el-button>
        </div>

        <el-card>
          <el-table :data="sortedMembers" :row-class-name="activityRowClass" v-loading="membersLoading" stripe>
            <el-table-column prop="git_email" label="Git 邮箱" min-width="180" />
            <el-table-column prop="git_name" label="Git 用户名" min-width="120" />
            <el-table-column prop="real_name" label="真实姓名" min-width="150">
              <template #default="{ row }">
                <span>{{ row.real_name }}</span>
                <el-tag v-if="row.is_outsourced" size="small" type="primary" class="identity-tag">外包</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="department" label="部门" min-width="100" />
            <el-table-column label="最近提交" width="164">
              <template #default="{ row }">
                <span>{{ displayLastCommit(row.last_commit_at) }}</span>
                <el-tag v-if="isStale(row.last_commit_at)" size="small" type="info" class="stale-tag">
                  {{ row.last_commit_at ? '超过六个月' : '无提交记录' }}
                </el-tag>
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
      </el-tab-pane>
    </el-tabs>

    <!-- ── 新增 / 编辑 dialog ─────────────────────────────────── -->
    <el-dialog v-model="dialogVisible" :title="editId ? '编辑人员' : '新增人员'" width="500">
      <el-form :model="form" label-width="100px">
        <el-form-item label="Git 邮箱">
          <el-input v-model="form.git_email" />
        </el-form-item>
        <el-form-item label="Git 用户名">
          <el-input v-model="form.git_name" />
        </el-form-item>
        <el-form-item label="真实姓名">
          <el-input v-model="form.real_name" />
        </el-form-item>
        <el-form-item label="部门">
          <el-input v-model="form.department" />
        </el-form-item>
        <el-form-item label="人员类型">
          <el-switch
            v-model="form.is_outsourced"
            active-text="外包"
            inactive-text="正式员工"
            @change="markOutsourcingManual"
          />
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
import { ref, reactive, computed, onMounted, watch } from 'vue'
import client from '../api/client'
import { ElMessage, ElMessageBox } from 'element-plus'

const activeTab = ref('contributors')

// ── 贡献者总览 ──────────────────────────────────────────────
const contributors = ref([])
const contribLoading = ref(false)
const contribSearch = ref('')

const filteredContribs = computed(() => {
  const q = contribSearch.value.trim().toLowerCase()
  const filtered = !q ? contributors.value : contributors.value.filter(c =>
    c.git_email.toLowerCase().includes(q) ||
    c.git_name.toLowerCase().includes(q) ||
    c.real_name.toLowerCase().includes(q)
  )
  return [...filtered].sort(compareLastCommit)
})

const sortedMembers = computed(() => [...members.value].sort(compareLastCommit))

function compareLastCommit(a, b) {
  const byDate = (b.last_commit_at || '').localeCompare(a.last_commit_at || '')
  return byDate || (a.real_name || a.git_name || '').localeCompare(b.real_name || b.git_name || '', 'zh-CN')
}

function sixMonthsAgo() {
  const cutoff = new Date()
  cutoff.setHours(0, 0, 0, 0)
  cutoff.setMonth(cutoff.getMonth() - 6)
  return cutoff
}

function isStale(value) {
  if (!value) return true
  const timestamp = Date.parse(value.length === 10 ? `${value}T00:00:00` : value)
  return Number.isNaN(timestamp) || timestamp < sixMonthsAgo().getTime()
}

function activityRowClass({ row }) { return isStale(row.last_commit_at) ? 'stale-activity-row' : '' }
function displayLastCommit(value) { return value ? value.slice(0, 10) : '-' }

function repoShortName(full) {
  // "org/repo" → "repo"
  return full.includes('/') ? full.split('/').pop() : full
}

async function fetchContributors() {
  contribLoading.value = true
  try {
    const { data } = await client.get('/members/contributors')
    contributors.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载贡献者数据失败')
  }
  contribLoading.value = false
}

// 认领：预填 git_email / git_name，切换到填写 dialog
function openClaimDialog(row) {
  editId.value = null
  outsourcingManuallySet.value = false
  Object.assign(form, {
    git_email: row.git_email,
    git_name: row.git_name,
    real_name: '',
    department: '',
    is_outsourced: false,
  })
  dialogVisible.value = true
}

// 从贡献者总览编辑已认领人员
function openEditFromContrib(row) {
  editId.value = row.member_id
  outsourcingManuallySet.value = true
  Object.assign(form, {
    git_email: row.git_email,
    git_name: row.git_name,
    real_name: row.real_name,
    department: row.department,
    is_outsourced: Boolean(row.is_outsourced),
  })
  dialogVisible.value = true
}

// ── 人员信息 CRUD ───────────────────────────────────────────
const members = ref([])
const membersLoading = ref(false)
const dialogVisible = ref(false)
const saving = ref(false)
const editId = ref(null)
const outsourcingManuallySet = ref(false)
const form = reactive({ git_email: '', git_name: '', real_name: '', department: '', is_outsourced: false })

function isOutsourcedName(name) { return String(name || '').trim().toLowerCase().startsWith('v_') }
function markOutsourcingManual() { outsourcingManuallySet.value = true }

watch(() => form.real_name, value => {
  if (!outsourcingManuallySet.value) form.is_outsourced = isOutsourcedName(value)
})

async function fetchMembers() {
  membersLoading.value = true
  const { data } = await client.get('/members')
  members.value = data
  membersLoading.value = false
}

function openDialog(row) {
  if (row) {
    editId.value = row.id
    outsourcingManuallySet.value = true
    Object.assign(form, {
      git_email: row.git_email,
      git_name: row.git_name,
      real_name: row.real_name,
      department: row.department,
      is_outsourced: Boolean(row.is_outsourced),
    })
  } else {
    editId.value = null
    outsourcingManuallySet.value = false
    Object.assign(form, { git_email: '', git_name: '', real_name: '', department: '', is_outsourced: false })
  }
  dialogVisible.value = true
}

async function handleSave() {
  saving.value = true
  try {
    if (editId.value) {
      await client.put(`/members/${editId.value}`, form)
    } else {
      await client.post('/members', form)
    }
    dialogVisible.value = false
    ElMessage.success('保存成功')
    await Promise.all([fetchMembers(), fetchContributors()])
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
  saving.value = false
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确定删除 ${row.real_name || row.git_name}？`, '确认')
  await client.delete(`/members/${row.id}`)
  ElMessage.success('删除成功')
  await Promise.all([fetchMembers(), fetchContributors()])
}

onMounted(() => {
  fetchContributors()
  fetchMembers()
})
</script>

<style scoped>
.stale-tag { margin-left: 6px; }
.identity-tag { margin-left: 6px; }
:deep(.el-table .stale-activity-row td.el-table__cell) {
  background: #f4f4f5 !important;
  color: #a8abb2;
}
:deep(.el-table .stale-activity-row .el-tag) {
  filter: grayscale(1);
  opacity: 0.72;
}
</style>
