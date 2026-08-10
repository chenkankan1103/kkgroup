/**
 * KK 群紙娃娃 RPG 遊戲 - JavaScript 主邏輯
 * 負責 UI 互動、API 通訊、數據管理
 */

// ==================== 全局變量 ====================
let currentUserId = null;
let currentUserData = null;
let currentInventory = null;
let paperdollShop = null;

// ==================== 初始化 ====================
document.addEventListener('DOMContentLoaded', async () => {
    console.log('🎮 KK 群紙娃娃 RPG 遊戲初始化...');

    // 從 URL 參數或 localStorage 獲取用戶 ID
    const params = new URLSearchParams(window.location.search);
    currentUserId = params.get('user_id') || localStorage.getItem('currentUserId');

    if (!currentUserId) {
        showLoginPrompt();
        return;
    }

    localStorage.setItem('currentUserId', currentUserId);

    // 載入紙娃娃商銷並初始化 UI
    await loadPaperdollShop();
    await loadUserData();
    attachEventListeners();
});

// ==================== 載入用戶數據 ====================
async function loadUserData() {
    try {
        const response = await fetch(`/api/game/user/${currentUserId}/paperdoll`);
        if (!response.ok) throw new Error('Failed to load user data');

        currentUserData = await response.json();
        console.log('✅ 用戶數據載入:', currentUserData);

        // 更新 UI
        updateUserUI();
        updateCharacterImage();
        await loadUserInventory();
    } catch (error) {
        console.error('❌ 載入用戶數據失敗:', error);
        showNotification('無法載入用戶數據', 'error');
    }
}

async function loadUserInventory() {
    try {
        const response = await fetch(`/api/game/user/${currentUserId}/inventory`);
        if (!response.ok) throw new Error('Failed to load inventory');

        currentInventory = await response.json();
        console.log('✅ 庫存數據載入:', currentInventory);
    } catch (error) {
        console.error('❌ 載入庫存失敗:', error);
    }
}

// ==================== 更新 UI ====================
function updateUserUI() {
    if (!currentUserData) return;

    const { nickname, level, stats, paperdoll } = currentUserData;

    // 更新頭部
    document.getElementById('user-name').textContent = nickname || '玩家';
    document.getElementById('user-level').textContent = `Lv. ${level}`;

    // 更新左側角色名稱
    document.getElementById('character-name').textContent = nickname || '角色';

    // 更新右側屬性面板
    document.getElementById('stat-level').textContent = level;
    document.getElementById('stat-kkcoin').textContent = formatNumber(stats?.kkcoin || 0);

    // 計算經驗值進度
    const nextLevelExp = level * 1000;
    const currentExp = stats?.experience || 0;
    const expPercent = Math.min((currentExp % nextLevelExp) / nextLevelExp * 100, 100);
    const expDisplay = `${formatNumber(currentExp % nextLevelExp)}/${formatNumber(nextLevelExp)}`;

    document.getElementById('exp-fill').style.width = expPercent + '%';
    document.getElementById('exp-text').textContent = expDisplay;

    // 更新裝備欄
    updateEquipmentDisplay(paperdoll);
}

function updateEquipmentDisplay(paperdoll) {
    if (!paperdoll) return;

    const equipmentNames = {
        face: `臉 #${paperdoll.face || '-'}`,
        hair: `髮 #${paperdoll.hair || '-'}`,
        top: `上衣 #${paperdoll.top || '-'}`,
        bottom: `下衣 #${paperdoll.bottom || '-'}`,
        shoes: `鞋 #${paperdoll.shoes || '-'}`
    };

    Object.keys(equipmentNames).forEach(key => {
        const element = document.getElementById(`eq-${key}`);
        if (element) {
            element.textContent = equipmentNames[key];
        }
    });
}

async function updateCharacterImage() {
    const img = document.getElementById('character-image');
    if (!img || !currentUserId) return;

    try {
        img.src = `/api/game/user/${currentUserId}/paperdoll/image?cache=true&t=${Date.now()}`;
        img.onerror = () => {
            console.error('❌ 無法載入角色圖像');
            img.src = '/static/images/placeholder.png';
        };
    } catch (error) {
        console.error('❌ 更新角色圖像失敗:', error);
    }
}

// ==================== 事件監聽 ====================
function attachEventListeners() {
    // 菜單按鈕
    document.getElementById('btn-wardrobe').addEventListener('click', () => openWardrobe());
    document.getElementById('btn-profile').addEventListener('click', () => openProfile());
    document.getElementById('btn-shop').addEventListener('click', () => openShop());
    document.getElementById('btn-battle').addEventListener('click', () => openBattle());

    // 模態窗口背景點擊關閉
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.remove('active');
            }
        });
    });
}

// ==================== 模態窗口操作 ====================
function openModal(modalId) {
    const modal = document.getElementById(`modal-${modalId}`);
    if (modal) {
        modal.classList.add('active');
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(`modal-${modalId}`);
    if (modal) {
        modal.classList.remove('active');
    }
}

// ==================== 衣櫃功能 ====================
async function openWardrobe() {
    console.log('📂 打開衣櫃...');
    openModal('wardrobe');

    if (!currentInventory) {
        await loadUserInventory();
    }

    renderWardrobeCategoriesSync();
}

function renderWardrobeCategoriesSync() {
    if (!currentInventory || !currentInventory.inventory) return;

    const container = document.getElementById('wardrobe-categories');
    container.innerHTML = '';

    const categories = {
        face: '👤 臉',
        hair: '💇 髮型',
        top: '👕 上衣',
        bottom: '👖 下衣',
        shoes: '👟 鞋'
    };

    const equipped = currentInventory.equipped || {};

    Object.entries(categories).forEach(([category, label]) => {
        const items = currentInventory.inventory[category] || [];

        const section = document.createElement('div');
        section.className = 'category-section';
        section.innerHTML = `<div class="category-label">${label}</div>`;

        const itemsContainer = document.createElement('div');
        itemsContainer.className = 'category-items';

        items.forEach(itemId => {
            const btn = document.createElement('button');
            btn.className = 'item-button';
            if (equipped[category] === itemId) {
                btn.classList.add('equipped');
            }
            btn.textContent = `#${itemId}`;
            btn.onclick = () => changePaperdollPart(category, itemId);
            itemsContainer.appendChild(btn);
        });

        section.appendChild(itemsContainer);
        container.appendChild(section);
    });
}

async function changePaperdollPart(category, itemId) {
    try {
        const response = await fetch(`/api/game/user/${currentUserId}/paperdoll/change`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                category: category,
                item_id: itemId
            })
        });

        if (!response.ok) throw new Error('Failed to change paperdoll');

        const result = await response.json();
        console.log('✅ 紙娃娃部位已更改:', result);

        // 更新本地數據
        await loadUserData();
        renderWardrobeCategoriesSync();
        showNotification(`✅ 已更改${category}`, 'success');
    } catch (error) {
        console.error('❌ 更改失敗:', error);
        showNotification('更改失敗', 'error');
    }
}

// ==================== 檔案功能 ====================
async function openProfile() {
    console.log('📊 打開檔案...');
    openModal('profile');

    const content = document.getElementById('profile-content');
    if (!currentUserData) return;

    const { nickname, level, stats } = currentUserData;
    content.innerHTML = `
        <div style="text-align: center;">
            <h3>${nickname}</h3>
            <div style="margin: 20px 0; padding: 20px; background: #f0f0f0; border-radius: 8px;">
                <div style="margin: 10px 0;">
                    <strong>等級:</strong> ${level}
                </div>
                <div style="margin: 10px 0;">
                    <strong>經驗值:</strong> ${formatNumber(stats?.experience || 0)}
                </div>
                <div style="margin: 10px 0;">
                    <strong>KKcoin:</strong> ${formatNumber(stats?.kkcoin || 0)}
                </div>
                <div style="margin: 10px 0;">
                    <strong>成就:</strong> ${stats?.achievements || 0}
                </div>
            </div>
        </div>
    `;
}

// ==================== 商店功能 ====================
async function openShop() {
    console.log('🛍️ 打開商店...');
    openModal('shop');

    if (!paperdollShop) {
        await loadPaperdollShop();
    }

    renderShopItems();
}

async function loadPaperdollShop() {
    // 示例商店數據，實際應該從後端獲取
    paperdollShop = {
        face: [
            { id: 20000, name: '新秀臉', price: 100 },
            { id: 20005, name: '自信臉', price: 100 },
            { id: 21731, name: '可愛臉', price: 150 }
        ],
        hair: [
            { id: 30000, name: '清爽短髮', price: 150 },
            { id: 30120, name: '蓬鬆短髮', price: 150 },
            { id: 34410, name: '齊肩長髮', price: 200 }
        ],
        top: [
            { id: 1040010, name: '白色T恤', price: 80 },
            { id: 1040014, name: '黑色上衣', price: 100 },
            { id: 1041004, name: '正式西裝', price: 300 }
        ],
        bottom: [
            { id: 1060096, name: '標準褲子', price: 100 },
            { id: 1061008, name: '短裙', price: 150 }
        ],
        shoes: [
            { id: 1072005, name: '黑色運動鞋', price: 80 },
            { id: 1072288, name: '棕色皮鞋', price: 100 }
        ]
    };
}

function renderShopItems() {
    const container = document.getElementById('shop-items');
    if (!paperdollShop) return;

    container.innerHTML = '';

    const categories = {
        face: '👤 臉',
        hair: '💇 髮型',
        top: '👕 上衣',
        bottom: '👖 下衣',
        shoes: '👟 鞋'
    };

    Object.entries(categories).forEach(([category, label]) => {
        const items = paperdollShop[category] || [];

        const section = document.createElement('div');
        section.className = 'category-section';
        section.style.marginBottom = '15px';
        section.innerHTML = `<div class="category-label">${label}</div>`;

        const itemsContainer = document.createElement('div');
        itemsContainer.className = 'category-items';

        items.forEach(item => {
            const btn = document.createElement('button');
            btn.className = 'item-button';
            btn.textContent = `${item.name} (${item.price}💰)`;
            btn.style.fontSize = '12px';
            btn.onclick = () => buyItem(category, item.id, item.price);
            itemsContainer.appendChild(btn);
        });

        section.appendChild(itemsContainer);
        container.appendChild(section);
    });
}

async function buyItem(category, itemId, price) {
    // 示例實現，實際應該調用後端 API
    showNotification(`購買失敗：功能開發中 (${price}💰)`, 'warning');
}

// ==================== 對戰功能 ====================
function openBattle() {
    console.log('⚔️ 開啟對戰...');
    const contentArea = document.getElementById('content-area');
    contentArea.innerHTML = `
        <div style="text-align: center; padding: 40px;">
            <h2>⚔️ 對戰系統</h2>
            <p>對戰功能開發中...</p>
            <p style="color: #999; font-size: 14px; margin-top: 20px;">
                敬請期待！
            </p>
        </div>
    `;
}

// ==================== 輔助函數 ====================
function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    }
    if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}

function showNotification(message, type = 'info') {
    // 簡單的通知系統
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 20px;
        background: ${type === 'error' ? '#e74c3c' : type === 'success' ? '#27ae60' : type === 'warning' ? '#f39c12' : '#3498db'};
        color: white;
        border-radius: 4px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        z-index: 2000;
        animation: slideInRight 0.3s ease;
    `;
    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

function showLoginPrompt() {
    const container = document.querySelector('.game-container');
    if (container) {
        container.innerHTML = `
            <div style="
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100vh;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            ">
                <div style="
                    background: white;
                    padding: 40px;
                    border-radius: 10px;
                    text-align: center;
                    box-shadow: 0 8px 16px rgba(0, 0, 0, 0.2);
                ">
                    <h2>🎮 KK 群紙娃娃 RPG</h2>
                    <p>請輸入你的用戶 ID 開始遊戲</p>
                    <input
                        type="text"
                        id="user-id-input"
                        placeholder="輸入 User ID"
                        style="
                            width: 100%;
                            padding: 10px;
                            margin: 15px 0;
                            border: 2px solid #3498db;
                            border-radius: 4px;
                            font-size: 16px;
                        "
                    />
                    <button
                        onclick="startGame()"
                        style="
                            width: 100%;
                            padding: 10px;
                            background: #3498db;
                            color: white;
                            border: none;
                            border-radius: 4px;
                            font-size: 16px;
                            font-weight: bold;
                            cursor: pointer;
                        "
                    >
                        開始遊戲
                    </button>
                </div>
            </div>
        `;
    }
}

function startGame() {
    const input = document.getElementById('user-id-input');
    const userId = input.value.trim();
    if (userId) {
        window.location.href = `?user_id=${userId}`;
    }
}

// ==================== CSS 動畫 ====================
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    @keyframes slideOutRight {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);
