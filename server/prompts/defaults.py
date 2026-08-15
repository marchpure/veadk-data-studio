"""Default content for user preferences (instructions and style guidelines)"""

DEFAULT_USER_INSTRUCTIONS = """# Query Generation Instructions

## Query Writing Principles
- Write clear, readable queries that are easy to understand and maintain
- Prefer explicit column names over SELECT * for better performance and clarity

## Performance
- Add WHERE clauses to filter data when possible
- Use indexes effectively (already defined in schema)

## Business Context
- Financial calculations should round to 2 decimal places
- Patient data queries must respect privacy constraints
"""

DEFAULT_STYLE_GUIDELINES = """# Byaan Brand & Style Guidelines

## Byaan Color System

### Primary Brand Colors
- Byaan Orange: #FF7700 (Primary brand, buttons, interactive elements, focus rings)
- Byaan Magenta: #FF66CC (Accents, hover states, secondary highlights)

### Background & Surface Colors
- Byaan Dark Background: #0A0A0A (Main page background)
- Byaan Card Surface: #0F0F0F (Cards, containers, popovers)
- Byaan Secondary: #1F1F1F (Secondary backgrounds, toggles, muted areas)
- Byaan Border: #242424 (Borders, dividers, input backgrounds)

### Text Colors
- Byaan Text: #F2F2F2 (Primary text color)
- Byaan Muted Text: #999999 (Secondary text, placeholders)
- Byaan White: #FFFFFF (Text on colored backgrounds)

### Semantic Colors
- Byaan Destructive: #F24444 (Error states, delete actions)

### Chart Color Palette
Use these Byaan colors for charts with multiple categories (in order):
- Byaan Orange: #FF7700
- Byaan Magenta: #FF66CC
- Byaan Destructive: #F24444
- Light variants: Blend between orange and magenta for additional categories

### Gradients
- Primary Gradient: linear-gradient(135deg, #FF7700, #FF66CC) - Use for hero text, feature highlights
- Soft Gradient: linear-gradient(#FF7700 @ 10% opacity → transparent) - Use for background overlays

## Design Tokens (HSL)
- --primary: 24 95% 53% (Byaan Orange #FF7700)
- --accent: 330 81% 60% (Byaan Magenta #FF66CC)
- --background: 0 0% 4% (Byaan Dark Background #0A0A0A)
- --card: 0 0% 6% (Byaan Card Surface #0F0F0F)
- --secondary: 0 0% 12% (Byaan Secondary #1F1F1F)
- --border: 0 0% 14% (Byaan Border #242424)
- --foreground: 0 0% 95% (Byaan Text #F2F2F2)
- --muted-foreground: 0 0% 60% (Byaan Muted Text #999999)
- --destructive: 0 84% 60% (Byaan Destructive #F24444)

## Dashboard Charts Instructions
- Use Byaan Orange (#FF7700) and Byaan Magenta (#FF66CC) as primary colors in all charts
- Always include x-labels and y-labels in all charts in charts where applicable
- Always include legends in all charts of dashboard
- **CRITICAL: For PIE CHARTS, always add labels to display values/percentages on the chart segments**
- Position legends to not overlap with data or y-labels
- If a chart has more than 7 data points (bars, categories, time periods, etc.), use FULL WIDTH layout instead of 2 grid columns
- Border radius for all containers: 0.75rem (12px)
- For BAR CHARTS (BarChart component):
    - VERTICAL BARS (going upward): DO NOT specify layout prop, or use layout="horizontal" (this is the DEFAULT)
    - HORIZONTAL BARS (going sideways): MUST use layout="vertical"

## Theme & UI Hierarchy
- Dark mode first design approach
- UI Hierarchy: Page (#0A0A0A) → Cards (#0F0F0F) → Elevated surfaces (#1F1F1F) → Borders (#242424)

"""
