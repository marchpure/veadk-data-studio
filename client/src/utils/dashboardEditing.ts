const SEARCH_REPLACE_REGEX = /<<<<<{7}\s*SEARCH\s*\n([\s\S]*?)\n=======\s*\n([\s\S]*?)\n>>>>>{7}\s*REPLACE/gi

function trimBoundaryNewlines(text: string): string {
  return text.replace(/^[\r\n]+/, '').replace(/[\r\n]+$/, '')
}

function splitLines(content: string): string[] {
  if (!content) return ['']
  return content.split(/\r?\n/)
}

function joinLines(lines: string[], original: string): string {
  const lineEnding = original.includes('\r\n') ? '\r\n' : '\n'
  const text = lines.join(lineEnding)
  return original.endsWith('\n') || original.endsWith('\r\n') ? text + lineEnding : text
}

const lineMatchers = [
  (a: string, b: string) => a === b,
  (a: string, b: string) => a.trim() === b.trim(),
  (a: string, b: string) => a.replace(/^\s+/, '') === b.replace(/^\s+/, ''),
]

function findBlockStart(targetLines: string[], blockLines: string[]): number {
  if (blockLines.length === 0) return -1

  for (const matcher of lineMatchers) {
    const candidates: number[] = []
    for (let i = 0; i <= targetLines.length - blockLines.length; i++) {
      let matches = true
      for (let j = 0; j < blockLines.length; j++) {
        if (!matcher(targetLines[i + j] ?? '', blockLines[j] ?? '')) {
          matches = false
          break
        }
      }
      if (matches) {
        candidates.push(i)
      }
    }
    if (candidates.length === 1) {
      return candidates[0]
    }
  }
  return -1
}

export function applyFindReplacePreview(html: string, findText?: string, replaceText?: string): string | null {
  if (!findText || typeof findText !== 'string') return null
  if (typeof replaceText !== 'string') return null
  if (!html) return null
  if (!html.includes(findText)) return null
  return html.replace(findText, replaceText)
}

export function applySearchReplacePreview(html: string, diffContent?: string): string | null {
  if (!diffContent || typeof diffContent !== 'string') return null
  const blocks = [...diffContent.matchAll(SEARCH_REPLACE_REGEX)]
  if (blocks.length === 0) return null

  const lines = splitLines(html)

  for (const block of blocks) {
    const searchContent = trimBoundaryNewlines(block[1] ?? '')
    const replaceContent = trimBoundaryNewlines(block[2] ?? '')
    const searchLines = splitLines(searchContent)
    const replaceLines = splitLines(replaceContent)
    if (searchLines.length === 0) return null

    const startIdx = findBlockStart(lines, searchLines)
    if (startIdx === -1) return null
    const endIdx = startIdx + searchLines.length
    lines.splice(startIdx, searchLines.length, ...replaceLines)
  }

  return joinLines(lines, html)
}

export function applyHtmlPatchPreview(html: string, patchText?: string): string | null {
  if (!patchText || typeof patchText !== 'string') return null

  const lines = splitLines(html)
  const patchLines = patchText.split(/\r?\n/)
  let i = 0

  while (i < patchLines.length) {
    const line = patchLines[i]
    if (line.startsWith('@@')) {
      i++
      const oldLines: string[] = []
      const newLines: string[] = []
      while (i < patchLines.length && !patchLines[i].startsWith('@@') && !patchLines[i].startsWith('***')) {
        const chunkLine = patchLines[i]
        if (chunkLine.startsWith('+')) {
          newLines.push(chunkLine.slice(1))
        } else if (chunkLine.startsWith('-')) {
          oldLines.push(chunkLine.slice(1))
        } else if (chunkLine.startsWith(' ')) {
          const segment = chunkLine.slice(1)
          oldLines.push(segment)
          newLines.push(segment)
        } else if (chunkLine === '') {
          oldLines.push('')
          newLines.push('')
        }
        i++
      }
      if (oldLines.length > 0) {
        const startIdx = findBlockStart(lines, oldLines)
        if (startIdx === -1) return null
        lines.splice(startIdx, oldLines.length, ...newLines)
      }
    } else {
      i++
    }
  }

  return joinLines(lines, html)
}
