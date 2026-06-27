// mc-bot/index.js
// Mineflayer HTTP service — Microsoft device-code auth, token in MongoDB
// Runs as a child process spawned by bot.py on startup

const mineflayer    = require('mineflayer')
const express       = require('express')
const { MongoClient } = require('mongodb')

const app = express()
app.use(express.json())

// ── MongoDB ───────────────────────────────────────────────────────────────────
const mongoClient = new MongoClient(process.env.MONGO_URI)
let db = null

async function connectMongo() {
  await mongoClient.connect()
  db = mongoClient.db('discord_bot')
  console.log('[MC-BOT] ✅ Connected to MongoDB')
}

async function saveToken(token) {
  await db.collection('mc_auth').updateOne(
    { _id: 'ms_token' },
    { $set: { token, updated_at: new Date() } },
    { upsert: true }
  )
}

async function loadToken() {
  const doc = await db.collection('mc_auth').findOne({ _id: 'ms_token' })
  return doc?.token ?? null
}

async function clearToken() {
  await db.collection('mc_auth').deleteOne({ _id: 'ms_token' })
}

// ── State ─────────────────────────────────────────────────────────────────────
let bot      = null
let botReady = false

// status: disconnected | awaiting_auth | awaiting_discord_auth | connecting | ready | error
let state = { status: 'disconnected', code: null, url: null, error: null }

function setState(patch) {
  state = { ...state, ...patch }
  console.log(`[MC-BOT] status → ${state.status}`)
}

// ── Bot ───────────────────────────────────────────────────────────────────────
let reconnectTimer = null

function scheduleReconnect(ms = 5000) {
  if (reconnectTimer) return
  reconnectTimer = setTimeout(async () => {
    reconnectTimer = null
    const token = await loadToken()
    startBot(token)
  }, ms)
}

function startBot(cachedToken = null) {
  if (bot) { try { bot.end() } catch(_) {} }
  bot      = null
  botReady = false
  setState({ status: 'connecting', code: null, url: null, error: null })

  const opts = {
    host:    process.env.MC_SERVER_HOST || 'play.donutsmp.net',
    version: process.env.MC_VERSION     || '1.21',
    auth:    'microsoft',
  }

  if (cachedToken) {
    opts.session = cachedToken
  } else {
    opts.onMsaCode = ({ user_code, verification_uri }) => {
      console.log(`[MC-BOT] Device code: ${user_code}  →  ${verification_uri}`)
      setState({ status: 'awaiting_auth', code: user_code, url: verification_uri, error: null })
    }
  }

  bot = mineflayer.createBot(opts)

  bot.on('spawn', async () => {
    botReady = true
    setState({ status: 'ready', code: null, url: null, error: null })
    // Persist token so next restart skips device-code
    if (bot._client?.session) {
      await saveToken(bot._client.session)
      console.log('[MC-BOT] 💾 Session token saved')
    }
  })

  bot.on('kicked', (reason) => {
    const msg = typeof reason === 'object' ? JSON.stringify(reason) : String(reason)
    console.log(`[MC-BOT] Kicked: ${msg}`)
    botReady = false

    // Donut SMP sends a kick when it's waiting for Discord auth
    const isAuthKick = msg.toLowerCase().includes('discord') ||
                       msg.toLowerCase().includes('verify') ||
                       msg.toLowerCase().includes('authoriz')

    if (isAuthKick) {
      setState({ status: 'awaiting_discord_auth', code: null, url: null, error: null })
    }
    // Don't auto-reconnect — wait for the "I Authorized" button
  })

  bot.on('error', (err) => {
    console.error('[MC-BOT] Error:', err.message)
    botReady = false
    setState({ status: 'error', code: null, url: null, error: err.message })
  })

  bot.on('end', (reason) => {
    console.log(`[MC-BOT] Disconnected: ${reason}`)
    botReady = false
    if (state.status !== 'awaiting_discord_auth') {
      setState({ status: 'disconnected', code: null, url: null, error: null })
      scheduleReconnect(15_000)
    }
  })
}

// ── Routes ────────────────────────────────────────────────────────────────────

app.get('/status', (_req, res) => res.json(state))

// Start fresh login (device-code flow)
app.post('/start-login', async (_req, res) => {
  if (botReady) return res.json({ ok: true, message: 'Already connected' })
  await clearToken()
  startBot(null)
  res.json({ ok: true })
})

// Called after user clicks "I Authorized" on the dashboard
app.post('/reconnect', (_req, res) => {
  console.log('[MC-BOT] Manual reconnect triggered')
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
  setState({ status: 'connecting', code: null, url: null, error: null })
  // Small delay so Donut SMP registers the auth before we reconnect
  setTimeout(async () => {
    const token = await loadToken()
    startBot(token)
  }, 2000)
  res.json({ ok: true })
})

// Logout — clear token and disconnect
app.post('/logout', async (_req, res) => {
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
  await clearToken()
  try { bot?.end() } catch(_) {}
  bot      = null
  botReady = false
  setState({ status: 'disconnected', code: null, url: null, error: null })
  res.json({ ok: true })
})

// Run an in-game command (called by Python bot)
app.post('/run-command', (req, res) => {
  const { command } = req.body
  if (!command || typeof command !== 'string')
    return res.status(400).json({ ok: false, error: 'Missing command' })
  if (!botReady || !bot)
    return res.status(503).json({ ok: false, error: 'MC bot not ready' })
  try {
    bot.chat(command)
    console.log(`[MC-BOT] ▶ ${command}`)
    res.json({ ok: true })
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message })
  }
})

// ── Start ─────────────────────────────────────────────────────────────────────
const PORT = parseInt(process.env.MC_BOT_PORT || '3001')

connectMongo().then(async () => {
  app.listen(PORT, '127.0.0.1', () =>
    console.log(`[MC-BOT] 🌐 Listening on 127.0.0.1:${PORT}`)
  )
  const token = await loadToken()
  if (token) {
    console.log('[MC-BOT] 🔄 Found saved token, connecting...')
    startBot(token)
  } else {
    console.log('[MC-BOT] ℹ️  No saved token — use the dashboard to log in.')
  }
}).catch(err => {
  console.error('[MC-BOT] ❌ MongoDB connection failed:', err)
  process.exit(1)
})
