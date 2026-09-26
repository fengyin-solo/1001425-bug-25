<template>
  <section class="page" data-module="crack">
    <header class="page-head">
      <div>
        <h2>裂缝处置管理</h2>
        <p class="page-desc">维护处置单，围绕处置单号、所在路段、裂缝类型、裂缝长度做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记处置单</button>
        <button class="btn" type="button" @click="exportRows">导出裂缝处置清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>处置状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="Boolean(actionPending[rowKey(row)])"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="rowErrors[rowKey(row)]" class="row-error">
              {{ rowErrors[rowKey(row)].message }}
              <button class="link" type="button" @click="retryAction(row)">重试</button>
            </span>
          </td>
        </tr>
        <tr v-if="loading">
          <td :colspan="columns.length + 1" class="empty-state">正在读取裂缝处置数据…</td>
        </tr>
        <tr v-else-if="listError">
          <td :colspan="columns.length + 1" class="empty-state">
            {{ listError }}
            <button class="link" type="button" @click="reload">重试</button>
          </td>
        </tr>
        <tr v-else-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">
            暂无裂缝处置数据，可先登记处置单，或
            <button class="link" type="button" @click="reload">重新加载</button>
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条裂缝处置记录</span>
      <span v-if="listError" class="error-text">{{ listError }}</span>
    </footer>

    <div v-if="showCreate" class="modal-mask" @click.self="closeCreate">
      <form class="modal-card" @submit.prevent="submitCreate">
        <h3>登记裂缝处置单</h3>
        <label v-for="field in createFields" :key="field.name" class="modal-field">
          <span>
            {{ field.name }}
            <em v-if="field.required" class="required-mark">*</em>
          </span>
          <input
            v-model="createForm[field.name]"
            :placeholder="field.required ? `必填，请填写${field.name}` : `选填，请填写${field.name}`"
          />
        </label>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeCreate">取消</button>
          <button class="btn primary" type="submit" :disabled="createSubmitting">
            {{ createSubmitting ? '提交中…' : '提交登记' }}
          </button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/crack'
const columns = ["处置单号", "所在路段", "裂缝类型", "裂缝长度", "灌缝材料", "作业班组", "完成日期", "处置状态"]
const actions = ["安排处置", "确认完成", "取消处置"]
const statuses = ["待安排", "处置中", "已完成", "已取消"]
const requiredCreateFields = ["处置单号", "所在路段", "裂缝类型"]
const optionalCreateFields = ["裂缝长度", "灌缝材料", "作业班组", "完成日期"]
const createFields = [
  ...requiredCreateFields.map((name) => ({ name, required: true })),
  ...optionalCreateFields.map((name) => ({ name, required: false })),
]

const rows = ref<Row[]>([])
const total = ref(0)
const loading = ref(false)
const listError = ref('')
const stats = ref([
  { label: '待安排处置', value: 0 },
  { label: '本月处置长度', value: 0 },
  { label: '取消单数', value: 0 },
])
const filters = ref<Record<string, string>>({})
const statusFilter = ref('')
const filterFields = columns.slice(0, 3)
const rowErrors = ref<Record<string, { action: string; message: string }>>({})
const actionPending = ref<Record<string, boolean>>({})

const showCreate = ref(false)
const createSubmitting = ref(false)
const createError = ref('')
const createForm = ref<Record<string, string>>({})

function rowKey(row: Row): string {
  return String(row.id ?? '')
}

function blankCreateForm(): Record<string, string> {
  return Object.fromEntries(createFields.map((field) => [field.name, '']))
}

function resetFilters() {
  filters.value = {}
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createForm.value = blankCreateForm()
  createError.value = ''
  showCreate.value = true
}

function closeCreate() {
  showCreate.value = false
  createError.value = ''
}

async function submitCreate() {
  const missing = requiredCreateFields.filter((field) => !(createForm.value[field] ?? '').trim())
  if (missing.length) {
    // 已填内容保留在表单里，只提示还缺哪几项
    createError.value = `请先补全必填项：${missing.join('、')}`
    return
  }
  createSubmitting.value = true
  createError.value = ''
  try {
    const values = Object.fromEntries(
      Object.entries(createForm.value).map(([key, value]) => [key, value.trim()]),
    )
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? '处置单登记未生效，请稍后重试')
    }
    closeCreate()
    await reload()
  } catch (error) {
    // 登记失败不清空表单，改完可直接再次提交
    createError.value = error instanceof Error ? error.message : '处置单登记失败，请稍后重试'
  } finally {
    createSubmitting.value = false
  }
}

async function runAction(action: string, row: Row) {
  const key = rowKey(row)
  const nextErrors = { ...rowErrors.value }
  delete nextErrors[key]
  rowErrors.value = nextErrors
  actionPending.value = { ...actionPending.value, [key]: true }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? `处置单${action}未生效，请重试`)
    }
    await reload()
  } catch (error) {
    // 失败只标记这一行，记住动作以便重试
    rowErrors.value = {
      ...rowErrors.value,
      [key]: {
        action,
        message: error instanceof Error ? error.message : '裂缝处置操作失败，请重试',
      },
    }
  } finally {
    actionPending.value = { ...actionPending.value, [key]: false }
  }
}

function retryAction(row: Row) {
  const failed = rowErrors.value[rowKey(row)]
  if (failed) {
    void runAction(failed.action, row)
  }
}

function updateStats() {
  const month = new Date()
  const monthPrefix = `${month.getFullYear()}-${String(month.getMonth() + 1).padStart(2, '0')}`
  const pending = rows.value.filter((row) => row.status === '待安排').length
  const cancelled = rows.value.filter((row) => row.status === '已取消').length
  const monthLength = rows.value
    .filter((row) => String(row['完成日期'] ?? '').startsWith(monthPrefix))
    .reduce((sum, row) => sum + (Number(row['裂缝长度']) || 0), 0)
  stats.value = [
    { label: '待安排处置', value: pending },
    { label: '本月处置长度', value: Number(monthLength.toFixed(1)) },
    { label: '取消单数', value: cancelled },
  ]
}

async function reload() {
  loading.value = true
  listError.value = ''
  const query = new URLSearchParams()
  if ((filters.value['处置单号'] ?? '').trim()) {
    query.set('keyword', filters.value['处置单号'].trim())
  }
  if ((filters.value['所在路段'] ?? '').trim()) {
    query.set('section', filters.value['所在路段'].trim())
  }
  if ((filters.value['裂缝类型'] ?? '').trim()) {
    query.set('crack_type', filters.value['裂缝类型'].trim())
  }
  if (statusFilter.value) {
    query.set('status', statusFilter.value)
  }
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload || !Array.isArray(payload.items)) {
      throw new Error('处置单列表读取失败，请重试')
    }
    rows.value = payload.items
    total.value = Number(payload.total ?? payload.items.length)
    updateStats()
  } catch (error) {
    rows.value = []
    total.value = 0
    updateStats()
    listError.value = error instanceof Error ? error.message : '裂缝处置列表读取失败，请重试'
  } finally {
    loading.value = false
  }
}

onMounted(reload)
</script>
