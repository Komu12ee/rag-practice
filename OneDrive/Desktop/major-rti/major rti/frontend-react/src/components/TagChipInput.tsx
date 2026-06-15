import { useState, KeyboardEvent, ChangeEvent } from 'react'
import { X } from 'lucide-react'

interface TagChipInputProps {
  label: string
  tags: string[]
  onChange: (tags: string[]) => void
  placeholder?: string
}

export default function TagChipInput({ label, tags, onChange, placeholder = "Add new…" }: TagChipInputProps) {
  const [inputValue, setInputValue] = useState('')

  const commit = () => {
    const trimmed = inputValue.trim()
    if (trimmed && !tags.includes(trimmed)) {
      onChange([...tags, trimmed])
      setInputValue('')
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      commit()
    } else if (e.key === 'Backspace' && !inputValue && tags.length) {
      onChange(tags.slice(0, -1))
    }
  }

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => setInputValue(e.target.value)
  const handleRemove = (tagToRemove: string) => onChange(tags.filter(t => t !== tagToRemove))

  return (
    <div className="space-y-1.5">
      <label className="eyebrow">{label}</label>
      <div className="flex flex-wrap gap-1.5 p-2 rounded-xl border border-slate-200 bg-white transition-colors focus-within:ring-2 focus-within:ring-brand-500/40 focus-within:border-brand-400 dark:border-slate-700 dark:bg-slate-900 dark:focus-within:border-brand-500 min-h-[42px] items-center">
        {tags.map(tag => (
          <span
            key={tag}
            className="inline-flex items-center gap-1 rounded-lg bg-brand-50 px-2 py-1 text-xs font-medium text-brand-700 ring-1 ring-brand-200/60 dark:bg-brand-500/10 dark:text-brand-300 dark:ring-brand-500/20"
          >
            {tag}
            <button
              type="button"
              onClick={() => handleRemove(tag)}
              className="text-brand-400 hover:text-brand-700 dark:hover:text-brand-200 transition-colors"
            >
              <X className="h-3 w-3" strokeWidth={2.5} />
            </button>
          </span>
        ))}
        <input
          type="text"
          value={inputValue}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onBlur={commit}
          placeholder={tags.length === 0 ? placeholder : ''}
          className="flex-1 min-w-[80px] bg-transparent text-sm focus:outline-none h-6 px-1 text-slate-900 dark:text-slate-100 placeholder:text-slate-400"
        />
      </div>
    </div>
  )
}
