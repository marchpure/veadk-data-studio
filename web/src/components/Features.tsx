import {
  BrainIcon,
  SwapIcon,
  PlugIcon,
  ChatIcon,
  DbIcon,
  CpuIcon,
  ShieldIcon,
  GithubIcon,
} from "@/components/landing/icons";

type Feature = {
  Icon: () => JSX.Element;
  title: string;
  body: string;
  featured?: boolean;
};

const features: Feature[] = [
  {
    Icon: () => <BrainIcon size={18} />,
    title: "Organizational memory",
    body: "Schema, definitions, fiscal calendars, edge cases — learned once, consumed correctly across the team.",
    featured: true,
  },
  {
    Icon: () => <SwapIcon size={18} />,
    title: "Shared skills",
    body: "Memory becomes named skills. One line, same accurate answer every time.",
    featured: true,
  },
  {
    Icon: () => <PlugIcon size={18} />,
    title: "Available via MCP",
    body: "Use Byaan from Claude Code, Cursor, Codex, or any MCP client. Same skills, same context.",
    featured: true,
  },
  {
    Icon: () => <ChatIcon size={18} />,
    title: "Slack-native",
    body: "@byaan in any channel. Threaded answers everyone sees. Reports inline.",
    featured: true,
  },
  {
    Icon: () => <GithubIcon size={18} />,
    title: "GitHub-aware",
    body: "Connect your repo — Byaan reads code to understand the intent behind your data: column meanings, business rules, naming conventions.",
  },
  {
    Icon: () => <DbIcon size={18} />,
    title: "Multi-database",
    body: "PostgreSQL, MongoDB, MySQL, MSSQL, SQLite. Plus CSV, Excel, Parquet, JSON.",
  },
  {
    Icon: () => <CpuIcon size={18} />,
    title: "Bring your own model",
    body: "Anthropic, OpenAI, Azure, Bedrock, Groq, OpenRouter, xAI. Your keys, your infra.",
  },
  {
    Icon: () => <ShieldIcon size={18} />,
    title: "Read-only by design",
    body: "Never executes DDL or DML. Validation blocks writes across SQL, Mongo, DuckDB.",
  },
];

const Features = () => {
  return (
    <section className="features" id="features">
      <div className="container">
        <div className="section-head reveal">
          <span className="section-eyebrow">Features</span>
          <h2 className="section-title">Everything you need,<br />nothing you don't</h2>
          <p className="section-sub">Built for engineers who need answers — not another tool to manage.</p>
        </div>

        <div className="features-grid">
          {features.map((feature, i) => (
            <div key={i} className={`feature-card ${feature.featured ? "featured" : ""} reveal`}>
              <div className="feature-icon">
                <feature.Icon />
              </div>
              <div className="feature-title">{feature.title}</div>
              <div className="feature-body">{feature.body}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default Features;
