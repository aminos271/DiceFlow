import { useEffect, useRef } from 'react'
import TurnCard from './TurnCard.jsx'

export default function TurnHistory({ turns }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns.length])

  if (turns.length === 0) {
    return (
      <div className="turn-history">
        <div className="turn-empty">
          输入你的行动开始冒险...
        </div>
      </div>
    )
  }

  return (
    <div className="turn-history">
      {turns.map((turn, index) => (
        <TurnCard key={turn.turn_id ?? index} turn={turn} />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
