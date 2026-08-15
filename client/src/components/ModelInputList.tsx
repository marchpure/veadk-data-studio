import { Button } from './ui/button'
import { Input } from './ui/input'
import { Label } from './ui/label'
import { X, Plus } from 'lucide-react'

interface ModelInputListProps {
  models: string[]
  onChange: (models: string[]) => void
  placeholder?: string
  label?: string
  description?: string
  minModels?: number
}

export function ModelInputList({
  models,
  onChange,
  placeholder = 'Enter model name',
  label = 'Models',
  description,
  minModels = 1,
}: ModelInputListProps) {
  const handleAddModel = () => {
    onChange([...models, ''])
  }

  const handleRemoveModel = (index: number) => {
    // Don't allow removing if at minimum
    if (models.length <= minModels) return

    const newModels = models.filter((_, i) => i !== index)
    onChange(newModels)
  }

  const handleUpdateModel = (index: number, value: string) => {
    const newModels = [...models]
    newModels[index] = value
    onChange(newModels)
  }

  // Ensure at least one model field exists
  const displayModels = models.length > 0 ? models : ['']

  return (
    <div>
      <Label className="text-white">
        {label} <span className="text-red-400">*</span>
      </Label>
      {description && (
        <p className="text-xs text-gray-400 mt-1 mb-2">{description}</p>
      )}

      <div className="space-y-2 mt-2">
        {displayModels.map((model, index) => (
          <div key={index} className="flex gap-2 items-center">
            <Input
              type="text"
              placeholder={placeholder}
              value={model}
              onChange={(e) => handleUpdateModel(index, e.target.value)}
              className="flex-1 bg-[#1a1a1a] border-[#555555] text-white"
            />
            {displayModels.length > minModels && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => handleRemoveModel(index)}
                className="text-red-400 hover:text-red-300 hover:bg-red-900/20 px-2"
              >
                <X className="w-4 h-4" />
              </Button>
            )}
          </div>
        ))}
      </div>

      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={handleAddModel}
        className="mt-3 border-[#555555] text-gray-300 hover:bg-[#3a3a3a] hover:text-white"
      >
        <Plus className="w-4 h-4 mr-2" />
        Add Another {label.includes('Deployment') ? 'Deployment' : 'Model'}
      </Button>
    </div>
  )
}
