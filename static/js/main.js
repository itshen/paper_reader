/**
 * Paper Reader MCP - Web 管理页面脚本
 */

// 工具定义
const TOOLS = {
    search_papers: {
        title: '搜索论文',
        desc: '通过关键词搜索 arXiv 论文，支持排序和分类过滤',
        fields: [
            { name: 'query', label: '搜索关键词', type: 'text', placeholder: 'transformer attention / machine learning', required: true },
            { name: 'max_results', label: '最大结果数', type: 'number', placeholder: '10', hint: '默认 10，最多 50' },
            { 
                name: 'sort_by', label: '排序方式', type: 'select',
                options: [
                    { value: 'smart', label: '智能排序（相关性+时间）' },
                    { value: 'relevance', label: '仅按相关性' },
                    { value: 'submitted', label: '仅按提交时间' },
                    { value: 'updated', label: '仅按更新时间' }
                ]
            },
            { 
                name: 'sort_order', label: '排序顺序', type: 'select',
                options: [
                    { value: 'descending', label: '降序（最新/最相关优先）' },
                    { value: 'ascending', label: '升序（最早/最不相关优先）' }
                ]
            },
            { 
                name: 'category', label: '分类过滤', type: 'select',
                options: [
                    { value: '', label: '全部分类' },
                    { value: 'cs.AI', label: 'cs.AI - 人工智能' },
                    { value: 'cs.CL', label: 'cs.CL - 计算语言学/NLP' },
                    { value: 'cs.CV', label: 'cs.CV - 计算机视觉' },
                    { value: 'cs.LG', label: 'cs.LG - 机器学习' },
                    { value: 'cs.NE', label: 'cs.NE - 神经网络' },
                    { value: 'cs.IR', label: 'cs.IR - 信息检索' },
                    { value: 'cs.RO', label: 'cs.RO - 机器人' },
                    { value: 'cs.SE', label: 'cs.SE - 软件工程' },
                    { value: 'stat.ML', label: 'stat.ML - 统计机器学习' },
                    { value: 'eess.AS', label: 'eess.AS - 音频与语音' },
                    { value: 'eess.IV', label: 'eess.IV - 图像与视频' }
                ]
            }
        ]
    },
    get_paper_content: {
        title: '获取论文全文',
        desc: '通过 arXiv ID 下载论文 PDF 并转换为 Markdown 格式（支持分页）',
        fields: [
            { name: 'paper_id', label: 'arXiv ID', type: 'text', placeholder: '2301.12345 / 1706.03762', required: true, hint: '从搜索结果中获取' },
            { name: 'page', label: '页码', type: 'number', placeholder: '1', hint: '默认第 1 页' },
            { name: 'max_chars', label: '每页字符数', type: 'number', placeholder: '20000', hint: '默认 20000，范围 1000-100000' }
        ]
    }
};

// 当前选中的工具
let currentTool = null;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    // 绑定工具按钮点击事件
    document.querySelectorAll('.tool-btn').forEach(btn => {
        btn.addEventListener('click', () => selectTool(btn.dataset.tool));
    });
    
    // 绑定表单提交事件
    document.getElementById('toolForm').addEventListener('submit', handleSubmit);
});

/**
 * 选择工具
 */
function selectTool(toolName) {
    const tool = TOOLS[toolName];
    if (!tool) return;
    
    currentTool = toolName;
    
    // 更新按钮状态
    document.querySelectorAll('.tool-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tool === toolName);
    });
    
    // 更新标题和描述
    document.getElementById('toolTitle').textContent = tool.title;
    document.getElementById('toolDesc').textContent = tool.desc;
    
    // 生成表单字段
    const formFields = document.getElementById('formFields');
    formFields.innerHTML = tool.fields.map(field => generateFieldHTML(field)).join('');
    
    // 显示表单
    document.getElementById('toolForm').style.display = 'flex';
    
    // 隐藏结果
    document.getElementById('resultPanel').style.display = 'none';
}

/**
 * 生成表单字段 HTML
 */
function generateFieldHTML(field) {
    let inputHTML = '';
    
    if (field.type === 'select') {
        const options = field.options.map(opt => 
            `<option value="${opt.value}">${opt.label}</option>`
        ).join('');
        inputHTML = `<select name="${field.name}" id="${field.name}">${options}</select>`;
    } else if (field.type === 'textarea') {
        const required = field.required ? 'required' : '';
        inputHTML = `<textarea name="${field.name}" id="${field.name}" 
            placeholder="${field.placeholder || ''}" ${required} rows="4"></textarea>`;
    } else {
        const required = field.required ? 'required' : '';
        inputHTML = `<input type="${field.type}" name="${field.name}" id="${field.name}" 
            placeholder="${field.placeholder || ''}" ${required}>`;
    }
    
    const hint = field.hint ? `<span class="form-hint">${field.hint}</span>` : '';
    
    return `
        <div class="form-group">
            <label for="${field.name}">${field.label}</label>
            ${inputHTML}
            ${hint}
        </div>
    `;
}

/**
 * 处理表单提交
 */
async function handleSubmit(e) {
    e.preventDefault();
    
    if (!currentTool) return;
    
    const form = e.target;
    const formData = new FormData(form);
    
    // 构建参数
    const params = {};
    for (const [key, value] of formData.entries()) {
        if (value !== '') {
            // 尝试转换数字
            const field = TOOLS[currentTool].fields.find(f => f.name === key);
            if (field && field.type === 'number') {
                params[key] = parseFloat(value);
            } else {
                params[key] = value;
            }
        }
    }
    
    // 显示加载状态
    const submitBtn = form.querySelector('.submit-btn');
    const originalHTML = submitBtn.innerHTML;
    submitBtn.innerHTML = '<span class="loading"></span> 执行中...';
    submitBtn.disabled = true;
    
    try {
        // 调用 API
        const response = await fetch('/api/call', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tool: currentTool,
                params: params
            })
        });
        
        const data = await response.json();
        
        // 显示结果
        const resultPanel = document.getElementById('resultPanel');
        const resultContent = document.getElementById('resultContent');
        
        if (data.success) {
            // 将 Markdown 风格的文本转换为 HTML
            resultContent.innerHTML = formatResult(data.result);
        } else {
            resultContent.innerHTML = `<div class="error">❌ 错误: ${escapeHtml(data.error)}</div>`;
        }
        
        resultPanel.style.display = 'block';
        
    } catch (error) {
        console.error('调用失败:', error);
        const resultPanel = document.getElementById('resultPanel');
        const resultContent = document.getElementById('resultContent');
        resultContent.innerHTML = `<div class="error">❌ 请求失败: ${escapeHtml(error.message)}</div>`;
        resultPanel.style.display = 'block';
    } finally {
        // 恢复按钮状态
        submitBtn.innerHTML = originalHTML;
        submitBtn.disabled = false;
    }
}

/**
 * 格式化结果（简单的 Markdown 转 HTML）
 */
function formatResult(text) {
    if (!text) return '';
    
    // 转义 HTML
    let html = escapeHtml(text);
    
    // 处理标题 **text**
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    
    // 处理代码 `text`
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // 处理分隔线 ---
    html = html.replace(/^---$/gm, '<hr>');
    
    // 处理换行
    html = html.replace(/\n/g, '<br>');
    
    return `<pre class="formatted-result">${html}</pre>`;
}

/**
 * 转义 HTML
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
