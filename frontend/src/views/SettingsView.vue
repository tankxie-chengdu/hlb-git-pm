<template>
  <div>
    <h2 style="margin-bottom: 24px">系统设置</h2>

    <el-tabs>
      <!-- ── Tab 1: 代理配置 ─────────────────────────────────── -->
      <el-tab-pane label="代理配置" name="proxy">
        <el-card style="max-width: 600px">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span>Git 操作代理设置</span>
              <span style="color: #909399; font-size: 12px">用于加速 GitHub 仓库的 clone/fetch 操作</span>
            </div>
          </template>

          <el-form :model="proxyConfig" label-width="120px" @submit.prevent="saveProxy">
            <!-- 启用状态 -->
            <el-form-item label="启用代理">
              <el-switch v-model="proxyConfig.enabled" :loading="proxyLoading" />
            </el-form-item>

            <!-- HTTP 代理 -->
            <el-form-item label="HTTP 代理">
              <el-input
                v-model="proxyConfig.http_proxy"
                :disabled="!proxyConfig.enabled"
                placeholder="例如: http://127.0.0.1:7897"
                clearable
              />
              <div style="color: #909399; font-size: 12px; margin-top: 4px">
                用于 HTTP 请求，如果为空则使用全局 HTTP_PROXY 环境变量
              </div>
            </el-form-item>

            <!-- HTTPS 代理 -->
            <el-form-item label="HTTPS 代理">
              <el-input
                v-model="proxyConfig.https_proxy"
                :disabled="!proxyConfig.enabled"
                placeholder="例如: http://127.0.0.1:7897"
                clearable
              />
              <div style="color: #909399; font-size: 12px; margin-top: 4px">
                用于 HTTPS 请求，通常与 HTTP 代理相同
              </div>
            </el-form-item>

            <!-- NO_PROXY -->
            <el-form-item label="不走代理的域名">
              <el-input
                v-model="proxyConfig.no_proxy"
                :disabled="!proxyConfig.enabled"
                placeholder="例如: localhost,127.0.0.1,internal.example.com"
                type="textarea"
                :rows="2"
              />
              <div style="color: #909399; font-size: 12px; margin-top: 4px">
                逗号分隔的域名列表，这些域名不会走代理
              </div>
            </el-form-item>

            <!-- 更新时间 -->
            <el-form-item v-if="proxyConfig.updated_at" label="最后更新">
              <span style="color: #606266">{{ formatTime(proxyConfig.updated_at) }}</span>
            </el-form-item>

            <!-- 操作按钮 -->
            <el-form-item>
              <el-button
                type="primary"
                :loading="proxyLoading"
                @click="saveProxy"
              >
                保存配置
              </el-button>
              <el-button :disabled="proxyLoading" @click="resetProxy">
                重置
              </el-button>
            </el-form-item>
          </el-form>

          <!-- 提示信息 -->
          <el-divider />
          <div style="background: #f0f9ff; border: 1px solid #b3d8ff; border-radius: 4px; padding: 12px; font-size: 12px; line-height: 1.6">
            <strong>使用说明：</strong>
            <ul style="margin: 8px 0 0 0; padding-left: 20px">
              <li>启用代理后，所有 Git clone/fetch 操作都会通过设置的代理服务器进行</li>
              <li>代理格式通常为 <code>http://host:port</code> 或 <code>socks5://host:port</code></li>
              <li>测试命令: <code>git -c http.proxy=http://127.0.0.1:7897 clone --mirror https://github.com/WeFi-HLB/fps-tp.git /tmp/test</code></li>
              <li>配置保存后，下次仓库同步时生效</li>
            </ul>
          </div>
        </el-card>
      </el-tab-pane>

      <!-- ── Tab 2: 系统信息 ─────────────────────────────────── -->
      <el-tab-pane label="系统信息" name="info">
        <el-card style="max-width: 600px">
          <el-form label-width="120px">
            <el-form-item label="时区">
              <span>{{ settings.timezone }}</span>
            </el-form-item>
            <el-form-item label="工作目录">
              <span style="word-break: break-all">{{ settings.workspace }}</span>
            </el-form-item>
            <el-form-item label="报告主题前缀">
              <span>{{ settings.subject_prefix }}</span>
            </el-form-item>
            <el-form-item label="AI 分析">
              <el-tag :type="settings.ai_enabled ? 'success' : 'info'">
                {{ settings.ai_enabled ? '已启用' : '已禁用' }}
              </el-tag>
              <span v-if="settings.ai_enabled" style="color: #606266; font-size: 12px; margin-left: 8px">
                ({{ settings.ai_model }})
              </span>
            </el-form-item>
          </el-form>
          <div style="color: #909399; font-size: 12px; margin-top: 16px">
            这些设置来自 <code>config.toml</code>，需要重启应用才能修改
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import client from '../api/client'

const proxyLoading = ref(false)
const proxyConfig = reactive({
  http_proxy: '',
  https_proxy: '',
  no_proxy: '',
  enabled: false,
  updated_at: null
})

const originalProxyConfig = reactive({
  http_proxy: '',
  https_proxy: '',
  no_proxy: '',
  enabled: false,
  updated_at: null
})

const settings = reactive({
  timezone: '',
  workspace: '',
  subject_prefix: '',
  ai_enabled: false,
  ai_model: ''
})

onMounted(() => {
  fetchProxyConfig()
  fetchSettings()
})

async function fetchProxyConfig() {
  proxyLoading.value = true
  try {
    const response = await client.get('/settings/proxy')
    Object.assign(proxyConfig, response.data)
    Object.assign(originalProxyConfig, response.data)
  } catch (error) {
    ElMessage.error('获取代理配置失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    proxyLoading.value = false
  }
}

async function fetchSettings() {
  try {
    const response = await client.get('/settings')
    Object.assign(settings, response.data)
  } catch (error) {
    ElMessage.error('获取系统设置失败: ' + (error.response?.data?.detail || error.message))
  }
}

async function saveProxy() {
  proxyLoading.value = true
  try {
    const response = await client.put('/settings/proxy', {
      http_proxy: proxyConfig.http_proxy || null,
      https_proxy: proxyConfig.https_proxy || null,
      no_proxy: proxyConfig.no_proxy || null,
      enabled: proxyConfig.enabled
    })
    Object.assign(proxyConfig, response.data)
    Object.assign(originalProxyConfig, response.data)
    ElMessage.success('代理配置已保存')
  } catch (error) {
    ElMessage.error('保存代理配置失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    proxyLoading.value = false
  }
}

function resetProxy() {
  Object.assign(proxyConfig, originalProxyConfig)
}

function formatTime(isoString) {
  if (!isoString) return '-'
  try {
    const date = new Date(isoString)
    return date.toLocaleString('zh-CN')
  } catch {
    return isoString
  }
}
</script>

<style scoped>
code {
  background-color: #f5f7fa;
  border: 1px solid #ebeef5;
  border-radius: 3px;
  padding: 0 4px;
  font-family: monospace;
  font-size: 12px;
}

ul {
  list-style: disc;
}
</style>
