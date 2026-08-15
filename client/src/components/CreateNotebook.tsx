import { useNavigate } from 'react-router-dom'

interface CreateNotebookProps {
  trigger?: React.ReactNode
  className?: string
}

export default function CreateNotebook({ trigger, className = "" }: CreateNotebookProps) {
  const navigate = useNavigate()

  const handleCreateNotebook = () => {
    // Navigate to new notebook page where user will select dataset and type first message
    navigate('/notebook/new')
  }

  // If trigger is provided, clone it with onClick handler
  if (trigger) {
    return (
      <div onClick={handleCreateNotebook} className={className}>
        {trigger}
      </div>
    )
  }

  // Default trigger if none provided
  return (
    <button onClick={handleCreateNotebook} className={className}>
      Create Notebook
    </button>
  )
}
