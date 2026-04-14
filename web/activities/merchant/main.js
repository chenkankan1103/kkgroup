// activities/merchant/main.js
// Minimal Discord Activities SDK integration

import { createActivity } from '@discord/activities';

const balanceEl = document.getElementById('balance');
const betBtn = document.getElementById('bet50');
let userId;

// helper functions to call backend
async function fetchBalance() {
    const res = await fetch(`/api/balance?user_id=${userId}`);
    const data = await res.json();
    return data.balance;
}

async function bet(amount) {
    const res = await fetch(`/api/bet`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ user_id: userId, amount })
    });
    return res.json();
}

async function refresh() {
    const bal = await fetchBalance();
    balanceEl.textContent = bal;
}

// activities sdk initialization
const activity = createActivity({
    name: 'Merchant Demo',
    description: 'Bet KKcoin with the village merchant',
    icon: '',
    onStart(context) {
        // Discord provides user info in context
        userId = context.user.id;
        refresh();
    },
    onMessage(message) {
        // optionally handle messages from bot
        console.log('message from bot:', message);
    }
});

activity.start();

betBtn.addEventListener('click', async () => {
    const result = await bet(50);
    if (result.success) {
        await refresh();
        alert('Bet placed!');
    } else {
        alert('Error: ' + result.error);
    }
});
