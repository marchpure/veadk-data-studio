# Common instructions that apply to all charts
COMMON_INSTRUCTIONS = """

**CRITICAL: USER PREFERENCES ALWAYS TAKE TOP PRIORITY**

BEFORE using any styling from this file, you MUST:
1. Call get_user_style_guidelines() tool to fetch user's custom brand and style preferences

USER PREFERENCES OVERRIDE EVERYTHING:
- If user specifies colors in get_user_style_guidelines() → USE THOSE COLORS (not the defaults below)
- If user specifies fonts, typography, chart types, dashboard features etc → USE THOSE PREFERENCES
- User's custom preferences are the highest priority - they override all examples and defaults in this file

This get_chart_styling() tool provides TECHNICAL IMPLEMENTATION PATTERNS and default chart styles (code structure, animations, gradients).
The get_user_style_guidelines() tool provides BRAND IDENTITY (colors, fonts, dashboard features, visual preferences etc).
Always combine both: use code patterns from here + colors/preferences from get_user_style_guidelines().
Always include legends in all chart types, and ensure the legend accurately represents the data series, colors and labels.

**MANDATORY STYLING REQUIREMENTS**
YOU MUST FOLLOW THE STYLING FROM THE EXAMPLES BELOW - DO NOT SIMPLIFY UNTIL THE USER GIVES SPECIFIES CHART STYLING!

WHAT YOU MUST COPY EXACTLY FROM EXAMPLES:
- ALWAYS include legends with all chart types as given in few shot examples
- ALWAYS include custom tooltips (CustomTooltip component) with styled gradient backgrounds as shown in TOOLTIP_PATTERN - NEVER use simple plain text tooltips
- ALWAYS include x-labels and y-labels in all charts but these labels should not overlap with legends or x-ticks and y-ticks
- Use full-width layout (grid-cols-1) for charts with >7 data points to prevent label overlap.
- NEVER add in-dashboard filter UI/components (FilterBar, SelectFilter, MultiselectFilter, DateRangeFilter, NumberRangeFilter, TextSearchFilter). Filters are rendered by host shell, outside iframe.
- ALL gradient definitions with exact same structure (linearGradient with x1, y1, x2, y2, stop offsets, colors)
- ALL filter definitions (feDropShadow with exact dx, dy, stdDeviation values)
- ALL animation properties (animationDuration, animationEasing values like "cubic-bezier(0.4, 0, 0.2, 1)")
- ALL hover effects (transform values like "translateY(-8px) scale(1.05)", filter brightness values)
- ALL transition properties (duration: 0.4s, easing: cubic-bezier)
- ALL radius values (e.g., radius={[12, 12, 0, 0]} for bar corners)
- ALL strokeWidth values (2px axis lines, 3px line charts, etc.)
- ALL axis styling (colors adapt to theme: like #F2F2F2 for dark backgrounds, #0A0A0A for light backgrounds according to the theme, fontWeight) - BUT use readable font sizes as specified below
- ALL grid styling (for example stroke="#242424" for dark theme, strokeOpacity={0.8}, vertical/horizontal settings etc.)
- ALL shadow effects (both normal and hover states)
- VERTICAL BARS (going upward): DO NOT specify layout prop, or use layout="horizontal" (this is the DEFAULT)
- HORIZONTAL BARS (going sideways): MUST use layout="vertical" (this is the Recharts convention)

**CRITICAL: AXIS LABEL FONT SIZES FOR READABILITY**
Use these MINIMUM font sizes for axis labels to ensure readability:
- XAxis tick labels: fontSize: 14 (minimum) - Use 15 or 16 for better readability
- YAxis tick labels: fontSize: 14 (minimum) - Use 15 or 16 for better readability
- Axis titles (label): fontSize: 14 (minimum) - Use 15 or 16 for better readability
- Legend text: fontSize: 14 (minimum)
NEVER use fontSize smaller than 14 for any axis labels or legends!

**CRITICAL: CHART LAYOUT - FULL WIDTH FOR MANY DATA POINTS**
RULE: If a chart has more than 7 data points (bars, categories, time periods, etc.), use FULL WIDTH layout instead of 2 grid columns.

GOOD EXAMPLES:
- 10 months of data → Use full width (grid-cols-1)
- 7+ categories → Use full width (grid-cols-1)

BAD EXAMPLES:
- 10 data points in 2-column grid → X-axis labels will overlap and become unreadable
- Many categories in half-width chart → Bars become too narrow

LAYOUT GUIDELINES:
- Few data points (≤7): Can use 2-column grid (grid-cols-2) or full width
- Many data points (>7): MUST use full width (grid-cols-1)
- Very complex charts (stacked, grouped, multi-series): Prefer full width
- When in doubt: Use full width for better readability


**CRITICAL: TEXT VISIBILITY - ADAPT COLORS TO DASHBOARD THEME**
ALWAYS check dashboard background and adjust ALL text colors for visibility:
Text on charts can be from color pallet or adapted to the theme as defined here
DARK BACKGROUNDS → Use LIGHT text colors (For Example: #F2F2F2 for primary text, #999999 for muted text, #FFFFFF for high contrast)
LIGHT BACKGROUNDS → Use DARK text colors (For Example: #0A0A0A for primary text, #1F1F1F for muted text, #242424 for borders/dividers)

This applies to ALL text in ALL charts:
- Axis labels (XAxis/YAxis tick fill)
- Axis titles (label style fill)
- Center text and percentages in pie/donut charts should be of their relevant slice color
- Percentage labels on chart segments can be colorful
- Chart titles and subtitles
- Legend text
- Any text element rendered on the chart should be adapted to chart colors or according to the theme

RULE: Text must be clearly readable against the dashboard background!

CRITICAL: COLOR PALETTE FOR ALL CHARTS

WHEN TO USE MULTIPLE COLORS vs SINGLE COLOR:

1. MULTIPLE COLORS (Different color for each item):
   - Comparing different categories (departments, products, regions, procedures)
   - Multiple data series on same chart (Product A vs Product B vs Product C)
   - Pie/donut charts showing composition
   - Any visualization where items represent DIFFERENT things
   - Use vibrant, distinct colors: ['#FF7700', '#FF66CC', '#FBBF24', '#D946EF', '#ec4899', '#f59e0b', '#f43f5e', '#ef4444']

2. SINGLE COLOR/GRADIENT (Same color for all items):
   - Time series data (single metric over time: daily sales, monthly revenue, quarterly growth)
   - Rankings/leaderboards (Top 10 - all same metric, gradient intensity by rank)
   - Use single color or gradient: '#667eea' with gradient, or color intensity based on position

COLOR PALETTE PRIORITY:
1. **PRIORITY: get_user_style_guidelines() tool**
   - Use colors from user's custom style guidelines (fetched from user_preferences)
   - User's brand colors in style guidelines override everything below

2. IF USER SPECIFIES COLORS IN CONVERSATION → USE EXACTLY THOSE COLORS
   - User says "use red, blue, green" → Use ['#ef4444', '#3b82f6', '#10b981']
   - User provides hex codes → Use those exact hex codes
   - User specifies brand colors or color scheme → Follow their specification exactly

3. IF USER DOES NOT SPECIFY COLORS → Use default vibrant palette (for multi-category) or single color/gradient (for time series)
   - Default palette: ['#FF7700', '#FF66CC', '#FBBF24', '#D946EF', '#ec4899', '#f59e0b', '#f43f5e', '#ef4444']

CRITICAL: DO NOT MAKE ANY JSX/SYNTAX ERRORS WHILE CREATING OR MODIFYING HTML
The examples below are TEMPLATES to ADAPT to your specific data, NOT to copy verbatim.

YOU MUST:
1. Match dataKey names to YOUR ACTUAL query (e.g. query_id_1, query_id_2)
2. Adapt chart dimensions, labels, and titles to YOUR specific use case
3. Map colors to YOUR data before rendering
4. Verify ALL syntax is correct - every bracket, brace, comma, and semicolon
5. Think step-by-step: understand the example, then adapt it to your needs

COMMON ERRORS FROM BLINDLY COPYING:
- Using example dataKey names that don't exist in your data
- Hardcoding example labels instead of using actual data labels
- Missing variable declarations (colors array, state variables)
- Unclosed brackets or malformed JSX
- Not mapping colors to data before using them

CRITICAL: CHART MARGINS MUST BE ≤40

ALWAYS keep margins BALANCED on all sides and NOT MORE THAN 40:
- CORRECT: margin={{ top: 20, right: 20, left: 20, bottom: 20 }}
- CORRECT: margin={{ top: 40, right: 40, left: 40, bottom: 40 }}
- CORRECT: margin={{ top: 20, right: 20, left: 40, bottom: 20 }} unequal but within limit of ≤40
- WRONG: margin={{ top: 20, right: 30, left: 120, bottom: 20 }} (unequal + left too large)
- WRONG: margin={{ top: 100, right: 100, left: 100, bottom: 100 }} (exceeds 40)

CRITICAL: RECHARTS COMPONENT DESTRUCTURING

BEFORE creating ANY chart, you MUST destructure Recharts components including ResponsiveContainer:

CORRECT PATTERN:
```jsx
const {
  ResponsiveContainer,  // CRITICAL: Always include this
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  Cell,
  PieChart,
  Pie,
  LineChart,
  Line,
  AreaChart,
  Area
} = Recharts;
```

COMMON ERRORS TO AVOID:
- Forgetting to include ResponsiveContainer in destructuring
- Using <ResponsiveContainer> without destructuring it first
- Typos in dataKey names - ensure they match your actual data property names exactly
- Missing closing brackets or semicolons - verify all syntax before generating HTML

TEMPLATE SYNTAX NOTE
The examples below show proper JSX syntax that you should use directly in your code.
JSX expressions use single curly braces: {value}

Example: height={480}

"""

# Tooltip pattern (reusable across all charts)
TOOLTIP_PATTERN = """
**MANDATORY: ALWAYS INCLUDE CUSTOM TOOLTIPS IN ALL CHARTS**

TOOLTIP PATTERN:
You MUST include custom tooltips (CustomTooltip component) in ALL chart types - DO NOT skip tooltips.
Always use custom tooltips (not defaults) with gradient backgrounds, rounded corners, shadows, and borders.
Display large gradient text for primary values with formatted numbers, context labels, and conditional status indicators.

CRITICAL: Every chart MUST have:
1. A CustomTooltip component definition (adapt the example below to your data)
2. A <Tooltip content={<CustomTooltip />} /> element inside the chart component

```jsx
const CustomTooltip = ({ active, payload }) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    const targetValue = 85; // Example threshold
    const isAboveTarget = data.value >= targetValue;

    return (
      <div className="bg-gradient-to-br from-gray-900 to-gray-800 px-7 py-6 rounded-2xl shadow-2xl border-3 backdrop-blur-sm" style={{ backgroundColor: '#0F0F0F', borderColor: '#FF7700', border: '2px solid #FF7700' }}>
        {/* Header with optional conditional badge */}
        <div className="flex items-center justify-between mb-1">
          <p className="text-xs font-bold uppercase tracking-wider" style={{ color: '#FF7700' }}>
            {data.category}
          </p>
          {data.isSpecial && (
            <span className="text-xs font-bold px-2 py-1 rounded-full" style={{ backgroundColor: '#1F1F1F', color: '#FF66CC' }}>
              Special
            </span>
          )}
        </div>

        {/* Subtitle/Date */}
        <p className="text-sm font-semibold mb-4" style={{ color: '#999999' }}>{data.subtitle}</p>

        <div className="space-y-3">
          {/* Main Value Display */}
          <div>
            <p className="text-xs font-semibold mb-1" style={{ color: '#999999' }}>Metric Name</p>
            <div className="flex items-baseline space-x-2">
              <p className="text-6xl font-black bg-gradient-to-r bg-clip-text text-transparent" style={{ backgroundImage: 'linear-gradient(135deg, #FF7700, #FF66CC)' }}>
                {payload[0].value.toLocaleString()}
              </p>
              <p className="text-3xl font-bold" style={{ color: '#999999' }}>unit</p>
            </div>
          </div>

          {/* Conditional Status Indicator */}
          <div className="pt-3 border-t-2" style={{ borderColor: '#242424' }}>
            <div className="flex items-center space-x-2">
              <div className={`w-3 h-3 rounded-full ${isAboveTarget ? 'bg-green-500' : 'bg-orange-500'}`}></div>
              <p className="text-sm font-semibold" style={{ color: isAboveTarget ? '#10b981' : '#f59e0b' }}>
                {isAboveTarget
                  ? `+${(data.value - targetValue).toFixed(1)}% above target`
                  : `${(targetValue - data.value).toFixed(1)}% below target`
                }
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }
  return null;
};
```
"""

# KPI Cards pattern (reusable)
KPI_CARDS_PATTERN = """
KPI CARDS (Grid of 3 or 4 depending upon the number of cards):
```jsx
<div className="grid grid-cols-4 gap-4 mb-6">
  <div className="rounded-xl p-4 border" style={{ backgroundColor: '#0F0F0F', borderColor: '#242424' }}>
    <p className="text-sm font-semibold mb-1" style={{ color: '#FF7700' }}>Metric Name</p>
    <p className="text-3xl font-bold" style={{ color: '#FF7700' }}>{value}</p>
    <p className="text-xs mt-1" style={{ color: '#999999' }}>description</p>
  </div>

  <div className="rounded-xl p-4 border" style={{ backgroundColor: '#0F0F0F', borderColor: '#242424' }}>
    <p className="text-sm font-semibold mb-1" style={{ color: '#FF66CC' }}>Metric Name</p>
    <p className="text-3xl font-bold" style={{ color: '#FF66CC' }}>{value}</p>
    <p className="text-xs mt-1" style={{ color: '#999999' }}>description</p>
  </div>

  <div className="rounded-xl p-4 border" style={{ backgroundColor: '#0F0F0F', borderColor: '#242424' }}>
    <p className="text-sm font-semibold mb-1" style={{ color: '#FBBF24' }}>Metric Name</p>
    <p className="text-3xl font-bold" style={{ color: '#FBBF24' }}>{value}</p>
    <p className="text-xs mt-1" style={{ color: '#999999' }}>description</p>
  </div>

  <div className="rounded-xl p-4 border" style={{ backgroundColor: '#0F0F0F', borderColor: '#242424' }}>
    <p className="text-sm font-semibold mb-1" style={{ color: '#D946EF' }}>Metric Name</p>
    <p className="text-3xl font-bold" style={{ color: '#D946EF' }}>{value}</p>
    <p className="text-xs mt-1" style={{ color: '#999999' }}>description</p>
  </div>
</div>
```
"""

FILTER_BAR_PATTERN = """
FILTER BAR PATTERN IS DEPRECATED.
Do not generate filter UI components in dashboard HTML.
Filters are managed by metadata tools and rendered by the host application outside iframe.
"""

# Dictionary of chart-specific examples
CHART_EXAMPLES = {
    "bar_chart": """
BAR CHART - Categorical Data Comparison:
To comparing different categories (e.g. departments, products, regions, etc.) where each bar represents a distinct category.

**MANDATORY: You MUST include the CustomLegend component with bar charts.**
**MANDATORY: You MUST include the CustomTooltip component with styled gradient backgrounds as shown in TOOLTIP_PATTERN - DO NOT use simple plain text tooltips.**
**Do NOT skip the legend - use it exactly as provided below, including the state and rendering, and ensure that each legend entry correctly reflects the corresponding data series, labels, and colors**
**Use full-width layout (grid-cols-1) for bar chart with more than 7 data points to prevent label overlap.**

```jsx
// State for tracking hovered bar and active category
const [hoveredBar, setHoveredBar] = React.useState(null);
const [activeCategory, setActiveCategory] = React.useState(null);

// Vibrant color palette for bars
const colors = ['#FF7700', '#FF66CC', '#FBBF24', '#D946EF', '#ec4899', '#f59e0b', '#f43f5e', '#ef4444'];

// Map data to categories for legend
const categories = data.map((item, index) => ({
  key: item.department,  // Adapt to your data key
  name: item.department, // Adapt to your data name
  color: colors[index % colors.length]
}));

// Custom Legend Component
const CustomLegend = () => {
  return (
    <div className="flex justify-center items-center space-x-6 flex-wrap gap-2 mt-6">
      {categories.map((category) => {
        const isActive = activeCategory === category.key;
        return (
          <div
            key={category.key}
            className="flex items-center space-x-2 px-4 py-2 rounded-full cursor-pointer transition-all relative"
            style={{
              backgroundColor: '#1F1F1F',
              borderColor: '#242424',
              border: '1px solid',
              transform: isActive ? 'translateY(-2px)' : 'translateY(0)',
              boxShadow: isActive ? '0 4px 12px rgba(255, 119, 0, 0.3)' : 'none',
              opacity: activeCategory === null || isActive ? 1 : 0.5
            }}
            onClick={() => setActiveCategory(isActive ? null : category.key)}
          >
            <div className="w-3.5 h-3.5 rounded" style={{ backgroundColor: category.color }} />
            <p className="text-sm font-semibold" style={{ color: '#F2F2F2' }}>{category.name}</p>
            <div
              style={{
                position: 'absolute',
                bottom: 0,
                left: '50%',
                transform: `translateX(-50%) scaleX(${isActive ? 1 : 0})`,
                width: '80%',
                height: '3px',
                background: category.color,
                borderRadius: '2px',
                transition: 'transform 0.3s ease'
              }}
            />
          </div>
        );
      })}
    </div>
  );
};

<ResponsiveContainer width="100%" height={480}>
  <BarChart
    data={data}
    margin={{ top: 20, right: 20, left: 20, bottom: 20 }}
    onMouseMove={(state) => {
      if (state.isTooltipActive) {
        setHoveredBar(state.activeTooltipIndex);
      } else {
        setHoveredBar(null);
      }
    }}
    onMouseLeave={() => setHoveredBar(null)}
  >
    <defs>
      {colors.map((color, index) => (
        <React.Fragment key={index}>
          <linearGradient id={`colorGradient${index}`} x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%" stopColor={color} stopOpacity={1}/>
            <stop offset="100%" stopColor={color + 'dd'} stopOpacity={1}/>
          </linearGradient>
          <filter id={`shadow${index}`}>
            <feDropShadow dx="0" dy="4" stdDeviation="3" floodOpacity="0.1"/>
          </filter>
          <filter id={`shadowHover${index}`}>
            <feDropShadow dx="0" dy="12" stdDeviation="12" floodOpacity="0.2"/>
          </filter>
        </React.Fragment>
      ))}
    </defs>

    <CartesianGrid strokeDasharray="3 3" stroke="#242424" strokeOpacity={0.8} vertical={false} />

    <XAxis
      dataKey="department"
      height={60}
      tick={{ fill: '#F2F2F2', fontSize: 15, fontWeight: 500 }}
      stroke="#242424"
      axisLine={{ stroke: '#242424', strokeWidth: 2 }}
      tickLine={false}
      label={{
        value: 'Department',
        position: 'insideBottom',
        offset: -10,
        style: { fill: '#F2F2F2', fontSize: 15, fontWeight: 600, letterSpacing: '0.5px' }
      }}
    />

    <YAxis
      tick={{ fill: '#999999', fontSize: 15, fontWeight: 400 }}
      label={{
        value: 'Number of Patients',
        angle: -90,
        position: 'insideLeft',
        style: { fill: '#F2F2F2', fontSize: 15, fontWeight: 600, letterSpacing: '0.5px' }
      }}
      stroke="#242424"
      axisLine={{ stroke: '#242424', strokeWidth: 2 }}
      tickLine={false}
    />

    <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(0, 0, 0, 0.02)' }} />

    <Bar
      dataKey="patients"
      radius={[12, 12, 0, 0]}
      animationDuration={1000}
      animationEasing="cubic-bezier(0.4, 0, 0.2, 1)"
      animationBegin={0}
    >
      {data.map((entry, index) => (
        <Cell
          key={`cell-${index}`}
          fill={`url(#colorGradient${index})`}
          opacity={
            hoveredBar === null || hoveredBar === index
              ? (activeCategory === null || activeCategory === entry.department ? 1 : 0.2)
              : (activeCategory === null || activeCategory === entry.department ? 0.35 : 0.2)
          }
          style={{
            cursor: 'pointer',
            transition: 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
            filter: hoveredBar === index
              ? `url(#shadowHover${index}) brightness(1.1)`
              : `url(#shadow${index})`,
            transform: hoveredBar === index ? 'translateY(-8px) scale(1.05)' : 'translateY(0) scale(1)',
            transformOrigin: 'bottom'
          }}
        />
      ))}
    </Bar>
  </BarChart>
</ResponsiveContainer>

{/* Render the custom legend below the chart */}
<CustomLegend />
```
""",
    "horizontal_bar_chart": """
HORIZONTAL BAR CHART - Categorical Comparison:
To comparing different types/categories (e.g. procedures, departments, product types).

**CRITICAL: MUST use layout="vertical" for HORIZONTAL bars (this is a Recharts convention - DO NOT use layout="horizontal")**
**MANDATORY: You MUST include the CustomLegend component with horizontal bar charts.**
**MANDATORY: You MUST include the CustomTooltip component with styled gradient backgrounds as shown in TOOLTIP_PATTERN - DO NOT use simple plain text tooltips.**
**Do NOT skip the legend - use it exactly as provided below, including the state and rendering, and ensure that each legend entry correctly reflects the corresponding data series, labels, and colors**
**Use full-width layout (grid-cols-1) for horizontal bar chart with more than 7 data points to prevent label overlap.**


```jsx
// State for tracking hovered bar and active category
const [hoveredBar, setHoveredBar] = React.useState(null);
const [activeCategory, setActiveCategory] = React.useState(null);

// Vibrant color palette
const colors = ['#FF7700', '#FF66CC', '#FBBF24', '#D946EF', '#ec4899', '#f59e0b', '#f43f5e', '#ef4444'];

// Add colors to your data
const dataWithColors = data.map((item, index) => ({
  ...item,
  color: colors[index % colors.length]
}));

// Map data to categories for legend
const categories = dataWithColors.map((item) => ({
  key: item.category,  // Adapt to your data key
  name: item.category, // Adapt to your data name
  color: item.color
}));

// Custom Legend Component
const CustomLegend = () => {
  return (
    <div className="flex justify-center items-center space-x-6 flex-wrap gap-2 mt-6">
      {categories.map((category) => {
        const isActive = activeCategory === category.key;
        return (
          <div
            key={category.key}
            className="flex items-center space-x-2 px-4 py-2 rounded-full cursor-pointer transition-all relative"
            style={{
              backgroundColor: '#1F1F1F',
              borderColor: '#242424',
              border: '1px solid',
              transform: isActive ? 'translateY(-2px)' : 'translateY(0)',
              boxShadow: isActive ? '0 4px 12px rgba(255, 119, 0, 0.3)' : 'none',
              opacity: activeCategory === null || isActive ? 1 : 0.5
            }}
            onClick={() => setActiveCategory(isActive ? null : category.key)}
          >
            <div className="w-3.5 h-3.5 rounded" style={{ backgroundColor: category.color }} />
            <p className="text-sm font-semibold" style={{ color: '#F2F2F2' }}>{category.name}</p>
            <div
              style={{
                position: 'absolute',
                bottom: 0,
                left: '50%',
                transform: `translateX(-50%) scaleX(${isActive ? 1 : 0})`,
                width: '80%',
                height: '3px',
                background: category.color,
                borderRadius: '2px',
                transition: 'transform 0.3s ease'
              }}
            />
          </div>
        );
      })}
    </div>
  );
};

<ResponsiveContainer width="100%" height={480}>
  <BarChart
    data={data}
    layout="vertical"  // CRITICAL: For HORIZONTAL bars, use layout="vertical" (Recharts convention)
    margin={{ top: 20, right: 20, left: 20, bottom: 20 }}
    onMouseMove={(state) => {
      if (state.isTooltipActive) {
        setHoveredBar(state.activeTooltipIndex);
      } else {
        setHoveredBar(null);
      }
    }}
    onMouseLeave={() => setHoveredBar(null)}
  >
    <defs>
      {colors.map((color, index) => (
        <React.Fragment key={index}>
          <linearGradient id={`horizontalGradient${index}`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={color} stopOpacity={1}/>
            <stop offset="100%" stopColor={color + 'dd'} stopOpacity={1}/>
          </linearGradient>
          <filter id={`horizontalShadow${index}`}>
            <feDropShadow dx="0" dy="4" stdDeviation="3" floodOpacity="0.1"/>
          </filter>
          <filter id={`horizontalShadowHover${index}`}>
            <feDropShadow dx="0" dy="12" stdDeviation="12" floodOpacity="0.2"/>
          </filter>
        </React.Fragment>
      ))}
    </defs>

    <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" horizontal={false} vertical={true} strokeOpacity={0.8} />

    <XAxis
      type="number"
      tick={{ fill: '#999999', fontSize: 15, fontWeight: 400 }}
      tickLine={false}
      axisLine={{ stroke: '#242424', strokeWidth: 2 }}
      stroke="#242424"
      label={{
        value: 'Number of Patients',
        position: 'insideBottom',
        offset: -10,
        style: { fill: '#F2F2F2', fontSize: 15, fontWeight: 600, letterSpacing: '0.5px' }
      }}
    />

    <YAxis
      type="category"
      dataKey="department"
      tick={{ fill: '#F2F2F2', fontSize: 15, fontWeight: 500 }}
      tickLine={false}
      axisLine={{ stroke: '#e5e7eb', strokeWidth: 2 }}
      width={110}
      stroke="#e5e7eb"
      label={{
        value: 'Department',
        angle: -90,
        position: 'insideLeft',
        style: { fill: '#F2F2F2', fontSize: 15, fontWeight: 600, letterSpacing: '0.5px' }
      }}
    />

    <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(0, 0, 0, 0.02)' }} />

    <Bar
      dataKey="patients"
      radius={[0, 20, 20, 0]}
      maxBarSize={40}
      animationDuration={1000}
      animationEasing="cubic-bezier(0.4, 0, 0.2, 1)"
      animationBegin={0}
    >
      {data.map((entry, index) => (
        <Cell
          key={`cell-${index}`}
          fill={`url(#horizontalGradient${index})`}
          opacity={
            hoveredBar === null || hoveredBar === index
              ? (activeCategory === null || activeCategory === entry.department ? 1 : 0.2)
              : (activeCategory === null || activeCategory === entry.department ? 0.35 : 0.2)
          }
          style={{
            cursor: 'pointer',
            transition: 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
            filter: hoveredBar === index
              ? `url(#horizontalShadowHover${index}) brightness(1.1)`
              : `url(#horizontalShadow${index})`,
            transform: hoveredBar === index ? 'translateX(8px) scaleY(1.1)' : 'translateX(0) scaleY(1)',
            transformOrigin: 'left center'
          }}
        />
      ))}
    </Bar>
  </BarChart>
</ResponsiveContainer>

{/* Render the custom legend below the chart */}
<CustomLegend />
```
""",
    "line_chart": """
LINE CHART - Multi-Series Comparison:
To compare multiple metrics/products/categories over time (Product A vs B vs C sales).

**MANDATORY: You MUST include the CustomLegend component with line charts.**
**MANDATORY: You MUST include the CustomTooltip component with styled gradient backgrounds as shown in TOOLTIP_PATTERN - DO NOT use simple plain text tooltips.**
**Do NOT skip the legend - use it exactly as provided below, including the state and rendering, and ensure that each legend entry correctly reflects the corresponding data series, labels, and colors.**
**Use full-width layout (grid-cols-1) for line chart with more than 7 data points to prevent label overlap.**

```jsx
// State for tracking active point and category
const [activePoint, setActivePoint] = React.useState(null);
const [activeCategory, setActiveCategory] = React.useState(null);

// Define categories for legend (adapt to your actual data series)
const categories = [
  { key: 'productA', name: 'Product A', color: '#FBBF24' },
  { key: 'productB', name: 'Product B', color: '#D946EF' },
  { key: 'productC', name: 'Product C', color: '#ec4899' }
];

// Custom Legend Component
const CustomLegend = () => {
  return (
    <div className="flex justify-center items-center space-x-6 flex-wrap gap-2 mt-6">
      {categories.map((category) => {
        const isActive = activeCategory === category.key;
        return (
          <div
            key={category.key}
            className="flex items-center space-x-2 px-4 py-2 rounded-full cursor-pointer transition-all relative"
            style={{
              backgroundColor: '#1F1F1F',
              borderColor: '#242424',
              border: '1px solid',
              transform: isActive ? 'translateY(-2px)' : 'translateY(0)',
              boxShadow: isActive ? '0 4px 12px rgba(255, 119, 0, 0.3)' : 'none',
              opacity: activeCategory === null || isActive ? 1 : 0.5
            }}
            onClick={() => setActiveCategory(isActive ? null : category.key)}
          >
            <div className="w-3.5 h-3.5 rounded" style={{ backgroundColor: category.color }} />
            <p className="text-sm font-semibold" style={{ color: '#F2F2F2' }}>{category.name}</p>
            <div
              style={{
                position: 'absolute',
                bottom: 0,
                left: '50%',
                transform: `translateX(-50%) scaleX(${isActive ? 1 : 0})`,
                width: '80%',
                height: '3px',
                background: category.color,
                borderRadius: '2px',
                transition: 'transform 0.3s ease'
              }}
            />
          </div>
        );
      })}
    </div>
  );
};

// Data should contain multiple metrics: { month: 'Jan', productA: 35000, productB: 28000, productC: 22000 }

<ResponsiveContainer width="100%" height={450}>
  <LineChart
    data={data}
    margin={{ top: 20, right: 40, left: 40, bottom: 20 }}
    onMouseMove={(state) => {
      if (state.isTooltipActive) {
        setActivePoint(state.activeTooltipIndex);
      }
    }}
    onMouseLeave={() => setActivePoint(null)}
  >
    <defs>
      <linearGradient id="gradientProductA" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="#FBBF24" stopOpacity={0.3}/>
        <stop offset="100%" stopColor="#FBBF24" stopOpacity={0}/>
      </linearGradient>
      <linearGradient id="gradientProductB" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="#D946EF" stopOpacity={0.3}/>
        <stop offset="100%" stopColor="#D946EF" stopOpacity={0}/>
      </linearGradient>
      <linearGradient id="gradientProductC" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="#ec4899" stopOpacity={0.3}/>
        <stop offset="100%" stopColor="#ec4899" stopOpacity={0}/>
      </linearGradient>
    </defs>

    <CartesianGrid strokeDasharray="3 3" stroke="#242424" strokeOpacity={0.8} />

    <XAxis
      dataKey="month"
      height={60}
      tick={{ fill: '#999999', fontSize: 15, fontWeight: 400 }}
      stroke="#242424"
      axisLine={{ stroke: '#242424', strokeWidth: 2 }}
      tickLine={false}
      label={{
        value: 'Month',
        position: 'insideBottom',
        offset: -10,
        style: { fill: '#F2F2F2', fontSize: 15, fontWeight: 600, letterSpacing: '0.5px' }
      }}
    />

    <YAxis
      tick={{ fill: '#999999', fontSize: 15, fontWeight: 400 }}
      tickFormatter={(value) => `$${value / 1000}k`}
      label={{
        value: 'Sales Revenue',
        angle: -90,
        position: 'insideLeft',
        style: { fill: '#F2F2F2', fontSize: 15, fontWeight: 600, letterSpacing: '0.5px' }
      }}
      stroke="#242424"
      axisLine={{ stroke: '#242424', strokeWidth: 2 }}
      tickLine={false}
    />

    <Tooltip content={<CustomTooltip />} cursor={{ strokeDasharray: '3 3', stroke: '#242424', strokeWidth: 1 }} />

    {/* Product A Line with Area */}
    <Area
      type="monotone"
      dataKey="productA"
      stroke="none"
      fill="url(#gradientProductA)"
      fillOpacity={activeCategory === null || activeCategory === 'productA' ? 1 : 0.2}
      animationDuration={1000}
      animationEasing="ease-in-out"
    />
    <Line
      type="monotone"
      dataKey="productA"
      stroke="#FBBF24"
      strokeWidth={3}
      strokeOpacity={activeCategory === null || activeCategory === 'productA' ? 1 : 0.2}
      strokeLinecap="round"
      strokeLinejoin="round"
      dot={{
        fill: '#FBBF24',
        strokeWidth: 2,
        r: 5,
        stroke: '#ffffff'
      }}
      activeDot={{
        r: 7,
        fill: '#FBBF24',
        stroke: '#ffffff',
        strokeWidth: 2
      }}
      animationDuration={1500}
      animationEasing="ease-in-out"
    />

    {/* Product B Line with Area */}
    <Area
      type="monotone"
      dataKey="productB"
      stroke="none"
      fill="url(#gradientProductB)"
      fillOpacity={activeCategory === null || activeCategory === 'productB' ? 1 : 0.2}
      animationDuration={1000}
      animationEasing="ease-in-out"
    />
    <Line
      type="monotone"
      dataKey="productB"
      stroke="#D946EF"
      strokeWidth={3}
      strokeOpacity={activeCategory === null || activeCategory === 'productB' ? 1 : 0.2}
      strokeLinecap="round"
      strokeLinejoin="round"
      dot={{
        fill: '#D946EF',
        strokeWidth: 2,
        r: 5,
        stroke: '#ffffff'
      }}
      activeDot={{
        r: 7,
        fill: '#D946EF',
        stroke: '#ffffff',
        strokeWidth: 2
      }}
      animationDuration={1500}
      animationEasing="ease-in-out"
    />

    {/* Product C Line with Area */}
    <Area
      type="monotone"
      dataKey="productC"
      stroke="none"
      fill="url(#gradientProductC)"
      fillOpacity={activeCategory === null || activeCategory === 'productC' ? 1 : 0.2}
      animationDuration={1000}
      animationEasing="ease-in-out"
    />
    <Line
      type="monotone"
      dataKey="productC"
      stroke="#ec4899"
      strokeWidth={3}
      strokeOpacity={activeCategory === null || activeCategory === 'productC' ? 1 : 0.2}
      strokeLinecap="round"
      strokeLinejoin="round"
      dot={{
        fill: '#ec4899',
        strokeWidth: 2,
        r: 5,
        stroke: '#ffffff'
      }}
      activeDot={{
        r: 7,
        fill: '#ec4899',
        stroke: '#ffffff',
        strokeWidth: 2
      }}
      animationDuration={1500}
      animationEasing="ease-in-out"
    />
  </LineChart>
</ResponsiveContainer>

{/* Render the custom legend below the chart */}
<CustomLegend />
```
""",
    "area_chart": """
AREA CHART - Cumulative or Volume Trends:
To show volume/cumulative values over time. Great for emphasizing magnitude.

**MANDATORY: You MUST include the CustomLegend component with area charts.**
**MANDATORY: You MUST include the CustomTooltip component with styled gradient backgrounds as shown in TOOLTIP_PATTERN - DO NOT use simple plain text tooltips.**
**Do NOT skip the legend - use it exactly as provided below, even for single series (shows the pattern), and ensure that each legend entry correctly reflects the corresponding data series, labels, and colors.**
**Use full-width layout (grid-cols-1) for area chart with more than 7 data points to prevent label overlap.**

```jsx
// State for active point and category tracking
const [activePoint, setActivePoint] = React.useState(null);
const [activeCategory, setActiveCategory] = React.useState(null);

// Define categories for legend (for single series, you can have just one; for multiple series, list all)
const categories = [
  { key: 'cumulative', name: 'Cumulative Discharges', color: '#a855f7' }
  // Add more series here if you have multiple area charts: { key: 'series2', name: 'Series 2', color: '#FBBF24' }
];

// Custom Legend Component
const CustomLegend = () => {
  return (
    <div className="flex justify-center items-center space-x-6 flex-wrap gap-2 mt-6">
      {categories.map((category) => {
        const isActive = activeCategory === category.key;
        return (
          <div
            key={category.key}
            className="flex items-center space-x-2 px-4 py-2 rounded-full cursor-pointer transition-all relative"
            style={{
              backgroundColor: '#1F1F1F',
              borderColor: '#242424',
              border: '1px solid',
              transform: isActive ? 'translateY(-2px)' : 'translateY(0)',
              boxShadow: isActive ? '0 4px 12px rgba(255, 119, 0, 0.3)' : 'none',
              opacity: activeCategory === null || isActive ? 1 : 0.5
            }}
            onClick={() => setActiveCategory(isActive ? null : category.key)}
          >
            <div className="w-3.5 h-3.5 rounded" style={{ backgroundColor: category.color }} />
            <p className="text-sm font-semibold" style={{ color: '#F2F2F2' }}>{category.name}</p>
            <div
              style={{
                position: 'absolute',
                bottom: 0,
                left: '50%',
                transform: `translateX(-50%) scaleX(${isActive ? 1 : 0})`,
                width: '80%',
                height: '3px',
                background: category.color,
                borderRadius: '2px',
                transition: 'transform 0.3s ease'
              }}
            />
          </div>
        );
      })}
    </div>
  );
};

// Custom Dot component for enhanced data point visualization
const CustomDot = (props) => {
  const { cx, cy, payload } = props;
  if (activePoint === payload.week) {
    return (
      <g>
        <circle cx={cx} cy={cy} r={12} fill="#a855f7" opacity={0.2} />
        <circle cx={cx} cy={cy} r={7} fill="#a855f7" stroke="#ffffff" strokeWidth={3} />
      </g>
    );
  }
  return <circle cx={cx} cy={cy} r={5} fill="#a855f7" opacity={0.7} stroke="#ffffff" strokeWidth={2} />;
};

<ResponsiveContainer width="100%" height={450}>
  <AreaChart
    data={data}
    margin={{ top: 40, right: 40, left: 40, bottom: 40 }}
    onMouseMove={(state) => {
      if (state.isTooltipActive) {
        setActivePoint(state.activeLabel);
      }
    }}
    onMouseLeave={() => setActivePoint(null)}
  >
    <defs>
      <linearGradient id="colorCumulative" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="#a855f7" stopOpacity={0.7} />
        <stop offset="50%" stopColor="#ec4899" stopOpacity={0.4} />
        <stop offset="100%" stopColor="#f43f5e" stopOpacity={0.1} />
      </linearGradient>
      <linearGradient id="strokeGradient" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stopColor="#D946EF" />
        <stop offset="50%" stopColor="#d946ef" />
        <stop offset="100%" stopColor="#f43f5e" />
      </linearGradient>
    </defs>

    <CartesianGrid strokeDasharray="3 3" stroke="#242424" opacity={0.4} />

    <XAxis
      dataKey="week"
      height={60}
      tick={{ fill: '#F2F2F2', fontSize: 15, fontWeight: 600 }}
      stroke="#242424"
      label={{
        value: 'Week',
        position: 'insideBottom',
        offset: -10,
        style: { fill: '#F2F2F2', fontSize: 16, fontWeight: 700 }
      }}
    />

    <YAxis
      tick={{ fill: '#999999', fontSize: 15, fontWeight: 500 }}
      tickFormatter={(value) => value.toLocaleString()}
      label={{
        value: 'Cumulative Discharges',
        angle: -90,
        position: 'insideLeft',
        style: { fill: '#F2F2F2', fontSize: 16, fontWeight: 700 }
      }}
      stroke="#242424"
    />

    <Tooltip
      content={<CustomTooltip />}
      cursor={{ stroke: '#a855f7', strokeWidth: 2, strokeDasharray: '5 5' }}
    />

    <Area
      type="monotone"
      dataKey="cumulative"
      stroke="url(#strokeGradient)"
      strokeWidth={4}
      strokeOpacity={activeCategory === null || activeCategory === 'cumulative' ? 1 : 0.2}
      fill="url(#colorCumulative)"
      fillOpacity={activeCategory === null || activeCategory === 'cumulative' ? 1 : 0.2}
      dot={<CustomDot />}
      activeDot={{ r: 9, fill: '#a855f7', stroke: '#ffffff', strokeWidth: 3 }}
      animationDuration={1500}
      animationEasing="ease-in-out"
    />
  </AreaChart>
</ResponsiveContainer>

{/* Render the custom legend below the chart */}
<CustomLegend />
```
""",
    "pie_chart": """
PIE CHART - Composition / Percentage Breakdown:
To show proportional breakdown of categories. ALWAYS use different colors for each slice.

**MANDATORY: You MUST include the CustomLegend component with pie charts.**
**MANDATORY: You MUST include the CustomTooltip component with styled gradient backgrounds as shown in TOOLTIP_PATTERN - DO NOT use simple plain text tooltips.**
**Do NOT skip the legend - use it exactly as provided below, including the state and rendering, and ensure that each legend entry correctly reflects the corresponding data series, labels, and colors.**

```jsx
// State for active index and active category tracking
const [activeIndex, setActiveIndex] = React.useState(null);
const [activeCategory, setActiveCategory] = React.useState(null);

// Vibrant color palette for different categories
const colors = ['#FF7700', '#FF66CC', '#FBBF24', '#D946EF', '#ec4899', '#f59e0b', '#f43f5e', '#ef4444'];

// Add colors to your data
const dataWithColors = data.map((item, index) => ({
  ...item,
  color: colors[index % colors.length]
}));

// Map data to categories for legend
const categories = dataWithColors.map((item) => ({
  key: item.name || item.category,  // Adapt to your data key
  name: item.name || item.category, // Adapt to your data name
  color: item.color
}));

// Custom Legend Component
const CustomLegend = () => {
  return (
    <div className="flex justify-center items-center space-x-6 flex-wrap gap-2 mt-6">
      {categories.map((category) => {
        const isActive = activeCategory === category.key;
        return (
          <div
            key={category.key}
            className="flex items-center space-x-2 px-4 py-2 rounded-full cursor-pointer transition-all relative"
            style={{
              backgroundColor: '#1F1F1F',
              borderColor: '#242424',
              border: '1px solid',
              transform: isActive ? 'translateY(-2px)' : 'translateY(0)',
              boxShadow: isActive ? '0 4px 12px rgba(255, 119, 0, 0.3)' : 'none',
              opacity: activeCategory === null || isActive ? 1 : 0.5
            }}
            onClick={() => setActiveCategory(isActive ? null : category.key)}
          >
            <div className="w-3.5 h-3.5 rounded" style={{ backgroundColor: category.color }} />
            <p className="text-sm font-semibold" style={{ color: '#F2F2F2' }}>{category.name}</p>
            <div
              style={{
                position: 'absolute',
                bottom: 0,
                left: '50%',
                transform: `translateX(-50%) scaleX(${isActive ? 1 : 0})`,
                width: '80%',
                height: '3px',
                background: category.color,
                borderRadius: '2px',
                transition: 'transform 0.3s ease'
              }}
            />
          </div>
        );
      })}
    </div>
  );
};

// Calculate total for center display
const total = dataWithColors.reduce((sum, item) => sum + item.value, 0);

// Custom active shape for dramatic hover effect (slice expands with outer ring)
const renderActiveShape = (props) => {
  const { cx, cy, innerRadius, outerRadius, startAngle, endAngle, fill } = props;

  return (
    <g>
      <Sector
        cx={cx}
        cy={cy}
        innerRadius={innerRadius}
        outerRadius={outerRadius + 20}
        startAngle={startAngle}
        endAngle={endAngle}
        fill={fill}
        style={{ filter: 'drop-shadow(0 12px 35px rgba(0,0,0,0.4))' }}
      />
      <Sector
        cx={cx}
        cy={cy}
        startAngle={startAngle}
        endAngle={endAngle}
        innerRadius={outerRadius + 25}
        outerRadius={outerRadius + 30}
        fill={fill}
        opacity={0.4}
      />
    </g>
  );
};

const onPieEnter = (_, index) => {
  setActiveIndex(index);
};

const onPieLeave = () => {
  setActiveIndex(null);
};

<ResponsiveContainer width="100%" height={520}>
  <PieChart>
    <Pie
      activeIndex={activeIndex}
      activeShape={renderActiveShape}
      data={dataWithColors}
      cx="50%"
      cy="50%"
      outerRadius={180}
      fill="#8884d8"
      dataKey="value"
      onMouseEnter={onPieEnter}
      onMouseLeave={onPieLeave}
      animationDuration={800}
      animationEasing="cubic-bezier(0.4, 0, 0.2, 1)"
      animationBegin={0}
      label={({ cx, cy, midAngle, innerRadius, outerRadius, percent, payload }) => {
        const RADIAN = Math.PI / 180;
        const radius = outerRadius + 30;
        const x = cx + radius * Math.cos(-midAngle * RADIAN);
        const y = cy + radius * Math.sin(-midAngle * RADIAN);

        return (
          <text
            x={x}
            y={y}
            fill={payload.color}
            textAnchor="middle"
            dominantBaseline="central"
            fontSize="16"
            fontWeight="700"
          >
            {`${(percent * 100).toFixed(0)}%`}
          </text>
        );
      }}
    >
      {dataWithColors.map((entry, index) => {
        const categoryKey = entry.name || entry.category;
        const isFiltered = activeCategory !== null && activeCategory !== categoryKey;
        return (
          <Cell
            key={`cell-${index}`}
            fill={entry.color}
            opacity={
              activeIndex === null || activeIndex === index
                ? (isFiltered ? 0.15 : 1)
                : (isFiltered ? 0.1 : 0.25)
            }
            stroke="#0A0A0A"
            strokeWidth={4}
            style={{
              cursor: 'pointer',
              transition: 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
              filter: activeIndex === index
                ? 'brightness(1.15) drop-shadow(0 8px 16px rgba(0,0,0,0.3))'
                : 'none',
              transform: activeIndex === index ? 'scale(1.08)' : 'scale(1)',
              transformOrigin: 'center'
            }}
          />
        );
      })}
    </Pie>
    <Tooltip content={<CustomTooltip />} />
  </PieChart>
</ResponsiveContainer>

{/* Render the custom legend below the chart */}
<CustomLegend />
```
""",
    "donut_chart": """
DONUT CHART - Composition with Central Metric:
Similar to pie chart but with a hole in center. To show percentage breakdowns with a central focus metric.

**MANDATORY: You MUST include the CustomLegend component with donut charts.**
**MANDATORY: You MUST include the CustomTooltip component with styled gradient backgrounds as shown in TOOLTIP_PATTERN - DO NOT use simple plain text tooltips.**
**Do NOT skip the legend - use it exactly as provided below, including the state and rendering, and ensure that each legend entry correctly reflects the corresponding data series, labels, and colors.**

```jsx
// State for tracking active segment and active category
const [activeIndex, setActiveIndex] = React.useState(null);
const [activeCategory, setActiveCategory] = React.useState(null);

// Vibrant color palette for different categories
const colors = ['#FF7700', '#FF66CC', '#FBBF24', '#D946EF', '#ec4899', '#f59e0b', '#f43f5e', '#ef4444'];

// Add colors to your data
const dataWithColors = data.map((item, index) => ({
  ...item,
  color: colors[index % colors.length]
}));

// Map data to categories for legend
const categories = dataWithColors.map((item) => ({
  key: item.name || item.category,  // Adapt to your data key
  name: item.name || item.category, // Adapt to your data name
  color: item.color
}));

// Custom Legend Component
const CustomLegend = () => {
  return (
    <div className="flex justify-center items-center space-x-6 flex-wrap gap-2 mt-6">
      {categories.map((category) => {
        const isActive = activeCategory === category.key;
        return (
          <div
            key={category.key}
            className="flex items-center space-x-2 px-4 py-2 rounded-full cursor-pointer transition-all relative"
            style={{
              backgroundColor: '#1F1F1F',
              borderColor: '#242424',
              border: '1px solid',
              transform: isActive ? 'translateY(-2px)' : 'translateY(0)',
              boxShadow: isActive ? '0 4px 12px rgba(255, 119, 0, 0.3)' : 'none',
              opacity: activeCategory === null || isActive ? 1 : 0.5
            }}
            onClick={() => setActiveCategory(isActive ? null : category.key)}
          >
            <div className="w-3.5 h-3.5 rounded" style={{ backgroundColor: category.color }} />
            <p className="text-sm font-semibold" style={{ color: '#F2F2F2' }}>{category.name}</p>
            <div
              style={{
                position: 'absolute',
                bottom: 0,
                left: '50%',
                transform: `translateX(-50%) scaleX(${isActive ? 1 : 0})`,
                width: '80%',
                height: '3px',
                background: category.color,
                borderRadius: '2px',
                transition: 'transform 0.3s ease'
              }}
            />
          </div>
        );
      })}
    </div>
  );
};

// Calculate total for center display
const total = dataWithColors.reduce((sum, item) => sum + item.value, 0);

// Custom label for percentage display
const renderCustomLabel = ({ cx, cy, midAngle, outerRadius, percent, payload }) => {
  const RADIAN = Math.PI / 180;
  const radius = outerRadius + 35;
  const x = cx + radius * Math.cos(-midAngle * RADIAN);
  const y = cy + radius * Math.sin(-midAngle * RADIAN);

  return (
    <text
      x={x}
      y={y}
      fill={payload.color}
      textAnchor="middle"
      dominantBaseline="central"
      fontSize="16"
      fontWeight="700"
    >
      {`${(percent * 100).toFixed(1)}%`}
    </text>
  );
};

<ResponsiveContainer width="100%" height={500}>
  <PieChart>
    <defs>
      <linearGradient id="centerGradient" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stopColor="#D946EF" stopOpacity={1}/>
        <stop offset="50%" stopColor="#ec4899" stopOpacity={1}/>
        <stop offset="100%" stopColor="#FBBF24" stopOpacity={1}/>
      </linearGradient>
    </defs>

    <Pie
      data={dataWithColors}
      cx="50%"
      cy="50%"
      labelLine={false}
      label={renderCustomLabel}
      outerRadius={180}
      innerRadius={95}
      dataKey="value"
      onMouseEnter={(_, index) => setActiveIndex(index)}
      onMouseLeave={() => setActiveIndex(null)}
      animationDuration={800}
      animationEasing="cubic-bezier(0.4, 0, 0.2, 1)"
      animationBegin={0}
    >
      {dataWithColors.map((entry, index) => {
        const categoryKey = entry.name || entry.category;
        const isFiltered = activeCategory !== null && activeCategory !== categoryKey;
        return (
          <Cell
            key={`cell-${index}`}
            fill={entry.color}
            opacity={
              activeIndex === null || activeIndex === index
                ? (isFiltered ? 0.15 : 1)
                : (isFiltered ? 0.1 : 0.3)
            }
            stroke="#0A0A0A"
            strokeWidth={3}
            style={{
              cursor: 'pointer',
              transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
              filter: activeIndex === index
                ? 'brightness(1.15) drop-shadow(0 4px 8px rgba(0,0,0,0.3))'
                : 'none',
              transform: activeIndex === index ? 'scale(1.05)' : 'scale(1)',
              transformOrigin: 'center'
            }}
          />
        );
      })}
    </Pie>
    <Tooltip content={<CustomTooltip />} />

    {/* Center label */}
    <text x="50%" y="50%" textAnchor="middle" dominantBaseline="middle">
      <tspan x="50%" dy="-10" fontSize="48" fontWeight="700" fill="url(#centerGradient)">
        {total.toLocaleString()}
      </tspan>
      <tspan x="50%" dy="30" fontSize="14" fontWeight="500" fill="#999999" textTransform="uppercase" letterSpacing="0.5">
        Total
      </tspan>
    </text>
  </PieChart>
</ResponsiveContainer>

{/* Render the custom legend below the chart */}
<CustomLegend />
```
""",
    "scatter_plot": """
SCATTER PLOT - Correlation / Distribution Analysis:
To show correlation between two variables or distribution patterns.

**MANDATORY: You MUST include the CustomLegend component with scatter plots.**
**MANDATORY: You MUST include the CustomTooltip component with styled gradient backgrounds as shown in TOOLTIP_PATTERN - DO NOT use simple plain text tooltips.**
**Do NOT skip the legend - use it exactly as provided below, including the state and rendering, and ensure that each legend entry correctly reflects the corresponding data series, labels, and colors.**
**Use full-width layout (grid-cols-1) for scatter chart with more than 7 data points to prevent label overlap.**

```jsx
// State for tracking active category
const [activeCategory, setActiveCategory] = React.useState(null);

// Vibrant color palette for scatter points
const colors = ['#FF7700', '#FF66CC', '#FBBF24', '#D946EF', '#ec4899', '#f59e0b', '#f43f5e', '#ef4444'];

// Add colors to your data
const dataWithColors = data.map((item, index) => ({
  ...item,
  color: colors[index % colors.length]
}));

// Map data to categories for legend (if data has categories)
const categories = dataWithColors.map((item, index) => ({
  key: item.category || `point-${index}`,  // Adapt to your data key
  name: item.category || `Point ${index + 1}`, // Adapt to your data name
  color: item.color
}));

// Custom Legend Component
const CustomLegend = () => {
  return (
    <div className="flex justify-center items-center space-x-6 flex-wrap gap-2 mt-6">
      {categories.map((category) => {
        const isActive = activeCategory === category.key;
        return (
          <div
            key={category.key}
            className="flex items-center space-x-2 px-4 py-2 rounded-full cursor-pointer transition-all relative"
            style={{
              backgroundColor: '#1F1F1F',
              borderColor: '#242424',
              border: '1px solid',
              transform: isActive ? 'translateY(-2px)' : 'translateY(0)',
              boxShadow: isActive ? '0 4px 12px rgba(255, 119, 0, 0.3)' : 'none',
              opacity: activeCategory === null || isActive ? 1 : 0.5
            }}
            onClick={() => setActiveCategory(isActive ? null : category.key)}
          >
            <div className="w-3.5 h-3.5 rounded" style={{ backgroundColor: category.color }} />
            <p className="text-sm font-semibold" style={{ color: '#F2F2F2' }}>{category.name}</p>
            <div
              style={{
                position: 'absolute',
                bottom: 0,
                left: '50%',
                transform: `translateX(-50%) scaleX(${isActive ? 1 : 0})`,
                width: '80%',
                height: '3px',
                background: category.color,
                borderRadius: '2px',
                transition: 'transform 0.3s ease'
              }}
            />
          </div>
        );
      })}
    </div>
  );
};

// Custom Dot component for styled data points with legend filtering
const CustomDot = (props) => {
  const { cx, cy, payload } = props;
  const radius = 8;
  const categoryKey = payload.category || `point-${payload.index}`;
  const isFiltered = activeCategory !== null && activeCategory !== categoryKey;

  return (
    <g>
      <circle
        cx={cx}
        cy={cy}
        r={radius}
        fill={payload.color}
        opacity={isFiltered ? 0.15 : 0.7}
        stroke="#ffffff"
        strokeWidth={2}
        style={{
          cursor: 'pointer',
          transition: 'opacity 0.3s ease'
        }}
      />
    </g>
  );
};

<ResponsiveContainer width="100%" height={500}>
  <ScatterChart margin={{ top: 40, right: 40, left: 40, bottom: 40 }}>
    <defs>
      <filter id="glow">
        <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
        <feMerge>
          <feMergeNode in="coloredBlur"/>
          <feMergeNode in="SourceGraphic"/>
        </feMerge>
      </filter>
    </defs>

    <CartesianGrid strokeDasharray="3 3" stroke="#242424" strokeOpacity={0.4} />

    <XAxis
      type="number"
      dataKey="age"
      tick={{ fill: '#F2F2F2', fontSize: 15, fontWeight: 600 }}
      stroke="#242424"
      label={{
        value: 'X Axis',
        position: 'insideBottom',
        offset: -10,
        style: { fill: '#F2F2F2', fontSize: 16, fontWeight: 700 }
      }}
    />

    <YAxis
      type="number"
      dataKey="stay"
      tick={{ fill: '#F2F2F2', fontSize: 15, fontWeight: 600 }}
      stroke="#242424"
      label={{
        value: 'Y Axis',
        angle: -90,
        position: 'insideLeft',
        style: { fill: '#F2F2F2', fontSize: 16, fontWeight: 700 }
      }}
    />

    <ZAxis range={[60, 200]} />

    <Tooltip content={<CustomTooltip />} cursor={{ strokeDasharray: '3 3' }} />

    <ReferenceLine
      x={avgAge}
      stroke="#ec4899"
      strokeWidth={2}
      strokeDasharray="8 4"
      label={{
        value: `Avg Age: ${avgAge}`,
        position: 'top',
        fill: '#ec4899',
        fontSize: 12,
        fontWeight: 'bold'
      }}
    />

    <ReferenceLine
      y={avgStay}
      stroke="#f59e0b"
      strokeWidth={2}
      strokeDasharray="8 4"
      label={{
        value: `Avg Stay: ${avgStay} days`,
        position: 'right',
        fill: '#f59e0b',
        fontSize: 12,
        fontWeight: 'bold'
      }}
    />

    <Scatter
      data={dataWithColors}
      shape={<CustomDot />}
    />
  </ScatterChart>
</ResponsiveContainer>

{/* Render the custom legend below the chart */}
<CustomLegend />
```
""",
    "stacked_bar_chart": """
STACKED BAR CHART - Composition Breakdown Over Categories:
To show part-to-whole relationships across categories. Each segment must have a distinct color.

**MANDATORY: You MUST include the CustomLegend component with stacked bar charts.**
**MANDATORY: You MUST include the CustomTooltip component with styled gradient backgrounds as shown in TOOLTIP_PATTERN - DO NOT use simple plain text tooltips.**
**Do NOT skip the legend - use it exactly as provided below, including the state and rendering, and ensure that each legend entry correctly reflects the corresponding data series, labels, and colors.**
**Use full-width layout (grid-cols-1) for stacked bar chart with more than 7 data points to prevent label overlap.**

```jsx
// State for tracking active category
const [activeCategory, setActiveCategory] = React.useState(null);

// Define stack categories with metadata
const stackCategories = [
  { key: 'emergency', name: 'Emergency', color: '#ef4444' },
  { key: 'scheduled', name: 'Scheduled', color: '#FBBF24' },
  { key: 'transfer', name: 'Transfer', color: '#D946EF' }
];

// Custom Legend Component
const CustomLegend = () => {
  return (
    <div className="flex justify-center items-center space-x-6 flex-wrap gap-2 mt-6">
      {stackCategories.map((category) => {
        const isActive = activeCategory === category.key;
        return (
          <div
            key={category.key}
            className="flex items-center space-x-2 px-4 py-2 rounded-full cursor-pointer transition-all relative"
            style={{
              backgroundColor: '#1F1F1F',
              borderColor: '#242424',
              border: '1px solid',
              transform: isActive ? 'translateY(-2px)' : 'translateY(0)',
              boxShadow: isActive ? '0 4px 12px rgba(255, 119, 0, 0.3)' : 'none',
              opacity: activeCategory === null || isActive ? 1 : 0.5
            }}
            onClick={() => setActiveCategory(isActive ? null : category.key)}
          >
            <div className="w-3.5 h-3.5 rounded" style={{ backgroundColor: category.color }} />
            <p className="text-sm font-semibold" style={{ color: '#F2F2F2' }}>{category.name}</p>
            <div
              style={{
                position: 'absolute',
                bottom: 0,
                left: '50%',
                transform: `translateX(-50%) scaleX(${isActive ? 1 : 0})`,
                width: '80%',
                height: '3px',
                background: category.color,
                borderRadius: '2px',
                transition: 'transform 0.3s ease'
              }}
            />
          </div>
        );
      })}
    </div>
  );
};

// Custom Tooltip for individual stack segments
const CustomStackedTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    // payload[0] contains the specific stack segment being hovered
    const data = payload[0];
    const categoryInfo = stackCategories.find(cat => cat.key === data.dataKey);

    return (
      <div className="bg-gradient-to-br from-gray-900 to-gray-800 px-6 py-5 rounded-2xl shadow-2xl border-3 backdrop-blur-sm"
           style={{ backgroundColor: '#0F0F0F', borderColor: categoryInfo?.color || '#FF7700', border: `2px solid ${categoryInfo?.color || '#FF7700'}` }}>
        {/* Category Header */}
        <div className="flex items-center justify-between mb-3">
          <p className="text-sm font-bold uppercase tracking-wider"
             style={{ color: categoryInfo?.color || '#FF7700' }}>
            {categoryInfo?.name || data.dataKey}
          </p>
        </div>

        {/* Location/Category Name */}
        <p className="text-sm font-semibold text-gray-600 mb-4">{label}</p>

        <div className="space-y-3">
          {/* Main Value Display */}
          <div>
            <p className="text-xs text-gray-500 font-semibold mb-1">Count</p>
            <div className="flex items-baseline space-x-2">
              <p className="text-5xl font-black bg-gradient-to-r bg-clip-text text-transparent"
                 style={{
                   backgroundImage: `linear-gradient(to right, ${categoryInfo?.color}, ${categoryInfo?.color}dd)`
                 }}>
                {data.value.toLocaleString()}
              </p>
              <p className="text-2xl font-bold text-gray-500">patients</p>
            </div>
          </div>

          {/* Stack Percentage */}
          <div className="pt-3 border-t-2" style={{ borderColor: `${categoryInfo?.color}30` }}>
            <p className="text-xs text-gray-500 font-semibold">
              Part of total stack
            </p>
          </div>
        </div>
      </div>
    );
  }
  return null;
};

<ResponsiveContainer width="100%" height={480}>
  <BarChart
    data={data}
    margin={{ top: 20, right: 40, left: 20, bottom: 20 }}
    barSize={70}
  >
    <defs>
      {stackCategories.map((category) => (
        <linearGradient key={category.key} id={`gradient-${category.key}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={category.color} stopOpacity={1}/>
          <stop offset="100%" stopColor={category.color} stopOpacity={0.7}/>
        </linearGradient>
      ))}
      <filter id="shadow">
        <feDropShadow dx="0" dy="4" stdDeviation="4" floodOpacity="0.3"/>
      </filter>
    </defs>

    <CartesianGrid strokeDasharray="3 3" stroke="#242424" strokeOpacity={0.4} />

    <XAxis
      dataKey="department"
      tick={{ fill: '#F2F2F2', fontSize: 15, fontWeight: 600 }}
      stroke="#242424"
      height={60}
      label={{
        value: 'Department',
        position: 'insideBottom',
        offset: -10,
        style: { fill: '#1f2937', fontSize: 15, fontWeight: 700 }
      }}
    />

    <YAxis
      tick={{ fill: '#F2F2F2', fontSize: 15, fontWeight: 600 }}
      stroke="#242424"
      label={{
        value: 'Number of Patients',
        angle: -90,
        position: 'insideLeft',
        style: { fill: '#F2F2F2', fontSize: 16, fontWeight: 700 }
      }}
    />

    <Tooltip content={<CustomStackedTooltip />} cursor={{ fill: 'rgba(99, 102, 241, 0.08)' }} />

    {/* Render each stack with individual hover capability and legend filtering */}
    {stackCategories.map((category, index) => (
      <Bar
        key={category.key}
        dataKey={category.key}
        stackId="a"
        fill={`url(#gradient-${category.key})`}
        fillOpacity={activeCategory === null || activeCategory === category.key ? 1 : 0.2}
        radius={index === stackCategories.length - 1 ? [8, 8, 0, 0] : [0, 0, 0, 0]}
      />
    ))}
  </BarChart>
</ResponsiveContainer>

{/* Render the custom legend below the chart */}
<CustomLegend />
```
""",
    "grouped_bar_chart": """
GROUPED BAR CHART - Multi-Category Comparison:
To show comparing multiple series across categories. Each series has a consistent color across all groups.

**MANDATORY: You MUST include the CustomLegend component with grouped bar charts.**
**MANDATORY: You MUST include the CustomTooltip component with styled gradient backgrounds as shown in TOOLTIP_PATTERN - DO NOT use simple plain text tooltips.**
**Do NOT skip the legend - use it exactly as provided below, including the state and rendering, and ensure that each legend entry correctly reflects the corresponding data series, labels, and colors.**
**Use full-width layout (grid-cols-1) for grouped bar chart with more than 7 data points to prevent label overlap.**

```jsx
// State for tracking interactions
const [hoveredIndex, setHoveredIndex] = React.useState(null);
const [activeCategory, setActiveCategory] = React.useState(null);

// Define categories with colors
const categories = [
  { key: 'emergency', name: 'Emergency', color: '#ef4444' },
  { key: 'surgery', name: 'Surgery', color: '#FBBF24' },
  { key: 'cardiology', name: 'Cardiology', color: '#D946EF' },
  { key: 'pediatrics', name: 'Pediatrics', color: '#ec4899' },
  { key: 'orthopedics', name: 'Orthopedics', color: '#f59e0b' }
];

// Custom Tooltip for individual grouped bars
const CustomGroupedTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    // payload[0] contains the specific bar being hovered
    const data = payload[0];
    const categoryInfo = categories.find(cat => cat.key === data.dataKey);

    return (
      <div className="bg-gradient-to-br from-gray-900 to-gray-800 px-6 py-5 rounded-2xl shadow-2xl border-3 backdrop-blur-sm"
           style={{ backgroundColor: '#0F0F0F', borderColor: categoryInfo?.color || '#FF7700', border: `2px solid ${categoryInfo?.color || '#FF7700'}` }}>
        {/* Category Header */}
        <div className="flex items-center justify-between mb-3">
          <p className="text-sm font-bold uppercase tracking-wider"
             style={{ color: categoryInfo?.color || '#FF7700' }}>
            {categoryInfo?.name || data.dataKey}
          </p>
        </div>

        {/* Time Period */}
        <p className="text-sm font-semibold text-gray-600 mb-4">{label}</p>

        <div className="space-y-3">
          {/* Main Value Display */}
          <div>
            <p className="text-xs text-gray-500 font-semibold mb-1">Revenue</p>
            <div className="flex items-baseline space-x-2">
              <p className="text-5xl font-black bg-gradient-to-r bg-clip-text text-transparent"
                 style={{
                   backgroundImage: `linear-gradient(to right, ${categoryInfo?.color}, ${categoryInfo?.color}dd)`
                 }}>
                ${(data.value / 1000).toFixed(0)}K
              </p>
            </div>
          </div>

          {/* Additional context */}
          <div className="pt-3 border-t-2" style={{ borderColor: `${categoryInfo?.color}30` }}>
            <p className="text-xs text-gray-500 font-semibold">
              Department performance for {label}
            </p>
          </div>
        </div>
      </div>
    );
  }
  return null;
};

// Custom Legend Component with Interactive Filtering
const CustomLegend = () => {
  return (
    <div className="flex justify-center items-center space-x-6 flex-wrap gap-2 mt-8">
      {categories.map((category) => {
        const isActive = activeCategory === category.key;

        return (
          <div
            key={category.key}
            className="flex items-center space-x-2 px-4 py-2 rounded-full cursor-pointer transition-all relative"
            style={{
              backgroundColor: '#f9fafb',
              transform: isActive ? 'translateY(-2px)' : 'translateY(0)',
              boxShadow: isActive ? '0 4px 12px rgba(0, 0, 0, 0.1)' : 'none',
              opacity: activeCategory === null || isActive ? 1 : 0.3
            }}
            onClick={() => setActiveCategory(isActive ? null : category.key)}
          >
            <div
              className="w-3.5 h-3.5 rounded"
              style={{ backgroundColor: category.color }}
            />
            <p className="text-sm font-semibold" style={{ color: '#F2F2F2' }}>{category.name}</p>
            <div
              style={{
                position: 'absolute',
                bottom: 0,
                left: '50%',
                transform: `translateX(-50%) scaleX(${isActive ? 1 : 0})`,
                width: '80%',
                height: '3px',
                background: category.color,
                borderRadius: '2px',
                transition: 'transform 0.3s ease'
              }}
            />
          </div>
        );
      })}
    </div>
  );
};

<ResponsiveContainer width="100%" height={500}>
  <BarChart
    data={data}
    margin={{ top: 20, right: 40, left: 20, bottom: 20 }}
    onMouseMove={(state) => {
      if (state.isTooltipActive) {
        setHoveredIndex(state.activeTooltipIndex);
      }
    }}
    onMouseLeave={() => setHoveredIndex(null)}
  >
    <defs>
      {categories.map((category, index) => (
        <React.Fragment key={index}>
          <linearGradient id={`gradient-${category.key}`} x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%" stopColor={category.color} stopOpacity={1}/>
            <stop offset="100%" stopColor={category.color + 'ee'} stopOpacity={1}/>
          </linearGradient>
          <filter id={`groupShadow${index}`}>
            <feDropShadow dx="0" dy="4" stdDeviation="3" floodOpacity="0.1"/>
          </filter>
          <filter id={`groupShadowHover${index}`}>
            <feDropShadow dx="0" dy="12" stdDeviation="12" floodOpacity="0.2"/>
          </filter>
        </React.Fragment>
      ))}
    </defs>

    <CartesianGrid strokeDasharray="3 3" stroke="#242424" strokeOpacity={0.8} vertical={false} />

    <XAxis
      dataKey="month"
      tick={{ fill: '#4b5563', fontSize: 15, fontWeight: 600 }}
      stroke="#242424"
      axisLine={{ stroke: '#242424', strokeWidth: 2 }}
      tickLine={false}
      height={60}
    />

    <YAxis
      tick={{ fill: '#999999', fontSize: 15, fontWeight: 400 }}
      tickFormatter={(value) => `${value / 1000}K`}
      stroke="#242424"
      axisLine={{ stroke: '#242424', strokeWidth: 2 }}
      tickLine={false}
      label={{
        value: 'Revenue ($)',
        angle: -90,
        position: 'insideLeft',
        style: { fill: '#F2F2F2', fontSize: 15, fontWeight: 600, letterSpacing: '0.5px' }
      }}
    />

    <Tooltip content={<CustomGroupedTooltip />} cursor={{ fill: 'rgba(0, 0, 0, 0.02)' }} />

    {/* Render multiple Bar components for grouped columns - NO stackId */}
    {categories.map((category, catIndex) => (
      <Bar
        key={category.key}
        dataKey={category.key}
        fill={`url(#gradient-${category.key})`}
        radius={[6, 6, 0, 0]}
        maxBarSize={35}
        animationDuration={800}
        animationEasing="cubic-bezier(0.4, 0, 0.2, 1)"
        animationBegin={catIndex * 100}
      >
        {data.map((entry, index) => (
          <Cell
            key={`cell-${category.key}-${index}`}
            opacity={
              hoveredIndex === null || hoveredIndex === index
                ? (activeCategory === null || activeCategory === category.key ? 1 : 0.1)
                : (activeCategory === null || activeCategory === category.key ? 0.3 : 0.1)
            }
            style={{
              cursor: 'pointer',
              transition: 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
              filter: hoveredIndex === index
                ? `url(#groupShadowHover${catIndex}) brightness(1.15)`
                : `url(#groupShadow${catIndex})`,
              transform: hoveredIndex === index ? 'translateY(-8px) scaleX(1.1)' : 'translateY(0) scaleX(1)',
              transformOrigin: 'bottom'
            }}
          />
        ))}
      </Bar>
    ))}
  </BarChart>
</ResponsiveContainer>

{/* Render the custom legend below the chart */}
<CustomLegend />
```
""",
}


def get_chart_instructions(chart_types: list[str] | None = None) -> str:
    """
    Get specific chart styling instructions based on chart type(s).

    Args:
        chart_types: List of chart types, or None for all. Options:
            - ["bar_chart"]
            - ["pie_chart", "line_chart"]
            - ["bar_chart", "donut_chart", "area_chart"]
            - None (returns all examples - for dashboard creation with unspecified charts)

        Available chart types:
            - "bar_chart"
            - "horizontal_bar_chart"
            - "line_chart"
            - "area_chart"
            - "pie_chart"
            - "donut_chart"
            - "scatter_plot"
            - "stacked_bar_chart"
            - "grouped_bar_chart"

    Returns:
        String containing relevant chart styling examples and instructions
    """
    # If no chart types specified, return all examples (for general dashboard creation)
    if chart_types is None or chart_types == ["all"]:
        all_examples = COMMON_INSTRUCTIONS + "\n\n" + TOOLTIP_PATTERN + "\n\n" + KPI_CARDS_PATTERN + "\n\n"
        all_examples += "CHART EXAMPLES:\n\n"
        for _, example in CHART_EXAMPLES.items():
            all_examples += f"{example}\n\n---\n\n"
        return all_examples

    # Return only the requested chart examples with common instructions
    result = COMMON_INSTRUCTIONS + "\n\n" + TOOLTIP_PATTERN + "\n\n" + KPI_CARDS_PATTERN + "\n\n"
    result += "CHART EXAMPLES:\n\n"

    for chart_type in chart_types:
        chart_example = CHART_EXAMPLES.get(chart_type)
        if chart_example:
            result += f"{chart_example}\n\n---\n\n"
        else:
            # If chart type not found, skip it
            pass

    return result
