export default function ScriptSelect({ scripts, onSelect }) {
  return (
    <div className="script-select">
      <h1>DiceFlow</h1>
      <p className="subtitle">选择一个剧本开始游戏</p>
      <div className="script-grid">
        {scripts.map((s) => (
          <div key={s.id} className="script-card" onClick={() => onSelect(s.id, s.title)}>
            <h3>{s.title}</h3>
            <p>{s.intro}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
