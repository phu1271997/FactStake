import { createClient, createAccount } from 'genlayer-js';
import { localnet, testnetAsimov, testnetBradbury, studionet } from 'genlayer-js/chains';

// State management
let client = null;
let currentAccount = null;
let factoryAddress = '';
let activeMarketAddress = null;
let marketsList = [];
let activeMarketDetails = null;
let activeMarketUserState = null;

// ABI Definitions (matching our Python signature structures)
const FACTORY_ABI = [
  {
    name: 'create_market',
    type: 'function',
    inputs: [
      { name: 'claim', type: 'string' },
      { name: 'close_delay', type: 'uint256' },
      { name: 'urls', type: 'string[]' },
      { name: 'bond_amount', type: 'uint256' }
    ],
    outputs: [{ name: '', type: 'address' }]
  },
  {
    name: 'get_markets',
    type: 'function',
    inputs: [],
    outputs: [{ name: '', type: 'address[]' }]
  }
];

const MARKET_ABI = [
  {
    name: 'stake',
    type: 'function',
    inputs: [{ name: 'vote_yes', type: 'bool' }],
    outputs: []
  },
  {
    name: 'resolve',
    type: 'function',
    inputs: [],
    outputs: []
  },
  {
    name: 'appeal',
    type: 'function',
    inputs: [],
    outputs: []
  },
  {
    name: 'resolve_appeal',
    type: 'function',
    inputs: [],
    outputs: []
  },
  {
    name: 'claim_winnings',
    type: 'function',
    inputs: [],
    outputs: []
  },
  {
    name: 'get_details',
    type: 'function',
    inputs: [],
    outputs: [{ name: '', type: 'string' }]
  },
  {
    name: 'get_user_state',
    type: 'function',
    inputs: [{ name: 'user', type: 'address' }],
    outputs: [{ name: '', type: 'string' }]
  }
];

// Initialize on page load
window.addEventListener('DOMContentLoaded', () => {
  initWallet();
  connectChain();
  setupEventListeners();
  
  // Try to load factory address from storage or default to deployed contract address
  const defaultFactory = '0xc11678bBCb76652031b4017a581123739495e17D';
  const storedFactory = localStorage.getItem('FACTSTAKE_FACTORY_ADDR') || defaultFactory;
  
  document.getElementById('factory-address-input').value = storedFactory;
  factoryAddress = storedFactory;
  loadMarkets();
});

// Setup wallet account (generate or read from localStorage)
function initWallet() {
  let storedKey = localStorage.getItem('FACTSTAKE_PRIVATE_KEY');
  if (!storedKey) {
    const acc = createAccount();
    storedKey = acc.privateKey;
    localStorage.setItem('FACTSTAKE_PRIVATE_KEY', storedKey);
  }
  try {
    currentAccount = createAccount(storedKey);
    document.getElementById('wallet-address').textContent = `${currentAccount.address.slice(0, 6)}...${currentAccount.address.slice(-4)}`;
    document.getElementById('pk-display').value = storedKey;
  } catch (e) {
    console.error("Wallet init failed", e);
    showNotification("Failed to initialize wallet", "error");
  }
}

// Connect to Chain Client
function connectChain() {
  const chainSelect = document.getElementById('chain-select').value;
  let chainObj = studionet;
  if (chainSelect === 'simulator') chainObj = localnet;
  if (chainSelect === 'asimov') chainObj = testnetAsimov;
  if (chainSelect === 'bradbury') chainObj = testnetBradbury;

  try {
    client = createClient({
      chain: chainObj,
      account: currentAccount
    });
    showNotification(`Connected to ${chainSelect.toUpperCase()}`);
  } catch (e) {
    console.error(e);
    showNotification("Chain connection error", "error");
  }
}

// Listeners setup
function setupEventListeners() {
  document.getElementById('chain-select').addEventListener('change', () => {
    connectChain();
    if (factoryAddress) loadMarkets();
  });
  
  document.getElementById('btn-save-factory').addEventListener('click', () => {
    const val = document.getElementById('factory-address-input').value.trim();
    if (val) {
      factoryAddress = val;
      localStorage.setItem('FACTSTAKE_FACTORY_ADDR', val);
      showNotification("Factory address updated!");
      loadMarkets();
    }
  });

  document.getElementById('btn-update-pk').addEventListener('click', () => {
    const pk = document.getElementById('pk-display').value.trim();
    if (pk) {
      localStorage.setItem('FACTSTAKE_PRIVATE_KEY', pk);
      initWallet();
      connectChain();
      showNotification("Wallet imported successfully!");
    } else {
      showNotification("Please enter a private key first", "warning");
    }
  });

  document.getElementById('create-market-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    await createMarket();
  });

  document.getElementById('btn-refresh-markets').addEventListener('click', loadMarkets);
  
  // Staking buttons
  document.getElementById('btn-stake-yes').addEventListener('click', () => stake(true));
  document.getElementById('btn-stake-no').addEventListener('click', () => stake(false));

  // Action buttons
  document.getElementById('btn-resolve').addEventListener('click', resolveMarket);
  document.getElementById('btn-appeal').addEventListener('click', appealMarket);
  document.getElementById('btn-resolve-appeal').addEventListener('click', resolveAppealMarket);
  document.getElementById('btn-claim').addEventListener('click', claimWinnings);
}

// Fetch all markets from factory
async function loadMarkets() {
  if (!factoryAddress) {
    showNotification("Please set a factory address first", "warning");
    return;
  }

  const listContainer = document.getElementById('markets-list');
  listContainer.innerHTML = '<div class="empty-state loading-pulse">Fetching markets from GenLayer...</div>';

  try {
    const markets = await client.readContract({
      address: factoryAddress,
      abi: FACTORY_ABI,
      functionName: 'get_markets',
      args: []
    });

    marketsList = markets || [];
    
    if (marketsList.length === 0) {
      listContainer.innerHTML = '<div class="empty-state">No prediction markets created yet.</div>';
      return;
    }

    listContainer.innerHTML = '';
    for (let i = marketsList.length - 1; i >= 0; i--) {
      const addr = marketsList[i];
      const details = await fetchMarketDetails(addr);
      
      const card = document.createElement('div');
      card.className = `market-card ${activeMarketAddress === addr ? 'active' : ''}`;
      card.dataset.address = addr;
      
      let badgeClass = 'badge-open';
      let statusText = 'OPEN';
      if (details.resolved) {
        statusText = details.verdict;
        badgeClass = 'badge-resolved';
      }
      if (details.appeal_bonded && !details.appeal_resolved) {
        statusText = 'APPEALED';
        badgeClass = 'badge-appealed';
      }

      card.innerHTML = `
        <div class="market-card-header">
          <span class="badge ${badgeClass}">${statusText}</span>
          <span style="font-size:0.75rem; color:var(--text-muted);">${addr.slice(0, 6)}...${addr.slice(-4)}</span>
        </div>
        <div class="market-card-title">${escapeHTML(details.claim)}</div>
        <div class="market-card-pools">
          <div class="pool-info">
            <span class="pool-dot yes"></span>
            <span>YES: ${formatGEN(details.yes_pool)}</span>
          </div>
          <div class="pool-info">
            <span class="pool-dot no"></span>
            <span>NO: ${formatGEN(details.no_pool)}</span>
          </div>
        </div>
      `;

      card.addEventListener('click', () => selectMarket(addr));
      listContainer.appendChild(card);
    }
  } catch (e) {
    console.error(e);
    listContainer.innerHTML = '<div class="empty-state">Error loading markets. Verify address and network.</div>';
  }
}

// Fetch individual market details using get_details
async function fetchMarketDetails(address) {
  try {
    const detailsStr = await client.readContract({
      address: address,
      abi: MARKET_ABI,
      functionName: 'get_details',
      args: []
    });
    return JSON.parse(detailsStr);
  } catch (e) {
    console.error("Error fetching details for " + address, e);
    return { claim: 'Error loading market', yes_pool: '0', no_pool: '0', resolved: false, verdict: 'ERROR' };
  }
}

// Select a market to display details
async function selectMarket(address) {
  activeMarketAddress = address;
  
  // Highlight active card
  document.querySelectorAll('.market-card').forEach(card => {
    if (card.dataset.address === address) {
      card.classList.add('active');
    } else {
      card.classList.remove('active');
    }
  });

  await refreshActiveMarket();
}

// Refresh details of the currently selected market
async function refreshActiveMarket() {
  if (!activeMarketAddress) return;

  const detailsContainer = document.getElementById('active-market-details');
  detailsContainer.innerHTML = '<div class="empty-state loading-pulse">Refreshing market state...</div>';

  try {
    activeMarketDetails = await fetchMarketDetails(activeMarketAddress);
    
    // Fetch active user state
    const userStateStr = await client.readContract({
      address: activeMarketAddress,
      abi: MARKET_ABI,
      functionName: 'get_user_state',
      args: [currentAccount.address]
    });
    activeMarketUserState = JSON.parse(userStateStr);

    renderActiveMarket();
  } catch (e) {
    console.error(e);
    detailsContainer.innerHTML = '<div class="empty-state">Error loading details.</div>';
  }
}

// Render active market details
function renderActiveMarket() {
  const container = document.getElementById('active-market-details');
  const d = activeMarketDetails;
  const u = activeMarketUserState;
  
  let statusText = 'OPEN';
  let badgeClass = 'badge-open';
  if (d.resolved) {
    statusText = `RESOLVED: ${d.verdict}`;
    badgeClass = 'badge-resolved';
  }
  if (d.appeal_bonded && !d.appeal_resolved) {
    statusText = 'APPEALED (WAITING TRIBUNAL)';
    badgeClass = 'badge-appealed';
  }

  const isClosed = Math.floor(Date.now() / 1000) >= Number(d.close_time);
  
  let actionsHTML = '';
  
  // Case: Open for staking
  if (!d.resolved && !isClosed) {
    actionsHTML = `
      <div class="stake-controls">
        <div class="stake-input-container">
          <input type="number" id="stake-amount-input" class="form-input" placeholder="Amount in GEN" min="1" step="any" value="10">
        </div>
        <div class="stake-buttons">
          <button id="btn-stake-yes" class="stake-btn yes">Stake YES</button>
          <button id="btn-stake-no" class="stake-btn no">Stake NO</button>
        </div>
      </div>
    `;
  }
  
  // Case: Closed for staking, waiting resolution
  if (!d.resolved && isClosed) {
    actionsHTML = `
      <div style="text-align:center; padding:1.5rem; background:rgba(255,255,255,0.02); border-radius:0.75rem; border:1px solid var(--panel-border); margin-bottom:1.5rem;">
        <p style="color:var(--text-secondary); margin-bottom:1rem;">Staking closed. Waiting for resolution.</p>
        <button id="btn-resolve" class="primary-btn">Trigger AI Resolution</button>
      </div>
    `;
  }

  // Case: Initial Resolution complete
  let resolutionHTML = '';
  let appealHTML = '';
  if (d.resolved) {
    let verdictClass = 'unresolvable-outcome';
    if (d.verdict === 'TRUE') verdictClass = 'true-outcome';
    if (d.verdict === 'FALSE') verdictClass = 'false-outcome';

    resolutionHTML = `
      <div class="resolution-box">
        <div class="resolution-title">Verdict Settled by AI Oracle</div>
        <div class="resolution-verdict ${verdictClass}">${d.verdict}</div>
        <div class="resolution-rationale">${escapeHTML(d.rationale)}</div>
      </div>
    `;

    // Appeal window open & not appealed yet
    const isAppealDeadlinePassed = Math.floor(Date.now() / 1000) >= Number(d.appeal_deadline);
    if (!d.appeal_bonded && !isAppealDeadlinePassed) {
      appealHTML = `
        <div class="appeal-box">
          <div class="appeal-title">Dispute Verdict?</div>
          <p class="appeal-description">Disagree with the LLM consensus? Stake an appeal bond of <strong>${formatGEN(d.appeal_bond_amount)}</strong> to force a senior tribunal re-evaluation with stricter reasoning rules.</p>
          <button id="btn-appeal" class="appeal-btn">Stake Appeal Bond</button>
        </div>
      `;
    }
  }

  // Case: Appealed, waiting tribunal
  if (d.appeal_bonded && !d.appeal_resolved) {
    appealHTML = `
      <div class="appeal-box">
        <div class="appeal-title">Tribunal Pending</div>
        <p class="appeal-description">This market has been appealed. The senior tribunal must run a stricter nondet resolution process.</p>
        <button id="btn-resolve-appeal" class="primary-btn" style="margin-top:0;">Resolve Appeal</button>
      </div>
    `;
  }

  // User stakes & Claim button
  let claimHTML = '';
  const totalStaked = Number(u.yes_stake) + Number(u.no_stake);
  if (totalStaked > 0) {
    const isClaimable = d.resolved && (d.appeal_resolved || (!d.appeal_bonded && Math.floor(Date.now() / 1000) >= Number(d.appeal_deadline)));
    const claimBtnDisabled = !isClaimable || u.claimed;
    
    claimHTML = `
      <div class="user-state-card">
        <div class="user-state-info">
          <div class="user-state-row">Your Staked YES: <span>${formatGEN(u.yes_stake)}</span></div>
          <div class="user-state-row">Your Staked NO: <span>${formatGEN(u.no_stake)}</span></div>
          <div class="user-state-row">Claim Status: <span style="color:${u.claimed ? 'var(--color-yes)' : 'var(--color-pending)'}">${u.claimed ? 'Claimed' : 'Unclaimed'}</span></div>
        </div>
        <button id="btn-claim" class="claim-btn" ${claimBtnDisabled ? 'disabled' : ''}>
          ${u.claimed ? 'Claimed' : 'Claim Winnings'}
        </button>
      </div>
    `;
  }

  container.innerHTML = `
    <div class="details-header">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
        <span class="badge ${badgeClass}">${statusText}</span>
        <span style="font-size:0.8rem; color:var(--text-muted);">Contract: ${activeMarketAddress}</span>
      </div>
      <div class="details-claim">${escapeHTML(d.claim)}</div>
      <div class="details-status-bar">
        <span>Close: ${new Date(Number(d.close_time) * 1000).toLocaleString()}</span>
        ${d.resolved ? `<span>Appeal Deadline: ${new Date(Number(d.appeal_deadline) * 1000).toLocaleTimeString()}</span>` : ''}
      </div>
    </div>

    <div class="details-pools-action">
      <div class="pool-box">
        <div class="pool-box-title">YES Pool</div>
        <div class="pool-box-value yes">${formatGEN(d.yes_pool)}</div>
      </div>
      <div class="pool-box">
        <div class="pool-box-title">NO Pool</div>
        <div class="pool-box-value no">${formatGEN(d.no_pool)}</div>
      </div>
    </div>

    ${actionsHTML}
    ${resolutionHTML}
    ${appealHTML}
    ${claimHTML}
  `;

  // Re-bind dynamically rendered element listeners
  if (document.getElementById('btn-stake-yes')) {
    document.getElementById('btn-stake-yes').addEventListener('click', () => stake(true));
    document.getElementById('btn-stake-no').addEventListener('click', () => stake(false));
  }
  if (document.getElementById('btn-resolve')) {
    document.getElementById('btn-resolve').addEventListener('click', resolveMarket);
  }
  if (document.getElementById('btn-appeal')) {
    document.getElementById('btn-appeal').addEventListener('click', appealMarket);
  }
  if (document.getElementById('btn-resolve-appeal')) {
    document.getElementById('btn-resolve-appeal').addEventListener('click', resolveAppealMarket);
  }
  if (document.getElementById('btn-claim')) {
    document.getElementById('btn-claim').addEventListener('click', claimWinnings);
  }
}

// Submit transaction to create a new market via Factory
async function createMarket() {
  const claim = document.getElementById('claim-input').value.trim();
  const delay = parseInt(document.getElementById('delay-input').value);
  const urlsText = document.getElementById('urls-input').value;
  const bond = parseFloat(document.getElementById('bond-input').value);

  if (!claim || isNaN(delay) || isNaN(bond)) {
    showNotification("Please fill in all creation fields", "warning");
    return;
  }

  const urls = urlsText.split('\n').map(u => u.trim()).filter(u => u.length > 0);
  if (urls.length === 0) {
    showNotification("Provide at least one search source URL", "warning");
    return;
  }

  const btn = document.getElementById('btn-create-market');
  btn.disabled = true;
  btn.textContent = "Deploying Market...";

  try {
    // Send deploy transaction
    // Convert bond amount to standard token value (1 GEN = 1000 units for easy integer math if needed)
    // Let's assume 1:1 format (value unit = wei size) or use simple integers:
    const bondVal = BigInt(bond * 1000);
    const txHash = await client.writeContract({
      address: factoryAddress,
      abi: FACTORY_ABI,
      functionName: 'create_market',
      args: [claim, BigInt(delay), urls, bondVal]
    });

    showNotification("Transaction submitted. Awaiting consensus...");
    
    await client.waitForTransactionReceipt({ hash: txHash });
    showNotification("Market created successfully!");
    
    document.getElementById('create-market-form').reset();
    await loadMarkets();
  } catch (e) {
    console.error(e);
    showNotification("Deployment failed!", "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Create Market";
  }
}

// Stake YES or NO on the current active market
async function stake(voteYes) {
  const amtInput = document.getElementById('stake-amount-input');
  const amount = parseFloat(amtInput.value);
  
  if (isNaN(amount) || amount <= 0) {
    showNotification("Please enter a valid stake amount", "warning");
    return;
  }

  const btn = voteYes ? document.getElementById('btn-stake-yes') : document.getElementById('btn-stake-no');
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Submitting...";

  try {
    // GenLayer value transfers are configured as value in wei-equivalent (using BigInt)
    const tokenVal = BigInt(amount * 1000);
    const txHash = await client.writeContract({
      address: activeMarketAddress,
      abi: MARKET_ABI,
      functionName: 'stake',
      args: [voteYes],
      value: tokenVal
    });

    showNotification("Stake transaction sent. Mining...");
    await client.waitForTransactionReceipt({ hash: txHash });
    
    showNotification("Stake recorded!");
    amtInput.value = "10";
    await refreshActiveMarket();
    await loadMarkets();
  } catch (e) {
    console.error(e);
    showNotification("Staking transaction failed!", "error");
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

// Call resolve() to trigger LLM resolution
async function resolveMarket() {
  const btn = document.getElementById('btn-resolve');
  btn.disabled = true;
  btn.textContent = "Querying Web & AI (Awaiting Consensus)...";

  try {
    const txHash = await client.writeContract({
      address: activeMarketAddress,
      abi: MARKET_ABI,
      functionName: 'resolve',
      args: []
    });

    showNotification("Resolution tx mining. Awaiting validation...");
    await client.waitForTransactionReceipt({ hash: txHash });
    
    showNotification("Market resolved!");
    await refreshActiveMarket();
    await loadMarkets();
  } catch (e) {
    console.error(e);
    showNotification("Resolution transaction failed", "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Trigger AI Resolution";
  }
}

// Appeal the active market resolution
async function appealMarket() {
  const btn = document.getElementById('btn-appeal');
  btn.disabled = true;
  btn.textContent = "Appealing...";

  try {
    // Send appeal bond as value
    const bondAmount = BigInt(activeMarketDetails.appeal_bond_amount);
    const txHash = await client.writeContract({
      address: activeMarketAddress,
      abi: MARKET_ABI,
      functionName: 'appeal',
      args: [],
      value: bondAmount
    });

    showNotification("Appeal bond staked! Waiting to resolve...");
    await client.waitForTransactionReceipt({ hash: txHash });
    
    showNotification("Appeal successfully filed!");
    await refreshActiveMarket();
    await loadMarkets();
  } catch (e) {
    console.error(e);
    showNotification("Appeal staking failed", "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Stake Appeal Bond";
  }
}

// Resolve the appeal with stricter tribunal LLM
async function resolveAppealMarket() {
  const btn = document.getElementById('btn-resolve-appeal');
  btn.disabled = true;
  btn.textContent = "Executing Stricter Reasoning Prompt...";

  try {
    const txHash = await client.writeContract({
      address: activeMarketAddress,
      abi: MARKET_ABI,
      functionName: 'resolve_appeal',
      args: []
    });

    showNotification("Tribunal tx mining...");
    await client.waitForTransactionReceipt({ hash: txHash });
    
    showNotification("Appeal resolved by tribunal!");
    await refreshActiveMarket();
    await loadMarkets();
  } catch (e) {
    console.error(e);
    showNotification("Appeal resolution failed", "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Resolve Appeal";
  }
}

// Claim winnings from a resolved market
async function claimWinnings() {
  const btn = document.getElementById('btn-claim');
  btn.disabled = true;
  btn.textContent = "Claiming...";

  try {
    const txHash = await client.writeContract({
      address: activeMarketAddress,
      abi: MARKET_ABI,
      functionName: 'claim_winnings',
      args: []
    });

    showNotification("Claiming transaction mining...");
    await client.waitForTransactionReceipt({ hash: txHash });
    
    showNotification("Winnings transferred to your wallet!");
    await refreshActiveMarket();
  } catch (e) {
    console.error(e);
    showNotification("Claim transaction failed", "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Claim Winnings";
  }
}

// Notification helpers
function showNotification(msg, type = "success") {
  const existing = document.querySelector('.notification');
  if (existing) existing.remove();

  const notif = document.createElement('div');
  notif.className = `notification`;
  
  let borderColor = 'var(--panel-border)';
  if (type === 'error') borderColor = 'rgba(239, 68, 68, 0.4)';
  if (type === 'warning') borderColor = 'rgba(245, 158, 11, 0.4)';
  notif.style.borderColor = borderColor;

  notif.textContent = msg;
  document.body.appendChild(notif);

  setTimeout(() => {
    notif.remove();
  }, 4000);
}

// Formatting helpers
function formatGEN(val) {
  const num = Number(val) / 1000;
  return `${num.toFixed(1)} GEN`;
}

function escapeHTML(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
