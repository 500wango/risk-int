const { createApp, ref, computed, onMounted } = Vue;

createApp({
    setup() {
        const currentTab = ref('global');
        const chartTab = ref('heatmap');  // 'heatmap' or 'trend'
        const currentTime = ref('');
        const newUrl = ref('');
        const loadingSource = ref(false);
        const intelligenceItems = ref([]);
        const totalSources = ref(0);
        const highRisks = ref(0);

        // --- NEW SOURCE MANAGEMENT STATE ---
        const showSourceModal = ref(false);
        const sources = ref([]);
        const editingSourceId = ref(null);
        const editingSourceUrl = ref('');

        // --- DETAIL VIEW STATE ---
        const showDetailModal = ref(false);
        const currentDetailItem = ref(null);
        const showTranslation = ref(false);

        // --- BATCH SELECT STATE ---
        const batchSelectMode = ref(false);
        const selectedItems = ref([]);

        // --- CONTRACT STATE ---
        const currentTask = ref(null);
        const risks = ref([]);
        const contractTasks = ref([]); // History of all contract reviews

        const chartDom = ref(null);
        const fileInputSidebar = ref(null);
        let riskChart = null;

        // --- CLOCK ---
        setInterval(() => {
            currentTime.value = new Date().toLocaleTimeString('zh-CN');
        }, 1000);

        // --- API CALLS ---
        const fetchIntelligence = async () => {
            try {
                const res = await fetch('/api/intelligence/list');
                const data = await res.json();
                intelligenceItems.value = data;
                totalSources.value = new Set(data.map(i => i.source_id)).size;
                highRisks.value = data.filter(i => {
                    const hint = (i.risk_hint || '').toLowerCase();
                    const summary = (i.summary || '').toLowerCase();
                    const highRiskKeywords = ['高风险', '重大风险', '严重', '紧急', '预警', '警告', 'high risk', 'critical', 'urgent', 'warning'];
                    return highRiskKeywords.some(k => hint.includes(k) || summary.includes(k));
                }).length;
                updateChart();
            } catch (e) {
                console.error(e);
            }
        };

        // --- SOURCE MANAGEMENT ACTIONS ---
        const fetchSources = async () => {
            try {
                const res = await fetch('/api/source/list');
                sources.value = await res.json();
            } catch (e) { console.error(e); }
        };

        const openSourceManager = () => {
            fetchSources();
            showSourceModal.value = true;
        };

        const deleteSource = async (id) => {
            if (!confirm("确定要删除该信源及其数据吗？")) return;
            try {
                await fetch(`/api/source/${id}`, { method: 'DELETE' });
                fetchSources();
                fetchIntelligence();
            } catch (e) { alert("删除失败"); }
        };

        const retrySource = async (id) => {
            try {
                // Optimistic update
                const idx = sources.value.findIndex(s => s.id === id);
                if (idx !== -1) sources.value[idx].status = 'processing';

                await fetch(`/api/source/${id}/retry`, { method: 'POST' });
                fetchSources();
                fetchIntelligence();
            } catch (e) { alert("采集失败"); fetchSources(); }
        };

        // --- BATCH CRAWL ---
        const batchCrawling = ref(false);
        const batchCrawlSources = async () => {
            if (batchCrawling.value) return;
            
            try {
                batchCrawling.value = true;
                // Optimistic update - set all to processing
                sources.value.forEach(s => {
                    if (s.status !== 'processing') s.status = 'processing';
                });
                
                const res = await fetch('/api/source/batch-crawl', { method: 'POST' });
                const data = await res.json();
                alert(`已启动 ${data.count} 个信源的采集任务`);
                
                // Start polling for updates
                const pollInterval = setInterval(() => {
                    fetchSources();
                    fetchIntelligence();
                    // Check if all done
                    const stillProcessing = sources.value.some(s => s.status === 'processing');
                    if (!stillProcessing) {
                        clearInterval(pollInterval);
                        batchCrawling.value = false;
                    }
                }, 5000);
                
                // Auto stop after 5 minutes
                setTimeout(() => {
                    clearInterval(pollInterval);
                    batchCrawling.value = false;
                    fetchSources();
                }, 300000);
                
            } catch (e) { 
                alert("批量采集失败"); 
                batchCrawling.value = false;
                fetchSources(); 
            }
        };

        // --- SOURCE EDIT FUNCTIONS ---
        const startEditSource = (source) => {
            editingSourceId.value = source.id;
            editingSourceUrl.value = source.url;
        };

        const cancelSourceEdit = () => {
            editingSourceId.value = null;
            editingSourceUrl.value = '';
        };

        const saveSourceEdit = async (sourceId) => {
            if (!editingSourceUrl.value.trim()) {
                alert('URL 不能为空');
                return;
            }
            try {
                const res = await fetch(`/api/source/${sourceId}?url=${encodeURIComponent(editingSourceUrl.value)}`, {
                    method: 'PUT'
                });
                if (res.ok) {
                    cancelSourceEdit();
                    fetchSources();
                } else {
                    alert('更新失败');
                }
            } catch (e) {
                console.error(e);
                alert('更新出错');
            }
        };

        const addSource = async () => {
            if (!newUrl.value) return;
            loadingSource.value = true;
            try {
                await fetch(`/api/intelligence/source?url=${encodeURIComponent(newUrl.value)}`, {
                    method: 'POST'
                });
                newUrl.value = '';
                fetchIntelligence();
                fetchSources(); // Refresh list if open
            } catch (e) {
                alert("添加信源失败，请检查 URL 是否有效");
            } finally {
                loadingSource.value = false;
            }
        };

        const openDetail = (item) => {
            currentDetailItem.value = item;
            showTranslation.value = false; // Reset to original by default
            showDetailModal.value = true;
        };

        const deleteItem = async (itemId) => {
            if (!confirm('确定要删除这条情报吗？(Are you sure?)')) return;
            try {
                const response = await fetch(`/api/intelligence/item/${itemId}`, { method: 'DELETE' });
                if (response.ok) {
                    intelligenceItems.value = intelligenceItems.value.filter(i => i.id !== itemId);
                    // Re-calculate stats after deletion
                    totalSources.value = new Set(intelligenceItems.value.map(i => i.source_id)).size;
                    highRisks.value = intelligenceItems.value.filter(i => {
                        const hint = (i.risk_hint || '').toLowerCase();
                        const summary = (i.summary || '').toLowerCase();
                        const highRiskKeywords = ['高风险', '重大风险', '严重', '紧急', '预警', '警告', 'high risk', 'critical', 'urgent', 'warning'];
                        return highRiskKeywords.some(k => hint.includes(k) || summary.includes(k));
                    }).length;
                    // Also close modal if open and matches
                    if (showDetailModal.value && currentDetailItem.value && currentDetailItem.value.id === itemId) {
                        showDetailModal.value = false;
                    }
                } else {
                    alert('Failed to delete item');
                }
            } catch (e) {
                console.error(e);
                alert('Error deleting item');
            }
        };

        const uploadContract = async (event) => {
            const file = event.target.files[0];
            if (!file) return;

            const formData = new FormData();
            formData.append('file', file);

            // Optimistic UI - 立即显示处理中状态
            currentTask.value = { filename: file.name, status: 'processing' };
            risks.value = [];
            console.log('Upload started, currentTask:', currentTask.value);

            try {
                const res = await fetch('/api/contract/upload', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                console.log('Upload response:', data);

                // Poll result (for MVP immediate, in real world socket or poll loop)
                const taskRes = await fetch(`/api/contract/${data.task_id}/result`);
                const taskData = await taskRes.json();

                currentTask.value = taskData.task;
                risks.value = taskData.risks;
                fetchContractTasks(); // Refresh list after upload
            } catch (e) {
                currentTask.value = { ...currentTask.value, status: 'failed', overall_risk_level: 'Error' };
                console.error(e);
            }
        };

        // --- CONTRACT HISTORY FUNCTIONS ---
        const fetchContractTasks = async () => {
            try {
                const res = await fetch('/api/contract/list');
                contractTasks.value = await res.json();
            } catch (e) { console.error(e); }
        };

        const viewContractResult = async (taskId) => {
            try {
                const res = await fetch(`/api/contract/${taskId}/result`);
                const data = await res.json();
                currentTask.value = data.task;
                risks.value = data.risks;
            } catch (e) {
                console.error(e);
                alert('加载失败');
            }
        };

        const deleteContractTask = async (taskId) => {
            if (!confirm('确定删除此合同审核记录？')) return;
            try {
                await fetch(`/api/contract/${taskId}`, { method: 'DELETE' });
                fetchContractTasks();
                // Clear current view if it was the deleted one
                if (currentTask.value && currentTask.value.id === taskId) {
                    currentTask.value = null;
                    risks.value = [];
                }
            } catch (e) {
                alert('删除失败');
            }
        };

        const backToContractList = () => {
            currentTask.value = null;
            risks.value = [];
        };

        // --- CHARTS ---
        const updateChart = () => {
            if (!riskChart || !chartDom.value) return;

            const option = {
                backgroundColor: 'transparent',
                tooltip: { trigger: 'item' },
                radar: {
                    indicator: [
                        { name: '政治风险', max: 100 },
                        { name: '经济风险', max: 100 },
                        { name: '法律合规', max: 100 },
                        { name: '安全形势', max: 100 },
                        { name: '社会舆情', max: 100 }
                    ],
                    name: {
                        textStyle: {
                            color: '#ffffff',
                            fontSize: 14,
                            fontWeight: 'bold'
                        }
                    },
                    splitArea: {
                        areaStyle: {
                            color: ['rgba(255,255,255,0.02)', 'rgba(255,255,255,0.05)']
                        }
                    },
                    axisLine: { lineStyle: { color: 'rgba(255,255,255,0.2)' } },
                    splitLine: { lineStyle: { color: 'rgba(255,255,255,0.15)' } },
                    axisName: {
                        color: '#ffffff',
                        fontSize: 14
                    }
                },
                series: [
                    {
                        name: '风险画像',
                        type: 'radar',
                        data: [
                            {
                                value: [80, 50, 60, 40, 70],
                                name: '当前态势',
                                areaStyle: { color: 'rgba(96, 165, 250, 0.4)' },
                                itemStyle: { color: '#60a5fa' },
                                label: {
                                    show: true,
                                    color: '#ffffff',
                                    fontSize: 12
                                }
                            }
                        ]
                    }
                ]
            };
            riskChart.setOption(option);
        };

        onMounted(() => {
            fetchIntelligence();
            fetchContractTasks(); // Load contract history

            // Init Chart
            if (chartDom.value) {
                if (typeof echarts !== 'undefined') {
                    try {
                        riskChart = echarts.init(chartDom.value);
                        updateChart();
                        window.addEventListener('resize', () => riskChart.resize());
                    } catch (e) {
                        console.warn('Chart init error:', e);
                    }
                } else {
                    console.warn('ECharts library not loaded. Chart disabled.');
                }
            }
        });

        const toggleTranslation = () => {
            showTranslation.value = !showTranslation.value;
        };

        // --- BATCH DELETE FUNCTIONS ---
        const enterBatchMode = () => {
            batchSelectMode.value = true;
            selectedItems.value = [];
        };

        const exitBatchMode = () => {
            batchSelectMode.value = false;
            selectedItems.value = [];
        };

        const toggleSelectItem = (itemId) => {
            const idx = selectedItems.value.indexOf(itemId);
            if (idx === -1) {
                selectedItems.value.push(itemId);
            } else {
                selectedItems.value.splice(idx, 1);
            }
        };

        const selectAllItems = () => {
            if (selectedItems.value.length === intelligenceItems.value.length) {
                selectedItems.value = [];
            } else {
                selectedItems.value = intelligenceItems.value.map(i => i.id);
            }
        };

        const batchDeleteItems = async () => {
            if (selectedItems.value.length === 0) return;
            if (!confirm(`确定要删除选中的 ${selectedItems.value.length} 条情报吗？`)) return;
            
            try {
                const response = await fetch('/api/intelligence/batch-delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(selectedItems.value)
                });
                if (response.ok) {
                    const result = await response.json();
                    // Remove deleted items from list
                    intelligenceItems.value = intelligenceItems.value.filter(
                        i => !selectedItems.value.includes(i.id)
                    );
                    // Re-calculate stats
                    totalSources.value = new Set(intelligenceItems.value.map(i => i.source_id)).size;
                    highRisks.value = intelligenceItems.value.filter(i => {
                        const hint = (i.risk_hint || '').toLowerCase();
                        const summary = (i.summary || '').toLowerCase();
                        const highRiskKeywords = ['高风险', '重大风险', '严重', '紧急', '预警', '警告', 'high risk', 'critical', 'urgent', 'warning'];
                        return highRiskKeywords.some(k => hint.includes(k) || summary.includes(k));
                    }).length;
                    // Exit batch mode
                    exitBatchMode();
                } else {
                    alert('批量删除失败');
                }
            } catch (e) {
                console.error(e);
                alert('批量删除出错');
            }
        };

        return {
            currentTab,
            chartTab,
            currentTime,
            newUrl,
            loadingSource,
            addSource,
            intelligenceItems,
            totalSources,
            highRisks,
            chartDom,
            fileInputSidebar,
            uploadContract,
            currentTask,
            risks,
            // Contract History
            contractTasks,
            fetchContractTasks,
            viewContractResult,
            deleteContractTask,
            backToContractList,
            // Source Management
            showSourceModal,
            sources,
            openSourceManager,
            deleteSource,
            retrySource,
            batchCrawling,
            batchCrawlSources,
            editingSourceId,
            editingSourceUrl,
            startEditSource,
            cancelSourceEdit,
            saveSourceEdit,
            // Detail View
            showDetailModal,
            currentDetailItem,
            openDetail,
            deleteItem,
            showTranslation,
            toggleTranslation,
            // Batch Delete
            batchSelectMode,
            selectedItems,
            enterBatchMode,
            exitBatchMode,
            toggleSelectItem,
            selectAllItems,
            batchDeleteItems
        };
    }
}).mount('#app');
