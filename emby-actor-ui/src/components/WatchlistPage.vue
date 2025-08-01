---  src/components/WatchlistPage.vue ---
<!-- src/components/WatchlistPage.vue (最终健壮版 - 弹窗终极修复 + 批量操作 + 排序) -->
<template>
  <n-layout content-style="padding: 24px;">
    <div class="watchlist-page">
      <n-page-header>
        <template #title>
          <n-space align="center">
            <span>智能追剧列表</span>
            <n-tag v-if="filteredWatchlist.length > 0" type="info" round :bordered="false" size="small">
              {{ filteredWatchlist.length }} 部
            </n-tag>
          </n-space>
        </template>
        <template #extra>
          <n-space>
            <!-- 【新增】批量操作按钮，仅在有项目被选中时显示 -->
            <n-dropdown 
              v-if="selectedItems.length > 0"
              trigger="click" 
              :options="batchActions"
              @select="handleBatchAction"
            >
              <n-button type="primary">
                批量操作 ({{ selectedItems.length }})
                <template #icon><n-icon :component="CaretDownIcon" /></template>
              </n-button>
            </n-dropdown>

            <n-radio-group v-model:value="currentView" size="small">
              <n-radio-button value="inProgress">追剧中</n-radio-button>
              <n-radio-button value="completed">已完结</n-radio-button>
            </n-radio-group>
            <!-- +++ 新增：一键扫描按钮 +++ -->
            <n-popconfirm @positive-click="addAllSeriesToWatchlist">
              <template #trigger>
                <n-tooltip>
                  <template #trigger>
                    <n-button circle :loading="isAddingAll">
                      <template #icon><n-icon :component="ScanIcon" /></template>
                    </n-button>
                  </template>
                  扫描媒体库并将所有剧集添加到追剧列表
                </n-tooltip>
              </template>
              确定要扫描 Emby 媒体库中的所有剧集吗？<br/>
              此操作会忽略已在列表中的剧集，只添加新的。
            </n-popconfirm>
            <n-tooltip>
              <template #trigger>
                <n-button @click="triggerAllWatchlistUpdate" :loading="isBatchUpdating" circle>
                  <template #icon><n-icon :component="SyncOutline" /></template>
                </n-button>
              </template>
              立即检查所有在追剧集
            </n-tooltip>
          </n-space>
        </template>
      </n-page-header>
      <n-divider />

      <div v-if="isLoading" class="center-container"><n-spin size="large" /></div>
      <div v-else-if="error" class="center-container"><n-alert title="加载错误" type="error" style="max-width: 500px;">{{ error }}</n-alert></div>
      <div v-else-if="filteredWatchlist.length > 0">
        <n-grid cols="1 s:1 m:2 l:3 xl:4" :x-gap="20" :y-gap="20" responsive="screen">
          <n-gi v-for="item in renderedWatchlist" :key="item.item_id">
            <!-- 【布局优化】减小海报和内容之间的 gap -->
            <n-card class="glass-section series-card" :bordered="false" content-style="display: flex; padding: 0; gap: 12px;">
              <n-checkbox 
                :checked="selectedItems.includes(item.item_id)"
                @update:checked="toggleSelection(item.item_id)"
                class="card-checkbox"
              />
              <div class="card-poster-container">
                <n-image lazy :src="getPosterUrl(item.item_id)" class="card-poster" object-fit="cover">
                  <template #placeholder><div class="poster-placeholder"><n-icon :component="TvIcon" size="32" /></div></template>
                </n-image>
              </div>
              <div class="card-content-container">
                <div class="card-header">
                  <n-ellipsis class="card-title" :tooltip="{ style: { maxWidth: '300px' } }">{{ item.item_name }}</n-ellipsis>
                  <n-popconfirm @positive-click="() => removeFromWatchlist(item.item_id, item.item_name)">
                    <template #trigger><n-button text type="error" circle title="移除" size="tiny"><template #icon><n-icon :component="TrashIcon" /></template></n-button></template>
                    确定要从追剧列表中移除《{{ item.item_name }}》吗？
                  </n-popconfirm>
                </div>
                <div class="card-status-area">
                  <n-space vertical size="small">
                    <!-- 
                      【布局修复】
                      1. 用一个 n-space 包裹状态按钮和 TMDB 状态，确保它们总是在一起。
                      2. 将“缺失”标签单独放在一行，确保布局稳定。
                    -->
                    <n-space align="center" :wrap="false">
                      <n-button round size="tiny" :type="statusInfo(item.status).type" @click="() => updateStatus(item.item_id, statusInfo(item.status).next)" :title="`点击切换到 '${statusInfo(item.status).nextText}'`">
                        <template #icon><n-icon :component="statusInfo(item.status).icon" /></template>
                        {{ statusInfo(item.status).text }}
                      </n-button>
                      <n-tag v-if="item.tmdb_status" size="small" :bordered="false" :type="getSmartTMDbStatusType(item)">
                        {{ getSmartTMDbStatusText(item) }}
                      </n-tag>
                    </n-space>
                    
                    <n-tag v-if="hasMissing(item)" type="warning" size="small" round>{{ getMissingCountText(item) }}</n-tag>

                    <n-text v-if="nextEpisode(item)?.name" :depth="3" class="next-episode-text">
                      <n-icon :component="CalendarIcon" /> 播出时间: {{ nextEpisode(item).name }} ({{ formatAirDate(nextEpisode(item).air_date) }})
                    </n-text>
                    <n-text :depth="3" class="last-checked-text">上次检查: {{ formatTimestamp(item.last_checked_at) }}</n-text>
                  </n-space>
                </div>
                <div class="card-actions">
                  <!-- 【最终优化】将“查看缺失”按钮改为带 Tooltip 的图标按钮 -->
                  <n-tooltip>
                    <template #trigger>
                      <n-button 
                        type="primary" 
                        size="small" 
                        circle 
                        @click="() => openMissingInfoModal(item)" 
                        :disabled="!hasMissing(item)"
                      >
                        <template #icon><n-icon :component="EyeIcon" /></template>
                      </n-button>
                    </template>
                    查看缺失详情
                  </n-tooltip>
                  <n-tooltip>
                    <template #trigger>
                      <n-button 
                        circle 
                        :loading="refreshingItems[item.item_id]" 
                        @click="() => triggerSingleRefresh(item.item_id, item.item_name)"
                      >
                        <template #icon><n-icon :component="SyncOutline" /></template>
                      </n-button>
                    </template>
                    立即刷新此剧集
                  </n-tooltip>
                  <n-tooltip>
                    <template #trigger><n-button text @click="openInEmby(item.item_id)"><template #icon><n-icon :component="EmbyIcon" size="18" /></template></n-button></template>
                    在 Emby 中打开
                  </n-tooltip>
                  <n-tooltip>
                    <template #trigger><n-button text tag="a" :href="`https://www.themoviedb.org/tv/${item.tmdb_id}`" target="_blank"><template #icon><n-icon :component="TMDbIcon" size="18" /></template></n-button></template>
                    在 TMDb 中打开
                  </n-tooltip>
                </div>
              </div>
            </n-card>
          </n-gi>
        </n-grid>

        <div ref="loaderRef" class="loader-trigger">
          <n-spin v-if="hasMore" size="small" />
        </div>

      </div>
      <div v-else class="center-container"><n-empty :description="emptyStateDescription" size="huge" /></div>
    </div>

    <n-modal v-model:show="showModal" preset="card" style="width: 90%; max-width: 900px;" :title="selectedSeries ? `缺失详情 - ${selectedSeries.item_name}` : ''" :bordered="false" size="huge">
      <div v-if="selectedSeries && missingData">
        <n-tabs type="line" animated>
          <n-tab-pane name="seasons" :tab="`缺失的季 (${missingData.missing_seasons.length})`" :disabled="missingData.missing_seasons.length === 0">
            <n-list bordered>
              <n-list-item v-for="season in missingData.missing_seasons" :key="season.season_number">
                <template #prefix><n-tag type="warning">S{{ season.season_number }}</n-tag></template>
                <n-ellipsis>{{ season.name }} ({{ season.episode_count }}集, {{ formatAirDate(season.air_date) }})</n-ellipsis>
                <template #suffix><n-button size="small" type="primary" @click="subscribeSeason(season.season_number)" :loading="subscribing['s'+season.season_number]">订阅本季</n-button></template>
              </n-list-item>
            </n-list>
          </n-tab-pane>
          <n-tab-pane name="episodes" :tab="`缺失的集 (${missingData.missing_episodes.length})`" :disabled="missingData.missing_episodes.length === 0">
            <n-list bordered>
              <n-list-item v-for="ep in missingData.missing_episodes" :key="`${ep.season_number}-${ep.episode_number}`">
                <template #prefix><n-tag>S{{ ep.season_number.toString().padStart(2, '0') }}E{{ ep.episode_number.toString().padStart(2, '0') }}</n-tag></template>
                <n-ellipsis>{{ ep.title }} ({{ formatAirDate(ep.air_date) }})</n-ellipsis>
              </n-list-item>
            </n-list>
          </n-tab-pane>
        </n-tabs>
      </div>
    </n-modal>
  </n-layout>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, h, computed, watch, nextTick } from 'vue';
import axios from 'axios';
import { NLayout, NPageHeader, NDivider, NEmpty, NTag, NButton, NSpace, NIcon, useMessage, useDialog, NPopconfirm, NTooltip, NGrid, NGi, NCard, NImage, NEllipsis, NSpin, NAlert, NRadioGroup, NRadioButton, NModal, NTabs, NTabPane, NList, NListItem, NCheckbox, NDropdown } from 'naive-ui';
// 【图标优化】引入 PlayCircleOutline，并重新命名图标别名，使其更符合逻辑
import { SyncOutline, TvOutline as TvIcon, TrashOutline as TrashIcon, EyeOutline as EyeIcon, CalendarOutline as CalendarIcon, PlayCircleOutline as WatchingIcon, PauseCircleOutline as PausedIcon, CheckmarkCircleOutline as CompletedIcon, ScanCircleOutline as ScanIcon, CaretDownOutline as CaretDownIcon, FlashOffOutline as ForceEndIcon } from '@vicons/ionicons5';
import { format, parseISO } from 'date-fns';
import { useConfig } from '../composables/useConfig.js';

const EmbyIcon = () => h('svg', { xmlns: "http://www.w3.org/2000/svg", viewBox: "0 0 48 48", width: "18", height: "18" }, [ h('path', { d: "M24,4.2c-11,0-19.8,8.9-19.8,19.8S13,43.8,24,43.8s19.8-8.9,19.8-19.8S35,4.2,24,4.2z M24,39.8c-8.7,0-15.8-7.1-15.8-15.8S15.3,8.2,24,8.2s15.8,7.1,15.8,15.8S32.7,39.8,24,39.8z", fill: "currentColor" }), h('polygon', { points: "22.2,16.4 22.2,22.2 16.4,22.2 16.4,25.8 22.2,25.8 22.2,31.6 25.8,31.6 25.8,25.8 31.6,31.6 31.6,22.2 25.8,22.2 25.8,16.4 ", fill: "currentColor" }) ]);
const TMDbIcon = () => h('svg', { xmlns: "http://www.w3.org/2000/svg", viewBox: "0 0 512 512", width: "18", height: "18" }, [ h('path', { d: "M256 512A256 256 0 1 0 256 0a256 256 0 1 0 0 512zM133.2 176.6a22.4 22.4 0 1 1 0-44.8 22.4 22.4 0 1 1 0 44.8zm63.3-22.4a22.4 22.4 0 1 1 44.8 0 22.4 22.4 0 1 1 -44.8 0zm74.8 108.2c-27.5-3.3-50.2-26-53.5-53.5a8 8 0 0 1 16-.6c2.3 19.3 18.8 34 38.1 31.7a8 8 0 0 1 7.4 8c-2.3.3-4.5.4-6.8.4zm-74.8-108.2a22.4 22.4 0 1 1 44.8 0 22.4 22.4 0 1 1 -44.8 0zm149.7 22.4a22.4 22.4 0 1 1 0-44.8 22.4 22.4 0 1 1 0 44.8zM133.2 262.6a22.4 22.4 0 1 1 0-44.8 22.4 22.4 0 1 1 0 44.8zm63.3-22.4a22.4 22.4 0 1 1 44.8 0 22.4 22.4 0 1 1 -44.8 0zm74.8 108.2c-27.5-3.3-50.2-26-53.5-53.5a8 8 0 0 1 16-.6c2.3 19.3 18.8 34 38.1 31.7a8 8 0 0 1 7.4 8c-2.3.3-4.5.4-6.8.4zm-74.8-108.2a22.4 22.4 0 1 1 44.8 0 22.4 22.4 0 1 1 -44.8 0zm149.7 22.4a22.4 22.4 0 1 1 0-44.8 22.4 22.4 0 1 1 0 44.8z", fill: "#01b4e4" }) ]);

const { configModel } = useConfig();
const message = useMessage();
const dialog = useDialog();
const props = defineProps({ taskStatus: { type: Object, required: true } });
const rawWatchlist = ref([]);
const currentView = ref('inProgress');
const isLoading = ref(true);
const isBatchUpdating = ref(false);
const error = ref(null);
const showModal = ref(false);
const isAddingAll = ref(false);
const selectedSeries = ref(null);
const subscribing = ref({});
const refreshingItems = ref({});
const isTaskRunning = computed(() => props.taskStatus.is_running);
const displayCount = ref(30);
const INCREMENT = 30;
const loaderRef = ref(null);
let observer = null;

const selectedItems = ref([]);
const toggleSelection = (itemId) => {
  const index = selectedItems.value.indexOf(itemId);
  if (index > -1) {
    selectedItems.value.splice(index, 1);
  } else {
    selectedItems.value.push(itemId);
  }
};

// 【核心修改】将 batchActions 转换为 computed 属性
const batchActions = computed(() => {
  if (currentView.value === 'inProgress') {
    return [
      {
        label: '强制完结',
        key: 'forceEnd',
        icon: () => h(NIcon, { component: ForceEndIcon })
      }
    ];
  } else if (currentView.value === 'completed') {
    return [
      {
        label: '重新追剧',
        key: 'rewatch',
        icon: () => h(NIcon, { component: WatchingIcon }) // 使用“追剧中”的图标
      }
    ];
  }
  return []; // 默认返回空数组
});


// 【核心修改】更新 handleBatchAction 以处理新的 'rewatch' 键
const handleBatchAction = (key) => {
  if (key === 'forceEnd') {
    dialog.warning({
      title: '确认操作',
      content: `确定要将选中的 ${selectedItems.value.length} 部剧集标记为“强制完结”吗？这会防止它们因集数更新而被错误地复活，但如果将来有新一季发布，它们仍会自动恢复追剧。`,
      positiveText: '确定',
      negativeText: '取消',
      onPositiveClick: async () => {
        try {
          const response = await axios.post('/api/watchlist/batch_force_end', {
            item_ids: selectedItems.value
          });
          message.success(response.data.message || '批量操作成功！');
          await fetchWatchlist();
          selectedItems.value = [];
        } catch (err) {
          message.error(err.response?.data?.error || '批量操作失败。');
        }
      }
    });
  } 
  // 【新增逻辑】处理“重新追剧”
  else if (key === 'rewatch') {
    dialog.info({
      title: '确认操作',
      content: `确定要将选中的 ${selectedItems.value.length} 部剧集的状态改回“追剧中”吗？`,
      positiveText: '确定',
      negativeText: '取消',
      onPositiveClick: async () => {
        try {
          // 注意：这里我们假设后端有一个可以批量更新状态的接口
          // 如果没有，你需要先在后端实现它
          const response = await axios.post('/api/watchlist/batch_update_status', {
            item_ids: selectedItems.value,
            new_status: 'Watching'
          });
          message.success(response.data.message || '批量操作成功！');
          // 操作成功后，自动切换到“追剧中”视图查看结果
          currentView.value = 'inProgress';
          // selectedItems 会被 currentView 的 watch 自动清空
        } catch (err) {
          message.error(err.response?.data?.error || '批量操作失败。');
        }
      }
    });
  }
};

// +++ 一键添加所有剧集到智能追剧列表 的函数 +++
const addAllSeriesToWatchlist = async () => {
  isAddingAll.value = true;
  try {
    const response = await axios.post('/api/actions/add_all_series_to_watchlist');
    message.success(response.data.message || '任务已成功提交！');
  } catch (err) {
    message.error(err.response?.data?.error || '启动扫描任务失败。');
  } finally {
    isAddingAll.value = false;
  }
};

const triggerSingleRefresh = async (itemId, itemName) => {
  refreshingItems.value[itemId] = true;
  try {
    await axios.post(`/api/watchlist/refresh/${itemId}`);
    message.success(`《${itemName}》的刷新任务已提交！`);
    setTimeout(() => { fetchWatchlist(); }, 5000);
  } catch (err) {
    message.error(err.response?.data?.error || '启动刷新失败。');
  } finally {
    setTimeout(() => { refreshingItems.value[itemId] = false; }, 5000);
  }
};
const subscribeSeason = async (seasonNumber) => {
  if (!selectedSeries.value) return;
  const key = `s${seasonNumber}`;
  subscribing.value[key] = true;
  try {
    await axios.post('/api/subscribe/moviepilot/series', {
      tmdb_id: selectedSeries.value.tmdb_id,
      title: selectedSeries.value.item_name,
      season_number: seasonNumber
    });
    message.success(`《${selectedSeries.value.item_name}》第 ${seasonNumber} 季已提交订阅！`);
    if (selectedSeries.value.missing_info_json) {
        const data = JSON.parse(selectedSeries.value.missing_info_json);
        data.missing_seasons = data.missing_seasons.filter(s => s.season_number !== seasonNumber);
        selectedSeries.value.missing_info_json = JSON.stringify(data);
    }
  } catch (err) {
    message.error(err.response?.data?.error || '订阅失败');
  } finally {
    subscribing.value[key] = false;
  }
};

const filteredWatchlist = computed(() => {
  let list = [];
  if (currentView.value === 'inProgress') {
    list = rawWatchlist.value
      .filter(item => item.status === 'Watching' || item.status === 'Paused')
      .sort((a, b) => {
        const statusOrder = { 'Watching': 0, 'Paused': 1 };
        const aStatus = statusOrder[a.status] ?? 99;
        const bStatus = statusOrder[b.status] ?? 99;
        if (aStatus !== bStatus) {
          return aStatus - bStatus;
        }
        const aDate = a.last_checked_at ? new Date(a.last_checked_at).getTime() : 0;
        const bDate = b.last_checked_at ? new Date(b.last_checked_at).getTime() : 0;
        return bDate - aDate;
      });
  } else if (currentView.value === 'completed') {
    list = rawWatchlist.value
      .filter(item => item.status === 'Completed')
      .sort((a, b) => {
        const aDate = a.last_checked_at ? new Date(a.last_checked_at).getTime() : 0;
        const bDate = b.last_checked_at ? new Date(b.last_checked_at).getTime() : 0;
        return bDate - aDate;
      });
  }
  return list;
});

watch(currentView, () => {
  displayCount.value = 30;
  selectedItems.value = [];
});

const renderedWatchlist = computed(() => {
  return filteredWatchlist.value.slice(0, displayCount.value);
});

const hasMore = computed(() => {
  return displayCount.value < filteredWatchlist.value.length;
});

const loadMore = () => {
  if (hasMore.value) {
    displayCount.value += INCREMENT;
  }
};

const emptyStateDescription = computed(() => {
  if (currentView.value === 'inProgress') {
    return '追剧列表为空，快去“手动处理”页面搜索并添加你正在追的剧集吧！';
  }
  return '还没有已完结的剧集。';
});

const missingData = computed(() => {
  if (!selectedSeries.value || !selectedSeries.value.missing_info_json) {
    return { missing_seasons: [], missing_episodes: [] };
  }
  try {
    return JSON.parse(selectedSeries.value.missing_info_json);
  } catch (e) {
    return { missing_seasons: [], missing_episodes: [] };
  }
});

const nextEpisode = (item) => {
  if (!item.next_episode_to_air_json) return null;
  try { return JSON.parse(item.next_episode_to_air_json); } 
  catch (e) { return null; }
};

const hasMissing = (item) => {
  if (!item.missing_info_json) return false;
  try {
    const data = JSON.parse(item.missing_info_json);
    return (data.missing_seasons?.length > 0) || (data.missing_episodes?.length > 0);
  } catch (e) {
    return false;
  }
};

const getMissingCountText = (item) => {
  if (!hasMissing(item)) return '';
  const data = JSON.parse(item.missing_info_json);
  const season_count = data.missing_seasons?.length || 0;
  const episode_count = data.missing_episodes?.length || 0;
  let parts = [];
  if (season_count > 0) parts.push(`缺 ${season_count} 季`);
  if (episode_count > 0) parts.push(`缺 ${episode_count} 集`);
  return parts.join(' | ');
};

const formatTimestamp = (timestamp) => {
  if (!timestamp) return '从未';
  try { return format(parseISO(timestamp), 'MM-dd HH:mm'); } 
  catch (e) { return 'N/A'; }
};
const formatAirDate = (dateString) => {
  if (!dateString) return '待定';
  try { return format(parseISO(dateString), 'yyyy-MM-dd'); }
  catch (e) { return 'N/A'; }
};
const getPosterUrl = (itemId) => `/image_proxy/Items/${itemId}/Images/Primary?maxHeight=480&tag=1`;
const getEmbyUrl = (itemId) => {
  const embyServerUrl = configModel.value?.emby_server_url;
  const serverId = configModel.value?.emby_server_id;
  if (!embyServerUrl || !itemId) return '#';
  const baseUrl = embyServerUrl.endsWith('/') ? embyServerUrl.slice(0, -1) : embyServerUrl;
  let finalUrl = `${baseUrl}/web/index.html#!/item?id=${itemId}`;
  if (serverId) {
    finalUrl += `&serverId=${serverId}`;
  }
  return finalUrl;
};
const openInEmby = (itemId) => {
  const url = getEmbyUrl(itemId);
  if (url !== '#') {
    window.open(url, '_blank');
  }
};

const statusInfo = (status) => {
  const map = {
    'Watching': { type: 'success', text: '追剧中', icon: WatchingIcon, next: 'Paused', nextText: '暂停' },
    'Paused': { type: 'warning', text: '已暂停', icon: PausedIcon, next: 'Watching', nextText: '继续追' },
    'Completed': { type: 'default', text: '已完结', icon: CompletedIcon, next: 'Watching', nextText: '重新追' },
  };
  return map[status] || map['Paused'];
};

const translateTmdbStatus = (status) => {
  const statusMap = {
    "Returning Series": "连载中",
    "Ended": "已完结",
    "Canceled": "已取消",
    "In Production": "制作中",
    "Planned": "计划中",
    "Pilot": "试播"
  };
  return statusMap[status] || status;
};
const getSmartTMDbStatusText = (item) => {
  const internalStatus = item.status;
  const tmdbStatus = item.tmdb_status;

  if (internalStatus === 'Completed') {
    if (tmdbStatus === 'Ended' || tmdbStatus === 'Canceled') {
      return '待回归';
    }
  }
  return translateTmdbStatus(tmdbStatus);
};

const getSmartTMDbStatusType = (item) => {
  if (getSmartTMDbStatusText(item) === '待回归') {
    return 'info';
  }
  return 'default';
};
const fetchWatchlist = async () => {
  isLoading.value = true;
  error.value = null;
  try {
    const response = await axios.get('/api/watchlist');
    rawWatchlist.value = response.data;
    // displayCount.value = 30; // 切换视图时已经重置，这里可以不重复
  } catch (err) {
    error.value = err.response?.data?.error || '获取追剧列表失败。';
  } finally {
    isLoading.value = false;
  }
};
const updateStatus = async (itemId, newStatus) => {
  const item = rawWatchlist.value.find(i => i.item_id === itemId);
  if (!item) return;
  const oldStatus = item.status;
  item.status = newStatus;
  try {
    await axios.post('/api/watchlist/update_status', { item_id: itemId, new_status: newStatus });
    message.success('状态更新成功！');
  } catch (err) {
    item.status = oldStatus;
    message.error(err.response?.data?.error || '更新状态失败。');
  }
};
const removeFromWatchlist = async (itemId, itemName) => {
  try {
    await axios.post(`/api/watchlist/remove/${itemId}`);
    message.success(`已将《${itemName}》从追剧列表移除。`);
    rawWatchlist.value = rawWatchlist.value.filter(i => i.item_id !== itemId);
  } catch (err)
 {
    message.error(err.response?.data?.error || '移除失败。');
  }
};
const triggerAllWatchlistUpdate = async () => {
  isBatchUpdating.value = true;
  try {
    const response = await axios.post('/api/tasks/trigger/process-watchlist');
    message.success(response.data.message || '所有追剧项目更新任务已启动！');
  } catch (err) {
    message.error(err.response?.data?.error || '启动更新任务失败。');
  } finally {
    isBatchUpdating.value = false;
  }
};
const triggerSingleUpdate = async (itemId) => {
  message.loading(`正在为该剧集检查更新...`, { duration: 0, key: `updating-${itemId}` });
  try {
    const response = await axios.post(`/api/watchlist/trigger_update/${itemId}/`);
    message.destroyAll();
    message.success(response.data.message || '单项更新任务已启动！');
  } catch (err) {
    message.destroyAll();
    message.error(err.response?.data?.error || '启动单项更新失败。');
  }
};

const openMissingInfoModal = (item) => {
  selectedSeries.value = item;
  showModal.value = true;
};

watch(() => props.taskStatus.is_running, (isRunning, wasRunning) => {
  if (wasRunning && !isRunning) {
    const relevantActions = [
        '追剧',
        '扫描全库剧集',
        '手动刷新'
    ];
    if (relevantActions.some(action => props.taskStatus.current_action.includes(action))) {
      message.info('相关后台任务已结束，正在刷新追剧列表...');
      fetchWatchlist();
    }
  }
});

onMounted(() => {
  fetchWatchlist();
  observer = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting) {
        loadMore();
      }
    },
    { threshold: 1.0 }
  );
  if (loaderRef.value) {
    observer.observe(loaderRef.value);
  }
});

onBeforeUnmount(() => {
  if (observer) {
    observer.disconnect();
  }
});

watch(loaderRef, (newEl) => {
  if (observer && newEl) {
    observer.observe(newEl);
  }
});

watch(isTaskRunning, (isRunning, wasRunning) => {
  if (wasRunning && !isRunning) {
    const lastAction = props.taskStatus.last_action;
    const relevantActions = ['追剧', '扫描全库剧集', '手动刷新'];
    const isRelevant = lastAction && relevantActions.some(action => lastAction.includes(action));

    if (isRelevant) {
      message.info('相关后台任务已结束，正在刷新追剧列表...');
      fetchWatchlist();
    }
  }
});

</script>

<style scoped>
.watchlist-page { padding: 0 10px; }
.center-container { display: flex; justify-content: center; align-items: center; height: calc(100vh - 200px); }

/* 卡片样式，为 checkbox 定位做准备 */
.series-card {
  position: relative;
}

/* 【修改】Checkbox 样式，默认隐藏，鼠标悬浮或已选中时显示 */
.card-checkbox {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 10;
  background-color: rgba(255, 255, 255, 0.7);
  border-radius: 50%;
  padding: 4px;
  --n-color-checked: var(--n-color-primary-hover);
  --n-border-radius: 50%;
  /* 默认隐藏并添加过渡效果 */
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.2s ease-in-out, visibility 0.2s ease-in-out;
}

/* 鼠标悬浮于卡片上时，或当多选框自身被勾选时，显示它 */
/* 注意: .n-checkbox--checked 是 Naive UI 内部用于标记“已选中”状态的类 */
.series-card:hover .card-checkbox,
.card-checkbox.n-checkbox--checked {
  opacity: 1;
  visibility: visible;
}

/* 【终极修复】为海报容器添加 overflow: hidden，裁剪掉溢出的图片部分，防止其挤压右侧内容 */
.card-poster-container { 
  flex-shrink: 0; 
  width: 160px; 
  height: 240px; 
  overflow: hidden;
}
.card-poster { width: 100%; height: 100%; }
.poster-placeholder { display: flex; align-items: center; justify-content: center; width: 100%; height: 100%; background-color: var(--n-action-color); }
/* 【布局优化】减小右侧内边距，给内容更多空间 */
.card-content-container { flex-grow: 1; display: flex; flex-direction: column; padding: 12px 8px 12px 0; min-width: 0; }
.card-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; flex-shrink: 0; }
.card-title { font-weight: 600; font-size: 1.1em; line-height: 1.3; }
.card-status-area { flex-grow: 1; padding-top: 8px; }
.last-checked-text { display: block; font-size: 0.8em; margin-top: 6px; }
.next-episode-text { display: flex; align-items: center; gap: 4px; font-size: 0.8em; }
/* 【最终优化】将按钮改为环绕对齐，使其均匀分布 */
.card-actions { border-top: 1px solid var(--n-border-color); padding-top: 8px; margin-top: 8px; display: flex; justify-content: space-around; align-items: center; flex-shrink: 0; }
.loader-trigger {
  height: 50px;
  display: flex;
  justify-content: center;
  align-items: center;
}
</style>