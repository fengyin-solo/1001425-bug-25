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
    <p v-if="summaryError" class="error-text summary-error">
      统计读取失败：{{ summaryError }}
      <button class="link" type="button" @click="loadSummary">重试</button>
    </p>

    <div v-if="showCreate" class="create-panel">
      <h3 class="create-title">登记裂缝处置单</h3>
      <form class="create-form" @submit.prevent="submitCreate">
        <label
          v-for="field in createFields"
          :key="field.key"
          class="filter-item"
          :class="{ 'field-missing': missingFields.includes(field.key) }"
        >
          <span>
            {{ field.key }}
            <em v-if="field.required" class="required-mark">*</em>
          </span>
          <input
            v-model="createForm[field.key]"
            :type="field.type ?? 'text'"
            :placeholder="field.placeholder ?? `填写${field.key}`"
            @input="clearMissing(field.key)"
          />
        </label>
        <div class="create-actions">
          <button class="btn primary" type="submit" :disabled="creating">
            {{ creating ? '提交中…' : '提交登记' }}
          </button>
          <button class="btn ghost" type="button" @click="closeCreate">收起</button>
        </div>
      </form>
      <p v-if="createError" class="error-text">{{ createError }}</p>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
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
        <template v-for="row in rows" :key="String(row.id)">
          <tr>
            <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
            <td class="row-actions">
              <button
                v-for="action in actions"
                :key="action"
                class="link"
                type="button"
                :disabled="isRowBusy(row)"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </td>
          </tr>
          <tr v-if="rowErrorOf(row)" :key="`${String(row.id)}-error`" class="row-error-row">
            <td :colspan="columns.length + 1">
              <span class="error-text">{{ rowErrorOf(row) }}</span>
              <button class="link" type="button" @click="retryRow(row)">重试</button>
            </td>
          </tr>
        </template>
        <tr v-if="loading">
          <td :colspan="columns.length + 1" class="empty-state">列表加载中…</td>
        </tr>
        <tr v-else-if="!rows.length && loadError">
          <td :colspan="columns.length + 1" class="empty-state">
            列表读取失败：{{ loadError }}
            <button class="link" type="button" @click="reload">重试</button>
          </td>
        </tr>
        <tr v-else-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">
            暂无裂缝处置数据，可先登记处置单
            <button class="link" type="button" @click="refreshAll">重新加载</button>
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条裂缝处置记录</span>
      <span v-if="notice" class="notice-text">{{ notice }}</span>
      <span v-if="loadError && rows.length" class="error-text">{{ loadError }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type StatCard = { label: string; value: string | number }
type RowState = { busy: boolean; error: string; lastAction: string }
type CreateField = { key: string; required: boolean; type?: string; placeholder?: string }

const ENDPOINT = '/api/crack'
const columns = ["处置单号", "所在路段", "裂缝类型", "裂缝长度", "灌缝材料", "作业班组", "完成日期", "处置状态"]
const actions = ["安排处置", "确认完成", "取消处置"]
const requiredOnCreate = ["处置单号", "所在路段", "裂缝类型"]
const createFields: CreateField[] = [
  { key: '处置单号', required: true, placeholder: '如 CRAC-0004' },
  { key: '所在路段', required: true, placeholder: '如 滨江路 K2+300' },
  { key: '裂缝类型', required: true, placeholder: '如 纵向裂缝' },
  { key: '裂缝长度', required: false, placeholder: '单位：米' },
  { key: '灌缝材料', required: false },
  { key: '作业班组', required: false },
  { key: '完成日期', required: false, type: 'date' },
]
// 筛选框字段 → 后端查询参数，逐一对上，避免条件发出去却被静默忽略
const filterParamMap: Record<string, string> = {
  处置单号: 'keyword',
  所在路段: 'section',
  裂缝类型: 'crack_type',
}

const rows = ref<Row[]>([])
const total = ref(0)
const loading = ref(false)
const loadError = ref('')
const notice = ref('')
const stats = ref<StatCard[]>([
  { label: '待安排处置', value: '—' },
  { label: '本月处置长度', value: '—' },
  { label: '取消单数', value: '—' },
])
const summaryError = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const rowStates = ref<Record<string, RowState>>({})
const showCreate = ref(false)
const creating = ref(false)
const createError = ref('')
const missingFields = ref<string[]>([])
const createForm = ref<Record<string, string>>({})

function rowKey(row: Row): string {
  return String(row.id)
}

function isRowBusy(row: Row): boolean {
  return rowStates.value[rowKey(row)]?.busy ?? false
}

function rowErrorOf(row: Row): string {
  return rowStates.value[rowKey(row)]?.error ?? ''
}

function setRowState(row: Row, state: RowState) {
  rowStates.value = { ...rowStates.value, [rowKey(row)]: state }
}

function buildQuery(): string {
  const params = new URLSearchParams()
  for (const [field, raw] of Object.entries(filters.value)) {
    const param = filterParamMap[field]
    const value = raw?.trim()
    if (param && value) {
      params.set(param, value)
    }
  }
  return params.toString()
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  showCreate.value = true
  createError.value = ''
  missingFields.value = []
  notice.value = ''
}

function closeCreate() {
  showCreate.value = false
  creating.value = false
  createError.value = ''
  missingFields.value = []
  createForm.value = {}
}

function clearMissing(key: string) {
  if (missingFields.value.includes(key)) {
    missingFields.value = missingFields.value.filter((field) => field !== key)
  }
}

async function submitCreate() {
  notice.value = ''
  // 先在前端点名叫人：哪个必填项没填，已填的内容原样保留
  const missing = requiredOnCreate.filter((field) => !createForm.value[field]?.trim())
  missingFields.value = missing
  if (missing.length) {
    createError.value = `缺少必填字段：${missing.join('、')}，已填写的内容已保留，补齐后再提交`
    return
  }
  creating.value = true
  createError.value = ''
  try {
    const values: Record<string, string> = {}
    for (const field of createFields) {
      const value = createForm.value[field.key]?.trim()
      if (value) {
        values[field.key] = value
      }
    }
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? '处置单登记失败，请稍后重试')
    }
    closeCreate()
    await refreshAll()
    notice.value = payload.message ?? '处置单已登记'
  } catch (error) {
    // 登记失败只提示原因，表单内容不清空
    createError.value = error instanceof Error ? error.message : '处置单登记失败'
  } finally {
    creating.value = false
  }
}

async function runAction(action: string, row: Row) {
  notice.value = ''
  setRowState(row, { busy: true, error: '', lastAction: action })
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? `动作「${action}」未生效，请重试`)
    }
    setRowState(row, { busy: false, error: '', lastAction: action })
    await refreshAll()
  } catch (error) {
    // 单条失败只挂在这一行上，列表其他记录不受影响
    setRowState(row, {
      busy: false,
      error: error instanceof Error ? error.message : '裂缝处置操作失败',
      lastAction: action,
    })
  }
}

function retryRow(row: Row) {
  const lastAction = rowStates.value[rowKey(row)]?.lastAction
  if (lastAction) {
    void runAction(lastAction, row)
  }
}

async function reload() {
  loading.value = true
  loadError.value = ''
  try {
    const response = await request(`${ENDPOINT}?${buildQuery()}`)
    if (!response.ok) {
      throw new Error('处置单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    // 读取失败保留已加载的行，页面不白屏；没有行时走可重试的空态
    loadError.value = error instanceof Error ? error.message : '裂缝处置列表读取失败'
  } finally {
    loading.value = false
  }
}

async function loadSummary() {
  summaryError.value = ''
  try {
    const response = await request(`${ENDPOINT}/summary`)
    if (!response.ok) {
      throw new Error('统计读取失败')
    }
    const payload = await response.json()
    stats.value = payload.cards ?? []
  } catch (error) {
    summaryError.value = error instanceof Error ? error.message : '统计读取失败'
  }
}

async function refreshAll() {
  await Promise.all([reload(), loadSummary()])
}

onMounted(refreshAll)
</script>
