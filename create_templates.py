# 完整的模板創建腳本
import os

def create_all_templates():
    """創建所有 Flask 模板文件"""
    template_dir = 'templates'
    if not os.path.exists(template_dir):
        os.makedirs(template_dir)
    
    # 資料庫列表頁面
    database_template = '''{% extends "base.html" %}
{% block title %}資料庫管理{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
    <h2><i class="fas fa-database"></i> 資料庫管理</h2>
</div>

<div class="row">
    {% for table in tables %}
    <div class="col-md-4 mb-3">
        <div class="card">
            <div class="card-body">
                <h5 class="card-title">
                    <i class="fas fa-table"></i> {{ table }}
                </h5>
                <p class="card-text">管理 {{ table }} 資料表</p>
                <a href="{{ url_for('view_table', table_name=table) }}" class="btn btn-primary">
                    <i class="fas fa-eye"></i> 查看資料
                </a>
                <a href="{{ url_for('add_row_form', table_name=table) }}" class="btn btn-success">
                    <i class="fas fa-plus"></i> 新增
                </a>
            </div>
        </div>
    </div>
    {% endfor %}
</div>

{% if not tables %}
<div class="alert alert-info">
    <i class="fas fa-info-circle"></i> 目前沒有找到任何資料表
</div>
{% endif %}
{% endblock %}'''
    
    with open(os.path.join(template_dir, 'database.html'), 'w', encoding='utf-8') as f:
        f.write(database_template)
    
    # 表格查看頁面
    table_view_template = '''{% extends "base.html" %}
{% block title %}{{ table_name }} - 資料查看{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
    <h2><i class="fas fa-table"></i> {{ table_name }}</h2>
    <div>
        <a href="{{ url_for('add_row_form', table_name=table_name) }}" class="btn btn-success">
            <i class="fas fa-plus"></i> 新增記錄
        </a>
        <a href="{{ url_for('database_view') }}" class="btn btn-secondary">
            <i class="fas fa-arrow-left"></i> 返回
        </a>
    </div>
</div>

{% if rows %}
<div class="table-responsive">
    <table class="table table-striped table-hover">
        <thead class="table-dark">
            <tr>
                {% for column in columns %}
                <th>{{ column }}</th>
                {% endfor %}
                <th width="120">操作</th>
            </tr>
        </thead>
        <tbody>
            {% for row in rows %}
            <tr>
                {% for cell in row %}
                <td>
                    {% if cell|length > 50 %}
                        <span title="{{ cell }}">{{ cell[:50] }}...</span>
                    {% else %}
                        {{ cell }}
                    {% endif %}
                </td>
                {% endfor %}
                <td>
                    <a href="{{ url_for('edit_row', table_name=table_name, row_id=loop.index) }}" 
                       class="btn btn-warning btn-sm" title="編輯">
                        <i class="fas fa-edit"></i>
                    </a>
                    <a href="{{ url_for('delete_row', table_name=table_name, row_id=loop.index) }}" 
                       class="btn btn-danger btn-sm" title="刪除"
                       onclick="return confirm('確定要刪除這筆記錄嗎？')">
                        <i class="fas fa-trash"></i>
                    </a>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% else %}
<div class="alert alert-info">
    <i class="fas fa-info-circle"></i> 此表格目前沒有任何資料
    <a href="{{ url_for('add_row_form', table_name=table_name) }}" class="btn btn-success btn-sm ms-2">
        立即新增
    </a>
</div>
{% endif %}
{% endblock %}'''
    
    with open(os.path.join(template_dir, 'table_view.html'), 'w', encoding='utf-8') as f:
        f.write(table_view_template)
    
    # 編輯記錄頁面
    edit_row_template = '''{% extends "base.html" %}
{% block title %}編輯記錄 - {{ table_name }}{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
    <h2><i class="fas fa-edit"></i> 編輯記錄 - {{ table_name }}</h2>
    <a href="{{ url_for('view_table', table_name=table_name) }}" class="btn btn-secondary">
        <i class="fas fa-arrow-left"></i> 返回
    </a>
</div>

<div class="row justify-content-center">
    <div class="col-lg-8">
        <div class="card">
            <div class="card-body">
                <form method="POST" action="{{ url_for('update_row', table_name=table_name, row_id=row_id) }}">
                    {% for i in range(columns|length) %}
                    {% set col = columns[i] %}
                    {% set col_name = col[1] %}
                    {% set col_type = col[2] %}
                    <div class="mb-3">
                        <label for="{{ col_name }}" class="form-label">
                            {{ col_name }}
                            {% if col[3] %}
                                <span class="badge bg-danger">必填</span>
                            {% endif %}
                            {% if col[5] %}
                                <span class="badge bg-info">主鍵</span>
                            {% endif %}
                        </label>
                        
                        {% if col_type.lower() == 'text' or 'varchar' in col_type.lower() %}
                            {% if row[i]|length > 100 %}
                                <textarea class="form-control" id="{{ col_name }}" name="{{ col_name }}" 
                                         rows="4" {% if col[3] %}required{% endif %}>{{ row[i] }}</textarea>
                            {% else %}
                                <input type="text" class="form-control" id="{{ col_name }}" name="{{ col_name }}" 
                                       value="{{ row[i] }}" {% if col[3] %}required{% endif %}>
                            {% endif %}
                        {% elif 'int' in col_type.lower() %}
                            <input type="number" class="form-control" id="{{ col_name }}" name="{{ col_name }}" 
                                   value="{{ row[i] }}" {% if col[3] %}required{% endif %}>
                        {% elif 'timestamp' in col_type.lower() or 'datetime' in col_type.lower() %}
                            <input type="datetime-local" class="form-control" id="{{ col_name }}" name="{{ col_name }}" 
                                   value="{{ row[i] }}" {% if col[3] %}required{% endif %}>
                        {% else %}
                            <input type="text" class="form-control" id="{{ col_name }}" name="{{ col_name }}" 
                                   value="{{ row[i] }}" {% if col[3] %}required{% endif %}>
                        {% endif %}
                        
                        <small class="form-text text-muted">類型: {{ col_type }}</small>
                    </div>
                    {% endfor %}
                    
                    <div class="text-end">
                        <button type="submit" class="btn btn-primary">
                            <i class="fas fa-save"></i> 儲存變更
                        </button>
                        <a href="{{ url_for('view_table', table_name=table_name) }}" class="btn btn-secondary">
                            <i class="fas fa-times"></i> 取消
                        </a>
                    </div>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}'''
    
    with open(os.path.join(template_dir, 'edit_row.html'), 'w', encoding='utf-8') as f:
        f.write(edit_row_template)
    
    # 新增記錄頁面
    add_row_template = '''{% extends "base.html" %}
{% block title %}新增記錄 - {{ table_name }}{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
    <h2><i class="fas fa-plus"></i> 新增記錄 - {{ table_name }}</h2>
    <a href="{{ url_for('view_table', table_name=table_name) }}" class="btn btn-secondary">
        <i class="fas fa-arrow-left"></i> 返回
    </a>
</div>

<div class="row justify-content-center">
    <div class="col-lg-8">
        <div class="card">
            <div class="card-body">
                <form method="POST" action="{{ url_for('insert_row', table_name=table_name) }}">
                    {% for col in columns %}
                    {% if not col[5] or col[1] != 'id' %} {# 跳過自增ID欄位 #}
                    <div class="mb-3">
                        <label for="{{ col[1] }}" class="form-label">
                            {{ col[1] }}
                            {% if col[3] %}
                                <span class="badge bg-danger">必填</span>
                            {% endif %}
                        </label>
                        
                        {% if col[2].lower() == 'text' or 'varchar' in col[2].lower() %}
                            <input type="text" class="form-control" id="{{ col[1] }}" name="{{ col[1] }}" 
                                   {% if col[3] %}required{% endif %}>
                        {% elif 'int' in col[2].lower() %}
                            <input type="number" class="form-control" id="{{ col[1] }}" name="{{ col[1] }}" 
                                   {% if col[3] %}required{% endif %}>
                        {% elif 'timestamp' in col[2].lower() or 'datetime' in col[2].lower() %}
                            <input type="datetime-local" class="form-control" id="{{ col[1] }}" name="{{ col[1] }}" 
                                   {% if col[3] %}required{% endif %}>
                        {% else %}
                            <input type="text" class="form-control" id="{{ col[1] }}" name="{{ col[1] }}" 
                                   {% if col[3] %}required{% endif %}>
                        {% endif %}
                        
                        <small class="form-text text-muted">類型: {{ col[2] }}</small>
                    </div>
                    {% endif %}
                    {% endfor %}
                    
                    <div class="text-end">
                        <button type="submit" class="btn btn-success">
                            <i class="fas fa-plus"></i> 新增記錄
                        </button>
                        <a href="{{ url_for('view_table', table_name=table_name) }}" class="btn btn-secondary">
                            <i class="fas fa-times"></i> 取消
                        </a>
                    </div>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}'''
    
    with open(os.path.join(template_dir, 'add_row.html'), 'w', encoding='utf-8') as f:
        f.write(add_row_template)
    
    # 系統日誌頁面
    logs_template = '''{% extends "base.html" %}
{% block title %}系統日誌{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
    <h2><i class="fas fa-list-alt"></i> 系統日誌</h2>
    <a href="{{ url_for('index') }}" class="btn btn-secondary">
        <i class="fas fa-arrow-left"></i> 返回儀表板
    </a>
</div>

{% if logs %}
<div class="table-responsive">
    <table class="table table-striped">
        <thead class="table-dark">
            <tr>
                <th>時間</th>
                <th>操作</th>
                <th>詳細資訊</th>
                <th>用戶</th>
            </tr>
        </thead>
        <tbody>
            {% for log in logs %}
            <tr>
                <td>
                    <small>{{ log[4] }}</small>
                </td>
                <td>
                    <span class="badge bg-primary">{{ log[1] }}</span>
                </td>
                <td>{{ log[2] or '-' }}</td>
                <td>
                    <i class="fas fa-user"></i> {{ log[3] or 'System' }}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% else %}
<div class="alert alert-info">
    <i class="fas fa-info-circle"></i> 目前沒有任何日誌記錄
</div>
{% endif %}
{% endblock %}'''
    
    with open(os.path.join(template_dir, 'logs.html'), 'w', encoding='utf-8') as f:
        f.write(logs_template)
    
    # Bot 狀態頁面
    bot_status_template = '''{% extends "base.html" %}
{% block title %}Bot 狀態監控{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4">
    <h2><i class="fas fa-robot"></i> Bot 狀態監控</h2>
    <a href="{{ url_for('index') }}" class="btn btn-secondary">
        <i class="fas fa-arrow-left"></i> 返回儀表板
    </a>
</div>

<div class="row">
    <div class="col-md-3">
        <div class="card text-white {% if status.online %}bg-success{% else %}bg-danger{% endif %}">
            <div class="card-body text-center">
                <i class="fas fa-power-off fa-3x mb-3"></i>
                <h4>{% if status.online %}線上{% else %}離線{% endif %}</h4>
                <p>Bot 連線狀態</p>
            </div>
        </div>
    </div>
    
    <div class="col-md-3">
        <div class="card text-white bg-info">
            <div class="card-body text-center">
                <i class="fas fa-server fa-3x mb-3"></i>
                <h4>{{ status.guilds }}</h4>
                <p>伺服器數量</p>
            </div>
        </div>
    </div>
    
    <div class="col-md-3">
        <div class="card text-white bg-warning">
            <div class="card-body text-center">
                <i class="fas fa-users fa-3x mb-3"></i>
                <h4>{{ status.users }}</h4>
                <p>用戶總數</p>
            </div>
        </div>
    </div>
    
    <div class="col-md-3">
        <div class="card text-white bg-primary">
            <div class="card-body text-center">
                <i class="fas fa-terminal fa-3x mb-3"></i>
                <h4>{{ status.commands }}</h4>
                <p>指令數量</p>
            </div>
        </div>
    </div>
</div>

<div class="row mt-4">
    <div class="col-12">
        <div class="card">
            <div class="card-header">
                <h5><i class="fas fa-info-circle"></i> 系統資訊</h5>
            </div>
            <div class="card-body">
                <table class="table table-borderless">
                    <tr>
                        <td><strong>版本：</strong></td>
                        <td>{{ version }}</td>
                    </tr>
                    <tr>
                        <td><strong>運行狀態：</strong></td>
                        <td>
                            {% if status.online %}
                                <span class="badge bg-success">正常運行</span>
                            {% else %}
                                <span class="badge bg-danger">連線中斷</span>
                            {% endif %}
                        </td>
                    </tr>
                    <tr>
                        <td><strong>管理後台：</strong></td>
                        <td><span class="badge bg-info">已啟動</span></td>
                    </tr>
                </table>
            </div>
        </div>
    </div>
</div>

<script>
// 每30秒自動重新整理狀態
setTimeout(function() {
    location.reload();
}, 30000);
</script>
{% endblock %}'''
    
    with open(os.path.join(template_dir, 'bot_status.html'), 'w', encoding='utf-8') as f:
        f.write(bot_status_template)
    
    print("✅ 所有模板文件已創建完成！")

# 執行創建模板
if __name__ == "__main__":
    create_all_templates()