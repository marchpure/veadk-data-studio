import { PlusIcon } from "@/components/landing/icons";
import { trackCtaClick } from "@/lib/analytics";

const DISCUSSIONS_URL = "https://github.com/byaan-ai/byaan/discussions";

const faqs: { q: string; a: JSX.Element }[] = [
  {
    q: "Is Byaan open source?",
    a: (
      <>
        The team-hosted version will be released under AGPL-3.0. The Mac app is MIT licensed. Both are going public on GitHub soon — you can star <code>github.com/byaan-ai/byaan</code> to follow the launch.
      </>
    ),
  },
  {
    q: "Is my data safe?",
    a: (
      <>
        Yes. The Mac app runs entirely on your machine — credentials, queries, and data never leave your computer. The team version is self-hosted, so the same is true at team scale. Byaan is also read-only by design: it never executes DDL or DML, so production databases are safe.
      </>
    ),
  },
  {
    q: 'What is "Bring Your Own Model"?',
    a: (
      <>
        Byaan works with any OpenAI-compatible API. Connect Anthropic, OpenAI, Azure OpenAI, AWS Bedrock, Groq, OpenRouter, or xAI. Your API keys stay on your machine or in your team deployment. Switch models any time.
      </>
    ),
  },
  {
    q: "How does Byaan build organizational memory?",
    a: (
      <>
        Byaan explores your schema, learns from your corrections, and saves metric definitions to org memory. Any workflow becomes a named skill — <code>@byaan q4-deck</code> is a one-line command your whole team can run.
      </>
    ),
  },
  {
    q: "Can Byaan understand my codebase?",
    a: (
      <>
        Yes. Connect a GitHub repo (or a local repo if you're on the Mac app) and Byaan reads the code to understand the intent behind your data — column meanings, business rules, naming conventions, the relationships your tables actually represent. This is one of the strongest signals for accurate answers.
      </>
    ),
  },
  {
    q: "What databases does Byaan support?",
    a: (
      <>
        PostgreSQL, MongoDB, MySQL, MariaDB, SQLite, MSSQL. You can also upload CSV, Excel, Parquet, and JSON files directly.
      </>
    ),
  },
  {
    q: "What is MCP and how does Byaan use it?",
    a: (
      <>
        MCP (Model Context Protocol) is the open standard for connecting AI tools. Byaan exposes an MCP server, so you can use it from Claude Code, Cursor, Codex, or any MCP-compatible client — with your full skill library and learned context intact.
      </>
    ),
  },
  {
    q: "How does the Slack integration work?",
    a: (
      <>
        Add Byaan to your workspace, mention <code>@byaan</code> in any channel or thread, and ask a question. Answers, charts, and reports appear inline so everyone in the channel sees them. Skills work in Slack just like in the Mac app.
      </>
    ),
  },
  {
    q: "How do I deploy the Byaan Team Version?",
    a: (
      <>
        One line: <code>curl -fsSL https://downloads.byaan.ai/docker/install.sh | bash</code>. The installer drops a <code>start.sh</code> and <code>.env</code> in a <code>byaan</code> directory. Set your admin email, password, and org name in <code>.env</code>, then run <code>./start.sh</code>. PostgreSQL, backend, frontend, and Caddy ship in a single container — you're live on port 8080 in five minutes. Set <code>DOMAIN</code> for automatic HTTPS via Let's Encrypt.
      </>
    ),
  },
];

const FAQ = () => {
  return (
    <section className="faq" id="faq">
      <div className="container">
        <div className="section-head reveal">
          <h2 className="section-title">Questions, answered</h2>
          <p className="section-sub">
            If something's not here, ask in{" "}
            <a
              href={DISCUSSIONS_URL}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: "var(--primary)", borderBottom: "1px solid var(--primary-line)" }}
              onClick={() => trackCtaClick({ cta: "github_discussions", location: "faq", url: DISCUSSIONS_URL })}
            >
              GitHub Discussions
            </a>
            .
          </p>
        </div>

        <div className="faq-list">
          {faqs.map((f, i) => (
            <details key={i} className="faq-item reveal" {...(i === 0 ? { open: true } : {})}>
              <summary>
                {f.q}
                <PlusIcon className="faq-chevron" />
              </summary>
              <div className="faq-body">{f.a}</div>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
};

export default FAQ;
