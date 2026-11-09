import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D, { ForceGraphMethods, NodeObject, LinkObject } from 'react-force-graph-2d'

export type GraphNode = NodeObject<{ id: string; label: string; group: string; spot: string; val: number }>
type GraphLink = LinkObject<GraphNode, { id: string; kind: string; value: number }>
export type GraphData = { nodes: GraphNode[]; links: GraphLink[] }
const colors: Record<string, string> = { ScenicSpot: '#f0cf83', Route: '#e99b75', Step: '#90bda5', POI: '#9dc8e4', Document: '#c3a3d8', Condition: '#d1cf83', Activity: '#a7b5cb', TimePeriod: '#d7b7a0', ConditionType: '#c5bc89' }
const labels: Record<string, string> = { ScenicSpot: '景区', Route: '路线', Step: '步骤', POI: '景点', Document: '原文', Condition: '条件建议', Activity: '活动', TimePeriod: '时段', ConditionType: '条件类型' }
const endpoint = (v: string | number | GraphNode | undefined) => typeof v === 'object' ? v.id : v
const escape = (s: string) => s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!))

// Uses the original directional-links-particles example's ForceGraph2D API.
// Stable IDs/objects preserve physical positions as real query projections change.
export function GraphExplorer({ data, selection, label, busy }: { data: GraphData; selection: string[] | null; label: string; busy: boolean }) {
  const host = useRef<HTMLDivElement>(null)
  const graph = useRef<ForceGraphMethods<GraphNode, GraphLink> | undefined>(undefined)
  const [size, setSize] = useState({ width: 500, height: 420 })
  const [ids, setIds] = useState<Set<string> | null>(null)
  const [fading, setFading] = useState<Set<string> | null>(null)
  const [fadeAlpha, setFadeAlpha] = useState(1)
  const [picked, setPicked] = useState<GraphNode | null>(null)
  const [reduced, setReduced] = useState(false)
  const objects = useMemo(() => data.nodes.map(n => ({ ...n })), [data])
  const allLinks = useMemo(() => data.links.map(l => ({ ...l })), [data])
  useEffect(() => {
    const mq = matchMedia('(prefers-reduced-motion: reduce)')
    const change = () => setReduced(mq.matches); change(); mq.addEventListener('change', change)
    return () => mq.removeEventListener('change', change)
  }, [])
  useEffect(() => {
    if (!host.current) return
    const observer = new ResizeObserver(([e]) => setSize({ width: Math.max(1, e.contentRect.width), height: Math.max(1, e.contentRect.height) }))
    observer.observe(host.current); return () => observer.disconnect()
  }, [])
  useEffect(() => {
    setPicked(null)
    const next = selection ? new Set(selection) : null
    setFading(next)
    setFadeAlpha(1)
    let frame = 0
    const start = performance.now()
    const fade = () => { const progress = Math.min(1, (performance.now() - start) / 650); setFadeAlpha(1 - progress); if (progress < 1) frame = requestAnimationFrame(fade) }
    if (!reduced && next) frame = requestAnimationFrame(fade)
    const timer = setTimeout(() => { setIds(next); setFading(null) }, reduced ? 0 : 650)
    return () => { clearTimeout(timer); cancelAnimationFrame(frame) }
  }, [selection, reduced])
  const visible = useMemo(() => ({ nodes: objects.filter(n => !ids || ids.has(n.id)), links: allLinks.filter(l => !ids || (ids.has(String(endpoint(l.source))) && ids.has(String(endpoint(l.target))))) }), [objects, allLinks, ids])
  useEffect(() => {
    const timer = setTimeout(() => graph.current?.zoomToFit(reduced ? 0 : 850, 38), 700)
    return () => clearTimeout(timer)
  }, [visible, size, reduced])
  const faded = (n: GraphNode) => fading && !fading.has(n.id)
  return <section className={`network-panel ${busy ? 'network-working' : 'network-complete'}`} aria-label="知识图谱检索网络">
    <div className="network-header"><div><span className="network-kicker">KNOWLEDGE IN MOTION</span><h2>{busy ? '从万千脉络，到你的旅程' : '这份行程，在图谱中的依据'}</h2></div><span className="network-live"><i />{busy ? '实时检索' : '已完成'}</span></div>
    <div className="network-canvas" ref={host}>
      <ForceGraph2D ref={graph} width={size.width} height={size.height} graphData={visible}
        backgroundColor="#172a28" nodeAutoColorBy="group" nodeRelSize={3.2}
        nodeLabel={n => `${escape(labels[n.group] || n.group)} · ${escape(n.label)}`}
        nodeColor={n => `${colors[n.group] || '#bacabd'}${faded(n) ? Math.round(fadeAlpha * 255).toString(16).padStart(2, '0') : 'ff'}`}
        linkColor={l => fading && (!fading.has(String(endpoint(l.source))) || !fading.has(String(endpoint(l.target)))) ? '#adc9ba08' : '#9ab7ad38'}
        linkWidth={.65} linkDirectionalParticles={l => reduced ? 0 : fading && (!fading.has(String(endpoint(l.source))) || !fading.has(String(endpoint(l.target)))) ? 0 : l.value}
        linkDirectionalParticleSpeed={l => l.value * .001} linkDirectionalParticleWidth={1.8} linkDirectionalParticleColor={() => '#e5d1a1'}
        cooldownTicks={100} d3AlphaDecay={.035} onEngineStop={() => graph.current?.zoomToFit(reduced ? 0 : 600, 38)}
        onNodeClick={n => { setPicked(n); graph.current?.centerAt(n.x, n.y, reduced ? 0 : 500) }}
      />
      <div className="network-count"><strong>{visible.nodes.length}</strong> 个节点 <span>/</span> <strong>{visible.links.length}</strong> 条关系</div>
      <button className="network-fit" onClick={() => graph.current?.zoomToFit(reduced ? 0 : 600, 38)}>适配全图 ↗</button>
      {picked && <div className="network-picked"><span>{labels[picked.group]}</span>{picked.label}<button aria-label="关闭节点详情" onClick={() => setPicked(null)}>×</button></div>}
    </div>
    <div className="network-caption" role="status"><span className={busy ? 'network-pulse' : ''} />{label}</div>
    <div className="network-legend">{['Route', 'POI', 'Step', 'Document', 'Condition'].map(k => <span key={k}><i style={{ background: colors[k] }} />{labels[k]}</span>)}<small>拖动节点 · 滚轮缩放</small></div>
    <p className="network-footnote">节点与连线来自本组知识图谱，随实际查询聚焦；粒子用于展示关系方向。</p>
  </section>
}
