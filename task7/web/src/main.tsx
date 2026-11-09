import React, { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { ArrowDownToLine, ArrowRight, ArrowUp, BookOpen, Check, ChevronDown, ChevronRight, Compass, ExternalLink, Footprints, History, Leaf, LoaderCircle, MapPin, Mountain, Plus, Route, Settings2, ShieldCheck, Sparkles, X } from 'lucide-react'
import './style.css'
import { GraphExplorer, GraphData } from './GraphExplorer'

type Source = { doc_id: string; title: string; url: string; source_type: string; quote?: string }
type Step = { order: number; day: number | null; pois: string[]; activity: string; time_text: string | null; time_period: string | null; visit_duration_text: string | null; source: Source }
type Advice = { pair_id: string; condition: string; recommendation: string; reason: string; user_evidence: string; review_status: string; sources: Source[] }
type Constraints = { scenic_spot: string | null; duration: string | null; travelers: string[]; preferences: string[]; must_visit: string[]; avoid: string[]; weather: string | null }
type Trace = { type: string; stage?: string; label?: string; name?: string; arguments?: unknown; result?: unknown }
type Result = { graph_selection?: string[]; status: 'ready' | 'clarification' | 'no_match' | 'error'; message: string; rationale?: string; request_id?: string; session_id?: string; constraints?: Constraints; steps?: Step[]; advice?: Advice[]; route?: { route_name: string; route_id: string; source_type: string }; sources?: Source[]; limitations?: string[]; trace?: Trace[]; model?: string }
type Message = { role: 'user' | 'assistant'; text: string; error?: boolean }
type Trip = { id: string; title: string; session_id?: string; messages: Message[]; result?: Result; lastMessage?: string }
type Health = { model_configured: boolean; model: string; stats: { nodes: number; edges: number } }

const places = [
  { name: '北京故宫', subtitle: '红墙黄瓦，漫步六百年', tag: '人文 · 建筑', kind: 'palace' },
  { name: '杭州西湖', subtitle: '山水之间，留一点闲适', tag: '湖畔 · 慢游', kind: 'lake' },
  { name: '九寨沟', subtitle: '沿着山谷，走进蓝绿色', tag: '自然 · 山谷', kind: 'mountain' },
]
const examples = ['带老人去九寨沟玩一天，希望轻松一些', '情侣去西湖游览一天，喜欢拍照', '带孩子去故宫玩半天，想看太和殿']
const stages = ['理解需求', '查询图谱', '检查方案', '生成行程']

function loadTrips(): Trip[] { try { return JSON.parse(localStorage.getItem('shanxing.trips') || '[]').slice(0, 12) } catch { return [] } }
function safeUrl(value: string) { try { const u = new URL(value); return ['http:', 'https:'].includes(u.protocol) ? u.href : undefined } catch { return undefined } }

function Landscape({ kind, large = false }: { kind: string; large?: boolean }) {
  return <svg className={`landscape ${large ? 'large' : ''}`} viewBox="0 0 600 330" fill="none" aria-hidden="true">
    <defs><linearGradient id={`sky-${kind}`} x2="0" y2="1"><stop stopColor={kind === 'palace' ? '#e9d9b7' : '#e1e9dd'} /><stop offset="1" stopColor="#f6f2e5" /></linearGradient></defs>
    <path fill={`url(#sky-${kind})`} d="M0 0h600v330H0z" />
    <circle cx={kind === 'palace' ? 470 : 450} cy="83" r="34" fill="#f8efcb" />
    {kind === 'palace' ? <>
      <path d="M0 225h600v105H0z" fill="#d1b88c" /><path d="M0 253h600v77H0z" fill="#bda889" />
      <path d="M110 183h380v93H110z" fill="#a35d48" /><path d="M151 155h298v105H151z" fill="#ad6650" />
      <path d="M124 160c35-3 67-19 83-36h186c16 17 48 33 83 36l-22 12H146z" fill="#967d47" />
      <path d="M150 122c37-2 68-22 88-44h124c20 22 51 42 88 44l-20 13H170z" fill="#b39755" />
      <path d="M188 121h224M158 158h284" stroke="#e3cb89" strokeWidth="4" />
      {[190, 238, 286, 334, 382].map(x => <path key={x} d={`M${x} 187h29v60h-29z`} fill="#70473b" />)}
      <path d="M258 267h84l56 63H202z" fill="#e1d4b9" /><path d="M25 267c8-42-2-61-3-91m0 37-21-16m22 0 15-19M558 287c-8-65 3-91 3-126m-1 47 25-25m-25-1-18-25" stroke="#68735b" strokeWidth="7" />
    </> : <>
      <path d="M0 187 95 73 160 142 266 56 350 159 459 64 600 183v147H0z" fill="#a4b5a1" />
      <path d="m0 230 110-94 110 70 126-97 98 106 101-57 55 44v128H0z" fill="#7d9987" />
      <path d="M0 264c122-72 181 39 296 7s180-58 304-12v71H0z" fill={kind === 'lake' ? '#b0c6b6' : '#78a9a3'} />
      <path d="M0 293c96-17 191 31 310 1s196-6 290-8M62 315c101-11 178 8 253-2" stroke="#d6e1cd" strokeWidth="2" />
      {kind === 'lake' ? <><path d="M166 268c19 17 57 17 76 0z" fill="#746f54" /><path d="M203 216v51m-2-49 30 40h-30z" stroke="#f0e4ca" fill="#f0e4ca" /><path d="M470 208h55v35h-55z" fill="#747f60" /><path d="m453 209 43-31 47 31z" fill="#566d57" /></> : <><path d="M329 188c-28 32-9 43 16 55s16 36-5 44" stroke="#d7e5cd" strokeWidth="13" /><path d="M0 276c60-45 87-33 121 8l-37 46H0zM600 245c-88-33-127 35-164 85h164z" fill="#526f60" /></>}
      <path d="M34 258v-83m0 8-26 37h52l-26-37m0 28-31 41h62l-31-41M560 254v-80m0 5-25 40h50l-25-40m0 30-32 44h64l-32-44" fill="#596f58" stroke="#596f58" strokeWidth="3" />
    </>}
    <path d="M0 328h600" stroke="#fff" strokeOpacity=".4" strokeWidth="3" />
  </svg>
}

function App() {
  const [trips, setTrips] = useState<Trip[]>(loadTrips)
  const [active, setActive] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [graphSelection, setGraphSelection] = useState<string[] | null>(null)
  const [graphLabel, setGraphLabel] = useState("浏览全部图谱，正在理解你的需求")
  const [showGraph, setShowGraph] = useState(true)
  const [events, setEvents] = useState<Trace[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [offline, setOffline] = useState(false)
  const [selectedSpot, setSelectedSpot] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [formTop, setFormTop] = useState<number | null>(null)
  const homeRef = useRef<HTMLElement>(null)
  const [duration, setDuration] = useState('一天')
  const [party, setParty] = useState('')
  const [mustVisit, setMustVisit] = useState('')
  const [avoid, setAvoid] = useState('')
  const [mobileTab, setMobileTab] = useState('chat')
  const [source, setSource] = useState<{ title: string; items: Source[]; review?: string } | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const bottom = useRef<HTMLDivElement>(null)
  const dialog = useRef<HTMLDivElement>(null)
  const opener = useRef<HTMLElement | null>(null)
  const trip = trips.find(t => t.id === active)
  const result = trip?.result
  const ready = result?.status === 'ready'

  useEffect(() => { try { localStorage.setItem('shanxing.trips', JSON.stringify(trips)) } catch { /* A full or disabled browser store must not break planning. */ } }, [trips])
  useEffect(() => { fetch('/api/graph').then(r => r.ok ? r.json() : null).then(setGraphData).catch(() => {}) }, [])
  useEffect(() => { fetch('/api/health').then(r => { if (!r.ok) throw new Error(); return r.json() }).then(setHealth).catch(() => setOffline(true)) }, [])
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }) }, [trip?.messages.length, events.length])
  useEffect(() => {
    if (!source) return
    opener.current = document.activeElement as HTMLElement
    dialog.current?.querySelector<HTMLButtonElement>('button')?.focus()
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSource(null)
      if (e.key === 'Tab') {
        const focusable = dialog.current?.querySelectorAll<HTMLElement>('button, a[href]')
        if (!focusable?.length) return
        const first = focusable[0], last = focusable[focusable.length - 1]
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
      }
    }
    document.addEventListener('keydown', handler)
    return () => { document.removeEventListener('keydown', handler); opener.current?.focus() }
  }, [source])

  function togglePreferences() {
    if (!showForm && homeRef.current) {
      const intro = homeRef.current.querySelector('.home-intro')
      if (intro) setFormTop(intro.getBoundingClientRect().top - homeRef.current.getBoundingClientRect().top)
    }
    setShowForm(value => !value)
  }
  function update(id: string, fn: (t: Trip) => Trip) { setTrips(all => all.map(t => t.id === id ? fn(t) : t)) }
  function newTrip() { if (busy) return; setActive(null); setInput(''); setEvents([]); setSelectedSpot(''); setShowHistory(false); setMobileTab('chat') }
  async function submit(text = input, useHomeOptions = true) {
    if (busy || !text.trim()) return
    let message = text.trim()
    if (useHomeOptions && !trip && selectedSpot && !/故宫|西湖|九寨沟/.test(message)) message = `${selectedSpot}，${message}`
    if (useHomeOptions && showForm && !trip) message += `；游览${duration}${party ? `；同行：${party}` : ''}${mustVisit ? `；必去：${mustVisit}` : ''}${avoid ? `；避开：${avoid}` : ''}`
    const current: Trip = trip || { id: crypto.randomUUID(), title: message.slice(0, 24), messages: [] }
    if (!trip) { setTrips(all => [current, ...all].slice(0, 12)); setActive(current.id) }
    update(current.id, t => ({ ...t, messages: [...t.messages, { role: 'user', text: message }], lastMessage: message }))
    setInput(''); setBusy(true); setEvents([]); setMobileTab('plan'); setGraphSelection(null); setGraphLabel('浏览全部图谱，正在理解你的需求'); setShowGraph(true)
    let completed = false
    try {
      const response = await fetch('/api/plan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message, session_id: current.session_id }) })
      if (!response.ok || !response.body) throw new Error(response.status === 409 ? '上一条需求仍在处理，请稍后重试。' : '暂时无法连接规划服务，请确认后台正在运行。')
      const reader = response.body.getReader(), decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { value, done } = await reader.read()
        buffer += decoder.decode(value, { stream: !done })
        const lines = buffer.split('\n'); buffer = lines.pop() || ''
        for (const line of lines) {
          if (!line.trim()) continue
          const event = JSON.parse(line)
          if (event.type === 'session') update(current.id, t => ({ ...t, session_id: event.session_id }))
          if (event.type === 'progress') { setEvents(prev => [...prev, event]); if (event.stage === 'graph') { setGraphSelection(event.node_ids); setGraphLabel(event.label) } }
          if (event.type === 'result') {
            const data = event.data as Result
            completed = true
            update(current.id, t => ({ ...t, session_id: data.session_id || t.session_id, result: data,
              messages: [...t.messages, { role: 'assistant', text: data.message, error: data.status === 'error' }] }))
            if (data.status === 'ready') setMobileTab('plan')
          }
        }
        if (done) break
      }
      if (!completed) throw new Error('连接意外中断，未收到完整方案，请重试。')
    } catch (error) {
      const message = error instanceof Error ? error.message : '请求失败，请重试。'
      update(current.id, t => ({ ...t, result: { status: 'error', message }, messages: [...t.messages, { role: 'assistant', text: message, error: true }] }))
    } finally { setBusy(false); setEvents([]); inputRef.current?.focus() }
  }
  function exportPlan() {
    if (!result) return
    if (result.request_id) {
      const a = document.createElement('a')
      a.href = `/api/export/${result.request_id}`
      a.download = `shanxing-${result.request_id.slice(0, 8)}.json`
      a.click()
      return
    }
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob), a = document.createElement('a')
    a.href = url; a.download = `山行_${result.constraints?.scenic_spot || '行程'}_${result.request_id?.slice(0, 8) || '结果'}.json`; a.click(); URL.revokeObjectURL(url)
  }
  const latestStage = events.at(-1)
  const stageIndex = !busy ? -1 : latestStage?.stage === 'understand' ? 0 : ['retrieve', 'tools', 'graph'].includes(latestStage?.stage || '') ? 1 : latestStage?.stage === 'validate' ? 2 : 3
  const composer = <div className={`composer ${!trip ? 'hero-composer' : ''}`}>
    {!trip && selectedSpot && <div className="selected-destination"><MapPin size={13} />{selectedSpot}<button aria-label="取消所选景区" onClick={() => setSelectedSpot('')}><X size={13} /></button></div>}
    <textarea ref={inputRef} aria-label="描述你的旅行需求" title="Enter 开始规划 · Shift + Enter 换行" rows={trip ? 3 : 2} placeholder={trip ? '继续调整，比如「不去珍宝馆」…' : '想去哪里，和谁出发？把你的想法告诉山行…'} value={input} disabled={busy} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void submit() } }} />
    <div className="composer-bottom">{trip ? <span><Sparkles size={13} />基于已有需求继续规划</span> : <button className="composer-preferences" onClick={togglePreferences} aria-expanded={showForm}><Settings2 size={14} />补充旅行偏好<ChevronDown size={13} className={showForm ? 'rotate' : ''} /></button>}<button className="send" aria-label="开始规划" disabled={busy || !input.trim()} onClick={() => void submit()}>{busy ? <LoaderCircle size={18} className="spin" /> : <ArrowUp size={19} />}</button></div>
    {!trip && showForm && <div className="preference-form"><label>游览时间<select value={duration} onChange={e => setDuration(e.target.value)}><option>半天</option><option>一天</option><option>两天</option></select></label><label>同行人<select value={party} onChange={e => setParty(e.target.value)}><option value="">暂不指定</option><option>老人</option><option>孩子</option><option>情侣</option><option>独自旅行</option></select></label><label>必去景点<input value={mustVisit} onChange={e => setMustVisit(e.target.value)} placeholder="例如：太和殿" /></label><label>避开景点<input value={avoid} onChange={e => setAvoid(e.target.value)} placeholder="可留空" /></label></div>}
  </div>

  return <div className="app-shell">
    <aside className={`sidebar ${showHistory ? 'mobile-open' : ''}`}>
      <button className="brand" onClick={newTrip} disabled={busy} aria-label="山行首页"><span className="brand-icon"><Mountain size={25} strokeWidth={1.5} /></span><span>山行<small>SHANXING</small></span></button>
      <button className="new-trip" onClick={newTrip} disabled={busy}><Plus size={17} />开启一段旅行<ArrowRight size={15} /></button>
      <div className="nav-label">你的旅行手记</div>
      <nav aria-label="旅行历史">{trips.length ? trips.map(t => <button key={t.id} disabled={busy} className={`history-item ${active === t.id ? 'active' : ''}`} onClick={() => { setActive(t.id); setShowHistory(false); setEvents([]); setMobileTab('chat') }}><BookOpen size={15} /><span>{t.title}</span><ChevronRight size={13} /></button>) : <div className="empty-history"><Route size={24} strokeWidth={1.2} /><p>每一段旅程<br />都从一个想法开始</p></div>}</nav>
      <div className="sidebar-bottom"><div className="small-landscape"><Mountain size={50} strokeWidth={.6} /><p>山水有相逢<br />出发有依据</p></div></div>
    </aside>
    <main>
      <button className="mobile-history icon-button mobile-history-shortcut" aria-label="打开旅行历史" onClick={() => setShowHistory(!showHistory)}><History size={20} /></button>

      {!trip ? <section ref={homeRef} className={`home ${showForm ? 'preferences-open' : ''}`} style={showForm && formTop !== null ? { paddingTop: formTop } : undefined}>

        <div className="home-intro">
        <div className="hero-heading"><div><h1>把向往，<br /><em>走成一段旅程。</em></h1><p>告诉山行目的地、时间和同行人，从真实攻略中找到适合你的路线。</p></div><div className="hero-stamp"><Compass size={72} strokeWidth={.75} /><span>FOLLOW YOUR OWN PACE</span></div></div>
        <div className="home-input">
        {composer}
        <div className="quick-settings"><div className="example-row"><span>试着问问</span>{examples.map((ex, i) => <button key={ex} onClick={() => { setSelectedSpot(''); void submit(ex, false) }}>{['老人轻松游', '情侣湖畔游', '亲子半日游'][i]}<ArrowRight size={12} /></button>)}</div></div>

        </div>
        </div>
        <section className="destinations"><div className="section-heading"><h2>从这里出发</h2><span>三个景区，各有风景</span></div><div className="destination-grid">{places.map((p, i) => <button key={p.name} className={`destination-card ${selectedSpot === p.name ? 'selected' : ''}`} onClick={() => { setSelectedSpot(p.name); inputRef.current?.focus() }} aria-pressed={selectedSpot === p.name}><div className="card-art"><Landscape kind={p.kind} /><span className="card-number">0{i + 1}</span><span className="card-tag">{p.tag}</span>{selectedSpot === p.name && <span className="card-check"><Check size={15} /></span>}</div><div className="card-caption"><div><h3>{p.name}</h3><p>{p.subtitle}</p></div><span className="card-arrow"><ArrowRight size={18} /></span></div></button>)}</div></section>
        {offline && <div className="service-notice">无法连接后台服务。请先启动 FastAPI 后刷新页面。</div>}
        {health && !health.model_configured && <div className="service-notice">尚未配置模型密钥，请在本机 .env 中设置后重启服务。</div>}
      </section> : <section className="workspace">
        <div className="mobile-tabs"><button className={mobileTab === 'chat' ? 'active' : ''} onClick={() => setMobileTab('chat')}>对话规划</button><button className={mobileTab === 'plan' ? 'active' : ''} onClick={() => setMobileTab('plan')}>我的行程{ready && <i />}</button></div>
        <section className={`chat-pane ${mobileTab === 'chat' ? 'mobile-visible' : ''}`} aria-label="规划对话"><div className="chat-heading"><span className="assistant-mark"><Mountain size={20} /></span><div><h2>山行向导</h2><p>一起找到适合你的步调</p></div><span className="online-dot" /></div><div className="messages"><div className="assistant-intro">你好，欢迎出发。告诉我目的地、游览时间和你的偏好，我会从已有路线里寻找合适的安排。</div>{trip.messages.map((m, i) => <div key={i} className={`message ${m.role} ${m.error ? 'error' : ''}`}>{m.role === 'assistant' && <div className="message-label"><Mountain size={13} />山行</div>}<p>{m.text}</p>{m.error && !busy && <button className="retry" onClick={() => void submit(trip.lastMessage)}>重新尝试<ArrowRight size={13} /></button>}</div>)}{busy && <div className="progress-box" role="status"><div><LoaderCircle size={15} className="spin" />{latestStage?.label || '正在准备规划'}</div><ol>{stages.map((s, i) => <li key={s} className={i <= stageIndex ? 'current' : ''}><span>{i < stageIndex ? <Check size={11} /> : i + 1}</span>{s}</li>)}</ol></div>}<div ref={bottom} /></div><div className="chat-compose">{composer}<p>推荐附来源 · 未知信息会如实说明</p></div></section>
        <section className={`plan-pane ${busy ? 'is-exploring' : ''} ${mobileTab === 'plan' ? 'mobile-visible' : ''}`} aria-label="行程方案">
          {(busy || (ready && result.graph_selection)) && graphData && <>
            {!busy && <button className="network-toggle" onClick={() => setShowGraph(!showGraph)}>{showGraph ? '收起检索网络' : '查看检索网络'}<ChevronDown size={14} /></button>}
            {(busy || showGraph) && <GraphExplorer data={graphData} selection={busy ? graphSelection : result?.graph_selection || null} label={busy ? graphLabel : '已定位最终行程及其原文依据'} busy={busy} />}
          </>}
          {busy && !graphData && <div className="plan-empty" role="status"><LoaderCircle className="spin" /><h2>{latestStage?.label || "正在加载检索网络"}</h2><p>正在查询路线与原文依据。</p></div>}
          {!busy && (ready ? <><div className="plan-top"><div><span className="eyebrow">YOUR FIELD GUIDE</span><h1>{result.constraints?.scenic_spot}<span>游览手记</span></h1><div className="plan-tags"><span><Route size={12} />{result.steps?.length} 个步骤</span><span>{result.constraints?.duration || '时间待定'}</span>{result.constraints?.travelers?.map(p => <span key={p}>{p}</span>)}</div></div><button className="export-button" onClick={exportPlan}><ArrowDownToLine size={15} />导出结果</button></div>
          <div className="route-banner"><div><span className="route-icon"><Footprints size={20} /></span><div><h3>{result.route?.route_name}</h3><p>{result.rationale || '依据现有路线，保留原文游览顺序。'}</p></div></div><span className="source-label">{result.route?.source_type === 'official' ? '官方来源路线' : '游客游记路线'}</span></div>
          <div className="route-strip" aria-label="路线顺序示意图">{result.steps?.map((s, i) => <React.Fragment key={s.order}>{i > 0 && <span className="strip-connector" />}<button onClick={() => document.getElementById(`step-${s.order}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })}><span>{i + 1}</span>{s.pois[0] || '路线步骤'}</button></React.Fragment>)}</div><p className="strip-note">路线顺序示意 · 不代表地理距离</p>
          <div className="itinerary-title"><h2>沿着这条路，慢慢走</h2><span>保留原文顺序</span></div><div className="timeline">{result.steps?.map((s, i) => <article className="step-card" id={`step-${s.order}`} key={s.order}><div className="step-index">{String(i + 1).padStart(2, '0')}</div><div className="step-body"><div className="step-top"><h3>{s.pois.join(' · ') || '路线衔接步骤'}</h3><span className={`time-tag ${!s.time_text && !s.time_period ? 'unknown' : ''}`}>{s.day ? `第${s.day}天 · ` : ''}{s.time_text || s.time_period || '时间待定'}</span></div><p>{s.activity}</p>{s.visit_duration_text && <p className="duration-note">原文停留时长：{s.visit_duration_text}</p>}<div className="step-bottom"><span><MapPin size={12} />原路线第 {s.order} 步</span><button onClick={() => setSource({ title: s.pois.join(' · ') || '路线依据', items: [s.source] })}>查看依据<ExternalLink size={12} /></button></div></div></article>)}</div>
          {!!result.advice?.length && <section className="advice-section"><h2><Leaf size={17} />与你有关的游览建议</h2>{result.advice.map(a => <article key={a.pair_id}><span className="advice-condition">{a.condition}</span><h3>{a.recommendation}</h3><p>{a.reason}</p><button onClick={() => setSource({ title: '条件建议的原文依据', items: a.sources, review: a.review_status })}>查看建议来源<ExternalLink size={12} /></button></article>)}</section>}
          <details className="limitations" open><summary><ShieldCheck size={16} />出发前，留意这些<ChevronDown size={15} /></summary><ul>{result.limitations?.map(l => <li key={l}>{l}</li>)}</ul></details>
          <details className="trace-details"><summary><Route size={14} />查看本次查询记录<span>{result.trace?.filter(t => t.type === 'tool').length || 0} 次调用</span><ChevronDown size={14} /></summary><p>记录工具名称、参数与实际返回，便于核查推荐依据。</p>{result.trace?.filter(t => t.type === 'tool').map((t, i) => <details key={i}><summary>{String(i + 1).padStart(2, '0')} · {t.name}</summary><pre>{JSON.stringify({ arguments: t.arguments, result: t.result }, null, 2)}</pre></details>)}</details>
          <div className="plan-end"><Mountain size={25} strokeWidth={1} /><span>路在脚下，依据在手边。</span></div></> : <div className="plan-empty"><div className="empty-illustration"><Landscape kind={result?.constraints?.scenic_spot === '北京故宫' ? 'palace' : 'mountain'} large /></div><span className="eyebrow">A LITTLE SPACE FOR POSSIBILITY</span><h2>{busy ? '正在寻找你的游览路线' : result?.status === 'clarification' ? '再补充一点，就能出发' : result?.status === 'error' ? '这次规划暂未完成' : result?.status === 'no_match' ? '暂时没有合适的路线' : '你的下一段旅程，在这里展开'}</h2><p>{busy ? '从现有攻略与游记中查询路线，核对建议与来源。' : result?.message || '完成左侧对话后，行程、路线顺序和原文依据会一起出现在这里。'}</p><div className="empty-features"><span><Route size={15} />有顺序的路线</span><span><BookOpen size={15} />可回查的来源</span><span><Leaf size={15} />适合你的建议</span></div>{!busy && <button className="back-to-chat" onClick={() => { setMobileTab('chat'); inputRef.current?.focus() }}>继续对话<ArrowRight size={15} /></button>}</div>)}
        </section>
      </section>}
    </main>
    {source && <div className="modal-overlay" onMouseDown={e => { if (e.target === e.currentTarget) setSource(null) }}><div className="source-dialog" role="dialog" aria-modal="true" aria-labelledby="source-title" ref={dialog}><div className="dialog-top"><span className="eyebrow">BACK TO THE SOURCE</span><button className="icon-button" aria-label="关闭来源" onClick={() => setSource(null)}><X size={20} /></button></div><h2 id="source-title">{source.title}</h2><p className="dialog-description">看看这条推荐从哪里来。</p>{source.items.map((s, i) => <article key={`${s.doc_id}-${i}`}><span className="source-type">{s.source_type === 'official' ? '官方类别来源' : '游客游记'}</span><h3>{s.title}</h3>{s.quote && <blockquote>{s.quote}</blockquote>}{safeUrl(s.url) && <a href={safeUrl(s.url)} target="_blank" rel="noreferrer">打开原始网页<ExternalLink size={13} /></a>}<details><summary>文档标识</summary><code>{s.doc_id}</code></details></article>)}{source.review && <p className="review-status"><ShieldCheck size={14} />{source.review}</p>}<p className="source-footnote">资料来源不等于实时公告，出发前请核对景区当前安排。</p></div></div>}
  </div>
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>)
